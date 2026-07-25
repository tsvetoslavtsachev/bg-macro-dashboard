"""
tests/test_catalog.py
=====================
Закотвя каталога: валиден е и сочи към живите Eurostat набори.
"""
from catalog.series import SERIES_CATALOG, validate_catalog


def test_catalog_is_valid():
    assert validate_catalog() == []


def test_hicp_points_to_ecoicop2_successor():
    """prc_hicp_manr е замразен на 12.2025; наследникът е prc_hicp_minr."""
    hicp_id = SERIES_CATALOG["BG_HICP"]["id"]
    assert "prc_hicp_minr" in hicp_id
    assert "coicop18=TOTAL" in hicp_id
    assert "prc_hicp_manr" not in hicp_id


def test_hicp_core_points_to_ecoicop2_successor():
    core_id = SERIES_CATALOG["BG_HICP_CORE"]["id"]
    assert "prc_hicp_minr" in core_id
    assert "coicop18=TOT_X_NRG_FOOD" in core_id
    assert "prc_hicp_manr" not in core_id


def test_esi_points_to_full_history_dataset():
    """teibs010 е ролираща 12-месечна таблица — percentile върху 12 точки."""
    esi_id = SERIES_CATALOG["BG_ESI"]["id"]
    assert "ei_bssi_m_r2" in esi_id
    assert "teibs010" not in esi_id


def test_current_account_is_four_quarter_rolling():
    assert SERIES_CATALOG["BG_CA_GDP"]["transform"] == "roll4q_mean"


# ── Фаза 3.1: БНБ сериите (мандат №39 §А2) ───────────────────────────────────

def test_catalog_carries_thirteen_series():
    assert len(SERIES_CATALOG) == 13


def test_loan_series_come_from_the_ecb_bsi_dataset():
    """БНБ кредитната статистика не е в Eurostat — тече в набора BSI на ЕЦБ."""
    assert SERIES_CATALOG["BG_LOANS_NFC"]["source"] == "ecb"
    assert SERIES_CATALOG["BG_LOANS_NFC"]["id"] == "BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E"
    assert SERIES_CATALOG["BG_LOANS_HH"]["source"] == "ecb"
    assert SERIES_CATALOG["BG_LOANS_HH"]["id"] == "BSI/M.BG.N.A.A20.A.1.U6.2250.Z01.E"


def test_loan_series_are_read_as_growth_rates():
    for key in ("BG_LOANS_NFC", "BG_LOANS_HH"):
        assert SERIES_CATALOG[key]["transform"] == "yoy_pct", key
        assert SERIES_CATALOG[key]["is_rate"] is False, key
        assert SERIES_CATALOG[key]["release_schedule"] == "monthly", key


def test_loan_history_starts_in_2022_because_the_portal_is_empty_before_that():
    for key in ("BG_LOANS_NFC", "BG_LOANS_HH"):
        assert SERIES_CATALOG[key]["historical_start"] == "2022-01-01", key


def test_both_loans_share_one_peer_group():
    """Двата заема са ЕДИН кредитен сигнал, не два — иначе кредитирането
    надтежава доходността в лещата."""
    assert SERIES_CATALOG["BG_LOANS_NFC"]["peer_group"] == "lending"
    assert SERIES_CATALOG["BG_LOANS_HH"]["peer_group"] == "lending"


def test_credit_lens_is_three_series_in_two_peer_groups():
    credit = {k: v for k, v in SERIES_CATALOG.items() if "credit" in v["lens"]}
    assert set(credit) == {"BG_LT_RATE", "BG_LOANS_NFC", "BG_LOANS_HH"}
    assert {v["peer_group"] for v in credit.values()} == {"yields", "lending"}


def test_external_lens_is_two_series_in_two_peer_groups():
    external = {k: v for k, v in SERIES_CATALOG.items() if "external" in v["lens"]}
    assert set(external) == {"BG_CA_GDP", "BG_TRADE_GS"}
    assert {v["peer_group"] for v in external.values()} == {"current_account", "trade"}


def test_trade_balance_is_the_goods_and_services_balance():
    spec = SERIES_CATALOG["BG_TRADE_GS"]
    assert spec["source"] == "eurostat"
    assert "bop_gdp6_q" in spec["id"]
    assert "bop_item=GS" in spec["id"]
    assert spec["transform"] == "roll4q_mean"
