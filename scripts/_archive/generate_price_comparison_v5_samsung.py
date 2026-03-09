from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "price_comparison_v5_wow.html"
CSV_PATH = ROOT / "output" / "prices.csv"
OUTPUT_PATH = ROOT / "price_comparison_v5_samsung_live.html"


def _parse_bool(raw: str) -> bool | None:
    value = (raw or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _parse_int(raw: str) -> int | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(raw: str) -> float | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_csv_records(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(
                {
                    "country": row.get("country") or "",
                    "retailer": row.get("retailer") or "",
                    "product_family": row.get("product_family") or "",
                    "brand": row.get("brand") or "",
                    "model": row.get("model") or "",
                    "capacity_gb": _parse_int(row.get("capacity_gb") or ""),
                    "offer_type": row.get("offer_type") or "",
                    "price_value": _parse_float(row.get("price_value") or ""),
                    "price_unit": row.get("price_unit") or "",
                    "term_months": _parse_int(row.get("term_months") or ""),
                    "in_stock": _parse_bool(row.get("in_stock") or ""),
                    "data_quality_tier": row.get("data_quality_tier") or "",
                    "source_url": row.get("source_url") or "",
                    "source_title": row.get("source_title") or "",
                }
            )

    # Samsung-only dataset for this view.
    samsung_records = [
        r
        for r in records
        if "samsung" in (r.get("brand") or "").lower()
        or "samsung" in (r.get("model") or "").lower()
        or (r.get("product_family") == "Samsung")
    ]
    return samsung_records


def patch_template(template: str, records: list[dict]) -> str:
    payload = {
        "records": records,
        "metadata": {
            "source": str(CSV_PATH.relative_to(ROOT)).replace("\\", "/"),
            "records": len(records),
            "brand_scope": "Samsung only",
        },
    }
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

    # Header logo block.
    template = template.replace(
        '<div class="santander-logo">\n                <span class="logo-text">Santander</span>\n                <span class="logo-boutique">Boutique</span>\n            </div>',
        '<div class="santander-logo">\n                <img src="https://upload.wikimedia.org/wikipedia/commons/b/b8/Santander_Logotipo.svg" alt="Santander">\n                <div class="logo-text-wrap">\n                    <span class="logo-text">Santander</span>\n                    <span class="logo-boutique">Boutique</span>\n                </div>\n            </div>',
    )

    # Header logo styles.
    template = template.replace(
        ".santander-logo {\n            text-align: right;\n        }",
        ".santander-logo {\n            display: flex;\n            align-items: center;\n            gap: 12px;\n        }\n\n        .santander-logo img {\n            height: 34px;\n            width: auto;\n            filter: brightness(0) invert(1);\n        }\n\n        .logo-text-wrap {\n            text-align: right;\n        }",
    )

    # Samsung-only navigation.
    nav_pattern = re.compile(
        r"<!-- Brand Navigation -->\s*<nav class=\"brand-nav\">.*?</nav>",
        re.DOTALL,
    )
    template = nav_pattern.sub(
        """<!-- Brand Navigation -->
        <nav class="brand-nav">
            <div class="brand-item samsung active">
                <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/2/24/Samsung_Logo.svg/1200px-Samsung_Logo.svg.png"
                    class="brand-logo-img" alt="Samsung">
                Samsung
            </div>
        </nav>""",
        template,
    )

    # Force single brand behavior.
    template = template.replace("let currentBrand = 'Apple';", "let currentBrand = 'Samsung';")
    template = template.replace(".brand-item.active.apple", ".brand-item.active.legacy")

    template = template.replace(
        "const brand = (m.toLowerCase().includes('samsung') || r.product_family === 'Samsung') ? 'Samsung' : 'Apple';",
        "const brand = 'Samsung';",
    )

    switch_brand_pattern = re.compile(
        r"function switchBrand\(brand\) \{.*?\n        \}",
        re.DOTALL,
    )
    template = switch_brand_pattern.sub(
        """function switchBrand(brand) {
            // Samsung-only view: keep UI stable and ignore brand switching.
            currentBrand = 'Samsung';
        }""",
        template,
    )

    # Remove external fetch fallback to avoid mixing old Apple dataset.
    init_data_pattern = re.compile(
        r"let data = EMBEDDED_DATA;\s*// Intentar cargar datos externos si no hay embebidos o para refrescar\s*try \{\s*const res = await fetch\('\.\./data/curated/merged_records\.json'\);\s*if \(res\.ok\) data = await res\.json\(\);\s*\} catch \(e\) \{\s*console\.log\(\"Usando datos embebidos como fallback\"\);\s*\}",
        re.DOTALL,
    )
    template = init_data_pattern.sub("let data = EMBEDDED_DATA;", template)

    # Replace embedded data block with live prices.csv payload.
    embedded_pattern = re.compile(
        r"const EMBEDDED_DATA = \{.*?\n\};\n",
        re.DOTALL,
    )
    template = embedded_pattern.sub(f"const EMBEDDED_DATA = {payload_json};\n", template, count=1)

    template = template.replace(
        "Dashboard v5.0 Premium",
        "Dashboard v5.1 Samsung Live",
    )

    return template


def main() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    records = load_csv_records(CSV_PATH)
    output = patch_template(template, records)
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH.name} with {len(records)} Samsung records from {CSV_PATH.name}")


if __name__ == "__main__":
    main()
