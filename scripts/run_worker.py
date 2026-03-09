from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app_backend.main:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
