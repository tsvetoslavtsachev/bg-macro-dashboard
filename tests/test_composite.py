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

def test_bg_module_weights_are_the_rebalanced_seven():
    """Мандат №50: седмата леща + ребалансът. Инфлацията и растежът остават
    водещи (0.20), ПЕТТЕ структурни лещи са равни по 0.12."""
    assert MODULE_WEIGHTS == {
        "inflation": 0.20, "labor": 0.12, "growth": 0.20,
        "credit": 0.12, "external": 0.12, "property": 0.12, "fiscal": 0.12,
    }


def test_the_five_structural_lenses_carry_equal_weight():
    """Никоя структурна леща няма повече право на глас от друга (мандат №50)."""
    structural = ("labor", "credit", "external", "property", "fiscal")
    assert len({MODULE_WEIGHTS[l] for l in structural}) == 1
    assert MODULE_WEIGHTS["inflation"] == MODULE_WEIGHTS["growth"] == 0.20


def test_module_weights_sum_to_exactly_one():
    """Точният тест (мандат №43 §А4, разширен с №50): сумата е 1.0.

    Ако утре някой добави осма леща, без да отнеме отнякъде, композитът тихо
    ще се пренормализира и числото ще се смени без обяснение — този тест го
    хваща на място.
    """
    assert sum(MODULE_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)
    assert len(MODULE_WEIGHTS) == 7


def test_composite_is_the_weighted_mean_when_every_lens_is_present():
    scores = {"inflation": 40.0, "labor": 60.0, "growth": 50.0,
              "credit": 30.0, "external": 20.0, "property": 70.0, "fiscal": 25.0}
    expected = sum(scores[m] * w for m, w in MODULE_WEIGHTS.items())
    assert compute_composite_score(scores) == pytest.approx(round(expected, 1))


# ── Ренормализация ───────────────────────────────────────────────────────────

def test_empty_lens_drops_out_and_weights_renormalise():
    scores = {"inflation": 40.0, "labor": 60.0, "growth": None,
              "credit": None, "external": None, "property": None, "fiscal": None}
    expected = (40.0 * 0.20 + 60.0 * 0.12) / (0.20 + 0.12)
    assert compute_composite_score(scores) == pytest.approx(round(expected, 1))


def test_an_empty_property_lens_renormalises_over_the_other_five():
    """Ако Eurostat замълчи и трите имотни серии → лещата ИЗПАДА и композитът
    се смята върху останалите тегла, а не с 50 на мястото ѝ (мандат №43 §А4)."""
    five = {"inflation": 34.8, "labor": 67.4, "growth": 47.1,
            "credit": 50.8, "external": 2.3}
    scores = dict(five, property=None)

    wsum = sum(MODULE_WEIGHTS[l] for l in five)
    expected = sum(five[l] * MODULE_WEIGHTS[l] for l in five) / wsum

    assert wsum == pytest.approx(0.76)
    assert compute_composite_score(scores) == pytest.approx(round(expected, 1))


def test_an_empty_fiscal_lens_renormalises_over_the_other_six():
    """Мандат №50: седмата леща изпада по същото правило като шестата.

    Фискалните серии са тримесечни и ревизионно чувствителни — денят, в който
    Eurostat замълчи, не бива да дърпа композита към средата с фалшиво „50".
    """
    six = {"inflation": 34.8, "labor": 75.8, "growth": 47.1,
           "credit": 40.8, "external": 2.3, "property": 62.3}
    scores = dict(six, fiscal=None)

    wsum = sum(MODULE_WEIGHTS[l] for l in six)
    expected = sum(six[l] * MODULE_WEIGHTS[l] for l in six) / wsum

    assert wsum == pytest.approx(0.88)
    assert compute_composite_score(scores) == pytest.approx(round(expected, 1))


def test_property_lens_actually_moves_the_composite():
    """Шестата леща не е декорация — при 0.12 тегло тя мести числото."""
    five = {"inflation": 34.8, "labor": 67.4, "growth": 47.1,
            "credit": 50.8, "external": 2.3}
    without = compute_composite_score(dict(five, property=None))
    with_high = compute_composite_score(dict(five, property=70.9))
    with_low = compute_composite_score(dict(five, property=10.0))

    assert with_high > without > with_low


def test_fiscal_lens_actually_moves_the_composite():
    """Седмата леща също не е декорация — ниският ѝ score дърпа надолу."""
    six = {"inflation": 34.8, "labor": 75.8, "growth": 47.1,
           "credit": 40.8, "external": 2.3, "property": 62.3}
    without = compute_composite_score(dict(six, fiscal=None))
    with_high = compute_composite_score(dict(six, fiscal=80.0))
    with_low = compute_composite_score(dict(six, fiscal=20.5))

    assert with_high > without > with_low


