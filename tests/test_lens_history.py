"""
tests/test_lens_history.py
==========================
Реконструираната лещова история + живият журнал (мандат №45, П0+П1).

Гейтът на цялата писта е ЕДИН: последният ред на решетката трябва да е
ТЪЖДЕСТВЕН на живото изчисление. Ако този тест падне, „историята" мери друг
уред от `--status` и всичко построено върху нея (праговете на П2, тензионната
сесия) стъпва на пясък.

Всичко работи върху КОМИТНАТИЯ кеш — `get_snapshot` чете само от `data/*.json`
и никога не пипа мрежата.
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from analysis import lens_history
from analysis.lens_history import (
    GRID_START,
    HONESTY_LABEL,
    ROW_LIVE,
    ROW_QUARTER,
    append_journal,
    build_grid,
    build_history,
    composition_tag,
    history_columns,
    history_stats,
    journal_columns,
    last_observation,
    load_journal,
    wow_delta,
    write_history,
    yearly_table,
)
from catalog.series import SERIES_CATALOG, series_by_source
from config import MODULE_WEIGHTS
from core.scorer import compute_composite_score, compute_lens_reports, score_series
from sources import build_adapters
from sources.manual_seed import splice_loans


# ═════════════════════════════════════════════════════════════════════════════
# ФИКСТУРИ
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def cache_snapshot():
    """Snapshot от КОМИТНАТИЯ кеш — без нито една мрежова заявка.

    `get_snapshot` чете само `data/*.json`; `splice_loans` е същата стъпка като
    в `run.py::_score_everything`, за да е сравнението с живото честно.
    """
    snapshot = {}
    for source_name, adapter in build_adapters().items():
        keys = [spec["_key"] for spec in series_by_source(source_name)]
        snapshot.update(adapter.get_snapshot(keys))
    if len(snapshot) < len(SERIES_CATALOG):
        pytest.skip("кешът в data/ е непълен — тестът иска комитнатия кеш")
    return splice_loans(snapshot)


@pytest.fixture(scope="module")
def live_history(cache_snapshot):
    return build_history(SERIES_CATALOG, cache_snapshot)


def _synthetic_snapshot(n: int = 300, end: str = "2026-06-01", seed: int = 7) -> dict:
    """Детерминистичен синтетичен snapshot — плавна серия без нулева база."""
    idx = pd.date_range(end=end, periods=n, freq="MS")
    rng = np.random.RandomState(seed)
    return {
        key: pd.Series(100.0 + np.cumsum(rng.normal(0, 0.8, n)), index=idx)
        for key in SERIES_CATALOG
    }


# ═════════════════════════════════════════════════════════════════════════════
# П0 — външният сектор в ЕДНА peer група
# ═════════════════════════════════════════════════════════════════════════════

def test_external_lens_z_is_the_mean_of_its_two_series_z(cache_snapshot):
    """Числовата еквивалентност: лещовият z = средното на двата серийни z-а.

    При ЕДНА peer-група лещата е средното на сериите в нея — точно това, което
    П0 иска да получи (един външен сигнал, не два).
    """
    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    rep = reports["external"]

    zs = [s["health_z"] for s in rep["series"] if s["health_z"] is not None]
    assert len(zs) == 2, "външната леща стои на две серии"
    assert rep["health_z"] == pytest.approx(round(float(np.mean(zs)), 3), abs=1e-9)

    groups = rep["peer_groups"]
    assert len(groups) == 1
    assert groups[0]["name"] == "external_balance"
    assert groups[0]["n_available"] == 2


def test_merging_two_peer_groups_into_one_leaves_the_lens_z_unchanged():
    """КОТВАТА на П0 като числов тест, не като ръчна снимка.

    При peer-тегла 1.0 средното на две групи по 1 серия ≡ една група от 2
    серии. Затова сливането НЕ е риск за композита — то е чиста семантика.
    """
    idx = pd.date_range(end="2026-06-01", periods=200, freq="MS")
    rng = np.random.RandomState(3)
    snap = {
        "A": pd.Series(100.0 + np.cumsum(rng.normal(0, 0.7, 200)), index=idx),
        "B": pd.Series(100.0 + np.cumsum(rng.normal(0, 0.7, 200)), index=idx),
    }
    spec = {"lens": ["external"], "transform": "level", "name_bg": "x", "id": "x"}
    split = {
        "A": {**spec, "peer_group": "current_account"},
        "B": {**spec, "peer_group": "trade"},
    }
    merged = {
        "A": {**spec, "peer_group": "external_balance"},
        "B": {**spec, "peer_group": "external_balance"},
    }

    z_split = compute_lens_reports(split, snap)["external"]["health_z"]
    z_merged = compute_lens_reports(merged, snap)["external"]["health_z"]
    assert z_split == z_merged


# ═════════════════════════════════════════════════════════════════════════════
# ГЕЙТЪТ — последният ред срещу живото изчисление
# ═════════════════════════════════════════════════════════════════════════════

def test_last_row_equals_the_live_computation_bit_for_bit(cache_snapshot, live_history):
    """Рязането при `t_live` е no-op → редът е ТЪЖДЕСТВЕН на живото.

    ТОЧНО равенство, не approx: историята минава през същия скорер, затова
    всяко разминаване значи, че двигателят е раздвоен.
    """
    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    composite = compute_composite_score(
        {lens: rep["score"] for lens, rep in reports.items()}
    )
    last = live_history.iloc[-1]

    assert last["composite"] == composite
    for lens in MODULE_WEIGHTS:
        assert last[f"score_{lens}"] == reports[lens]["score"], lens
        assert last[f"z_{lens}"] == reports[lens]["health_z"], lens


def test_the_live_row_sits_on_the_last_observation(cache_snapshot, live_history):
    t_live = last_observation(cache_snapshot)
    assert live_history.index[-1] == t_live
    assert live_history["row_type"].iloc[-1] == ROW_LIVE
    assert (live_history["row_type"] == ROW_LIVE).sum() == 1


# ═════════════════════════════════════════════════════════════════════════════
# РЕШЕТКАТА
# ═════════════════════════════════════════════════════════════════════════════

def test_grid_starts_at_the_credit_seed_birth(live_history):
    """2005Q4 — по-рано кредитната леща пада до 1 серия и уредът става друг."""
    assert GRID_START == "2005-12-01"
    assert live_history.index[0] == pd.Timestamp("2005-12-01")


def test_quarter_marks_are_day_one_of_the_quarter_end_months(live_history):
    """Ден 1 на месеците 3/6/9/12 — марк, който хваща завършеното тримесечие
    и в двете датови конвенции на репото."""
    q = live_history[live_history["row_type"] == ROW_QUARTER]
    assert len(q) > 0
    assert set(q.index.month) <= {3, 6, 9, 12}
    assert set(q.index.day) == {1}


def test_grid_is_strictly_ascending(live_history):
    assert live_history.index.is_monotonic_increasing
    assert live_history.index.is_unique


def test_history_carries_the_mandated_columns(live_history):
    assert list(live_history.columns) == history_columns()
    assert live_history.index.name == "date"
    for lens in MODULE_WEIGHTS:
        assert f"z_{lens}" in live_history.columns
        assert f"score_{lens}" in live_history.columns


def test_every_row_declares_how_much_instrument_stands_behind_it(live_history):
    """`n_series`/`n_lenses` пътуват във всеки ред — ранните точки стъпват на
    по-малко серии и това не бива да се губи."""
    assert (live_history["n_lenses"] >= 1).all()
    assert (live_history["n_series"] >= 1).all()
    assert live_history["n_series"].iloc[0] <= live_history["n_series"].iloc[-1]


# ═════════════════════════════════════════════════════════════════════════════
# НЕ-ИЗТИЧАНЕ
# ═════════════════════════════════════════════════════════════════════════════

def test_the_cut_does_not_leak_future_values():
    """Стойностите СЛЕД марка се сменят → редът на марка остава идентичен.

    Ако рязането течеше напред, реконструкцията щеше да е безсмислена: всяка
    историческа точка щеше да знае бъдещето си.
    """
    snap = _synthetic_snapshot()
    grid_start = "2020-12-01"
    base = build_history(SERIES_CATALOG, snap, grid_start=grid_start)

    cutoff = pd.Timestamp("2023-03-01")
    tampered = {
        k: pd.Series(
            np.where(s.index > cutoff, s.values * 3.0 + 500.0, s.values),
            index=s.index,
        )
        for k, s in snap.items()
    }
    after = build_history(SERIES_CATALOG, tampered, grid_start=grid_start)

    past = base.index[base.index <= cutoff]
    assert len(past) >= 4, "тестът иска няколко минали марка"
    assert_frame_equal(base.loc[past], after.loc[past])


def test_building_does_not_mutate_the_snapshot():
    snap = _synthetic_snapshot()
    lengths = {k: len(s) for k, s in snap.items()}
    build_history(SERIES_CATALOG, snap, grid_start="2024-12-01")
    assert {k: len(s) for k, s in snap.items()} == lengths


# ═════════════════════════════════════════════════════════════════════════════
# ИДЕМПОТЕНТНОСТ
# ═════════════════════════════════════════════════════════════════════════════

def test_two_builds_from_the_same_snapshot_are_equal(cache_snapshot, live_history):
    assert_frame_equal(build_history(SERIES_CATALOG, cache_snapshot), live_history)


def test_two_writes_produce_byte_identical_files(live_history, tmp_path):
    """Иначе всеки пуск ражда diff и `git add -A` шуми без промяна по същество."""
    a, b = tmp_path / "a.parquet", tmp_path / "b.parquet"
    write_history(live_history, a)
    write_history(live_history, b)
    assert a.read_bytes() == b.read_bytes()


def test_written_history_round_trips(live_history, tmp_path):
    path = tmp_path / "h.parquet"
    write_history(live_history, path)
    assert_frame_equal(lens_history.load_history(path), live_history)


# ═════════════════════════════════════════════════════════════════════════════
# ЖИВИЯТ ЖУРНАЛ
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def reports_and_composite(cache_snapshot):
    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    composite = compute_composite_score(
        {lens: rep["score"] for lens, rep in reports.items()}
    )
    return reports, composite


def test_journal_is_born_with_the_mandated_columns(reports_and_composite, tmp_path):
    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    journal = append_journal(reports, composite, today=date(2026, 7, 28), path=path)
    assert list(journal.columns) == journal_columns()
    assert len(journal) == 1
    assert journal["date"].iloc[0] == "2026-07-28"
    assert journal["composite"].iloc[0] == composite


def test_journal_appends_one_row_per_new_date(reports_and_composite, tmp_path):
    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    append_journal(reports, composite, today=date(2026, 7, 28), path=path)
    append_journal(reports, composite, today=date(2026, 8, 4), path=path)
    assert len(load_journal(path)) == 2


def test_journal_replaces_the_row_for_the_same_date(reports_and_composite, tmp_path):
    """Повторен пуск в същия ден ЗАМЕНЯ реда — иначе WoW делтата сравнява днес
    с днес и показва нула при всяко повторение."""
    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    append_journal(reports, composite, today=date(2026, 7, 28), path=path)

    bumped = {lens: dict(rep) for lens, rep in reports.items()}
    bumped["growth"]["score"] = 99.9
    append_journal(bumped, 61.5, today=date(2026, 7, 28), path=path)

    journal = load_journal(path)
    assert len(journal) == 1
    assert journal["composite"].iloc[0] == 61.5
    assert journal["score_growth"].iloc[0] == 99.9


def test_journal_is_byte_identical_on_a_double_run(reports_and_composite, tmp_path):
    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    append_journal(reports, composite, today=date(2026, 7, 28), path=path)
    first = path.read_bytes()
    append_journal(reports, composite, today=date(2026, 7, 28), path=path)
    assert path.read_bytes() == first


def test_wow_delta_is_none_with_fewer_than_two_records(reports_and_composite, tmp_path):
    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    assert wow_delta(load_journal(path)) is None
    append_journal(reports, composite, today=date(2026, 7, 28), path=path)
    assert wow_delta(load_journal(path)) is None


def test_wow_delta_reports_composite_and_lens_deltas(reports_and_composite, tmp_path):
    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    append_journal(reports, composite, today=date(2026, 7, 28), path=path)

    moved = {lens: dict(rep) for lens, rep in reports.items()}
    moved["growth"]["score"] = (reports["growth"]["score"] or 0) + 4.0
    append_journal(moved, (composite or 0) + 1.5, today=date(2026, 8, 4), path=path)

    wow = wow_delta(load_journal(path))
    assert wow is not None
    assert wow["prev_date"] == "2026-07-28"
    assert wow["composite_delta"] == pytest.approx(1.5)
    assert wow["lens_deltas"]["growth"] == pytest.approx(4.0)
    assert wow["lens_deltas"]["labor"] == pytest.approx(0.0)
    assert wow["composition_changed"] is False


def test_wow_delta_flags_a_composition_change(reports_and_composite, tmp_path, monkeypatch):
    """Смяна на теглата между два записа → делтата се обявява за нечиста."""
    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    append_journal(reports, composite, today=date(2026, 7, 28), path=path)

    other = dict(MODULE_WEIGHTS)
    other["growth"] = 0.30
    monkeypatch.setattr(lens_history, "MODULE_WEIGHTS", other)
    append_journal(reports, composite, today=date(2026, 8, 4), path=path)

    wow = wow_delta(load_journal(path))
    assert wow["composition_changed"] is True


def test_composition_tag_changes_when_the_weights_change(monkeypatch):
    before = composition_tag()
    other = dict(MODULE_WEIGHTS)
    other["growth"] = 0.30
    monkeypatch.setattr(lens_history, "MODULE_WEIGHTS", other)
    assert composition_tag() != before


def test_composition_tag_changes_when_a_peer_group_changes():
    """П2 ще смени състава — тагът трябва да го хване САМ, без някой да помни."""
    tweaked = {k: dict(v) for k, v in SERIES_CATALOG.items()}
    tweaked["BG_TRADE_GS"]["peer_group"] = "trade"
    assert composition_tag(tweaked) != composition_tag()


def test_composition_tag_declares_the_shape(reports_and_composite):
    tag = composition_tag()
    assert tag.startswith(f"{len(SERIES_CATALOG)}s{len(MODULE_WEIGHTS)}l-")


# ═════════════════════════════════════════════════════════════════════════════
# ЧЕТЕНЕТО НА РЕШЕТКАТА
# ═════════════════════════════════════════════════════════════════════════════

def test_history_stats_reads_the_quarters_not_the_live_point(live_history):
    stats = history_stats(live_history)
    q = live_history[live_history["row_type"] == ROW_QUARTER]
    assert stats["n_quarters"] == len(q.dropna(subset=["composite"]))
    assert stats["current"] == live_history["composite"].iloc[-1]
    assert 0.0 <= stats["percentile"] <= 100.0


def test_yearly_table_covers_the_whole_grid(live_history):
    rows = yearly_table(live_history)
    years = [r["year"] for r in rows]
    assert years == sorted(years)
    assert years[0] == 2005
    assert sum(r["n"] for r in rows) == history_stats(live_history)["n_quarters"]


def test_the_honesty_label_refuses_the_pit_claim():
    """Етикетът е ЕДИН източник и НЕ твърди point-in-time.

    Лицето и briefing_context цитират ТОЗИ стринг, затова семантиката се пази
    тук, а не по местата, където се показва.
    """
    assert "Реконструирана история" in HONESTY_LABEL
    assert "не point-in-time" in HONESTY_LABEL
    assert "2005Q4" in HONESTY_LABEL


def test_the_engine_declares_its_semantics_in_the_docstrings():
    """Мандатът иска семантиката ДЕКЛАРИРАНА при кода, не само в receipt-а."""
    assert "НЕ е point-in-time" in lens_history.__doc__
    assert "ревизирани" in lens_history.__doc__
    doc = lens_history.build_history.__doc__
    assert "не point-in-time" in doc
    assert "n_lenses" in doc


def test_empty_snapshot_yields_an_empty_grid():
    assert build_grid({}) == []
    assert build_history(SERIES_CATALOG, {}).empty


# ═════════════════════════════════════════════════════════════════════════════
# СКОРЕРЪТ СЕ ДЪРЖИ НА КЪСА СЕРИЯ (предпоставка на ранните маркове)
# ═════════════════════════════════════════════════════════════════════════════

def test_scoring_a_one_point_series_with_yoy_does_not_explode():
    """На 2005-12-01 кредитният seed има ТОЧНО една точка.

    `pd.infer_freq` хвърля при < 3 дати; без guard-а в `compute_yoy_pct`
    билдът на историята гърми на първия си марк.
    """
    s = pd.Series([100.0], index=pd.DatetimeIndex(["2005-12-01"]))
    res = score_series(s, transform="yoy_pct", polarity=+1, name="X")
    assert res["score"] is not None
