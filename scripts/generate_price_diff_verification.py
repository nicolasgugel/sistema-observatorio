#!/usr/bin/env python
"""
Generate a fast verification pack for suspicious price gaps vs Santander Boutique.

Outputs:
1) CSV with side-by-side URLs and Excel HYPERLINK formulas.
2) HTML table with clickable links for rapid manual review.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


Key = Tuple[str, str, str, str, str, str]
PairKey = Tuple[str, str, str, str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build verification CSV/HTML for Santander vs competitors when diff exceeds threshold."
    )
    parser.add_argument(
        "--input-csv",
        default="master_prices.csv",
        help="Input unified CSV file.",
    )
    parser.add_argument(
        "--output-csv",
        default="output/santander_vs_competidores_diff_gt_30_verificacion.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--output-html",
        default="output/santander_vs_competidores_diff_gt_30_verificacion.html",
        help="Output HTML path.",
    )
    parser.add_argument(
        "--threshold-pct",
        type=float,
        default=30.0,
        help="Absolute percentage difference threshold against Santander.",
    )
    parser.add_argument(
        "--ignore-term-months",
        action="store_true",
        help="If enabled, matching ignores term_months (less strict).",
    )
    return parser.parse_args()


def parse_price(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    v = v.replace("€", "").replace("EUR", "").replace(" ", "")
    if "," in v and "." in v:
        if v.rfind(",") > v.rfind("."):
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", "")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def parse_dt(value: Optional[str]) -> datetime:
    if not value:
        return datetime.min
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def excel_hyperlink(url: str, label: str) -> str:
    safe_url = url.replace('"', '""')
    safe_label = label.replace('"', '""')
    if not safe_url:
        return ""
    return f'=HYPERLINK("{safe_url}","{safe_label}")'


def latest_rows(rows: Iterable[dict]) -> Dict[Key, dict]:
    latest: Dict[Key, dict] = {}
    for row in rows:
        key: Key = (
            row.get("retailer", "").strip(),
            row.get("brand", "").strip(),
            row.get("model", "").strip(),
            row.get("capacity_gb", "").strip(),
            row.get("offer_type", "").strip(),
            row.get("term_months", "").strip(),
        )
        existing = latest.get(key)
        if existing is None or parse_dt(row.get("extracted_at")) >= parse_dt(existing.get("extracted_at")):
            latest[key] = row
    return latest


def build_match_key(row: dict, ignore_term_months: bool) -> PairKey:
    term = "" if ignore_term_months else row.get("term_months", "").strip()
    return (
        row.get("brand", "").strip(),
        row.get("model", "").strip(),
        row.get("capacity_gb", "").strip(),
        row.get("offer_type", "").strip(),
        term,
    )


def build_rows_for_review(latest: Dict[Key, dict], threshold_pct: float, ignore_term_months: bool) -> List[dict]:
    santander_rows: Dict[PairKey, dict] = {}
    for row in latest.values():
        if row.get("retailer", "").strip() == "Santander Boutique":
            santander_rows[build_match_key(row, ignore_term_months)] = row

    out: List[dict] = []
    for row in latest.values():
        competitor = row.get("retailer", "").strip()
        if competitor == "Santander Boutique":
            continue

        match_key = build_match_key(row, ignore_term_months)
        base = santander_rows.get(match_key)
        if not base:
            continue

        price_s = parse_price(base.get("price_value"))
        price_c = parse_price(row.get("price_value"))
        if price_s is None or price_c is None or price_s == 0:
            continue

        diff_signed = ((price_c - price_s) / price_s) * 100.0
        diff_abs = abs(diff_signed)
        if diff_abs <= threshold_pct:
            continue

        term_months = row.get("term_months", "").strip()
        out.append(
            {
                "brand": row.get("brand", "").strip(),
                "model": row.get("model", "").strip(),
                "capacity_gb": row.get("capacity_gb", "").strip(),
                "offer_type": row.get("offer_type", "").strip(),
                "term_months": term_months,
                "santander_price_value": round(price_s, 4),
                "competitor": competitor,
                "competitor_price_value": round(price_c, 4),
                "difference_pct_signed_vs_santander": round(diff_signed, 2),
                "difference_pct_abs_vs_santander": round(diff_abs, 2),
                "santander_extracted_at": base.get("extracted_at", "").strip(),
                "competitor_extracted_at": row.get("extracted_at", "").strip(),
                "santander_source_url": base.get("source_url", "").strip(),
                "competitor_source_url": row.get("source_url", "").strip(),
                "santander_link_excel": excel_hyperlink(base.get("source_url", "").strip(), "Abrir Santander"),
                "competitor_link_excel": excel_hyperlink(row.get("source_url", "").strip(), "Abrir Competidor"),
                "review_status": "",
                "review_notes": "",
            }
        )

    out.sort(key=lambda r: r["difference_pct_abs_vs_santander"], reverse=True)
    return out


def write_csv(rows: List[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "brand",
        "model",
        "capacity_gb",
        "offer_type",
        "term_months",
        "santander_price_value",
        "competitor",
        "competitor_price_value",
        "difference_pct_signed_vs_santander",
        "difference_pct_abs_vs_santander",
        "santander_extracted_at",
        "competitor_extracted_at",
        "santander_source_url",
        "competitor_source_url",
        "santander_link_excel",
        "competitor_link_excel",
        "review_status",
        "review_notes",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_html(rows: List[dict], output_path: Path, threshold_pct: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_rows = []
    for row in rows:
        html_rows.append(
            "<tr>"
            f"<td>{escape(row['competitor'])}</td>"
            f"<td>{escape(row['brand'])}</td>"
            f"<td>{escape(row['model'])}</td>"
            f"<td>{escape(row['capacity_gb'])}</td>"
            f"<td>{escape(row['offer_type'])}</td>"
            f"<td>{escape(row['term_months'])}</td>"
            f"<td>{row['santander_price_value']}</td>"
            f"<td>{row['competitor_price_value']}</td>"
            f"<td>{row['difference_pct_signed_vs_santander']}%</td>"
            f"<td>{row['difference_pct_abs_vs_santander']}%</td>"
            f"<td><a href=\"{escape(row['santander_source_url'])}\" target=\"_blank\" rel=\"noopener noreferrer\">Santander</a></td>"
            f"<td><a href=\"{escape(row['competitor_source_url'])}\" target=\"_blank\" rel=\"noopener noreferrer\">Competidor</a></td>"
            "</tr>"
        )

    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Verificacion precios Santander vs competidores</title>
  <style>
    body {{
      font-family: "Segoe UI", Tahoma, Arial, sans-serif;
      margin: 20px;
      background: #f7f9fb;
      color: #1a1f36;
    }}
    h1 {{
      margin: 0 0 8px 0;
      font-size: 22px;
    }}
    p {{
      margin: 0 0 16px 0;
      color: #4a5568;
    }}
    .toolbar {{
      margin-bottom: 12px;
    }}
    input {{
      width: 320px;
      max-width: 100%;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid #cbd5e0;
      background: #ffffff;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      background: #ffffff;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 3px 12px rgba(0, 0, 0, 0.07);
    }}
    th, td {{
      border-bottom: 1px solid #edf2f7;
      padding: 8px 10px;
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{
      background: #1f2937;
      color: #ffffff;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    tr:hover {{
      background: #f3f6fb;
    }}
    a {{
      color: #0b5ed7;
      text-decoration: none;
      font-weight: 600;
    }}
    a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <h1>Verificacion rapida de diferencias > {threshold_pct:.2f}%</h1>
  <p>Filas: {len(rows)}. Busca por modelo, competidor o modalidad para revisar enlaces y precios.</p>
  <div class="toolbar">
    <input id="searchBox" type="text" placeholder="Filtrar (ej. S25, Media Markt, financing_max_term)">
  </div>
  <table id="reviewTable">
    <thead>
      <tr>
        <th>Competidor</th>
        <th>Marca</th>
        <th>Modelo</th>
        <th>Capacidad</th>
        <th>Modalidad</th>
        <th>Plazo</th>
        <th>Precio Santander</th>
        <th>Precio Competidor</th>
        <th>Dif. Firmada</th>
        <th>Dif. Abs</th>
        <th>Link Santander</th>
        <th>Link Competidor</th>
      </tr>
    </thead>
    <tbody>
      {"".join(html_rows)}
    </tbody>
  </table>
  <script>
    const input = document.getElementById('searchBox');
    const rows = Array.from(document.querySelectorAll('#reviewTable tbody tr'));
    input.addEventListener('input', function() {{
      const q = input.value.toLowerCase().trim();
      rows.forEach((row) => {{
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
      }});
    }});
  </script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_csv)
    output_csv = Path(args.output_csv)
    output_html = Path(args.output_html)

    if not input_path.exists():
        raise SystemExit(f"Input CSV not found: {input_path}")

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    latest = latest_rows(rows)
    review_rows = build_rows_for_review(
        latest=latest,
        threshold_pct=args.threshold_pct,
        ignore_term_months=args.ignore_term_months,
    )
    write_csv(review_rows, output_csv)
    write_html(review_rows, output_html, args.threshold_pct)

    print(f"Input rows: {len(rows)}")
    print(f"Unique latest keys: {len(latest)}")
    print(f"Rows for review (> {args.threshold_pct}%): {len(review_rows)}")
    print(f"CSV: {output_csv}")
    print(f"HTML: {output_html}")


if __name__ == "__main__":
    main()