def test_empty_lens_is_not_counted_as_neutral_fifty():
    scores = {"inflation": 40.0, "labor": 60.0, "growth": None,
              "credit": None, "external": None, "property": None, "fiscal": None}
    as_neutral = sum(
        (scores[m] if scores[m] is not None else 50.0) * w
        for m, w in MODULE_WEIGHTS.items()
    )
    assert compute_composite_score(scores) != pytest.approx(round(as_neutral, 1))


def test_composite_is_none_when_no_lens_has_data():
    scores = {m: None for m in MODULE_WEIGHTS}
    assert compute_composite_score(scores) is None


def test_nan_lens_score_is_treated_as_missing():
    scores = {"inflation": float("nan"), "labor": 60.0, "growth": None,
              "credit": None, "external": None, "property": None, "fiscal": None}
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


def test_two_series_in_one_peer_group_produce_one_signal():
    """Мандат №39 §А2: двата заема НЕ гласуват поотделно в лещата.

    Групата дава средното на своите серии; лещата претегля ГРУПИТЕ. Иначе
    кредитирането щеше да надтежи доходността 2:1.
    """
    catalog = {
        "L1": {"lens": ["credit"], "peer_group": "lending", "transform": "level",
               "name_bg": "Заеми 1", "id": "BSI/K1"},
        "L2": {"lens": ["credit"], "peer_group": "lending", "transform": "level",
               "name_bg": "Заеми 2", "id": "BSI/K2"},
        "Y": {"lens": ["credit"], "peer_group": "yields", "transform": "level",
              "name_bg": "Доходност", "id": "irt?geo=BG"},
    }
    snapshot = {
        "L1": _monthly([1.0, 3.0] * 60 + [7.0]),
        "L2": _monthly([1.0, 3.0] * 60 + [6.0]),
        "Y": _monthly([1.0, 3.0] * 60 + [2.0]),
    }
    rep = compute_lens_reports(catalog, snapshot)["credit"]

    groups = {pg["name"]: pg for pg in rep["peer_groups"]}
    assert set(groups) == {"lending", "yields"}
    assert groups["lending"]["n_available"] == 2

    zs = {s["key"]: s["health_z"] for s in rep["series"]}
    lending_z = (zs["L1"] + zs["L2"]) / 2
    assert groups["lending"]["health_z"] == pytest.approx(round(lending_z, 3))

    # Лещата = средно на ДВЕТЕ групи, не на трите серии
    expected_lens_z = (lending_z + zs["Y"]) / 2
    assert rep["health_z"] == pytest.approx(round(expected_lens_z, 3), abs=0.001)

    three_series_mean = (zs["L1"] + zs["L2"] + zs["Y"]) / 3
    assert rep["health_z"] != pytest.approx(round(three_series_mean, 3))


def test_adding_a_second_loan_does_not_double_the_lending_weight():
    """Един заем срещу два в същата група → групата тежи еднакво в лещата."""
    one = {
        "L1": {"lens": ["credit"], "peer_group": "lending", "transform": "level",
               "name_bg": "Заеми 1", "id": "BSI/K1"},
        "Y": {"lens": ["credit"], "peer_group": "yields", "transform": "level",
              "name_bg": "Доходност", "id": "irt?geo=BG"},
    }
    two = dict(one)
    two["L2"] = {"lens": ["credit"], "peer_group": "lending", "transform": "level",
                 "name_bg": "Заеми 2", "id": "BSI/K2"}

    snapshot = {
        "L1": _monthly([1.0, 3.0] * 60 + [7.0]),
        "L2": _monthly([1.0, 3.0] * 60 + [7.0]),   # идентичен на L1
        "Y": _monthly([1.0, 3.0] * 60 + [2.0]),
    }

    z_one = compute_lens_reports(one, snapshot)["credit"]["health_z"]
    z_two = compute_lens_reports(two, snapshot)["credit"]["health_z"]
    assert z_one == pytest.approx(z_two)


# ── Мандат №42: цената на кредита в лещата ───────────────────────────────────

