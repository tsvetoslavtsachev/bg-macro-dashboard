"""
catalog/series.py
=================
Каталог на макроикономическите серии за България.
Използваме основно Eurostat за макро данни (GDP, HICP, Unemployment),
тъй като са стандартизирани и лесни за автоматизирано извличане.
"""
from __future__ import annotations
from typing import Any

ALLOWED_SOURCES = {"eurostat", "ecb", "nsi", "bnb", "derived"}
ALLOWED_REGIONS = {"BG", "EU"}
ALLOWED_LENSES = {"labor", "inflation", "growth", "credit", "external", "property",
                  "fiscal"}
ALLOWED_TRANSFORMS = {"level", "yoy_pct", "mom_pct", "qoq_pct", "z_score",
                      "first_diff", "roll4q_mean", "yoy_roll4"}
ALLOWED_SCORING_MODES = {"level", "momentum"}
ALLOWED_SCHEDULES = {"daily", "weekly", "monthly", "quarterly", "annually"}

SERIES_CATALOG: dict[str, dict[str, Any]] = {
    # ════════════════════════════════════════════════════════
    # GROWTH
    # ════════════════════════════════════════════════════════
    "BG_GDP_YOY": {
        "source": "eurostat",
        "id": "namq_10_gdp?geo=BG&unit=CLV_PCH_SM&na_item=B1GQ&s_adj=SCA",
        "region": "BG",
        "name_bg": "БВП (Реален растеж, г/г)",
        "name_en": "Real GDP Growth (YoY)",
        "lens": ["growth"],
        "peer_group": "gdp",
        "tags": ["headline"],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Основен измерител за икономическия растеж.",
    },
    "BG_INDPRO": {
        "source": "eurostat",
        "id": "sts_inpr_m?geo=BG&nace_r2=B-D&s_adj=CA&indic_bt=PRD&unit=I21",
        "region": "BG",
        "name_bg": "Промишлено производство (г/г)",
        "name_en": "Industrial Production Index",
        "lens": ["growth"],
        "peer_group": "production",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": False,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Индустриалното производство е водещ индикатор за бизнес цикъла.",
    },
    "BG_CONS": {
        "source": "eurostat",
        "id": "namq_10_gdp?geo=BG&unit=CLV_PCH_SM&na_item=P31_S14_S15&s_adj=SCA",
        "region": "BG",
        "name_bg": "Потребление на домакинствата (г/г)",
        "name_en": "Household Consumption (YoY)",
        "lens": ["growth"],
        "peer_group": "consumption",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Основен двигател на българската икономика.",
    },
    "BG_ESI": {
        "source": "eurostat",
        "id": "ei_bssi_m_r2?geo=BG&indic=BS-ESI-I&s_adj=SA",
        "region": "BG",
        "name_bg": "Икономическо доверие (ESI)",
        "name_en": "Economic Sentiment Indicator",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": ["leading"],
        "transform": "level",
        "is_rate": False,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Водещ индикатор, базиран на анкети с бизнеса и потребителите.",
    },
    
    # ════════════════════════════════════════════════════════
    # INFLATION
    # ════════════════════════════════════════════════════════
    "BG_HICP": {
        "source": "eurostat",
        "id": "prc_hicp_minr?geo=BG&coicop18=TOTAL&unit=RCH_A",
        "region": "BG",
        "name_bg": "Инфлация (ХИПЦ, г/г)",
        "name_en": "HICP Inflation (YoY)",
        "lens": ["inflation"],
        "peer_group": "headline_inflation",
        "tags": ["headline"],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Хармонизиран индекс на потребителските цени - критерий за Еврозоната.",
    },
    "BG_HICP_CORE": {
        "source": "eurostat",
        "id": "prc_hicp_minr?geo=BG&coicop18=TOT_X_NRG_FOOD&unit=RCH_A",
        "region": "BG",
        "name_bg": "Базисна инфлация (без храни и енергия, г/г)",
        "name_en": "Core HICP Inflation (YoY)",
        "lens": ["inflation"],
        "peer_group": "core_inflation",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Показва устойчивия инфлационен натиск.",
    },
    # ── Усещаната инфлация — КОНТЕКСТНА серия (мандат №48) ────────────────────
    # ЕК потребителска анкета (Eurostat `ei_bsco_m`, indic `BS-PT-LY`): как
    # потребителите ОЦЕНЯВАТ ценовите тенденции през последните 12 месеца.
    # Числото е качествен БАЛАНС (дял „поскъпнаха силно/умерено" минус дял
    # „не се промениха/поевтиняха"), НЕ процент — 75 не значи 75% инфлация.
    # Затова серията:
    #   · няма леща (`lens: []`) и няма да получи score — `context_only: True`;
    #   · НЕ влиза в композита ПО КОНСТРУКЦИЯ, а не по изключение в скорера;
    #   · стои ДО официалната HICP на лицето, защото самата РАЗЛИКА между двете
    #     е находката: възприятието стои на нивата от инфлационната криза
    #     2021-23, докато официалната инфлация е кратно по-ниска.
    # Живо проверено 28.07.2026: n=302, пълна месечна история 2001-05 → 2026-06,
    # s_adj=SA, unit=BAL (единствената налична мерна единица за този набор).
    # Съседът `BS-PT-NY` (очакванията за СЛЕДВАЩИТЕ 12 месеца, също n=302,
    # последно 21.9 — закотвени) е меню-кандидат, НЕ влиза с този мандат.
    "BG_INFL_PERCEIVED": {
        "source": "eurostat",
        "id": "ei_bsco_m?geo=BG&indic=BS-PT-LY&s_adj=SA&unit=BAL",
        "region": "BG",
        "name_bg": "Усещана инфлация (ЕК анкета, баланс)",
        "name_en": "Perceived Inflation (EC survey, balance)",
        "lens": [],
        "context_only": True,
        "peer_group": "context",
        "tags": ["survey", "context"],
        "transform": "level",
        "is_rate": False,
        "historical_start": "2001-05-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Качественият баланс на потребителските възприятия за "
                          "цените през последните 12 месеца — не е процент; "
                          "гравитира далеч над официалната ХИПЦ и показва как се "
                          "ЧУВСТВА инфлацията.",
    },

    # ════════════════════════════════════════════════════════
    # LABOR
    # ════════════════════════════════════════════════════════
    "BG_UNRATE": {
        "source": "eurostat",
        "id": "une_rt_m?geo=BG&unit=PC_ACT&sex=T&age=TOTAL&s_adj=SA",
        "region": "BG",
        "name_bg": "Безработица (%)",
        "name_en": "Unemployment Rate",
        "lens": ["labor"],
        "peer_group": "unemployment",
        "tags": ["headline"],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "first_week",
        "revision_prone": False,
        "narrative_hint": "Изоставащ индикатор, но ключов за здравето на икономиката.",
    },
    "BG_WAGES": {
        "source": "eurostat",
        "id": "namq_10_a10?geo=BG&unit=CP_MEUR&nace_r2=TOTAL&na_item=D1&s_adj=SCA",
        "region": "BG",
        "name_bg": "Компенсация на наетите (Растеж, г/г)",
        "name_en": "Compensation of Employees",
        "lens": ["labor"],
        "peer_group": "wages",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": False,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Растежът на заплатите е основен двигател на инфлацията в услугите.",
    },
    
    # ════════════════════════════════════════════════════════
    # EXTERNAL — външният сектор (мандат №45 П0)
    # ════════════════════════════════════════════════════════
    # Двете серии живеят в ЕДНА peer-група `external_balance`, по прецедента на
    # `lending`: търговският баланс на стоки и услуги е ПОДМНОЖЕСТВОТО-ДВИГАТЕЛ
    # на дефицита по текущата сметка — един и същ външен шок. Отделни peer-групи
    # биха го броили ДВА пъти и биха направили външната леща двойно по-уверена,
    # отколкото данните позволяват. Външният сектор = 1 peer сигнал, докато не
    # дойде ортогонална серия (туризъм/услуги — отделен скаут, не тук).
    # Математически: при peer-тегла 1.0 средното на две групи по 1 серия ≡ една
    # група от 2 серии → композитът и външният z НЕ се менят при сливането.
    "BG_CA_GDP": {
        "source": "eurostat",
        "id": "bop_gdp6_q?geo=BG&bop_item=CA&stk_flow=BAL&partner=WRL_REST",
        "region": "BG",
        "name_bg": "Текуща сметка (% от БВП, 4-тримесечна плъзгаща)",
        "name_en": "Current Account to GDP",
        "lens": ["external"],
        "peer_group": "external_balance",
        "tags": [],
        "transform": "roll4q_mean",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "end_quarter",
        "revision_prone": True,
        "narrative_hint": "Показва външните дисбаланси на икономиката.",
    },
    "BG_TRADE_GS": {
        "source": "eurostat",
        "id": "bop_gdp6_q?geo=BG&bop_item=GS&stk_flow=BAL&partner=WRL_REST",
        "region": "BG",
        "name_bg": "Търговски баланс — стоки и услуги (% от БВП, 4-тримесечна плъзгаща)",
        "name_en": "Trade Balance, Goods and Services to GDP",
        "lens": ["external"],
        "peer_group": "external_balance",
        "tags": [],
        "transform": "roll4q_mean",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "end_quarter",
        "revision_prone": True,
        "narrative_hint": "Търговската компонента на текущата сметка — разделя дефицита, "
                          "воден от стоки и услуги, от дохода и трансферите.",
    },

    # ════════════════════════════════════════════════════════
    # CREDIT / FINANCIAL
    # ════════════════════════════════════════════════════════
    "BG_LT_RATE": {
        "source": "eurostat",
        "id": "irt_lt_mcby_m?geo=BG",
        "region": "BG",
        "name_bg": "Дългосрочен лихвен процент (10г ДЦК)",
        "name_en": "Long-term Interest Rate (10Y Gov Bond)",
        "lens": ["credit"],
        "peer_group": "yields",
        "tags": ["sovereign"],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2003-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Критерий от Маастрихт за конвергенция. Отразява цената на държавния дълг.",
    },
    # ── Цената на кредита (мандат №42) ───────────────────────────────────────
    # MIR = „MFI Interest Rate Statistics“ — лихвената статистика на ЕЦБ. Четем
    # ставката по НОВ БИЗНЕС (кредити различни от револвиращи и овърдрафт) към
    # нефинансови предприятия, в евро, годишно приведена (AAR/NDER): какво плаща
    # фирмата, която тегли ДНЕС. Това е острият прочит на трансмисията — салдата
    # усредняват стари договори и реагират с тримесечия закъснение.
    # За разлика от BSI обемите, MIR носи ЦЯЛАТА история в API-то:
    # 2007-01 → 2026-05 (n=233, живо проверено 26.07.2026) → пълна 10-г. норма,
    # никакъв seed, никакъв сплайс.
    #
    # Отхвърлени алтернативи (живо проверени 26.07.2026 — не се преоткриват):
    #   (а) САЛДА вариантът (`…A2A…O`) — ЕЦБ го държи чак от 2019-12 (n=78, тънък
    #       прозорец) и включва овърдрафтите вътре;
    #   (б) БНБ файлът `s_ir_loan_oa_nfc_bg.xlsx` като seed — той е салда САМО по
    #       евро-деноминираните кредити и се разминава ДЕФИНИЦИОННО с всички API
    #       варианти (0.3–2.2 пп). Остава РЕФЕРЕНЦИЯ за ръчна сверка; сплайс
    #       върху дефиниционно разминаване би произвел фалшива история.
    "BG_LENDING_RATE": {
        "source": "ecb",
        "id": "MIR/M.BG.B.A2A.A.R.A.2240.EUR.N",
        "region": "BG",
        "name_bg": "Лихва по нови фирмени кредити (%)",
        "name_en": "Lending Rate, New Business to NFCs",
        "lens": ["credit"],
        "peer_group": "lending_cost",
        "tags": ["transmission"],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2007-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Цената на новия фирмен кредит — трансмисията на "
                          "паричната политика към реалния сектор.",
    },
    # ── Дългата кредитна памет (мандат №41) ──────────────────────────────────
    # ECB Data Portal (набор BSI) е ПРАЗЕН преди 01.2022 за България (проверено
    # с wildcard + startPeriod). Първоизточникът обаче ги има: БНБ „Кредитна
    # динамика“ публикува същите редове ТРИМЕСЕЧНО от 2005Q4. Затова сериите се
    # зашиват в `sources/manual_seed.py` — seed отпред, завършените BSI
    # тримесечия отзад, шевът валидиран ≤0.5% на всички общи тримесечия
    # (припокриването е 0.00%: БНБ репортва точно този поток към ЕЦБ).
    # Следствия: `release_schedule` е "quarterly" (лещата се опреснява на
    # тримесечие), `historical_start` е 2005-12-01, а нормата вече е ПЪЛНА
    # 10-годишна — флагът `thin_window` изчезва сам.
    "BG_LOANS_NFC": {
        "source": "ecb",
        "id": "BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E",
        "region": "BG",
        "name_bg": "Кредит за нефинансови предприятия (г/г)",
        "name_en": "Loans to Non-Financial Corporations (YoY)",
        "lens": ["credit"],
        "peer_group": "lending",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": False,
        "historical_start": "2005-12-01",
        "release_schedule": "quarterly",
        "typical_release": "end_quarter",
        "revision_prone": False,
        "narrative_hint": "Кредитният цикъл е двигател на търсенето — бърз ръст е "
                          "едновременно сила и риск.",
    },
    "BG_LOANS_HH": {
        "source": "ecb",
        "id": "BSI/M.BG.N.A.A20.A.1.U6.2250.Z01.E",
        "region": "BG",
        "name_bg": "Кредит за домакинствата (г/г)",
        "name_en": "Loans to Households (YoY)",
        "lens": ["credit"],
        "peer_group": "lending",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": False,
        "historical_start": "2005-12-01",
        "release_schedule": "quarterly",
        "typical_release": "end_quarter",
        "revision_prone": False,
        "narrative_hint": "Кредитът за домакинствата храни потреблението и жилищния "
                          "пазар — бърз ръст е едновременно сила и риск.",
    },

    # ════════════════════════════════════════════════════════
    # PROPERTY — имоти и строителство (мандат №43)
    # ════════════════════════════════════════════════════════
    # Шестата леща. Трите крака са ТРИ РАЗЛИЧНИ въпроса, затова са три отделни
    # peer-групи, не един „имотен“ сигнал:
    #   `prices`   — колко струва активът (цената на жилището)
    #   `activity` — колко се строи ДНЕС (реалната продукция)
    #   `pipeline` — колко влиза в тръбата (разрешителните, водещият индикатор)
    # Живо проверени Eurostat заявки (26.07.2026 — не се преоткриват):
    # `prc_hpi_q` носи готов г/г темп (unit `RCH_A`) → transform `level`;
    # другите две са ИНДЕКСИ (2021=100) → г/г. Внимание при разрешителните:
    # dimension кодът `PSQM` НЕ съществува — верният е `BPRM_SQM`; и от мандат
    # №47 темпът им се чете като 4-тримесечна плъзгаща (`yoy_roll4`).
    "BG_HPI": {
        "source": "eurostat",
        "id": "prc_hpi_q?geo=BG&purchase=TOTAL&unit=RCH_A",
        "region": "BG",
        "name_bg": "Цени на жилищата (HPI, г/г)",
        "name_en": "House Price Index (YoY)",
        "lens": ["property"],
        "peer_group": "prices",
        "tags": ["headline"],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2006-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Жилищният пазар — цената на актива, който държи "
                          "по-голямата част от богатството на домакинствата и "
                          "обезпечава ипотечния кредит.",
    },
    "BG_CONSTR": {
        "source": "eurostat",
        "id": "sts_copr_m?geo=BG&nace_r2=F&s_adj=CA&indic_bt=PRD&unit=I21",
        "region": "BG",
        "name_bg": "Строителна продукция (г/г)",
        "name_en": "Construction Production Index (YoY)",
        "lens": ["property"],
        "peer_group": "activity",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": False,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Реалната строителна активност — какво се строи в "
                          "момента, а не какво се планира.",
    },
    "BG_PERMITS": {
        "source": "eurostat",
        "id": "sts_cobp_q?geo=BG&indic_bt=BPRM_SQM&cpa2_1=CPA_F41001&s_adj=SCA&unit=I21",
        "region": "BG",
        "name_bg": "Разрешителни за строеж — жилищни, м² (г/г, 4-тримесечна плъзгаща)",
        "name_en": "Building Permits, Residential Floor Area (YoY, 4Q rolling)",
        "lens": ["property"],
        "peer_group": "pipeline",
        "tags": ["leading"],
        # Мандат №47 §А2: СУРОВОТО г/г е негодно за абсолютна котва — в
        # спокойната епоха 2015-19 то стига 61.1% (p90 47.7), т.е. шумът гаси
        # всяка зона. 4-тримесечната плъзгаща сепарира епохите чисто:
        # 2015-19 max 38.7 срещу 2005-08 med 39.8. Суровото г/г остава видимо
        # на графиката като тънка прекъсната линия.
        "transform": "yoy_roll4",
        "is_rate": False,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Водещият индикатор на строителния цикъл — какво влиза "
                          "в тръбата днес, за да излезе като предлагане след "
                          "година-две.",
    },

    # ── Наемите — ВТОРАТА контекстна серия (мандат №51) ──────────────────────
    # Другата половина на жилищния въпрос. Уредът мери КУПУВАНЕТО (цена на
    # жилището, разрешителни, ипотечен кредит), а наемането е алтернативата,
    # спрямо която домакинството избира — двете се преоценяват заедно. Точно
    # затова серията е и ДИСКРИМИНАТОРЪТ на двете хипотези за кредитно-жилищния
    # бум: „заместващата" теза (растящи доходи → покупка вместо наем, изместващо
    # спекулативното търсене) очаква свиващо се наемно търсене, а наемите растат
    # с двуцифрен темп — двусмислено, значи хипотезата не е установена.
    #
    # Живо проверено 29.07.2026 (не се преоткрива): n=343 от 1997-12, последно
    # 10.1 (06.2026); пътека 01-06.2026: 10.6/10.6/10.2/9.4/10.2/10.1. Епохи:
    # 2015-19 med 1.0 / max 4.0 · 2021-23 med 6.6 · 2024-сега med 7.9 / max 11.9.
    # Индексната форма (`prc_hicp_midx`) е ПРАЗНА за BG/CP041 — готовата г/г
    # ставка (`RCH_A`) е наличният формат, затова `transform: level`.
    #
    # Като усещаната инфлация (№48): `lens: []` + `context_only: True` → извън
    # композита ПО КОНСТРУКЦИЯ, сив бадж, без score. Наблюдение ДО уреда.
    "BG_RENTS": {
        "source": "eurostat",
        "id": "prc_hicp_minr?geo=BG&coicop18=CP041&unit=RCH_A",
        "region": "BG",
        "name_bg": "Наеми (действителни, ХИПЦ, г/г)",
        "name_en": "Actual Rentals for Housing (HICP, YoY)",
        "lens": [],
        "context_only": True,
        "peer_group": "context",
        "tags": ["context", "housing"],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Другата половина на жилищния въпрос — купуването И "
                          "наемането се преоценяват заедно; дискриминаторът на "
                          "двете хипотези за кредитно-жилищния бум.",
    },

    # ════════════════════════════════════════════════════════
    # FISCAL — държавни финанси (мандат №50)
    # ════════════════════════════════════════════════════════
    # Седмата леща. Двата крака са ДВА РАЗЛИЧНИ въпроса, затова са две отделни
    # peer-групи, не един „фискален“ сигнал:
    #   `fiscal_balance` — ПОТОКЪТ: колко се харчи над приходите тази година
    #   `debt`           — СТОКЪТ: колко е натрупано като дял от икономиката
    # Днешната разцепка е точно тази: остър поток (−4.7% от БВП) при все още
    # нисък сток (28.5%). Не е случаят CA+GS (там едното беше подмножеството-
    # двигател на другото) — тук потокът пълни стока с години закъснение.
    #
    # Живо проверени Eurostat заявки (29.07.2026 — не се преоткриват):
    # `gov_10q_ggnfa` носи B9 = „Net lending (+) / net borrowing (−)“, т.е.
    # знакът е ПЛЮС при излишък; сезонно и календарно изгладените варианти
    # (SA/SCA) са ПРАЗНИ за България, затова четем сурово NSA. Суровото
    # тримесечие е силно сезонно (Q4 дупки от −10% и повече) → 4-тримесечна
    # плъзгаща по прецедента на текущата сметка (`roll4q_mean`, от №37).
    "BG_GOV_BALANCE": {
        "source": "eurostat",
        "id": "gov_10q_ggnfa?geo=BG&unit=PC_GDP&s_adj=NSA&sector=S13&na_item=B9",
        "region": "BG",
        "name_bg": "Бюджетно салдо (% от БВП, 4-тримесечна плъзгаща)",
        "name_en": "General Government Net Lending/Borrowing to GDP (4Q rolling)",
        "lens": ["fiscal"],
        "peer_group": "fiscal_balance",
        "tags": ["headline"],
        "transform": "roll4q_mean",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "end_quarter",
        "revision_prone": True,
        "narrative_hint": "Фискалният лост е ЕДИНСТВЕНИЯТ домашен макро лост — "
                          "България няма собствена лихвена политика. Салдото е "
                          "потокът, който пълни или свива дълга.",
    },
    "BG_GOV_DEBT": {
        "source": "eurostat",
        "id": "gov_10q_ggdebt?geo=BG&na_item=GD&sector=S13&unit=PC_GDP",
        "region": "BG",
        "name_bg": "Държавен дълг (% от БВП)",
        "name_en": "General Government Consolidated Gross Debt to GDP",
        "lens": ["fiscal"],
        "peer_group": "debt",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "end_quarter",
        "revision_prone": True,
        "narrative_hint": "Нивото е сред най-ниските в ЕС, но скорът мери "
                          "ДРЕЙФА спрямо собствената 10-годишна норма — "
                          "качването с 6пп за година е сигналът, не класацията.",
    },
}

