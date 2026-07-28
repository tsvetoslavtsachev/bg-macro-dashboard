"""
tests/test_temperature.py
=========================
Температурният слой + ПРИЕМНИЯТ ГЕЙТ на мандат №47 (П2).

Гейтът-звезда е един: с фиксираните зони уредът трябва да СВЕТИ в бума
2006H2-2008 и да МЪЛЧИ в спокойните 2015-2019. Ако този тест падне, зоните вече
не мерят прегряване, а нещо друго — и целият температурен слой става декорация.

Всичко работи върху КОМИТНАТИЯ кеш (`get_snapshot` не пипа мрежата).
"""
import numpy as np
import pandas as pd
import pytest

from analysis.lens_history import build_history
from analysis.temperature import (
    TEMP_SERIES,
    hot_keys_str,
    temp_level,
    temperature,
    zone_table,
)
from catalog.polarity import opt_keys, opt_zone, polarity_for
from catalog.series import SERIES_CATALOG, series_by_source
from sources import build_adapters
from sources.manual_seed import splice_loans


# ═════════════════════════════════════════════════════════════════════════════
# ФИКСТУРИ
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def cache_snapshot():
    snapshot = {}
    for source_name, adapter in build_adapters().items():
        keys = [spec["_key"] for spec in series_by_source(source_name)]
        snapshot.update(adapter.get_snapshot(keys))
    if len(snapshot) < len(SERIES_CATALOG):
        pytest.skip("кешът в data/ е непълен — тестът иска комитнатия кеш")
    return splice_loans(snapshot)


@pytest.fixture(scope="module")
def history(cache_snapshot):
    return build_history(SERIES_CATALOG, cache_snapshot)


def _quarters(history):
    return history[history["row_type"] == "quarter"]


def _synthetic(value_by_key: dict) -> dict:
    """Тримесечен snapshot, чиято ПОСЛЕДНА трансформирана стойност е зададената.

    Сериите с `yoy_pct` / `yoy_roll4` се строят от ниво, което расте с точния
    темп — така тестът минава през истинската трансформация, не я заобикаля.
    """
    idx = pd.date_range(end="2026-03-01", periods=40, freq="QS-DEC")
    snap = {}
    for key, target in value_by_key.items():
        transform = SERIES_CATALOG[key]["transform"]
        if transform == "level":
            snap[key] = pd.Series([float(target)] * len(idx), index=idx)
        else:
            growth = (1.0 + float(target) / 100.0) ** 0.25
            snap[key] = pd.Series(
                [100.0 * growth ** i for i in range(len(idx))], index=idx
            )
    return snap


# ═════════════════════════════════════════════════════════════════════════════
# ЕДИН ИЗТОЧНИК ЗА „КОИ СА БУМ-СЕРИИТЕ"
# ═════════════════════════════════════════════════════════════════════════════

def test_temp_series_is_derived_from_the_polarity_map():
    """Нула дублиране: шеста OPT серия утре влиза и в скоринга, и тук наведнъж."""
    assert TEMP_SERIES == opt_keys()
    assert set(TEMP_SERIES) == {
        "BG_WAGES", "BG_LOANS_NFC", "BG_LOANS_HH", "BG_HPI", "BG_PERMITS"
    }


def test_the_zone_table_reads_the_thresholds_from_the_code():
    rows = {r["key"]: r for r in zone_table(SERIES_CATALOG)}
    assert set(rows) == set(TEMP_SERIES)
    for key, row in rows.items():
        lo, hi, width = opt_zone(polarity_for(key))
        assert (row["lo"], row["hi"], row["s"]) == (lo, hi, width)
        assert row["name_bg"] == SERIES_CATALOG[key]["name_bg"]
        assert row["provenance"]


def test_temp_level_has_three_steps():
    assert temp_level(0) == "cold"
    assert temp_level(1) == "warm"
    assert temp_level(2) == "warm"
    assert temp_level(3) == "hot"
    assert temp_level(5) == "hot"


