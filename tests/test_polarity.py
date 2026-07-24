"""
tests/test_polarity.py
======================
БГ полярностната карта (мандат №38 §А2) — изричното решение за всяка серия.

Полярността е обсъдено решение, не тих избор: закотвяме я, за да не се разпадне
мълчаливо при следващо пипане на каталога.
"""
import pytest

from catalog.polarity import (
    INFLATION_TARGET,
    POLARITY,
    U_BAND,
    is_u_shaped,
    peer_group_weight,
    polarity_for,
)
from catalog.series import SERIES_CATALOG


def test_inflation_is_u_shaped_around_the_ecb_target():
    for key in ("BG_HICP", "BG_HICP_CORE"):
        pol = polarity_for(key)
        assert is_u_shaped(pol), key
        assert pol == ("U", "target", 2.0)


def test_inflation_target_is_the_euro_area_two_percent():
    assert INFLATION_TARGET == 2.0


def test_unemployment_and_yield_are_inverted():
    assert polarity_for("BG_UNRATE") == -1
    assert polarity_for("BG_LT_RATE") == -1


def test_wages_stay_positive_pending_phase_three():
    """Двузначността на заплатите е Фаза 3 обсъждане — тук остават +1."""
    assert polarity_for("BG_WAGES") == +1


def test_everything_else_is_plus_one():
    inverted_or_u = {"BG_UNRATE", "BG_LT_RATE", "BG_HICP", "BG_HICP_CORE"}
    for key in SERIES_CATALOG:
        if key in inverted_or_u:
            continue
        assert polarity_for(key) == +1, key


def test_every_catalog_series_has_an_explicit_polarity():
    """Нито една серия не бива да минава на мълчаливия default."""
    for key in SERIES_CATALOG:
        assert key in POLARITY, key


def test_unknown_series_defaults_to_plus_one():
    assert polarity_for("BG_NOT_A_SERIES") == +1


def test_peer_group_weight_is_one_for_all_bg_groups():
    """При 10 серии групите са по 1-2 серии → без тегла (мандат §А3)."""
    for spec in SERIES_CATALOG.values():
        assert peer_group_weight(spec.get("peer_group", "")) == 1.0


def test_u_band_is_the_family_constant():
    assert U_BAND == 1.0


def test_is_u_shaped_rejects_linear_polarities():
    assert is_u_shaped(("U", "self")) is True
    assert is_u_shaped(+1) is False
    assert is_u_shaped(-1) is False
