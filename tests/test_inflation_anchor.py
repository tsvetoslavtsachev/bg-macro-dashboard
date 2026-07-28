"""
tests/test_inflation_anchor.py
==============================
Котвеният прочит на инфлацията + усещаната инфлация (мандат №48).

Двата гейта на П3:
  1. Котвата чете АБСОЛЮТНО разстояние до целта — пиннати зони, не калибрация.
  2. Композитът остава БИТ-В-БИТ същият с и без контекстната серия в каталога.
     Това е гейтът-звезда: контекстът е наблюдение ДО уреда, не в него.
"""
import numpy as np
import pandas as pd
import pytest

from catalog.polarity import INFLATION_TARGET
from catalog.series import SERIES_CATALOG, validate_catalog
from core.display import (
    ANCHOR_DISCLAIMER,
    ANCHOR_GREEN_PP,
    ANCHOR_YELLOW_PP,
    crisis_epoch_label,
    inflation_anchor,
    inflation_voices,
    perceived_inflation_reading,
)
from core.scorer import compute_composite_score, compute_lens_reports

PERCEIVED = "BG_INFL_PERCEIVED"


# ═════════════════════════════════════════════════════════════════════════════
# КОТВАТА — пиннатите зони
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "value, gap, zone",
    [
        (2.9, 0.9, "green"),    # при целта
        (3.5, 1.5, "yellow"),   # отклонена
        (5.2, 3.2, "red"),      # далеч от целта — живото четене на 06.2026
        (0.8, -1.2, "yellow"),  # дефлационната посока, същите зони огледално
        (2.0, 0.0, "green"),    # точно на целта
    ],
)
def test_anchor_zones_are_pinned(value, gap, zone):
    a = inflation_anchor(value)
    assert a["gap_pp"] == pytest.approx(gap)
    assert a["zone"] == zone


def test_anchor_boundaries_use_less_or_equal_semantics():
    """Точно 1.0 пп е ОЩЕ зелено, точно 2.0 пп е ОЩЕ жълто (`≤`)."""
    assert inflation_anchor(INFLATION_TARGET + ANCHOR_GREEN_PP)["zone"] == "green"
    assert inflation_anchor(INFLATION_TARGET - ANCHOR_GREEN_PP)["zone"] == "green"
    assert inflation_anchor(INFLATION_TARGET + ANCHOR_YELLOW_PP)["zone"] == "yellow"
    assert inflation_anchor(INFLATION_TARGET - ANCHOR_YELLOW_PP)["zone"] == "yellow"
    assert inflation_anchor(INFLATION_TARGET + ANCHOR_YELLOW_PP + 0.1)["zone"] == "red"


def test_anchor_sentence_is_deterministic_and_names_the_direction():
    a = inflation_anchor(5.2)
    assert a["sentence"] == "5.2% = 3.2 пп над целта (2%) — червена зона"
    assert a["label_bg"] == "далеч от целта"
    assert inflation_anchor(5.2) == a          # детерминистично, не свободен текст


def test_anchor_says_under_the_target_below_it():
    a = inflation_anchor(0.8)
    assert "под целта" in a["sentence"]
    assert "над целта" not in a["sentence"]
    assert a["gap_pp"] < 0


def test_anchor_at_the_target_says_so_without_a_direction():
    a = inflation_anchor(2.0)
    assert "точно на целта" in a["sentence"]
    assert "над" not in a["sentence"] and "под" not in a["sentence"]


def test_anchor_reads_the_target_from_the_single_source():
    """Целта идва от `catalog.polarity.INFLATION_TARGET`, не от литерал."""
    assert inflation_anchor(INFLATION_TARGET)["gap_pp"] == 0.0
    assert f"({INFLATION_TARGET:g}%)" in inflation_anchor(5.2)["gap_phrase"]
    # Друга цел → друга котва, без пипане на кода
    assert inflation_anchor(5.2, target=4.0)["gap_pp"] == pytest.approx(1.2)
    assert inflation_anchor(5.2, target=4.0)["zone"] == "yellow"


def test_anchor_carries_the_zone_colour_from_config():
    from config import INFLATION_ANCHOR_COLORS

    for value, zone in ((2.5, "green"), (3.5, "yellow"), (5.2, "red")):
        assert inflation_anchor(value)["color"] == INFLATION_ANCHOR_COLORS[zone]


def test_anchor_survives_a_missing_value():
    for missing in (None, float("nan")):
        a = inflation_anchor(missing)
        assert a["zone"] is None
        assert a["sentence"] == "—"


