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
