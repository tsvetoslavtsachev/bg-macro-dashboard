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
    inflation_anchor(value)              → котвеният прочит: пп от целта + зона
    perceived_inflation_reading(series)  → усещаната инфлация + епохалният ѝ контекст
    inflation_voices(snapshot)           → двата гласа, готови за двете повърхности
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from urllib.parse import quote

import pandas as pd

from catalog.polarity import INFLATION_TARGET
from catalog.series import SERIES_CATALOG
from config import (
    ECB_DATA_PORTAL,
    ECB_SEARCH,
    EUROSTAT_DATABROWSER,
    INFLATION_ANCHOR_COLORS,
    LENS_SUBJECTS_BG,
    STALE_AFTER_MONTHS,
)
from core.primitives import apply_transform


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

    Функцията е GENERIC по набор — наборът идва от каталожното id, не е зашит
    „BSI". Живо проверено 26.07.2026 и за MIR:
    `/data/datasets/MIR/MIR.M.BG.B.A2A.A.R.A.2240.EUR.N` → 200.
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


# ═════════════════════════════════════════════════════════════════════════════
# КОТВЕНИЯТ ПРОЧИТ НА ИНФЛАЦИЯТА — вторият глас (мандат №48)
# ═════════════════════════════════════════════════════════════════════════════
# U-score-ът в композита мери инфлацията ОТНОСИТЕЛНО: колко σ е отклонението от
# целта спрямо собствената разсейка на серията. Това е верният уред за
# агрегация, но е системно МЕК за България — в страна, свикнала с висока
# инфлация, „нормалното" отклонение е голямо и 5% излиза по-малко тревожно,
# отколкото е. И 2007 беше „нормално" висока инфлация.
#
# Затова тук стои ВТОРИ, АБСОЛЮТЕН глас: колко процентни пункта сме от целта.
# Зоните са ФИКСИРАНИ политики-смислени котви, НЕ калибрирани по историята —
# ако ги калибрираме, връщаме същата мекота, която котвата трябва да поправи.
#
# Двата гласа НЕ се смесват: котвата не пипа нито score, нито композит.
ANCHOR_GREEN_PP = 1.0    # |отклонение| ≤ 1 пп → при целта
ANCHOR_YELLOW_PP = 2.0   # 1 < |отклонение| ≤ 2 пп → отклонена

ANCHOR_ZONE_LABELS_BG = {
    "green": "при целта",
    "yellow": "отклонена",
    "red": "далеч от целта",
}

ANCHOR_ZONE_PHRASES_BG = {
    "green": "зелена зона",
    "yellow": "жълта зона",
    "red": "червена зона",
}

# Изречението, което пази двата гласа разделени — цитира се и от лицето, и от
# context експорта (ЕДИН източник, ФОРМА-КАНОН).
ANCHOR_DISCLAIMER = (
    "Котвите НЕ пипат композита — U-score-ът остава гласът в него; това е "
    "вторият, абсолютен глас."
)

# Сериите, на които се слага котва (официалните измерители на инфлацията).
ANCHOR_KEYS = ("BG_HICP", "BG_HICP_CORE")
HEADLINE_ANCHOR_KEY = "BG_HICP"

# Контекстната серия + епохата, спрямо която се чете (инфлационната криза).
PERCEIVED_KEY = "BG_INFL_PERCEIVED"
CRISIS_EPOCH_START = "2021-01-01"
CRISIS_EPOCH_END = "2023-12-31"


def fmt_target(target: float) -> str:
    """2.0 → „2%"; 2.5 → „2.5%". Целта се показва както се говори."""
    return f"{float(target):g}%"


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value)


def inflation_anchor(value: Optional[float], target: float = INFLATION_TARGET) -> dict:
    """Котвеният прочит на едно инфлационно число: пп от целта + зона.

    `gap_pp` е ЗНАКОВ (над/под целта), зоната е по |gap| със `≤` семантика:
    ≤1 пп зелено · 1–2 пп жълто · >2 пп червено. Дефлационната посока минава
    през същите зони огледално — отклонението е отклонение и надолу.
    """
    if _is_missing(value):
        return {
            "value": None, "target": float(target), "gap_pp": None,
            "zone": None, "label_bg": None, "color": None,
            "value_str": "—", "gap_phrase": "", "zone_phrase": "",
            "sentence": "—",
        }

    value = float(value)
    gap = round(value - float(target), 1)
    spread = abs(gap)

    if spread <= ANCHOR_GREEN_PP:
        zone = "green"
    elif spread <= ANCHOR_YELLOW_PP:
        zone = "yellow"
    else:
        zone = "red"

    target_str = fmt_target(target)
    if gap == 0:
        gap_phrase = f"точно на целта ({target_str})"
    else:
        direction = "над целта" if gap > 0 else "под целта"
        gap_phrase = f"{spread:.1f} пп {direction} ({target_str})"

    zone_phrase = ANCHOR_ZONE_PHRASES_BG[zone]
    return {
        "value": value,
        "target": float(target),
        "gap_pp": gap,
        "zone": zone,
        "label_bg": ANCHOR_ZONE_LABELS_BG[zone],
        "color": INFLATION_ANCHOR_COLORS[zone],
        "value_str": f"{value:.1f}%",
        "gap_phrase": gap_phrase,
        "zone_phrase": zone_phrase,
        "sentence": f"{value:.1f}% = {gap_phrase} — {zone_phrase}",
    }