# ═════════════════════════════════════════════════════════════════════════════
# УСЕЩАНАТА ИНФЛАЦИЯ — контекстната серия
# ═════════════════════════════════════════════════════════════════════════════

def _perceived_series(crisis=72.4, now=75.4, n_tail=30):
    """Синтетична анкетна серия: спокойна епоха, криза 2021-23, днешна опашка."""
    idx = pd.date_range(start="2015-01-01", periods=138, freq="MS")
    values = []
    for d in idx:
        if pd.Timestamp("2021-01-01") <= d <= pd.Timestamp("2023-12-31"):
            values.append(crisis)
        else:
            values.append(38.0)
    s = pd.Series(values, index=idx, dtype="float64")
    s.iloc[-n_tail:] = now
    return s


def test_perceived_reading_reports_value_date_and_length():
    s = _perceived_series()
    r = perceived_inflation_reading(s, official=5.2)
    assert r["value"] == pytest.approx(75.4)
    assert r["n"] == len(s)
    assert r["last_date"] == s.index[-1].strftime("%Y-%m")


def test_perceived_claims_crisis_levels_only_when_the_data_says_so():
    """„Нива като 2021-23" се ГЕНЕРИРА от медианата на епохата, не се зашива."""
    hot = perceived_inflation_reading(_perceived_series(crisis=70.0, now=75.4))
    cool = perceived_inflation_reading(_perceived_series(crisis=90.0, now=40.0))

    assert hot["at_crisis_levels"] is True
    assert "нива като 2021-23" in hot["sentence"]

    assert cool["at_crisis_levels"] is False
    assert "нива като" not in cool["sentence"]
    assert "под медианата на 2021-23" in cool["sentence"]


def test_perceived_sentence_carries_the_official_number_next_to_it():
    """Находката Е разликата — двете числа стоят в едно изречение."""
    r = perceived_inflation_reading(_perceived_series(), official=5.2)
    assert r["sentence"] == (
        "Усещаната (ЕК анкета): 75.4 — нива като 2021-23; официалната е 5.2%"
    )


def test_epoch_label_is_derived_from_the_epoch_bounds():
    assert crisis_epoch_label() == "2021-23"
    assert crisis_epoch_label("2007-01-01", "2008-12-31") == "2007-08"


def test_perceived_reading_is_none_without_data():
    assert perceived_inflation_reading(None) is None
    assert perceived_inflation_reading(pd.Series(dtype="float64")) is None


# ═════════════════════════════════════════════════════════════════════════════
# КАТАЛОГЪТ
# ═════════════════════════════════════════════════════════════════════════════

def test_catalog_carries_eighteen_series_after_the_context_series():
    assert len(SERIES_CATALOG) == 18


def test_perceived_series_reads_the_ec_survey_balance():
    """Точният набор/показател е решение на мандата — пинва се.

    `ei_bsco_m` (ЕК потребителска анкета) · `BS-PT-LY` (ценовите тенденции през
    ПОСЛЕДНИТЕ 12 месеца) · `SA` · `BAL` (баланс — единствената мерна единица).
    """
    spec = SERIES_CATALOG[PERCEIVED]
    assert spec["source"] == "eurostat"
    assert spec["id"] == "ei_bsco_m?geo=BG&indic=BS-PT-LY&s_adj=SA&unit=BAL"
    assert "BS-PT-NY" not in spec["id"], "очакванията са МЕНЮ-кандидат, не влизат"
    assert spec["transform"] == "level"
    assert spec["is_rate"] is False
    assert spec["historical_start"] == "2001-05-01"
    assert spec["release_schedule"] == "monthly"


def test_perceived_series_is_context_only_and_lensless():
    spec = SERIES_CATALOG[PERCEIVED]
    assert spec["lens"] == []
    assert spec["context_only"] is True
    assert spec["peer_group"] == "context"


def test_narrative_hint_warns_that_the_balance_is_not_a_percent():
    assert "не е процент" in SERIES_CATALOG[PERCEIVED]["narrative_hint"]


def test_validate_catalog_rejects_an_empty_lens_without_the_flag():
    """Тихият пропуск на леща остава хванат — флагът е ЕДИНСТВЕНОТО изключение."""
    silent = {"X": {"source": "eurostat", "region": "BG", "lens": [],
                    "transform": "level"}}
    errors = validate_catalog(silent)
    assert errors and "empty lens" in errors[0]

    declared = {"X": dict(silent["X"], context_only=True)}
    assert validate_catalog(declared) == []


def test_validate_catalog_rejects_a_context_series_that_also_claims_a_lens():
    mixed = {"X": {"source": "eurostat", "region": "BG", "lens": ["inflation"],
                   "transform": "level", "context_only": True}}
    assert validate_catalog(mixed) != []


