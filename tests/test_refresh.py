"""
tests/test_refresh.py
=====================
Регресионен предпазител за най-сериозния бъг: не-force пътят връщаше всичко
от кеша през get_snapshot и TTL логиката беше мъртъв код — седмичната
автоматизация никога не опресняваше данните.
"""
import pandas as pd
import pytest

import run
from catalog.series import series_by_source


class _SpyAdapter:
    """Записва през кой път е минато."""

    def __init__(self):
        self.fetch_many_calls = []
        self.get_snapshot_calls = []

    def fetch_many(self, specs, force=False):
        self.fetch_many_calls.append(
            {"keys": [s["_key"] for s in specs], "force": force}
        )
        return {
            s["_key"]: pd.Series([1.0], index=pd.to_datetime(["2026-06-01"]))
            for s in specs
        }

    def get_snapshot(self, keys):
        self.get_snapshot_calls.append(list(keys))
        return {}


@pytest.fixture
def spy():
    return _SpyAdapter()


def test_non_force_path_sends_all_specs_through_fetch_many(spy):
    expected_keys = [s["_key"] for s in series_by_source("eurostat")]

    snapshot = run._build_snapshot({"eurostat": spy}, force=False)

    assert len(spy.fetch_many_calls) == 1
    assert spy.fetch_many_calls[0]["keys"] == expected_keys
    assert spy.fetch_many_calls[0]["force"] is False
    assert sorted(snapshot) == sorted(expected_keys)


def test_non_force_path_never_shortcuts_through_get_snapshot(spy):
    run._build_snapshot({"eurostat": spy}, force=False)
    assert spy.get_snapshot_calls == []


def test_force_path_still_forces(spy):
    run._build_snapshot({"eurostat": spy}, force=True)

    assert len(spy.fetch_many_calls) == 1
    assert spy.fetch_many_calls[0]["force"] is True
    assert spy.get_snapshot_calls == []
