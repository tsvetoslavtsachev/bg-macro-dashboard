"""
tests/test_primitives.py
========================
Математиката под трансформациите.
"""
import pandas as pd
import pytest

from core.primitives import apply_transform, compute_roll4q_mean, compute_yoy_pct


def _quarterly(values):
    idx = pd.date_range("2020-01-01", periods=len(values), freq="QS")
    return pd.Series([float(v) for v in values], index=idx)


def test_roll4q_mean_is_four_period_rolling_average():
    s = _quarterly([1, 2, 3, 4, 5, 6])
    r = compute_roll4q_mean(s)

    # Първите три точки нямат пълен прозорец
    assert r.iloc[:3].isna().all()
    assert r.iloc[3] == pytest.approx(2.5)   # (1+2+3+4)/4
    assert r.iloc[4] == pytest.approx(3.5)   # (2+3+4+5)/4
    assert r.iloc[5] == pytest.approx(4.5)   # (3+4+5+6)/4


def test_roll4q_mean_reachable_through_apply_transform():
    s = _quarterly([-1.8, -3.98, -5.45, -6.55])
    direct = compute_roll4q_mean(s)
    through = apply_transform(s, "roll4q_mean")
    pd.testing.assert_series_equal(direct, through)


def test_roll4q_mean_smooths_single_quarter_spike():
    """Едно лошо тримесечие не бива да води целия прочит."""
    s = _quarterly([-2.0, -2.0, -2.0, -10.0])
    assert apply_transform(s, "roll4q_mean").iloc[-1] == pytest.approx(-4.0)


def test_yoy_pct_on_quarterly_index_uses_four_periods():
    # Четири тримесечия на 100, после четири на 110 → +10% г/г от 5-тата точка
    s = _quarterly([100, 100, 100, 100, 110, 110, 110, 110])
    yoy = compute_yoy_pct(s)

    assert yoy.iloc[:4].isna().all()
    assert yoy.iloc[4] == pytest.approx(10.0)
    assert yoy.iloc[7] == pytest.approx(10.0)


def test_yoy_pct_on_monthly_index_uses_twelve_periods():
    idx = pd.date_range("2020-01-01", periods=14, freq="MS")
    s = pd.Series([100.0] * 12 + [105.0, 105.0], index=idx)
    yoy = compute_yoy_pct(s)

    assert yoy.iloc[:12].isna().all()
    assert yoy.iloc[12] == pytest.approx(5.0)