# ═════════════════════════════════════════════════════════════════════════════
# temperature() — какво брои и какво НЕ брои
# ═════════════════════════════════════════════════════════════════════════════

def test_a_series_above_its_upper_bound_is_hot():
    snap = _synthetic({"BG_LOANS_HH": 21.0})
    temp = temperature(SERIES_CATALOG, snap)

    assert temp["n_hot"] == 1
    assert temp["n_total"] == 1
    hot = temp["hot"][0]
    assert hot["key"] == "BG_LOANS_HH"
    assert hot["name_bg"] == SERIES_CATALOG["BG_LOANS_HH"]["name_bg"]
    assert hot["value"] == pytest.approx(21.0, abs=0.1)
    assert hot["hi"] == 12.0


def test_a_series_inside_its_zone_is_neither_hot_nor_cold():
    temp = temperature(SERIES_CATALOG, _synthetic({"BG_LOANS_NFC": 11.9}))
    assert temp["n_hot"] == 0
    assert temp["cold"] == []
    assert temp["n_total"] == 1


def test_a_series_below_its_lower_bound_is_cold_and_does_not_count_as_hot():
    """Двойният смисъл: под lo е КРИЗА, не прегряване. Термометърът брои само
    нарушенията нагоре; кризата се чете в score-а."""
    temp = temperature(SERIES_CATALOG, _synthetic({"BG_LOANS_NFC": -8.0}))
    assert temp["n_hot"] == 0
    assert [e["key"] for e in temp["cold"]] == ["BG_LOANS_NFC"]
    assert temp["cold"][0]["lo"] == 0.0


def test_a_missing_series_is_not_counted_in_the_denominator():
    """Честност: „2/4“ вместо „2/5“, когато една серия мълчи."""
    snap = _synthetic({"BG_LOANS_HH": 21.0, "BG_HPI": 14.8, "BG_WAGES": 11.5})
    temp = temperature(SERIES_CATALOG, snap)

    assert temp["n_total"] == 3
    assert temp["n_hot"] == 2
    assert set(e["key"] for e in temp["hot"]) == {"BG_LOANS_HH", "BG_HPI"}


def test_an_empty_snapshot_reports_zero_of_zero():
    temp = temperature(SERIES_CATALOG, {})
    assert temp == {"n_hot": 0, "n_total": 0, "hot": [], "cold": [], "as_of": None}


def test_the_cut_date_reads_the_past_not_the_present():
    """`at` реже по ПЕРИОДНАТА дата — същата семантика като реконструкцията."""
    idx = pd.date_range(end="2026-03-01", periods=40, freq="QS-DEC")
    hot_then_calm = [100.0 * 1.2 ** i for i in range(30)]
    hot_then_calm += [hot_then_calm[-1] * 1.001 ** (i + 1) for i in range(10)]
    snap = {"BG_HPI": pd.Series(
        [80.0] * 30 + [1.0] * 10, index=idx  # HPI е готов темп (transform=level)
    )}

    assert temperature(SERIES_CATALOG, snap)["n_hot"] == 0
    past = temperature(SERIES_CATALOG, snap, at=idx[29])
    assert past["n_hot"] == 1
    assert past["as_of"] == idx[29].strftime("%Y-%m-%d")


def test_hot_keys_string_is_compact_and_stable():
    snap = _synthetic({"BG_LOANS_HH": 21.0, "BG_HPI": 14.8})
    assert hot_keys_str(temperature(SERIES_CATALOG, snap)) == "BG_LOANS_HH+BG_HPI"
    assert hot_keys_str(None) == ""
    assert hot_keys_str(temperature(SERIES_CATALOG, {})) == ""


# ═════════════════════════════════════════════════════════════════════════════
# ЖИВОТО ЧИСЛО
# ═════════════════════════════════════════════════════════════════════════════

