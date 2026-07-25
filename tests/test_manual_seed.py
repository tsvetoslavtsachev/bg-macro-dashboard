"""
tests/test_manual_seed.py
=========================
Дългата кредитна памет (мандат №41): екстракторът върху комитнатата суровина +
тримесечният сплайс.

Двата гейта, които държат уреда честен:
  1. Екстракторът намира редовете ПО ЕТИКЕТ и сверява мерната единица — при
     разместен лист гърми, вместо да произведе разместени числа.
  2. Шевът се валидира на ВСИЧКИ общи тримесечия. Разминаване > 0.5% е грешка,
     не бележка под линия.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.extract_bnb_seed import (
    DEFAULT_RAW,
    ROW_LABELS,
    build_csv_text,
    extract_seed,
    extract_series,
    find_label_row,
    load_sheet,
)
from sources.manual_seed import (
    SEAM_TOLERANCE,
    SEED_CSV,
    load_seed,
    splice_loans,
    splice_series,
    to_quarterly,
    validate_seam,
)


# ═════════════════════════════════════════════════════════════════════════════
# ЕКСТРАКТОРЪТ върху комитнатата суровина (§А4)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def sheet():
    assert Path(DEFAULT_RAW).exists(), "суровината трябва да е комитната в репото"
    return load_sheet(Path(DEFAULT_RAW))


@pytest.fixture(scope="module")
def seed_raw():
    return extract_seed(Path(DEFAULT_RAW))


def test_extractor_finds_both_label_rows(sheet):
    """Редовете се намират по ЕТИКЕТ, не по фиксиран индекс."""
    for label in ROW_LABELS.values():
        assert find_label_row(sheet, label) > 0


def test_extractor_covers_at_least_eighty_quarters(seed_raw):
    for key, points in seed_raw.items():
        assert len(points) >= 80, key


def test_extractor_reaches_the_current_quarter(seed_raw):
    for key, points in seed_raw.items():
        assert max(points) >= date(2026, 3, 1), key


def test_extractor_starts_at_the_fourth_quarter_of_2005(seed_raw):
    for key, points in seed_raw.items():
        assert min(points) == date(2005, 12, 1), key


def test_the_2005q4_anchor_matches_the_raw_file(seed_raw):
    """Котвата от скаут-фактите: 5 676 072 хил. EUR → 5676.072 млн."""
    assert seed_raw["NFC"][date(2005, 12, 1)] == pytest.approx(5676.072)


def test_every_quarter_falls_on_a_quarter_end_month(seed_raw):
    for key, points in seed_raw.items():
        assert {d.month for d in points} <= {3, 6, 9, 12}, key


def test_a_wrong_unit_row_blows_up_instead_of_being_swallowed(sheet, monkeypatch):
    """Мерната единица е тихият убиец — разминаване = ValueError."""
    label = ROW_LABELS["NFC"]
    row = find_label_row(sheet, label)
    original = sheet.cell(row=row + 1, column=2).value
    sheet.cell(row=row + 1, column=2).value = "хил. лева"
    try:
        with pytest.raises(ValueError, match="хил. евро"):
            extract_series(sheet, label)
    finally:
        sheet.cell(row=row + 1, column=2).value = original


def test_a_missing_label_blows_up(sheet):
    with pytest.raises(ValueError, match="намерен 0 пъти"):
        find_label_row(sheet, "Няма такъв ред")


def test_csv_header_names_the_source_and_the_definitions(seed_raw):
    text = build_csv_text(seed_raw, Path(DEFAULT_RAW), extracted_on=date(2026, 7, 26))
    head = text.split("date,series,value_meur")[0]
    for token in ("Кредитна динамика", "cred_q_dyn_type_eur_bg_2026-07-25.xlsx",
                  "25.07.2026", "2026-07-26", "2240", "2250", "млн. EUR"):
        assert token in head, token


def test_the_committed_csv_matches_a_fresh_extraction(seed_raw):
    """Комитнатият CSV не е откъснат от суровината — числата съвпадат."""
    from_csv = load_seed(SEED_CSV)
    for seed_key, catalog_key in (("NFC", "BG_LOANS_NFC"), ("HH", "BG_LOANS_HH")):
        s = from_csv[catalog_key]
        assert len(s) == len(seed_raw[seed_key]), catalog_key
        for when, value in seed_raw[seed_key].items():
            assert s.loc[pd.Timestamp(when)] == pytest.approx(value, abs=0.001)


# ═════════════════════════════════════════════════════════════════════════════
# ТРИМЕСЕЧНИЯТ СПЛАЙС
# ═════════════════════════════════════════════════════════════════════════════

def _monthly(start, values):
    idx = pd.date_range(start=start, periods=len(values), freq="MS")
    return pd.Series([float(v) for v in values], index=idx)


def _quarterly(start, values):
    idx = pd.date_range(start=start, periods=len(values), freq="QS-DEC")
    return pd.Series([float(v) for v in values], index=idx)


def test_monthly_api_series_collapses_to_quarter_end_observations():
    s = _monthly("2022-01-01", range(1, 13))     # 2022-01 … 2022-12
    q = to_quarterly(s)

    assert list(q.index.month) == [3, 6, 9, 12]
    assert list(q.values) == [3.0, 6.0, 9.0, 12.0]


def test_a_partial_quarter_never_enters_the_series():
    """API-то стига до 05.2026 → второто тримесечие на 2026 НЕ съществува."""
    s = _monthly("2026-01-01", [1, 2, 3, 4, 5])  # 01…05.2026
    q = to_quarterly(s)

    assert list(q.index) == [pd.Timestamp("2026-03-01")]
    assert pd.Timestamp("2026-06-01") not in q.index


def test_seed_covers_everything_before_the_first_api_quarter():
    seed = _quarterly("2020-12-01", [100, 110, 120, 130, 140, 150])   # 2020Q4…2022Q1
    api = _monthly("2022-01-01", [138, 139, 150, 151, 152, 160])      # 01…06.2022

    out = splice_series("BG_LOANS_NFC", seed, api)

    assert out.loc["2020-12-01"] == 100.0          # само от seed-а
    assert out.loc["2021-09-01"] == 130.0
    assert out.loc["2022-03-01"] == 150.0          # шевът — двата съвпадат
    assert out.loc["2022-06-01"] == 160.0          # само от API-то
    assert out.index.is_monotonic_increasing
    assert not out.index.has_duplicates


def test_after_the_seam_the_api_value_wins():
    """Seed редове след първото API тримесечие не се смесват — API-то води."""
    seed = _quarterly("2021-12-01", [100, 200, 300])        # 2021Q4, 2022Q1, 2022Q2
    api = _monthly("2022-01-01", [0, 0, 200.5, 0, 0, 301])  # в допустимите 0.5%

    out = splice_series("BG_LOANS_HH", seed, api)

    assert out.loc["2021-12-01"] == 100.0        # seed
    assert out.loc["2022-03-01"] == 200.5        # API-то, не seed-ът
    assert out.loc["2022-06-01"] == 301.0
    assert len(out) == 3


def test_a_seam_mismatch_above_half_a_percent_raises():
    """Фабрикувано разминаване → ValueError, не warning."""
    seed = _quarterly("2021-12-01", [100, 200])
    api = _monthly("2022-01-01", [0, 0, 210])              # 5% разлика

    with pytest.raises(ValueError, match="шевът се разпада"):
        splice_series("BG_LOANS_NFC", seed, api)


def test_a_mismatch_just_under_the_threshold_passes():
    seed = _quarterly("2021-12-01", [100, 200.8])          # 0.4% над API-то
    api = _monthly("2022-01-01", [0, 0, 200.0])

    out = splice_series("BG_LOANS_NFC", seed, api)
    assert out.loc["2022-03-01"] == 200.0


def test_the_seam_is_checked_on_every_common_quarter_not_just_the_first():
    """Разминаване в ТРЕТОТО общо тримесечие също гърми."""
    seed = _quarterly("2021-12-01", [100, 200, 300, 500])
    api = _monthly("2022-01-01", [0, 0, 200, 0, 0, 300, 0, 0, 400])

    with pytest.raises(ValueError, match="2022-09-01"):
        splice_series("BG_LOANS_NFC", seed, api)


def test_no_overlap_at_all_is_an_error_not_a_silent_splice():
    seed = _quarterly("2005-12-01", [100, 110])
    api = _monthly("2022-01-01", [0, 0, 500])

    with pytest.raises(ValueError, match="нито едно общо тримесечие"):
        splice_series("BG_LOANS_NFC", seed, api)


def test_validate_seam_returns_every_common_quarter():
    seed = _quarterly("2021-12-01", [100, 200, 300])
    api = to_quarterly(_monthly("2022-01-01", [0, 0, 200, 0, 0, 300]))

    common = validate_seam("BG_LOANS_NFC", seed, api)
    assert common == [pd.Timestamp("2022-03-01"), pd.Timestamp("2022-06-01")]


def test_a_missing_api_series_falls_back_to_the_seed_alone():
    """ЕЦБ пада → лещата тръгва на seed-а, не изчезва."""
    seed = _quarterly("2021-12-01", [100, 200])
    out = splice_series("BG_LOANS_NFC", seed, None)

    assert list(out.values) == [100.0, 200.0]


def test_splice_loans_replaces_both_keys_in_the_snapshot():
    seed = {
        "BG_LOANS_NFC": _quarterly("2021-12-01", [100, 200]),
        "BG_LOANS_HH": _quarterly("2021-12-01", [50, 60]),
    }
    snapshot = {
        "BG_LOANS_NFC": _monthly("2022-01-01", [0, 0, 200]),
        "BG_LOANS_HH": _monthly("2022-01-01", [0, 0, 60]),
        "BG_HICP": _monthly("2022-01-01", [1, 2, 3]),
    }
    out = splice_loans(snapshot, seed=seed)

    assert list(out["BG_LOANS_NFC"].index.month) == [12, 3]
    assert list(out["BG_LOANS_HH"].values) == [50.0, 60.0]
    assert len(out["BG_HICP"]) == 3          # другите серии не се пипат


def test_the_tolerance_is_half_a_percent():
    assert SEAM_TOLERANCE == pytest.approx(0.005)


# ═════════════════════════════════════════════════════════════════════════════
# ЖИВИЯТ ШЕВ (комитнат seed срещу комитнат ЕЦБ кеш)
# ═════════════════════════════════════════════════════════════════════════════

def _cached_api_snapshot() -> dict:
    """Комитнатият ЕЦБ кеш → snapshot, както го вижда пайплайнът."""
    import json

    from config import DATA_DIR

    cache = json.loads((DATA_DIR / "ecb_cache.json").read_text(encoding="utf-8"))
    return {
        key: pd.Series(
            {pd.Timestamp(d): float(v) for d, v in entry["data"].items()}
        ).sort_index()
        for key, entry in cache.items()
    }


def test_the_real_seam_holds_on_every_common_quarter():
    """Двата източника са един и същ поток — БНБ репортва BSI-то."""
    api_snapshot = _cached_api_snapshot()
    seed = load_seed()

    for key, s in seed.items():
        common = validate_seam(key, s, to_quarterly(api_snapshot[key]))
        assert len(common) >= 16, key


def test_the_loan_series_no_longer_carry_a_thin_window_flag():
    """§А3: честността се обръща. Прозорецът е пълен → флагът пада сам."""
    from catalog.polarity import polarity_for
    from catalog.series import SERIES_CATALOG
    from core.scorer import score_series

    snapshot = splice_loans(_cached_api_snapshot())

    for key in ("BG_LOANS_NFC", "BG_LOANS_HH"):
        res = score_series(
            snapshot[key],
            SERIES_CATALOG[key]["transform"],
            polarity_for(key, "credit"),
            name=key,
        )
        assert res["thin_window"] is False, key
        assert res["percentile_window"] == "10г", key
        assert "къс прозорец" not in res["percentile_window"], key
        assert res["history_n"] >= 36, key
        assert res["last_date"] >= "2026-03-01", key


def test_the_spliced_series_is_quarterly_and_reaches_2005():
    seed = load_seed()
    for key, s in seed.items():
        assert s.index[0] == pd.Timestamp("2005-12-01"), key
        assert pd.infer_freq(s.index) == "QS-DEC", key


def test_quarterly_yoy_uses_four_periods_not_twelve():
    """Тримесечен индекс → pct_change(4). Иначе г/г щеше да е г/3г."""
    from core.primitives import apply_transform

    s = _quarterly("2020-12-01", [100, 100, 100, 100, 110, 110, 110, 110])
    y = apply_transform(s, "yoy_pct").dropna()

    assert len(y) == 4
    assert y.iloc[0] == pytest.approx(10.0)
    assert y.index[0] == pd.Timestamp("2021-12-01")