def crisis_epoch_label(
    start: str = CRISIS_EPOCH_START, end: str = CRISIS_EPOCH_END
) -> str:
    """`2021-01-01`, `2023-12-31` → „2021-23" — етикетът се ИЗВЕЖДА, не се зашива."""
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    return f"{a.year}-{str(b.year)[-2:]}"


def perceived_inflation_reading(
    series: Optional[pd.Series],
    official: Optional[float] = None,
    *,
    epoch_start: str = CRISIS_EPOCH_START,
    epoch_end: str = CRISIS_EPOCH_END,
) -> Optional[dict]:
    """Усещаната инфлация + епохалният ѝ контекст — детерминистично от данните.

    „Нива като 2021-23" се ТВЪРДИ само ако текущата стойност е ≥ медианата на
    епохата, изчислена от самата серия. Нула зашити литерали: ако утре
    възприятието слезе, изречението се сменя само.
    """
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    if s.empty:
        return None

    value = float(s.iloc[-1])
    last_date = (
        s.index[-1].strftime("%Y-%m")
        if isinstance(s.index, pd.DatetimeIndex)
        else str(s.index[-1])
    )

    epoch_median = None
    if isinstance(s.index, pd.DatetimeIndex):
        epoch = s[(s.index >= pd.Timestamp(epoch_start))
                  & (s.index <= pd.Timestamp(epoch_end))]
        if len(epoch):
            epoch_median = round(float(epoch.median()), 1)

    label = crisis_epoch_label(epoch_start, epoch_end)
    at_crisis_levels = epoch_median is not None and value >= epoch_median

    parts = [f"Усещаната (ЕК анкета): {value:.1f}"]
    if at_crisis_levels:
        parts.append(f" — нива като {label}")
    elif epoch_median is not None:
        parts.append(f" — под медианата на {label} ({epoch_median:.1f})")
    if not _is_missing(official):
        parts.append(f"; официалната е {float(official):.1f}%")

    return {
        "value": round(value, 1),
        "last_date": last_date,
        "n": int(len(s)),
        "epoch_label": label,
        "epoch_median": epoch_median,
        "at_crisis_levels": bool(at_crisis_levels),
        "official": None if _is_missing(official) else round(float(official), 1),
        "sentence": "".join(parts),
    }


def _last_transformed(snapshot: dict, key: str, spec: dict) -> pd.Series:
    """Серията както се ЧЕТЕ (след каталожната трансформация), без празни точки."""
    s = snapshot.get(key) if snapshot else None
    if s is None or len(s) == 0:
        return pd.Series(dtype="float64")
    return apply_transform(s, spec.get("transform", "level")).dropna()


def inflation_voices(
    snapshot: dict,
    catalog: Optional[dict] = None,
    target: float = INFLATION_TARGET,
) -> dict:
    """Двата гласа за инфлацията, готови за ДВЕТЕ повърхности (ФОРМА-КАНОН).

    Връща `{"anchors": [...], "perceived": {...} | None, "disclaimer": ...}` —
    лицето и `briefing_context` четат ЕДИН източник, за да не се разминат.
    """
    catalog = SERIES_CATALOG if catalog is None else catalog

    anchors: list[dict] = []
    official: Optional[float] = None
    for key in ANCHOR_KEYS:
        spec = catalog.get(key)
        if not spec:
            continue
        s = _last_transformed(snapshot, key, spec)
        if s.empty:
            continue
        value = float(s.iloc[-1])
        row = inflation_anchor(value, target)
        row.update({
            "key": key,
            "name_bg": spec.get("name_bg", key),
            "last_date": (
                s.index[-1].strftime("%Y-%m")
                if isinstance(s.index, pd.DatetimeIndex) else str(s.index[-1])
            ),
        })
        anchors.append(row)
        if key == HEADLINE_ANCHOR_KEY:
            official = value

    perceived = None
    spec = catalog.get(PERCEIVED_KEY)
    if spec:
        s = _last_transformed(snapshot, PERCEIVED_KEY, spec)
        perceived = perceived_inflation_reading(s, official=official)
        if perceived is not None:
            perceived["key"] = PERCEIVED_KEY
            perceived["name_bg"] = spec.get("name_bg", PERCEIVED_KEY)

    return {
        "anchors": anchors,
        "perceived": perceived,
        "disclaimer": ANCHOR_DISCLAIMER,
    }
