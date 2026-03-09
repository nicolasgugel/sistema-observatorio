from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from observatorio.models import PriceRecord


def _most_frequent_brand(records: list[PriceRecord]) -> str:
    brand = "Apple"
    counts: dict[str, int] = {}
    for row in records:
        key = (row.brand or "").strip() or "Samsung"
        counts[key] = counts.get(key, 0) + 1
    if counts:
        brand = max(counts.items(), key=lambda x: x[1])[0]
    return brand


def _find_balanced_literal_end(text: str, start: int, open_char: str, close_char: str) -> int:
    depth = 0
    in_string: str | None = None
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == in_string:
                in_string = None
            continue

        if ch in ("'", '"'):
            in_string = ch
            continue

        if ch == open_char:
            depth += 1
            continue
        if ch == close_char:
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _replace_constant_payload(
    template_html: str,
    marker: str,
    open_char: str,
    close_char: str,
    payload: dict | list,
) -> str:
    start = template_html.find(marker)
    if start < 0:
        raise ValueError(f"No se encontro '{marker}' en la plantilla HTML.")

    literal_start = template_html.find(open_char, start)
    if literal_start < 0:
        raise ValueError(f"No se encontro apertura '{open_char}' para {marker}.")

    literal_end = _find_balanced_literal_end(template_html, literal_start, open_char, close_char)
    if literal_end < 0:
        raise ValueError(f"No se encontro cierre '{close_char}' para {marker}.")

    semicolon = template_html.find(";", literal_end)
    if semicolon < 0:
        raise ValueError(f"No se encontro ';' al final de {marker}.")

    replacement = f"{marker} {json.dumps(payload, ensure_ascii=False, indent=2)};"
    return template_html[:start] + replacement + template_html[semicolon + 1 :]


def _patch_extracted_at(template_html: str, records: list[PriceRecord]) -> str:
    extracted_at = datetime.now(tz=timezone.utc).isoformat()
    record_timestamps = [r.extracted_at for r in records if (r.extracted_at or "").strip()]
    if record_timestamps:
        extracted_at = max(record_timestamps)
    return re.sub(
        r'const\s+EXTRACTED_AT\s*=\s*"[^"]*";',
        f'const EXTRACTED_AT = "{extracted_at}";',
        template_html,
        count=1,
    )


def inject_embedded_data(template_html: str, records: list[PriceRecord]) -> str:
    records_payload = [r.to_dict() for r in records]
    brand = _most_frequent_brand(records)

    if "const EMBEDDED_DATA =" in template_html:
        patched = _replace_constant_payload(
            template_html=template_html,
            marker="const EMBEDDED_DATA =",
            open_char="{",
            close_char="}",
            payload={"records": records_payload},
        )
        patched = re.sub(
            r"let\s+currentBrand\s*=\s*'[^']*';",
            f"let currentBrand = '{brand}';",
            patched,
            count=1,
        )
        return _patch_extracted_at(patched, records)

    if "const DATA =" in template_html:
        patched = _replace_constant_payload(
            template_html=template_html,
            marker="const DATA =",
            open_char="[",
            close_char="]",
            payload=records_payload,
        )
        return _patch_extracted_at(patched, records)

    raise ValueError("No se encontro marcador de datos soportado (EMBEDDED_DATA o DATA) en la plantilla HTML.")


def build_html(template_path: Path, output_path: Path, records: list[PriceRecord]) -> None:
    template_html = template_path.read_text(encoding="utf-8")
    rendered = inject_embedded_data(template_html, records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