def test_the_live_catalog_is_valid():
    assert validate_catalog() == []


# ═════════════════════════════════════════════════════════════════════════════
# ГЕЙТЪТ-ЗВЕЗДА — композитът е БИТ-В-БИТ недокоснат
# ═════════════════════════════════════════════════════════════════════════════

def _synthetic_snapshot(n: int = 300, seed: int = 11) -> dict:
    idx = pd.date_range(end="2026-06-01", periods=n, freq="MS")
    rng = np.random.RandomState(seed)
    return {
        key: pd.Series(50.0 + np.cumsum(rng.normal(0, 0.6, n)), index=idx)
        for key in SERIES_CATALOG
    }


def test_the_context_series_does_not_move_a_single_lens_or_the_composite():
    """ГЕЙТЪТ на П3: каталог СЪС и БЕЗ контекстната серия → бит-в-бит равни.

    Не approx — ТОЧНО равенство на композита, на шестте score-а и на шестте z-а.
    Контекстът не влиза в никоя леща, затова разликата трябва да е нула ПО
    КОНСТРУКЦИЯ, а не по случайност на закръглението.
    """
    snapshot = _synthetic_snapshot()
    without = {k: v for k, v in SERIES_CATALOG.items() if k != PERCEIVED}

    rep_with = compute_lens_reports(SERIES_CATALOG, snapshot)
    rep_without = compute_lens_reports(without, snapshot)

    assert set(rep_with) == set(rep_without)
    for lens in rep_with:
        assert rep_with[lens]["score"] == rep_without[lens]["score"], lens
        assert rep_with[lens]["health_z"] == rep_without[lens]["health_z"], lens
        assert rep_with[lens]["n_series"] == rep_without[lens]["n_series"], lens

    comp_with = compute_composite_score(
        {l: r["score"] for l, r in rep_with.items()})
    comp_without = compute_composite_score(
        {l: r["score"] for l, r in rep_without.items()})
    assert comp_with == comp_without


def test_the_context_series_never_reaches_a_lens_report():
    """Механиката, не само числото: ключът го няма в нито един лещов доклад."""
    reports = compute_lens_reports(SERIES_CATALOG, _synthetic_snapshot())
    scored_keys = {s["key"] for rep in reports.values() for s in rep["series"]}
    assert PERCEIVED not in scored_keys
    assert "BG_HICP" in scored_keys


def test_the_reconstructed_history_is_untouched_too(tmp_path):
    """И филмът мери същия уред — иначе историята щеше да се раздвои с лицето."""
    from analysis.lens_history import build_history
    from pandas.testing import assert_frame_equal

    snapshot = _synthetic_snapshot()
    without = {k: v for k, v in SERIES_CATALOG.items() if k != PERCEIVED}
    assert_frame_equal(
        build_history(SERIES_CATALOG, snapshot, grid_start="2024-12-01"),
        build_history(without, snapshot, grid_start="2024-12-01"),
    )


# ═════════════════════════════════════════════════════════════════════════════
# ЖИВОТО СЪСТОЯНИЕ — от КОМИТНАТИЯ кеш, без нито една мрежова заявка
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def cache_snapshot():
    from sources import build_adapters
    from catalog.series import series_by_source

    snapshot = {}
    for source_name, adapter in build_adapters().items():
        keys = [spec["_key"] for spec in series_by_source(source_name)]
        snapshot.update(adapter.get_snapshot(keys))
    if PERCEIVED not in snapshot:
        pytest.skip("кешът в data/ няма контекстната серия — тестът иска комитнатия кеш")
    return snapshot


def test_the_perceived_series_is_in_the_committed_cache(cache_snapshot):
    """Живо проверено 28.07.2026: 75.4 @2026-06, пълна история от 2001-05."""
    s = cache_snapshot[PERCEIVED].dropna()
    assert len(s) >= 300
    assert s.index[-1] == pd.Timestamp("2026-06-01")
    assert float(s.iloc[-1]) == pytest.approx(75.4)
    assert s.index[0] == pd.Timestamp("2001-05-01")


def test_the_perceived_series_sits_far_above_the_official_inflation(cache_snapshot):
    """Находката е РАЗЛИКАТА — тя е и причината серията да е на лицето."""
    reading = perceived_inflation_reading(
        cache_snapshot[PERCEIVED],
        official=float(cache_snapshot["BG_HICP"].dropna().iloc[-1]),
    )
    assert reading["at_crisis_levels"] is True
    assert reading["epoch_median"] is not None
    assert reading["value"] > reading["epoch_median"]
    assert reading["value"] > reading["official"] * 5


