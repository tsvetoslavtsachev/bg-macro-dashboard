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

from analysis import temperature as temperature_mod
from analysis.lens_history import build_history, history_columns
from analysis.temperature import (
    BUBBLE_PAIR_CREDIT,
    BUBBLE_PAIR_LABEL_BG,
    BUBBLE_PAIR_PROPERTY,
    BUBBLE_PAIR_PROVENANCE,
    TEMP_SERIES,
    bubble_pair,
    bubble_pair_from_hot,
    bubble_pair_line,
    bubble_pair_streak,
    hot_keys_str,
    temp_level,
    temperature,
    zone_table,
)
from catalog.polarity import opt_keys, opt_zone, polarity_for
from catalog.series import SERIES_CATALOG, series_by_source
from sources import build_adapters
from sources.derived import derive_series
from sources.manual_seed import splice_loans


# ═════════════════════════════════════════════════════════════════════════════
# ФИКСТУРИ
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def cache_snapshot():
    # Живата верига от `run.py::_score_everything` (мандат №54): fetch → splice
    # → derive. Проверката за пълнота е СЛЕД деривацията — изведената серия не
    # идва от адаптер и без нея снапшотът винаги би изглеждал „непълен".
    snapshot = {}
    for source_name, adapter in build_adapters().items():
        keys = [spec["_key"] for spec in series_by_source(source_name)]
        snapshot.update(adapter.get_snapshot(keys))
    snapshot = derive_series(splice_loans(snapshot))
    if len(snapshot) < len(SERIES_CATALOG):
        pytest.skip("кешът в data/ е непълен — тестът иска комитнатия кеш")
    return snapshot


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


# ═════════════════════════════════════════════════════════════════════════════
# БАЛОННАТА ДВОЙКА (мандат №53) — К3 прероден върху температурата
# ═════════════════════════════════════════════════════════════════════════════

