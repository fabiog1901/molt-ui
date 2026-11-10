import pytest


@pytest.fixture(autouse=True)
def isolated_metadata_database(monkeypatch, tmp_path):
    monkeypatch.setenv("MOLT_DATABASE", str(tmp_path / "runs.sqlite3"))
