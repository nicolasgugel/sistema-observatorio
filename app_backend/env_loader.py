from __future__ import annotations

import os
from pathlib import Path

_LOADED_PATHS: set[Path] = set()


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None

    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None

    value = raw_value.strip()
    if value and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]

    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()

    return key, value


def load_env_file(path: Path, *, override: bool = False) -> None:
    resolved = path.resolve()
    if resolved in _LOADED_PATHS or not resolved.exists():
        return

    for raw_line in resolved.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value

    _LOADED_PATHS.add(resolved)

