"""
tests/test_scorer.py
====================
Робастният скоринг двигател (мандат №38 §А1) — портнат от фамилията.

Пази трите неща, заради които percentile-of-full-history падна:
дрейфът (близка норма, не 2000г), MAD=0 капанът (фалшиво „неутрално 50"
върху реален екстремум) и полярността (U-форма за инфлацията).
"""
import math

import pandas as pd
import pytest

from core.primitives import robust_stats_latest
from core.scorer import TANH_SLOPE, percentile_rank, score_series


def _monthly(values):
    """Месечна серия, завършваща на 2026-06-01 (изцяло след HISTORY_START)."""
    idx = pd.date_range(end="2026-06-01", periods=len(values), freq="MS")
    return pd.Series([float(v) for v in values], index=idx)


# ── Норма и скала ────────────────────────────────────────────────────────────

def test_score_is_fifty_at_the_local_norm():
    """Стойност на медианата на 10-годишния прозорец → точно 50."""
    s = _monthly([1.0, 3.0] * 60 + [2.0])
    res = score_series(s, "level", +1)

    assert res["health_z"] == pytest.approx(0.0)
    assert res["score"] == pytest.approx(50.0)
    assert res["degenerate"] is False


def test_score_is_tanh_of_the_robust_z():
    """score = 50·(1 + tanh(z/2)) върху (x − median₁₀)/(1.4826·MAD₁₀)."""
    s = _monthly([1.0, 3.0] * 60 + [7.0])
    res = score_series(s, "level", +1)

    val, med, scale = robust_stats_latest(s)
    expected = 50.0 * (1.0 + math.tanh(((val - med) / scale) / TANH_SLOPE))

    assert res["score"] == pytest.approx(round(expected, 1))
    assert res["score"] > 50.0


def test_ten_year_window_ignores_the_old_regime():
    """Дефектът, който гасим: серията се съди спрямо близката си норма, не спрямо 2000г."""
    old_era = [10.0] * 180                      # 15 г. „висока" ера
    recent = [1.0, 3.0] * 60 + [2.0]            # последните 10 г. около 2
    s = _monthly(old_era + recent)

    res = score_series(s, "level", +1)
    full_history_pct = float((s < 2.0).mean() * 100)

    assert full_history_pct < 25.0              # старият percentile: „на дъното"
    assert res["score"] == pytest.approx(50.0)  # робастният: „на нормата"
    assert res["percentile_window"] == "10г"


def test_percentile_stays_secondary_context():
    """Percentile се публикува, но НЕ е заглавният score."""
    s = _monthly([1.0, 3.0] * 60 + [7.0])
    res = score_series(s, "level", +1)

    assert res["percentile"] == pytest.approx(
        percentile_rank(7.0, s.tail(121)), abs=0.1
    )
    assert res["score"] != res["percentile"]


# ── MAD = 0 guard ────────────────────────────────────────────────────────────

def test_mad_zero_in_window_falls_back_to_full_history_scale():
    """Пинната серия + реален екстремум: без guard-а → фалшиво 50."""
    s = _monthly([1.0, 9.0] * 98 + [5.0] * 120 + [100.0])
    res = score_series(s, "level", +1)

    assert res["scale_fallback"] is True
    assert res["degenerate"] is False
    assert res["score"] > 95.0                       # екстремумът се вижда
    assert res["percentile_window"] == "пълна история"


def test_scale_fallback_clips_at_six_sigma():
    s = _monthly([1.0, 9.0] * 98 + [5.0] * 120 + [100.0])
    res = score_series(s, "level", +1)

    assert abs(res["health_z"]) <= 6.0
    assert abs(res["z_raw"]) <= 6.0


def test_constant_series_is_degenerate_not_extreme():
    """Без вариация дори в пълната история → неутрално + флаг, не 0/100."""
    s = _monthly([5.0] * 300)
    res = score_series(s, "level", +1)

    assert res["degenerate"] is True
    assert res["score"] == pytest.approx(50.0)
    assert res["health_z"] == pytest.approx(0.0)


# ── Полярност ────────────────────────────────────────────────────────────────

def test_negative_polarity_inverts_the_health():
    s = _monthly([1.0, 3.0] * 60 + [7.0])
    up = score_series(s, "level", +1)
    down = score_series(s, "level", -1)

    assert up["score"] > 50.0
    assert down["score"] < 50.0
    assert up["health_z"] == pytest.approx(-down["health_z"])


def test_u_form_pins_health_at_the_target():
    """Мандатният пин: score(2.0) > score(5.2) И score(2.0) > score(0.0)."""
    def at(x):
        return score_series(_monthly([1.0, 3.0] * 60 + [x]), "level",
                            ("U", "target", 2.0))["score"]

    assert at(2.0) > at(5.2)
    assert at(2.0) > at(0.0)


def test_u_form_stops_deflation_from_scoring_excellent():
    """Наивното „ниско = добре" правеше дефлацията отличник."""
    s = _monthly([1.0, 3.0] * 60 + [0.0])
    naive = score_series(s, "level", -1)["score"]
    u_form = score_series(s, "level", ("U", "target", 2.0))["score"]

    assert naive > 60.0        # старият прочит: „чудесно"
    assert u_form < 50.0       # честният: отклонение от целта


def test_polarity_is_serialised_as_string():
    s = _monthly([1.0, 3.0] * 60 + [2.0])
    assert score_series(s, "level", ("U", "target", 2.0))["polarity"] == "U:target=2.0"
    assert score_series(s, "level", -1)["polarity"] == "-1"


# ── Трансформация преди скоринга ─────────────────────────────────────────────

def test_transform_is_applied_before_scoring():
    """Номинално растящ индекс се съди на ТЕМП, не на ниво."""
    levels = [100.0 * (1.10 ** (i / 12)) for i in range(300)]
    s = _monthly(levels)

    res = score_series(s, "yoy_pct", +1)

    assert res["display_is_pct"] is True
    assert res["display_value"] == pytest.approx(10.0, abs=0.6)
    assert res["score"] < 90.0     # постоянен темп → близо до нормата, не екстремум


def test_empty_series_returns_empty_score():
    res = score_series(pd.Series(dtype="float64"), "level", +1, name="X")
    assert res["score"] is None
    assert res["health_z"] is None
    assert res["name"] == "X"
