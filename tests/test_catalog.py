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

def test_catalog_carries_eighteen_series_of_which_seventeen_are_scored():
    """14 след М42 + трите имотни серии на М43 + контекстната на М48.

    Двете числа се държат ОТДЕЛНО нарочно: каталогът расте на 18, но уредът,
    който произвежда композита, остава на 17. Ако някой ден контекстна серия
    се промъкне в леща, второто число ще се смени и тестът ще го каже.
    """
    assert len(SERIES_CATALOG) == 18
    scored = [k for k, v in SERIES_CATALOG.items() if not v.get("context_only")]
    assert len(scored) == 17
    assert all(SERIES_CATALOG[k]["lens"] for k in scored)


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


# ── Мандат №41: дългата кредитна памет ───────────────────────────────────────

def test_loan_series_are_quarterly_after_the_bnb_seed():
    """Цената на дългата памет: лещата се опреснява на тримесечие."""
    for key in ("BG_LOANS_NFC", "BG_LOANS_HH"):
        assert SERIES_CATALOG[key]["release_schedule"] == "quarterly", key


def test_loan_history_starts_at_the_bnb_seed_not_at_the_ecb_portal():
    """БНБ „Кредитна динамика“ дава 2005Q4+; ЕЦБ порталът тръгва чак от 2022."""
    for key in ("BG_LOANS_NFC", "BG_LOANS_HH"):
        assert SERIES_CATALOG[key]["historical_start"] == "2005-12-01", key


def test_both_loans_share_one_peer_group():
    """Двата заема са ЕДИН кредитен сигнал, не два — иначе кредитирането
    надтежава доходността в лещата."""
    assert SERIES_CATALOG["BG_LOANS_NFC"]["peer_group"] == "lending"
    assert SERIES_CATALOG["BG_LOANS_HH"]["peer_group"] == "lending"


def test_credit_lens_is_four_series_in_three_peer_groups():
    """Мандат №42: цената на новия кредит е ТРЕТИ крак в лещата."""
    credit = {k: v for k, v in SERIES_CATALOG.items() if "credit" in v["lens"]}
    assert set(credit) == {
        "BG_LT_RATE", "BG_LENDING_RATE", "BG_LOANS_NFC", "BG_LOANS_HH"
    }
    assert {v["peer_group"] for v in credit.values()} == {
        "yields", "lending", "lending_cost"
    }


def test_external_lens_is_two_series_in_one_peer_group():
    """Мандат №45 П0: CA и GS са ЕДИН външен шок, не два.

    Търговският баланс е подмножеството-двигател на дефицита по текущата сметка.
    Отделни peer-групи го броят двойно и правят външната леща двойно по-уверена,
    отколкото данните позволяват — прецедентът е `lending` (двата заема).
    """
    external = {k: v for k, v in SERIES_CATALOG.items() if "external" in v["lens"]}
    assert set(external) == {"BG_CA_GDP", "BG_TRADE_GS"}
    assert {v["peer_group"] for v in external.values()} == {"external_balance"}


# ── Мандат №42: цената на кредита ────────────────────────────────────────────

def test_lending_rate_reads_the_ecb_mir_new_business_key():
    """Точният ключ е решение на мандата, не подробност — пинва се.

    `MIR` (лихвената статистика) · `A2A` (кредити различни от револвиращи и
    овърдрафт) · `2240` (нефинансови предприятия) · `EUR` · `N` (нов бизнес).
    """
    spec = SERIES_CATALOG["BG_LENDING_RATE"]
    assert spec["source"] == "ecb"
    assert spec["id"] == "MIR/M.BG.B.A2A.A.R.A.2240.EUR.N"


def test_lending_rate_is_new_business_not_outstanding_amounts():
    """Салда вариантът (`…O`) беше отхвърлен: ЕЦБ го държи чак от 2019-12 и
    смесва овърдрафтите. Ако някой го върне, тестът пада."""
    spec = SERIES_CATALOG["BG_LENDING_RATE"]
    assert spec["id"].endswith(".N"), "нов бизнес завършва на N, салдата на O"
    assert not spec["id"].endswith(".O")


def test_lending_rate_is_read_as_a_level_rate():
    """Ставка се чете като НИВО — г/г върху лихва би било безсмислица."""
    spec = SERIES_CATALOG["BG_LENDING_RATE"]
    assert spec["transform"] == "level"
    assert spec["is_rate"] is True


def test_lending_rate_carries_the_full_history_from_2007():
    """За разлика от BSI обемите, MIR носи цялата история → пълна 10-г. норма
    без seed и без сплайс."""
    spec = SERIES_CATALOG["BG_LENDING_RATE"]
    assert spec["historical_start"] == "2007-01-01"
    assert spec["release_schedule"] == "monthly"


