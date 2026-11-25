import pytest

from app.modules.investigator.store import IncidentStore


def test_save_get_list_newest_first(tmp_path):
    store = IncidentStore(tmp_path)
    store.save({"id": "aaaaaaaaaaaa", "status": "open", "started_at": "2026-11-25T10:00:00Z"})
    store.save({"id": "bbbbbbbbbbbb", "status": "closed", "started_at": "2026-11-25T11:00:00Z"})
    assert store.get("aaaaaaaaaaaa")["status"] == "open"
    assert [i["id"] for i in store.list()] == ["bbbbbbbbbbbb", "aaaaaaaaaaaa"]
    assert [i["id"] for i in store.list("open")] == ["aaaaaaaaaaaa"]
    assert not list((tmp_path / "incidents").glob("*.tmp"))


def test_bad_ids(tmp_path):
    store = IncidentStore(tmp_path)
    assert store.get("../../etc/passwd") is None
    assert store.get("ABCDEF123456") is None
    assert store.get("aaaaaaaaaaaa") is None
    assert store.list() == []
    with pytest.raises(ValueError):
        store.save({"id": "../x"})
