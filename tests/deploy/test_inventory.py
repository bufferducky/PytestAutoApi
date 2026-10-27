import copy

import pytest
from inventory import collect


def responses():
    return {
        "fixture-definitions": [
            {"id": "same-id", "version": 2, "data": {"name": "new"}},
            {"id": "same-id", "version": 1, "data": {"name": "old"}},
        ],
        "worker/status": {"available": True, "last_error": None, "queued": 0},
        "runs?limit=100&offset=0": {"items": [], "total": 0},
    }


@pytest.mark.parametrize("change", ["delete_new", "change_new"])
def test_all_asset_versions_are_fingerprinted(change):
    data = responses()
    before = collect(lambda path: copy.deepcopy(data.get(path, [])))
    assert len(before["records"]["fixtures"]) == 2
    if change == "delete_new":
        data["fixture-definitions"].pop(0)
    else:
        data["fixture-definitions"][0]["data"]["name"] = "modified"
    after = collect(lambda path: copy.deepcopy(data.get(path, [])))
    assert before["records"] != after["records"]


def test_duplicate_version_fails_instead_of_hiding_record():
    data = responses()
    data["fixture-definitions"].append(data["fixture-definitions"][0])
    with pytest.raises(ValueError, match="duplicate"):
        collect(lambda path: copy.deepcopy(data.get(path, [])))
