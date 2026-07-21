"""
catalog/series.py
=================
Каталог на макроикономическите серии за България.
Използваме основно Eurostat за макро данни (GDP, HICP, Unemployment),
тъй като са стандартизирани и лесни за автоматизирано извличане.
"""
from __future__ import annotations
from typing import Any

ALLOWED_SOURCES = {"eurostat", "nsi", "bnb", "derived"}
ALLOWED_REGIONS = {"BG", "EU"}
ALLOWED_LENSES = {"labor", "inflation", "growth", "credit", "external"}
ALLOWED_TRANSFORMS = {"level", "yoy_pct", "mom_pct", "qoq_pct", "z_score", "first_diff"}
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
        "name_bg": "Промишлено производство (Индекс)",
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
        "id": "teibs010?geo=BG",
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
        "id": "prc_hicp_manr?geo=BG&coicop=CP00",
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
        "id": "prc_hicp_manr?geo=BG&coicop=TOT_X_NRG_FOOD",
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
    # EXTERNAL
    # ════════════════════════════════════════════════════════
    "BG_CA_GDP": {
        "source": "eurostat",
        "id": "bop_gdp6_q?geo=BG&bop_item=CA&stk_flow=BAL&partner=WRL_REST",
        "region": "BG",
        "name_bg": "Текуща сметка (% от БВП)",
        "name_en": "Current Account to GDP",
        "lens": ["external"],
        "peer_group": "current_account",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "quarterly",
        "typical_release": "end_quarter",
        "revision_prone": True,
        "narrative_hint": "Показва външните дисбаланси на икономиката.",
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

def validate_catalog() -> list[str]:
    """Валидира каталога за грешки."""
    errors = []
    for k, v in SERIES_CATALOG.items():
        if v.get("source") not in ALLOWED_SOURCES:
            errors.append(f"{k}: invalid source {v.get('source')}")
        if v.get("region") not in ALLOWED_REGIONS:
            errors.append(f"{k}: invalid region {v.get('region')}")
        for l in v.get("lens", []):
            if l not in ALLOWED_LENSES:
                errors.append(f"{k}: invalid lens {l}")
        if v.get("transform") not in ALLOWED_TRANSFORMS:
            errors.append(f"{k}: invalid transform {v.get('transform')}")
    return errors
