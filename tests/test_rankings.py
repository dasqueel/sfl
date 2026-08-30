"""Tests for the rankings store.

This is the only file in the project holding data that cannot be
recomputed, so the tests lean hard on the failure paths: a damaged file
must never be overwritten, a failed write must never destroy the previous
version, and nothing may vanish silently.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rankings  # noqa: E402


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "rankings.json"


def read(path):
    return json.loads(path.read_text())


class TestLoad:
    def test_missing_file_is_an_empty_store(self, store_path):
        store = rankings.load(store_path, 2026)
        assert store == {
            "season": 2026,
            "updated": None,
            "tags": {},
            "projections": {},
            "keepers": {},
        }

    def test_round_trip(self, store_path):
        rankings.set_tag("RB|Jahmyr Gibbs", "gem", store_path, 2026)
        rankings.set_projection("WR|Puka Nacua", 350.0, store_path, 2026)
        store = rankings.load(store_path, 2026)
        assert store["tags"] == {"RB|Jahmyr Gibbs": "gem"}
        assert store["projections"] == {"WR|Puka Nacua": 350.0}
        assert store["updated"]

    def test_corrupt_file_degrades_instead_of_raising(self, store_path):
        store_path.write_text("{ this is not json")
        store = rankings.load(store_path, 2026)
        assert store["tags"] == {}
        assert "could not read" in store["error"]

    def test_non_object_json_is_rejected(self, store_path):
        store_path.write_text("[1, 2, 3]")
        assert "not a JSON object" in rankings.load(store_path, 2026)["error"]

    def test_partial_file_keeps_what_it_can(self, store_path):
        store_path.write_text(json.dumps({"tags": {"QB|X": "fade"}}))
        store = rankings.load(store_path, 2026)
        assert store["tags"] == {"QB|X": "fade"}
        assert store["projections"] == {}

    def test_wrong_typed_sections_fall_back_to_empty(self, store_path):
        store_path.write_text(json.dumps({"tags": "nope", "projections": 5}))
        store = rankings.load(store_path, 2026)
        assert store["tags"] == {} and store["projections"] == {}


class TestNeverDestroysData:
    def test_damaged_file_is_not_overwritten(self, store_path):
        store_path.write_text("{ broken")
        with pytest.raises(ValueError, match="refusing to overwrite"):
            rankings.set_tag("RB|X", "gem", store_path, 2026)
        assert store_path.read_text() == "{ broken"

    def test_write_leaves_no_temp_files_behind(self, store_path):
        rankings.set_tag("RB|X", "gem", store_path, 2026)
        leftovers = list(store_path.parent.glob(".rankings-*"))
        assert not leftovers, f"temp files left behind: {leftovers}"

    def test_a_failed_write_preserves_the_previous_version(self, store_path, monkeypatch):
        rankings.set_tag("RB|Keep Me", "gem", store_path, 2026)
        original = store_path.read_text()

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(rankings.os, "replace", boom)
        with pytest.raises(OSError):
            rankings.set_tag("RB|New", "fade", store_path, 2026)

        assert store_path.read_text() == original
        assert not list(store_path.parent.glob(".rankings-*"))

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "deep" / "down" / "rankings.json"
        rankings.set_tag("RB|X", "gem", nested, 2026)
        assert nested.exists()


class TestTags:
    def test_set_and_change(self, store_path):
        rankings.set_tag("RB|X", "gem", store_path, 2026)
        assert read(store_path)["tags"]["RB|X"] == "gem"
        rankings.set_tag("RB|X", "fade", store_path, 2026)
        assert read(store_path)["tags"]["RB|X"] == "fade"

    def test_null_clears_the_key_entirely(self, store_path):
        rankings.set_tag("RB|X", "gem", store_path, 2026)
        rankings.set_tag("RB|X", None, store_path, 2026)
        assert "RB|X" not in read(store_path)["tags"]

    def test_clearing_an_untagged_player_is_harmless(self, store_path):
        rankings.set_tag("RB|Never Tagged", None, store_path, 2026)
        assert read(store_path)["tags"] == {}

    @pytest.mark.parametrize("bad", ["star", "GEM", "", 1, True])
    def test_invalid_tag_rejected(self, store_path, bad):
        with pytest.raises(ValueError, match="tag must be one of"):
            rankings.set_tag("RB|X", bad, store_path, 2026)

    @pytest.mark.parametrize("bad", [None, "", "no pipe here"])
    def test_invalid_key_rejected(self, store_path, bad):
        with pytest.raises(ValueError, match="key must look like"):
            rankings.set_tag(bad, "gem", store_path, 2026)

    def test_tags_survive_editing_a_projection(self, store_path):
        rankings.set_tag("RB|X", "gem", store_path, 2026)
        rankings.set_projection("WR|Y", 300.0, store_path, 2026)
        store = rankings.load(store_path, 2026)
        assert store["tags"] == {"RB|X": "gem"}
        assert store["projections"] == {"WR|Y": 300.0}


class TestProjections:
    def test_set_and_clear(self, store_path):
        rankings.set_projection("WR|X", 275.5, store_path, 2026)
        assert read(store_path)["projections"]["WR|X"] == 275.5
        rankings.set_projection("WR|X", None, store_path, 2026)
        assert read(store_path)["projections"] == {}

    def test_strings_coerce(self, store_path):
        rankings.set_projection("WR|X", "250.5", store_path, 2026)
        assert read(store_path)["projections"]["WR|X"] == 250.5

    @pytest.mark.parametrize("bad", ["abc", -1, 1001, "nope"])
    def test_out_of_range_rejected(self, store_path, bad):
        with pytest.raises(ValueError):
            rankings.set_projection("WR|X", bad, store_path, 2026)


class TestClear:
    def test_clears_only_the_named_section(self, store_path):
        rankings.set_tag("RB|X", "gem", store_path, 2026)
        rankings.set_projection("WR|Y", 300.0, store_path, 2026)
        rankings.clear("projections", store_path, 2026)
        store = rankings.load(store_path, 2026)
        assert store["projections"] == {}
        assert store["tags"] == {"RB|X": "gem"}

    def test_unknown_section_rejected(self, store_path):
        with pytest.raises(ValueError, match="field must be one of"):
            rankings.clear("everything", store_path, 2026)

    @pytest.mark.parametrize("section", rankings.SECTIONS)
    def test_every_section_can_be_cleared(self, store_path, section):
        rankings.set_tag("RB|X", "gem", store_path, 2026)
        rankings.set_projection("WR|Y", 300.0, store_path, 2026)
        rankings.set_keeper("QB|Z", 4, store_path, 2026)
        rankings.clear(section, store_path, 2026)
        assert rankings.load(store_path, 2026)[section] == {}


class TestCounts:
    def test_counts(self):
        store = {
            "tags": {"a|1": "gem", "b|2": "gem", "c|3": "fade"},
            "projections": {"d|4": 1.0},
            "keepers": {"e|5": {"paid": 4, "mine": True},
                        "f|6": {"paid": 9, "mine": False}},
        }
        assert rankings.counts(store) == {
            "gems": 2, "fades": 1, "projections": 1, "keepers": 2, "mine": 1
        }

    def test_counts_on_empty(self):
        assert rankings.counts(rankings.empty(2026)) == {
            "gems": 0, "fades": 0, "projections": 0, "keepers": 0, "mine": 0
        }


class TestKeepers:
    def test_round_trip(self, store_path):
        rankings.set_keeper("QB|Jaxson Dart", 4, store_path, 2026)
        stored = read(store_path)["keepers"]["QB|Jaxson Dart"]
        assert stored == {"paid": 4.0, "mine": True}

    def test_stores_the_price_paid_not_this_years_cost(self, store_path):
        """The doubling rule belongs in config, not baked into the file."""
        rankings.set_keeper("QB|X", 4, store_path, 2026)
        assert read(store_path)["keepers"]["QB|X"]["paid"] == 4.0

    def test_opponents_keepers_are_marked(self, store_path):
        rankings.set_keeper("RB|Theirs", 12, store_path, 2026, mine=False)
        assert read(store_path)["keepers"]["RB|Theirs"]["mine"] is False

    def test_null_removes_the_keeper(self, store_path):
        rankings.set_keeper("QB|X", 4, store_path, 2026)
        rankings.set_keeper("QB|X", None, store_path, 2026)
        assert read(store_path)["keepers"] == {}

    def test_zero_is_a_valid_price(self, store_path):
        """A free keeper is real — it must not be read as "remove"."""
        rankings.set_keeper("QB|X", 0, store_path, 2026)
        assert read(store_path)["keepers"]["QB|X"]["paid"] == 0.0

    @pytest.mark.parametrize("bad", ["abc", -1, 501, ""])
    def test_bad_price_rejected(self, store_path, bad):
        with pytest.raises(ValueError):
            rankings.set_keeper("QB|X", bad, store_path, 2026)

    @pytest.mark.parametrize("bad", [None, "", "no pipe here"])
    def test_invalid_key_rejected(self, store_path, bad):
        with pytest.raises(ValueError, match="key must look like"):
            rankings.set_keeper(bad, 4, store_path, 2026)

    def test_keepers_survive_tag_and_projection_writes(self, store_path):
        rankings.set_keeper("QB|Dart", 4, store_path, 2026)
        rankings.set_tag("RB|X", "gem", store_path, 2026)
        rankings.set_projection("WR|Y", 300.0, store_path, 2026)
        store = rankings.load(store_path, 2026)
        assert store["keepers"] == {"QB|Dart": {"paid": 4.0, "mine": True}}
        assert store["tags"] == {"RB|X": "gem"}
        assert store["projections"] == {"WR|Y": 300.0}

    def test_damaged_file_is_not_overwritten(self, store_path):
        store_path.write_text("{ broken")
        with pytest.raises(ValueError, match="refusing to overwrite"):
            rankings.set_keeper("QB|X", 4, store_path, 2026)
        assert store_path.read_text() == "{ broken"
