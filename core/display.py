"""
core/display.py
===============
Дисплейните примитиви на ФОРМА-КАНОН — един източник за това КАК се показва
число, име и период, за да казват HTML лицето и briefing_context едно и също.

Public API:
    databrowser_url(catalog_id)          → линк към Eurostat първоизточника
    ecb_series_url(catalog_id)           → линк към серията в ECB Data Portal
    source_url(source, catalog_id)       → линкът според източника на серията
    fmt_value(res)                       → „5.20 %" / „95.00" (по is_rate/transform)
    months_old(last_date, today)         → възраст на наблюдението в месеци
    is_stale(last_date, schedule, today) → по-старо от 2× очаквания ритъм?
    thin_window_note(percentile_window)  → обяснението зад ⚠ при къс прозорец
    verdict_sentence(lens_reports)       → „Тежи X (n), крепи Y (m)."
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from urllib.parse import quote

import pandas as pd

from config import (
    ECB_DATA_PORTAL,
    ECB_SEARCH,
    EUROSTAT_DATABROWSER,
    LENS_SUBJECTS_BG,
    STALE_AFTER_MONTHS,
)


def databrowser_url(catalog_id: str) -> str:
    """Каталожно id → стабилен Eurostat databrowser линк.

    `{dataset}` е частта преди `?`: `namq_10_gdp?geo=BG&...` → `namq_10_gdp`.
    """
    dataset = (catalog_id or "").split("?", 1)[0].strip()
    if not dataset:
        return ""
    return EUROSTAT_DATABROWSER.format(dataset=dataset)


def ecb_series_url(catalog_id: str) -> str:
    """Каталожно id `<набор>/<ключ>` → страницата на серията в ECB Data Portal.

    Живо проверено 25.07.2026: порталът иска ключа С префикса на набора —
    `/data/datasets/BSI/BSI.M.BG.…`. Без префикса адресът връща 404.
    Ако id-то не се разложи на набор + ключ → резервно търсене в портала.
    """
    cid = (catalog_id or "").strip()
    if not cid:
        return ""
    flow, _, key = cid.partition("/")
    flow, key = flow.strip(), key.strip()
    if not flow or not key:
        return ECB_SEARCH.format(term=quote(cid, safe=""))
    return ECB_DATA_PORTAL.format(flow=flow, key=key)


def source_url(source: str, catalog_id: str) -> str:
    """Линкът на серията се разклонява по източник — един вход за дисплея."""
    if (source or "").strip().lower() == "ecb":
        return ecb_series_url(catalog_id)
    return databrowser_url(catalog_id)


def fmt_value(res: dict, digits: int = 2) -> str:
    """Стойността както се чете: процент, когато серията е ставка/темп."""
    val = res.get("display_value")
    if val is None or (isinstance(val, float) and val != val):
        return "—"
    txt = f"{float(val):.{digits}f}"
    if res.get("is_rate") or res.get("display_is_pct"):
        return f"{txt} %"
    return txt


def months_old(last_date, today: Optional[date] = None) -> Optional[int]:
    """Колко месеца има наблюдението (по календарни месеци, не по дни)."""
    if not last_date:
        return None
    try:
        d = pd.Timestamp(last_date)
    except Exception:
        return None
    ref = pd.Timestamp(today or date.today())
    return (ref.year - d.year) * 12 + (ref.month - d.month)


def is_stale(last_date, schedule: str = "monthly", today: Optional[date] = None) -> bool:
    """Наблюдението по-старо ли е от 2× очаквания ритъм на публикуване?

    monthly > 2 месеца · quarterly > 6 месеца (виж config.STALE_AFTER_MONTHS).
    """
    age = months_old(last_date, today)
    if age is None:
        return False
    return age > STALE_AFTER_MONTHS.get(schedule, 2)


def stale_note(schedule: str = "monthly") -> str:
    """Обяснението зад ⚠ — какъв ритъм се очакваше."""
    limit = STALE_AFTER_MONTHS.get(schedule, 2)
    return (
        f"Наблюдението е по-старо от {limit} месеца — двойно над очаквания ритъм "
        f"на публикуване ({schedule}). Провери за прекъсване на серията."
    )


def thin_window_note(percentile_window: Optional[str] = None) -> str:
    """Обяснението зад ⚠ при къс прозорец — едно изречение, без жаргон."""
    where = f" ({percentile_window})" if percentile_window else ""
    return (
        f"Нормата е върху къс, изцяло бум период{where} — z-ът подценява "
        f"екстремността."
    )


def verdict_sentence(lens_reports: dict) -> str:
    """Детерминистичен извод от лещовите scores — без свободен текст.

    „Тежи външният сектор (4.4), крепи пазарът на труда (67.4)." Най-слабата и
    най-силната леща с числата им. Без данни → честно изречение, не мълчание.
    """
    scored = [
        (lens, rep["score"])
        for lens, rep in lens_reports.items()
        if rep.get("score") is not None
    ]
    if not scored:
        return "Няма достатъчно данни за извод."

    weakest = min(scored, key=lambda p: (p[1], p[0]))
    strongest = max(scored, key=lambda p: (p[1], -ord(p[0][0])))

    if len(scored) == 1 or weakest[0] == strongest[0]:
        name = LENS_SUBJECTS_BG.get(weakest[0], weakest[0])
        return f"Единствената измерена леща е {name} ({weakest[1]:.1f})."

    return (
        f"Тежи {LENS_SUBJECTS_BG.get(weakest[0], weakest[0])} ({weakest[1]:.1f}), "
        f"крепи {LENS_SUBJECTS_BG.get(strongest[0], strongest[0])} ({strongest[1]:.1f})."
    )