def test_todays_temperature_is_two_of_five(cache_snapshot):
    """Данни-пасът на №47: горят кредитът за домакинствата и цените на жилищата.

    Фирменият кредит (11.9) и разрешителните (34.6) са НА ПРАГА, но не горят —
    точно това прави числото полезно: то не се вдига „за всеки случай“.
    """
    temp = temperature(SERIES_CATALOG, cache_snapshot)
    assert temp["n_total"] == 5
    assert temp["n_hot"] == 2
    assert [e["key"] for e in temp["hot"]] == ["BG_LOANS_HH", "BG_HPI"]


# ═════════════════════════════════════════════════════════════════════════════
# ПРИЕМНИЯТ ГЕЙТ — гейтът-звезда на мандата
# ═════════════════════════════════════════════════════════════════════════════

def test_the_acceptance_gate_the_boom_lights_up_and_the_calm_era_stays_silent(history):
    """2006H2-2008 СВЕТИ (≥3 горещи в ≥8 от 11 тримесечия) · 2015-2019 МЪЛЧИ (0).

    Това е ЕДИНСТВЕНИЯТ тест, който казва дали абсолютните зони мерят
    прегряване. Праговете са фиксирани от данни-пас (28.07.2026) и не се
    калибрират наново — ако гейтът падне, поправя се ПРИЧИНАТА, не прагът.
    """
    q = _quarters(history)

    boom = q.loc["2006-06-01":"2008-12-31", "temp_count"].astype("Int64")
    calm = q.loc["2015-01-01":"2019-12-31", "temp_count"].astype("Int64")

    assert len(calm) == 20
    assert int(calm.max()) == 0, "спокойната епоха трябва да МЪЛЧИ"

    assert len(boom) == 11
    assert int(boom.max()) == 5, "върхът на бума пали и петте серии"
    assert int((boom >= 3).sum()) >= 8, "бумът трябва да СВЕТИ, не да мигне"


def test_the_2009_shock_is_cold_not_hot(history):
    """Верният прочит: кризата НЕ е прегряване. Тя се вижда в score-а."""
    q = _quarters(history)
    shock = q.loc["2009-01-01":"2014-12-31", "temp_count"].astype("Int64")
    assert int(shock.max()) <= 2
    assert float(shock.astype(float).mean()) < 0.5


def test_the_current_wave_is_winding_up_not_at_the_2007_peak(history):
    """2020-2023 се навива (върхове 3/5), но не стига 5/5 на 2007."""
    q = _quarters(history)
    wave = q.loc["2020-01-01":"2023-12-31", "temp_count"].astype("Int64")
    assert int(wave.max()) < 5
    assert int(wave.max()) >= 3


def test_every_quarter_row_carries_a_temperature(history):
    q = _quarters(history)
    assert q["temp_count"].notna().all()
    assert (q["temp_count"] >= 0).all()
    assert (q["temp_count"] <= len(TEMP_SERIES)).all()


def test_the_hot_string_names_the_series_behind_the_count(history):
    """Числото без имена е безполезно — редът казва КОЙ гори."""
    q = _quarters(history)
    row = q.loc["2007-03-01"]
    assert int(row["temp_count"]) == 5
    assert row["temp_hot"].split("+") == TEMP_SERIES

    calm_row = q.loc["2017-06-01"]
    assert int(calm_row["temp_count"]) == 0
    assert calm_row["temp_hot"] == ""


def test_the_temperature_has_no_look_ahead():
    """Абсолютните прагове не знаят бъдещето: смяна на стойностите СЛЕД марка
    не мени температурата на марка. Точно това прави гейта честен."""
    idx = pd.date_range(end="2026-03-01", periods=60, freq="QS-DEC")
    base = {key: pd.Series(np.linspace(2.0, 8.0, len(idx)), index=idx)
            for key in SERIES_CATALOG}
    cutoff = idx[40]

    before = temperature(SERIES_CATALOG, base, at=cutoff)
    tampered = {
        k: pd.Series(np.where(s.index > cutoff, 999.0, s.values), index=s.index)
        for k, s in base.items()
    }
    after = temperature(SERIES_CATALOG, tampered, at=cutoff)

    assert before["n_hot"] == after["n_hot"]
    assert hot_keys_str(before) == hot_keys_str(after)