def _grid(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """[(дата, temp_hot, row_type)] → минимална решетка с верните колони."""
    records = [
        {"composite": 50.0, "temp_count": len([p for p in hot.split("+") if p]),
         "temp_hot": hot, "row_type": row_type}
        for _, hot, row_type in rows
    ]
    df = pd.DataFrame(
        records, index=pd.DatetimeIndex([r[0] for r in rows], name="date")
    )
    return df.reindex(columns=history_columns())


def test_the_bubble_pair_representatives_are_the_ones_p4_froze():
    """Дефиницията е замразена в П4 §5 — не се преизбира по вкус.

    HPI е ЦЕНАТА НА АКТИВА (PERMITS е тръбата — друг въпрос), а двата заема са
    ЕДИН кредитен сигнал (peer-прецедентът на `lending`).
    """
    assert BUBBLE_PAIR_PROPERTY == "BG_HPI"
    assert set(BUBBLE_PAIR_CREDIT) == {"BG_LOANS_HH", "BG_LOANS_NFC"}
    # Представителите са ЧАСТ от бум-сериите — иначе двойката би четяла ключ,
    # който термометърът никога не пали.
    for key in (BUBBLE_PAIR_PROPERTY, *BUBBLE_PAIR_CREDIT):
        assert key in TEMP_SERIES, key
    assert "BG_PERMITS" not in (BUBBLE_PAIR_PROPERTY, *BUBBLE_PAIR_CREDIT)


def test_the_bubble_pair_needs_both_sides_burning():
    """Правилото върху стринга на решетката: имоти И поне един заем."""
    assert bubble_pair_from_hot("") is False
    assert bubble_pair_from_hot(None) is False
    assert bubble_pair_from_hot("BG_HPI") is False
    assert bubble_pair_from_hot("BG_LOANS_HH") is False
    assert bubble_pair_from_hot("BG_LOANS_HH+BG_LOANS_NFC") is False
    assert bubble_pair_from_hot("BG_WAGES+BG_PERMITS") is False

    assert bubble_pair_from_hot("BG_HPI+BG_LOANS_NFC") is True
    assert bubble_pair_from_hot("BG_LOANS_NFC+BG_HPI") is True      # обърнат ред
    assert bubble_pair_from_hot("BG_WAGES+BG_LOANS_HH+BG_HPI") is True


def test_the_bubble_pair_and_the_grid_column_agree_by_construction(cache_snapshot):
    """Двата пътя са ЕДНО правило — иначе лицето и решетката биха се разминали."""
    for at in (None, pd.Timestamp("2007-06-01"), pd.Timestamp("2017-06-01")):
        temp = temperature(SERIES_CATALOG, cache_snapshot, at=at)
        assert bubble_pair(temp)["active"] == bubble_pair_from_hot(hot_keys_str(temp))


def test_the_bubble_pair_names_which_side_burns():
    snap = _synthetic({"BG_LOANS_HH": 21.0, "BG_HPI": 14.8, "BG_WAGES": 11.5})
    pair = bubble_pair(temperature(SERIES_CATALOG, snap))

    assert pair["active"] is True
    assert pair["burning"] == ["BG_HPI", "BG_LOANS_HH"]     # имоти → кредит
    assert pair["label_bg"] == BUBBLE_PAIR_LABEL_BG
    assert pair["sentence"].startswith(f"{BUBBLE_PAIR_LABEL_BG}: АКТИВНА")
    for key in pair["burning"]:
        assert SERIES_CATALOG[key]["name_bg"] in pair["sentence"]
    # Заплатите горят, но не са от двойката — не влизат нито в едното, нито в
    # другото.
    assert "BG_WAGES" not in pair["burning"]


def test_one_burning_side_is_diagnostics_not_an_activation():
    """Само цените (без кредита) → неактивна, но горящата страна се вижда."""
    pair = bubble_pair(temperature(SERIES_CATALOG, _synthetic({"BG_HPI": 14.8})))
    assert pair["active"] is False
    assert pair["burning"] == ["BG_HPI"]
    assert pair["sentence"] == f"{BUBBLE_PAIR_LABEL_BG}: неактивна"


def test_an_empty_thermometer_leaves_the_pair_inactive():
    for temp in (None, {}, temperature(SERIES_CATALOG, {})):
        pair = bubble_pair(temp)
        assert pair["active"] is False
        assert pair["burning"] == []


def test_the_streak_counts_marks_from_the_end_including_the_live_row():
    grid = _grid([
        ("2024-03-01", "BG_HPI+BG_LOANS_HH", "quarter"),   # прекъснат по-рано
        ("2024-06-01", "BG_HPI", "quarter"),
        ("2024-09-01", "BG_HPI+BG_LOANS_NFC", "quarter"),
        ("2024-12-01", "BG_WAGES+BG_LOANS_HH+BG_HPI", "quarter"),
        ("2025-03-01", "BG_HPI+BG_LOANS_HH", "live"),
    ])
    streak = bubble_pair_streak(grid)
    assert streak == {"n": 3, "since": "2024-09-01"}


def test_the_streak_is_zero_when_today_is_inactive():
    """Прекъсната вчера серия НЕ е текуща — не се показва като такава."""
    grid = _grid([
        ("2024-09-01", "BG_HPI+BG_LOANS_HH", "quarter"),
        ("2024-12-01", "BG_HPI+BG_LOANS_HH", "quarter"),
        ("2025-03-01", "BG_WAGES", "live"),
    ])
    assert bubble_pair_streak(grid) == {"n": 0, "since": None}
    assert bubble_pair_streak(None) == {"n": 0, "since": None}
    assert bubble_pair_streak(pd.DataFrame()) == {"n": 0, "since": None}


def test_the_line_carries_the_sentence_untouched_plus_the_persistence():
    pair = {"active": True, "burning": ["BG_HPI"], "label_bg": BUBBLE_PAIR_LABEL_BG,
            "sentence": "изречението"}
    line = bubble_pair_line(pair, {"n": 11, "since": "2023-12-01"})
    assert line == "изречението, от 2023-12-01 (11 поредни марка)"
    # Неактивна двойка не носи опашка, а празният вход не ражда празен ред.
    off = {"active": False, "burning": [], "label_bg": BUBBLE_PAIR_LABEL_BG,
           "sentence": "неактивна"}
    assert bubble_pair_line(off, {"n": 0, "since": None}) == "неактивна"
    assert bubble_pair_line(pair, None) == "изречението"
    assert bubble_pair_line(None) == ""


def test_the_old_k3_label_stays_retired():
    """П4 присъдата: етикетът „≥2 двойки" НЕ се възкресява в никаква форма."""
    public = [name for name in dir(temperature_mod) if not name.startswith("_")]
    assert not [n for n in public if "k3" in n.lower()]
    assert "ТЕНЗИЯ" not in bubble_pair(None)["sentence"]
    assert "≥2" not in bubble_pair(None)["sentence"]
    # Провенансът КАЗВА, че старият етикет е пенсиониран — иначе следващият
    # читател би го помислил за пропуск.
    assert "ПЕНСИОНИРАН" in BUBBLE_PAIR_PROVENANCE
    assert "8/8" in BUBBLE_PAIR_PROVENANCE and "0/20" in BUBBLE_PAIR_PROVENANCE


def test_the_bubble_pair_acceptance_gate(history):
    """ГЕЙТЪТ-ЗВЕЗДА на мандат №53 — смятан от `temp_hot` на ЖИВАТА решетка.

    8/8 активни марка в бум-прозореца 2007-2008 · 0 от 20-те в спокойните
    2015-2019 · живият ред ДНЕС активен (жива котва 29.07.2026: цените на
    жилищата + кредитът за домакинствата). НЕ от снимка и НЕ от П4 CSV-тата —
    ако този тест падне, прероденият К3 вече не мери съ-прегряване.
    """
    q = _quarters(history)
    boom = q.loc["2007-01-01":"2008-12-31", "temp_hot"].map(bubble_pair_from_hot)
    calm = q.loc["2015-01-01":"2019-12-31", "temp_hot"].map(bubble_pair_from_hot)

    assert len(boom) == 8
    assert int(boom.sum()) == 8, "бумът трябва да гори ЦЯЛ, не да мигне"
    assert len(calm) == 20
    assert int(calm.sum()) == 0, "спокойната епоха трябва да МЪЛЧИ"

    live = history[history["row_type"] == "live"].iloc[-1]
    assert bubble_pair_from_hot(live["temp_hot"]) is True


def test_the_live_pair_is_active_and_persistent(cache_snapshot, history):
    """Живата котва: двойката гори, а персистенцията се брои в МАРКОВЕ."""
    pair = bubble_pair(temperature(SERIES_CATALOG, cache_snapshot))
    assert pair["active"] is True
    assert pair["burning"] == ["BG_HPI", "BG_LOANS_HH"]

    streak = bubble_pair_streak(history)
    assert streak["n"] >= 1
    assert bubble_pair_from_hot(history.loc[pd.Timestamp(streak["since"]), "temp_hot"])
    # Марк ПРЕДИ началото на серията (ако има такъв) трябва да е неактивен —
    # иначе `since` не е първият от поредицата.
    earlier = history.loc[history.index < pd.Timestamp(streak["since"]), "temp_hot"]
    if len(earlier):
        assert bubble_pair_from_hot(earlier.iloc[-1]) is False


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