def series_by_source(source: str) -> list[dict[str, Any]]:
    """Връща списък със серии за даден източник, добавяйки _key."""
    result = []
    for k, v in SERIES_CATALOG.items():
        if v.get("source") == source:
            item = dict(v)
            item["_key"] = k
            result.append(item)
    return result

def validate_catalog(catalog: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Валидира каталога за грешки.

    Празна леща е ГРЕШКА — иначе серия, на която някой е забравил лещата, тихо
    изпада от композита и никой не разбира. Единственото изключение е изричният
    флаг `context_only: True` (мандат №48): контекстната серия е наблюдение ДО
    композита по СЪЗНАТЕЛНО решение, а флагът е декларацията на това решение.
    """
    catalog = SERIES_CATALOG if catalog is None else catalog
    errors = []
    for k, v in catalog.items():
        if v.get("source") not in ALLOWED_SOURCES:
            errors.append(f"{k}: invalid source {v.get('source')}")
        if v.get("region") not in ALLOWED_REGIONS:
            errors.append(f"{k}: invalid region {v.get('region')}")
        lenses = v.get("lens", [])
        if not lenses and not v.get("context_only"):
            errors.append(
                f"{k}: empty lens without context_only "
                f"(серия без леща изпада от композита мълчаливо)"
            )
        for l in lenses:
            if l not in ALLOWED_LENSES:
                errors.append(f"{k}: invalid lens {l}")
        if v.get("context_only") and lenses:
            errors.append(f"{k}: context_only series must not carry a lens")
        if v.get("transform") not in ALLOWED_TRANSFORMS:
            errors.append(f"{k}: invalid transform {v.get('transform')}")
    return errors