def test_the_inflation_lens_is_untouched_by_this_mandate(cache_snapshot):
    """U-score-ът на инфлационната леща е ТОЧНО този отпреди мандата.

    Пинът е спрямо ПРЕД-МАНДАТНИЯ каталог (без контекстната серия), а не спрямо
    зашито число: така тестът казва „мандатът не мръдна лещата" всяка седмица,
    вместо да гърми, щом Eurostat публикува нов месец.
    Живото състояние на 28.07.2026 е score 34.8 (z −0.63) — същото преди и след.
    """
    before = {k: v for k, v in SERIES_CATALOG.items() if k != PERCEIVED}
    rep_before = compute_lens_reports(before, cache_snapshot)["inflation"]
    rep_after = compute_lens_reports(SERIES_CATALOG, cache_snapshot)["inflation"]

    assert rep_after["score"] == rep_before["score"]
    assert rep_after["health_z"] == rep_before["health_z"]
    assert rep_after["n_series"] == rep_before["n_series"] == 2


def test_the_live_anchor_sentences_read_the_real_numbers(cache_snapshot):
    voices = inflation_voices(cache_snapshot)
    assert [a["key"] for a in voices["anchors"]] == ["BG_HICP", "BG_HICP_CORE"]
    for a in voices["anchors"]:
        assert a["gap_pp"] == pytest.approx(round(a["value"] - INFLATION_TARGET, 1))
        assert a["value_str"] in a["sentence"]
        assert a["zone_phrase"] in a["sentence"]


# ═════════════════════════════════════════════════════════════════════════════
# U-МЕХАНИЗМЪТ — замразен пин, независим от данните
# ═════════════════════════════════════════════════════════════════════════════

def test_the_u_score_mechanism_is_pinned_on_a_frozen_series():
    """Котвата е ВТОРИ глас — тя не пипа U-score-а. Пинът го доказва numerically.

    Замразена серия → замразен U-score. Ако някой ден U_BAND, tanh наклонът или
    целта се сменят, това число ще се смени и мандатът ще се види.
    """
    from core.scorer import score_series

    idx = pd.date_range(end="2026-06-01", periods=200, freq="MS")
    s = pd.Series([1.0, 3.0] * 100, index=idx)
    res = score_series(s, transform="level",
                       polarity=("U", "target", INFLATION_TARGET), name="BG_HICP")

    # median = 2.0 = целта · scale = 1.4826·MAD = 1.4826 · последно 3.0
    # → отклонение 0.674σ · health_z = U_BAND − 0.674 = 0.326
    assert res["health_z"] == pytest.approx(0.326)
    assert res["score"] == pytest.approx(58.1)
    # Котвата чете СЪЩОТО число абсолютно — и стига до друга, по-строга присъда
    assert inflation_anchor(3.0)["zone"] == "green"
    assert inflation_anchor(5.2)["zone"] == "red"


# ═════════════════════════════════════════════════════════════════════════════
# ДВАТА ГЛАСА ЗАЕДНО
# ═════════════════════════════════════════════════════════════════════════════

def test_inflation_voices_anchors_both_official_measures():
    snapshot = {
        "BG_HICP": pd.Series([5.2], index=pd.to_datetime(["2026-06-01"])),
        "BG_HICP_CORE": pd.Series([4.6], index=pd.to_datetime(["2026-06-01"])),
    }
    voices = inflation_voices(snapshot)
    keys = [a["key"] for a in voices["anchors"]]

    assert keys == ["BG_HICP", "BG_HICP_CORE"]
    assert voices["anchors"][0]["gap_pp"] == pytest.approx(3.2)
    assert voices["anchors"][1]["gap_pp"] == pytest.approx(2.6)
    assert all(a["zone"] == "red" for a in voices["anchors"])
    assert voices["perceived"] is None       # няма серия → няма ред, не празнота


def test_inflation_voices_compares_the_perceived_to_the_headline():
    snapshot = {
        "BG_HICP": pd.Series([5.2], index=pd.to_datetime(["2026-06-01"])),
        PERCEIVED: _perceived_series(),
    }
    voices = inflation_voices(snapshot)
    assert voices["perceived"]["official"] == pytest.approx(5.2)
    assert "официалната е 5.2%" in voices["perceived"]["sentence"]


def test_inflation_voices_keeps_the_two_voices_apart():
    assert "НЕ пипат композита" in ANCHOR_DISCLAIMER
    assert inflation_voices({})["disclaimer"] == ANCHOR_DISCLAIMER