def test_lending_rate_has_its_own_peer_group_apart_from_yields():
    """Цената на новия кредит и цената на държавния дълг са РАЗЛИЧНИ канали —
    в една група щяха да се усреднят в един сигнал."""
    assert SERIES_CATALOG["BG_LENDING_RATE"]["peer_group"] == "lending_cost"
    assert SERIES_CATALOG["BG_LT_RATE"]["peer_group"] == "yields"


def test_lending_rate_is_not_spliced_with_any_manual_seed():
    """Мандатната забрана: никакъв seed/сплайс върху дефиниционно разминаване
    (БНБ файлът е салда само по евро-деноминираните — остава референция)."""
    from sources.manual_seed import SEED_TO_CATALOG

    assert "BG_LENDING_RATE" not in SEED_TO_CATALOG.values()


# ── Мандат №43: имотната леща ────────────────────────────────────────────────

def test_property_lens_is_three_series_in_three_peer_groups():
    """Трите крака са ТРИ въпроса — цена · активност · тръба. В една peer-група
    щяха да се усреднят в един „имотен“ сигнал и водещият индикатор щеше да се
    удави в текущата продукция."""
    prop = {k: v for k, v in SERIES_CATALOG.items() if "property" in v["lens"]}
    assert set(prop) == {"BG_HPI", "BG_CONSTR", "BG_PERMITS"}
    assert {v["peer_group"] for v in prop.values()} == {
        "prices", "activity", "pipeline"
    }


def test_property_lens_is_allowed_in_the_catalog_vocabulary():
    from catalog.series import ALLOWED_LENSES

    assert "property" in ALLOWED_LENSES


def test_hpi_is_already_a_year_on_year_rate_so_it_stays_a_level():
    """`prc_hpi_q` unit `RCH_A` = ВЕЧЕ г/г процент. `yoy_pct` върху него би дало
    „темп на темпа“ — безсмислица. Затова transform=level, is_rate=True."""
    spec = SERIES_CATALOG["BG_HPI"]
    assert spec["source"] == "eurostat"
    assert "prc_hpi_q" in spec["id"]
    assert "unit=RCH_A" in spec["id"]
    assert "purchase=TOTAL" in spec["id"]
    assert spec["transform"] == "level"
    assert spec["is_rate"] is True
    assert spec["historical_start"] == "2006-01-01"
    assert spec["release_schedule"] == "quarterly"


def test_construction_and_permits_are_indices_read_as_growth_rates():
    """И двете са индекси 2021=100 → нивото не е сравнимо във времето; четат се
    като г/г. Разрешителните — през 4-тримесечната плъзгаща (мандат №47)."""
    for key in ("BG_CONSTR", "BG_PERMITS"):
        spec = SERIES_CATALOG[key]
        assert spec["transform"] in ("yoy_pct", "yoy_roll4"), key
        assert spec["is_rate"] is False, key
        assert "unit=I21" in spec["id"], key
    assert SERIES_CATALOG["BG_CONSTR"]["transform"] == "yoy_pct"


def test_permits_are_read_as_a_four_quarter_rolling_growth_rate():
    """Мандат №47 §А2: суровото г/г е негодно за АБСОЛЮТЕН праг — в спокойните
    2015-19 то стига 61.1% (p90 47.7) и шумът гаси всяка зона. Плъзгащата
    сепарира епохите чисто (2015-19 max 38.7 срещу 2005-08 med 39.8)."""
    spec = SERIES_CATALOG["BG_PERMITS"]
    assert spec["transform"] == "yoy_roll4"
    assert "4-тримесечна плъзгаща" in spec["name_bg"]

    from catalog.series import ALLOWED_TRANSFORMS

    assert "yoy_roll4" in ALLOWED_TRANSFORMS


def test_permits_use_the_square_metre_indicator_that_actually_exists():
    """Живо проверено 26.07.2026: `indic_bt=PSQM` НЕ съществува в `sts_cobp_q`;
    верният код за разгъната площ е `BPRM_SQM`. Ако някой върне PSQM, заявката
    се връща празна и лещата тихо губи един крак — затова се пинва тук."""
    spec = SERIES_CATALOG["BG_PERMITS"]
    assert "sts_cobp_q" in spec["id"]
    assert "indic_bt=BPRM_SQM" in spec["id"]
    assert "indic_bt=PSQM" not in spec["id"]
    assert "cpa2_1=CPA_F41001" in spec["id"], "жилищни сгради, не всички"


def test_construction_reads_the_calendar_adjusted_nace_f_production():
    spec = SERIES_CATALOG["BG_CONSTR"]
    assert "sts_copr_m" in spec["id"]
    assert "nace_r2=F" in spec["id"]
    assert "s_adj=CA" in spec["id"]
    assert spec["release_schedule"] == "monthly"


def test_trade_balance_is_the_goods_and_services_balance():
    spec = SERIES_CATALOG["BG_TRADE_GS"]
    assert spec["source"] == "eurostat"
    assert "bop_gdp6_q" in spec["id"]
    assert "bop_item=GS" in spec["id"]
    assert spec["transform"] == "roll4q_mean"
