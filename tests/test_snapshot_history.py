from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import app_backend.persistence as persistence
from app_backend.persistence import _load_snapshot_from_metadata


def _create_snapshot_fixture(tmp_path: Path) -> tuple[Path, Path]:
    # Simulate the current published table at repo root.
    root_master = tmp_path / "master_prices.csv"
    root_master.write_text("root-current", encoding="utf-8")

    snapshot_dir = tmp_path / "data" / "history" / "snapshot_1"
    snapshot_dir.mkdir(parents=True)
    snapshot_master = snapshot_dir / "master_prices.csv"
    snapshot_master.write_text("historical-snapshot", encoding="utf-8")
    (snapshot_dir / "latest_prices.csv").write_text("snapshot-csv", encoding="utf-8")
    (snapshot_dir / "latest_prices.json").write_text("{}", encoding="utf-8")
    (snapshot_dir / "price_comparison_live.html").write_text("<html></html>", encoding="utf-8")

    metadata_path = snapshot_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "id": "snapshot_1",
                "created_at": "2026-03-18T08:37:19.170486+00:00",
                "mode": "scheduled",
                "brand_scope": "all",
                "competitors": ["Amazon"],
                "record_count": 10,
                "files": {
                    "master_prices_csv": "master_prices.csv",
                    "latest_prices_csv": "latest_prices.csv",
                    "latest_prices_json": "latest_prices.json",
                    "price_comparison_live_html": "price_comparison_live.html",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return metadata_path, snapshot_master


def test_load_snapshot_from_metadata_prefers_snapshot_relative_files() -> None:
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        os.chdir(tmp_path)

        try:
            metadata_path, snapshot_master = _create_snapshot_fixture(tmp_path)

            payload = _load_snapshot_from_metadata(metadata_path)

            assert payload is not None
            assert payload["csv_path"] == str(snapshot_master)
            assert payload["files"]["master_prices_csv"] == str(snapshot_master)
        finally:
            os.chdir(original_cwd)


def test_get_snapshot_returns_resolved_snapshot_files(monkeypatch) -> None:
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        os.chdir(tmp_path)

        try:
            _, snapshot_master = _create_snapshot_fixture(tmp_path)
            monkeypatch.setattr(persistence, "HISTORY_DATA_DIR", tmp_path / "data" / "history")
            monkeypatch.setattr(persistence, "get_run", lambda run_id: None)

            payload = persistence.get_snapshot("snapshot_1")

            assert payload is not None
            assert payload["csv_path"] == str(snapshot_master)
            assert payload["files"]["master_prices_csv"] == str(snapshot_master)
            assert payload["files"]["latest_prices_json"] == str(
                tmp_path / "data" / "history" / "snapshot_1" / "latest_prices.json"
            )
        finally:
            os.chdir(original_cwd)