def test_a_full_history_rate_carries_no_thin_window_flag():
    """MIR носи месечна история от 2007-01 → нормата е ПЪЛНА 10-годишна.

    Ако някой ден серията се смени с къс вариант (напр. салдата от 2019-12),
    етикетът трябва да спре да казва „10г" — точно това пази тестът.
    """
    from core.scorer import score_series

    idx = pd.date_range(start="2007-01-01", end="2026-05-01", freq="MS")
    s = pd.Series([4.0, 6.0] * (len(idx) // 2) + [4.15] * (len(idx) % 2), index=idx)

    res = score_series(s, transform="level", polarity=-1, name="BG_LENDING_RATE")

    assert res["thin_window"] is False
    assert res["percentile_window"] == "10г"


def test_lending_cost_is_a_third_leg_not_folded_into_yields():
    """Трите крака на кредита тежат по 1/3 — не 50/50 с цената на дълга."""
    catalog = {
        "Y": {"lens": ["credit"], "peer_group": "yields", "transform": "level",
              "name_bg": "Доходност", "id": "irt?geo=BG"},
        "C": {"lens": ["credit"], "peer_group": "lending_cost", "transform": "level",
              "name_bg": "Цена на новия кредит", "id": "MIR/K"},
        "L": {"lens": ["credit"], "peer_group": "lending", "transform": "level",
              "name_bg": "Заеми", "id": "BSI/K"},
    }
    snapshot = {
        "Y": _monthly([1.0, 3.0] * 60 + [2.0]),
        "C": _monthly([1.0, 3.0] * 60 + [7.0]),
        "L": _monthly([1.0, 3.0] * 60 + [6.0]),
    }
    rep = compute_lens_reports(catalog, snapshot)["credit"]

    groups = {pg["name"] for pg in rep["peer_groups"]}
    assert groups == {"yields", "lending", "lending_cost"}

    zs = {s["key"]: s["health_z"] for s in rep["series"]}
    expected = (zs["Y"] + zs["C"] + zs["L"]) / 3
    assert rep["health_z"] == pytest.approx(round(expected, 3), abs=0.001)


# ── Мандат №50: фискалната леща в агрегацията ────────────────────────────────

def _quarterly(values, end="2026-01-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="QS")
    return pd.Series([float(v) for v in values], index=idx)


def test_fiscal_lens_is_the_mean_of_its_two_peer_groups():
    """Потокът и стокът гласуват ПООТДЕЛНО — по 1/2 всеки, не като едно число."""
    catalog = {
        "B": {"lens": ["fiscal"], "peer_group": "fiscal_balance",
              "transform": "level", "name_bg": "Салдо", "id": "gov_10q_ggnfa?geo=BG"},
        "D": {"lens": ["fiscal"], "peer_group": "debt",
              "transform": "level", "name_bg": "Дълг", "id": "gov_10q_ggdebt?geo=BG"},
    }
    snapshot = {
        "B": _monthly([1.0, 3.0] * 60 + [7.0]),
        "D": _monthly([1.0, 3.0] * 60 + [6.0]),
    }
    rep = compute_lens_reports(catalog, snapshot)["fiscal"]

    assert {pg["name"] for pg in rep["peer_groups"]} == {"fiscal_balance", "debt"}
    zs = {s["key"]: s["health_z"] for s in rep["series"]}
    expected = (zs["B"] + zs["D"]) / 2
    assert rep["health_z"] == pytest.approx(round(expected, 3), abs=0.001)


def test_the_budget_balance_is_scored_on_the_four_quarter_rolling_mean():
    """Аритметичният пин: суровото NSA тримесечие е сезонен трион; скорът чете
    средното на ПОСЛЕДНИТЕ ЧЕТИРИ тримесечия, не последната дупка."""
    from core.scorer import score_series

    # Сезонен модел, какъвто е суровият B9: три положителни тримесечия и Q4 дупка.
    raw = _quarterly([1.0, 2.0, 1.0, -8.0] * 26)
    res = score_series(raw, transform="roll4q_mean", polarity=+1, name="BG_GOV_BALANCE")

    assert res["value"] == pytest.approx((1.0 + 2.0 + 1.0 - 8.0) / 4)
    assert res["value"] != pytest.approx(float(raw.iloc[-1]))


def test_the_debt_is_scored_on_its_level_and_a_rise_is_unhealthy():
    """Полярност −1 върху НИВОТО: качване спрямо собствената 10-г. норма сваля
    score-а. Ако някой обърне знака или мине на делта, тестът пада."""
    from core.scorer import score_series

    flat = [22.0, 23.0] * 30
    steady = score_series(_quarterly(flat + [22.5]), transform="level",
                          polarity=-1, name="BG_GOV_DEBT")
    risen = score_series(_quarterly(flat + [29.9]), transform="level",
                         polarity=-1, name="BG_GOV_DEBT")

    assert risen["score"] < steady["score"]
    assert risen["z_raw"] > 0          # нивото е НАД нормата…
    assert risen["health_z"] < 0       # …и точно това е нездравото


def test_series_entries_carry_the_catalog_metadata():
    snapshot = {"A": _monthly([1.0, 3.0] * 60 + [2.0])}
    entry = compute_lens_reports(_mini_catalog(), snapshot)["growth"]["series"][0]

    assert entry["key"] == "A"
    assert entry["name_bg"] == "А"
    assert entry["catalog_id"] == "ds_a?geo=BG"
