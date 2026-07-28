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
    OPT_PROVENANCE,
    OPT_SOURCE_NOTE,
    POLARITY,
    U_BAND,
    is_opt,
    is_u_shaped,
    opt_keys,
    opt_zone,
    peer_group_weight,
    polarity_for,
)
from catalog.series import SERIES_CATALOG

# ФИКСИРАНИТЕ зони от данни-паса на мандат №47 (28.07.2026). Това е
# КОНСТИТУЦИОНЕН пин: праговете са решение с provenance, не настройка. Мърдане
# без нов мандат пада тук.
MANDATED_ZONES = {
    "BG_LOANS_NFC": (0.0, 12.0, 6.0),
    "BG_LOANS_HH":  (0.0, 12.0, 6.0),
    "BG_HPI":       (0.0, 10.0, 4.0),
    "BG_WAGES":     (0.0, 13.0, 5.0),
    "BG_PERMITS":   (-20.0, 40.0, 15.0),
}


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


def test_lending_rate_is_inverted():
    """Мандат №42: по-скъп нов кредит = по-стегнати условия, не по-здраво."""
    assert polarity_for("BG_LENDING_RATE") == -1


# ── Мандат №47: бум-полярностите (РЕШЕНИ, не под преглед) ────────────────────

def test_the_five_boom_series_carry_the_mandated_optimal_zones():
    """КОНСТИТУЦИОННИЯТ пин: точните lo/hi/s от данни-паса на №47.

    Зоните са фиксирани с provenance (номиналният БВП ръст · доходният ръст ·
    конвергентният таван · спокойната епоха 2015-19). „Подобряване“ на праг без
    нов мандат = друг уред, който мълчаливо мери друго.
    """
    for key, zone in MANDATED_ZONES.items():
        pol = polarity_for(key)
        assert is_opt(pol), key
        assert opt_zone(pol) == zone, key


def test_construction_stays_linear_because_it_is_activity_not_an_asset_price():
    """Строителната продукция ОСТАВА +1 — тя е текуща реална активност.

    Бумът ѝ е производство, не надут баланс; зоните са за цената на актива
    (HPI), за тръбата (разрешителните), за кредита и за заплатите.
    """
    assert polarity_for("BG_CONSTR") == +1
    assert is_opt(polarity_for("BG_CONSTR")) is False


def test_property_prices_and_permits_are_no_longer_plain_positive():
    """Мандат №43 ги остави +1 „под преглед“; №47 затваря прегледа."""
    for key in ("BG_HPI", "BG_PERMITS"):
        assert polarity_for(key) != +1, key
        assert is_opt(polarity_for(key)), key


def test_wages_and_loan_growth_are_bounded_optima_not_more_is_better():
    """Бумът престава да се брои за здраве — това е цялата П2."""
    for key in ("BG_WAGES", "BG_LOANS_NFC", "BG_LOANS_HH"):
        assert is_opt(polarity_for(key)), key


def test_opt_keys_are_exactly_the_five_boom_series():
    """`opt_keys()` е ЕДИНСТВЕНИЯТ източник за „кои са бум-сериите“."""
    assert set(opt_keys()) == set(MANDATED_ZONES)
    assert len(opt_keys()) == 5


def test_every_zone_carries_its_provenance():
    """Числото не пътува без изречението, което го оправдава."""
    for key in opt_keys():
        assert key in OPT_PROVENANCE, key
        assert len(OPT_PROVENANCE[key]) > 20, key
    assert "28.07.2026" in OPT_SOURCE_NOTE
    assert "2015-2019" in OPT_SOURCE_NOTE


def test_zones_are_ordered_and_have_a_positive_slope():
    for key in opt_keys():
        lo, hi, width = opt_zone(polarity_for(key))
        assert lo < hi, key
        assert width > 0, key


def test_is_opt_rejects_the_other_polarity_types():
    assert is_opt(("OPT", 0.0, 12.0, 6.0)) is True
    assert is_opt(("U", "target", 2.0)) is False
    assert is_opt(+1) is False
    assert is_opt(-1) is False


def test_everything_else_is_plus_one():
    inverted_or_u = {"BG_UNRATE", "BG_LT_RATE", "BG_LENDING_RATE",
                     "BG_HICP", "BG_HICP_CORE"}
    for key in SERIES_CATALOG:
        if key in inverted_or_u or is_opt(polarity_for(key)):
            continue
        assert polarity_for(key) == +1, key


def test_the_decision_carries_its_data_at_the_decision():
    """Мандат №47: provenance таблицата и гейт-репликацията живеят ПРИ кода."""
    import catalog.polarity as polarity_module

    doc = polarity_module.__doc__
    for token in ("Provenance на hi", "ПРИЕМНИЯТ ГЕЙТ", "0/20", "5/5",
                  "namq_10_gdp", "2015-19", "2005-08"):
        assert token in doc, token


def test_the_boom_polarities_are_no_longer_declared_under_review():
    """„Под преглед“ беше вярно до №47; след него е тиха неистина."""
    import catalog.polarity as polarity_module
    from pathlib import Path

    source = Path(polarity_module.__file__).read_text(encoding="utf-8")
    assert "ПОД ПРЕГЛЕД" not in source
    assert "под преглед" not in source
    assert "РЕШЕНО с №47" in source


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
