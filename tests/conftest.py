import pytest


@pytest.fixture(autouse=True)
def isolated_metadata_database(monkeypatch, tmp_path):
    monkeypatch.setenv("MOLT_DATABASE", str(tmp_path / "runs.sqlite3"))


@pytest.fixture(autouse=True)
def isolated_catalog_refresh(monkeypatch, tmp_path):
    from molt_ui import catalog_update
    from molt_ui.core.catalog import catalog_path

    output = tmp_path / "resources/command_catalog.json"
    output.parent.mkdir()
    output.write_bytes(catalog_path().read_bytes())
    monkeypatch.setattr(catalog_update, "catalog_path", lambda: output)
