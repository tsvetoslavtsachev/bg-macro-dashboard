"""
tests/test_display.py
=====================
Дисплеят трябва да показва СЪЩОТО число, което скорингът смята —
т.е. серията след каталожната трансформация, не суровото ниво.
Регресията, която пази: заплатите излизаха като 14 181 „млн. евро"
с етикет „Растеж, г/г".
"""
import pandas as pd
import pytest

from export.weekly_briefing import _compute_as_of, _display_series, _prep_chart_data
from catalog.series import SERIES_CATALOG


def _recent_quarterly(values):
    """Тримесечна серия, завършваща близо до днес (вътре в 12-годишния прозорец)."""
    end_q = pd.Timestamp.now().to_period("Q").start_time
    idx = pd.date_range(end=end_q, periods=len(values), freq="QS")
    return pd.Series([float(v) for v in values], index=idx)


def test_chart_data_shows_transformed_values_not_levels():
    # WAGES-подобна серия: нива в млн. евро, растящи с точно 10% годишно
    levels = [10000, 10000, 10000, 10000, 11000, 11000, 11000, 11000, 12100, 12100, 12100, 12100]
    snapshot = {"BG_WAGES": _recent_quarterly(levels)}

    chart_data = _prep_chart_data(snapshot)
    values = chart_data["BG_WAGES"]["values"]

    # Каталогът казва yoy_pct → на графиката трябва да има проценти, не нива
    assert SERIES_CATALOG["BG_WAGES"]["transform"] == "yoy_pct"
    assert all(v == pytest.approx(10.0) for v in values)
    assert max(values) < 100  # нивата биха били хиляди


def test_display_series_applies_catalog_transform():
    snapshot = {"BG_WAGES": _recent_quarterly([100, 100, 100, 100, 112, 112, 112, 112])}
    s = _display_series(snapshot, "BG_WAGES", SERIES_CATALOG["BG_WAGES"])

    assert not s.empty
    assert s.iloc[-1] == pytest.approx(12.0)


def test_rolling_current_account_keeps_raw_quarter_as_second_trace():
    raw = [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0, -8.8]
    snapshot = {"BG_CA_GDP": _recent_quarterly(raw)}

    entry = _prep_chart_data(snapshot)["BG_CA_GDP"]

    assert "values_raw" in entry
    assert len(entry["values_raw"]) == len(entry["values"])
    # Плъзгащата е по-мека от последното тримесечие
    assert entry["values"][-1] == pytest.approx(-6.7)  # (-5-6-7-8.8)/4
    assert entry["values_raw"][-1] == pytest.approx(-8.8)


def test_as_of_is_latest_observation_not_generation_time():
    snapshot = {
        "BG_HICP": pd.Series([5.2], index=pd.to_datetime(["2026-06-01"])),
        "BG_UNRATE": pd.Series([2.9], index=pd.to_datetime(["2026-05-01"])),
    }
    assert _compute_as_of(snapshot) == "2026-06"


def test_as_of_is_none_without_data():
    assert _compute_as_of({}) is None
