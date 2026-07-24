"""
tests/test_composite.py
=======================
Лещовата агрегация и ренормализацията на композита (мандат №38 §А3).

Ключовото правило: празна леща ИЗПАДА и теглата се преизчисляват. Да я броим
като „неутрално 50" е тихо твърдение за нещо, което не сме измерили.
"""
import math

import pandas as pd
import pytest

from config import MODULE_WEIGHTS
from core.scorer import compute_composite_score, compute_lens_reports, get_regime


def _monthly(values):
    idx = pd.date_range(end="2026-06-01", periods=len(values), freq="MS")
    return pd.Series([float(v) for v in values], index=idx)


def _mini_catalog():
    return {
        "A": {"lens": ["growth"], "peer_group": "pg_a", "transform": "level",
              "name_bg": "А", "id": "ds_a?geo=BG"},
        "B": {"lens": ["growth"], "peer_group": "pg_b", "transform": "level",
              "name_bg": "Б", "id": "ds_b?geo=BG"},
        "C": {"lens": ["labor"], "peer_group": "pg_c", "transform": "level",
              "name_bg": "В", "id": "ds_c?geo=BG"},
    }


# ── Тегла ────────────────────────────────────────────────────────────────────

def test_bg_module_weights_are_untouched():
    """Композитът тежи по БГ теглата, не по EU-те (мандат §А3)."""
    assert MODULE_WEIGHTS == {
        "inflation": 0.25, "labor": 0.20, "growth": 0.20,
        "credit": 0.15, "external": 0.20,
    }
    assert sum(MODULE_WEIGHTS.values()) == pytest.approx(1.0)


def test_composite_is_the_weighted_mean_when_every_lens_is_present():
    scores = {"inflation": 40.0, "labor": 60.0, "growth": 50.0,
              "credit": 30.0, "external": 20.0}
    expected = sum(scores[m] * w for m, w in MODULE_WEIGHTS.items())
    assert compute_composite_score(scores) == pytest.approx(round(expected, 1))


# ── Ренормализация ───────────────────────────────────────────────────────────

def test_empty_lens_drops_out_and_weights_renormalise():
    scores = {"inflation": 40.0, "labor": 60.0,
              "growth": None, "credit": None, "external": None}
    expected = (40.0 * 0.25 + 60.0 * 0.20) / (0.25 + 0.20)
    assert compute_composite_score(scores) == pytest.approx(round(expected, 1))


def test_empty_lens_is_not_counted_as_neutral_fifty():
    scores = {"inflation": 40.0, "labor": 60.0,
              "growth": None, "credit": None, "external": None}
    as_neutral = sum(
        (scores[m] if scores[m] is not None else 50.0) * w
        for m, w in MODULE_WEIGHTS.items()
    )
    assert compute_composite_score(scores) != pytest.approx(round(as_neutral, 1))


def test_composite_is_none_when_no_lens_has_data():
    scores = {m: None for m in MODULE_WEIGHTS}
    assert compute_composite_score(scores) is None


def test_nan_lens_score_is_treated_as_missing():
    scores = {"inflation": float("nan"), "labor": 60.0,
              "growth": None, "credit": None, "external": None}
    assert compute_composite_score(scores) == pytest.approx(60.0)


def test_regime_of_missing_composite_says_so():
    regime = get_regime(None)
    assert regime["name"] == "НЯМА ДАННИ"
    assert regime["score"] is None


def test_regime_thresholds_follow_the_family_table():
    assert get_regime(85.0)["name"] == "ЕКСПАНЗИОНЕН"
    assert get_regime(70.0)["name"] == "ЗДРАВ"
    assert get_regime(55.0)["name"] == "СМЕСЕН"
    assert get_regime(40.0)["name"] == "ВЛОШАВАЩ СЕ"
    assert get_regime(10.0)["name"] == "РЕЦЕСИОНЕН"


# ── Лещова агрегация ─────────────────────────────────────────────────────────

def test_lens_score_is_tanh_of_the_mean_peer_group_z():
    snapshot = {
        "A": _monthly([1.0, 3.0] * 60 + [7.0]),
        "B": _monthly([1.0, 3.0] * 60 + [2.0]),
        "C": _monthly([1.0, 3.0] * 60 + [2.0]),
    }
    reports = compute_lens_reports(_mini_catalog(), snapshot)

    zs = [s["health_z"] for s in reports["growth"]["series"]]
    expected_z = sum(zs) / len(zs)

    assert reports["growth"]["health_z"] == pytest.approx(round(expected_z, 3))
    assert reports["growth"]["score"] == pytest.approx(
        round(50.0 * (1.0 + math.tanh(expected_z / 2.0)), 1)
    )
    assert reports["growth"]["n_series"] == 2


def test_lens_without_any_data_reports_none():
    reports = compute_lens_reports(_mini_catalog(), {})
    assert reports["growth"]["score"] is None
    assert reports["growth"]["health_z"] is None
    assert reports["growth"]["n_series"] == 0


def test_lens_survives_a_partially_missing_snapshot():
    snapshot = {"A": _monthly([1.0, 3.0] * 60 + [2.0])}
    reports = compute_lens_reports(_mini_catalog(), snapshot)

    assert reports["growth"]["score"] is not None
    assert reports["growth"]["n_series"] == 1
    missing = [s for s in reports["growth"]["series"] if s["key"] == "B"][0]
    assert missing["score"] is None


def test_every_configured_lens_appears_in_the_report():
    reports = compute_lens_reports(_mini_catalog(), {})
    assert set(reports) == set(MODULE_WEIGHTS)


def test_series_entries_carry_the_catalog_metadata():
    snapshot = {"A": _monthly([1.0, 3.0] * 60 + [2.0])}
    entry = compute_lens_reports(_mini_catalog(), snapshot)["growth"]["series"][0]

    assert entry["key"] == "A"
    assert entry["name_bg"] == "А"
    assert entry["catalog_id"] == "ds_a?geo=BG"
