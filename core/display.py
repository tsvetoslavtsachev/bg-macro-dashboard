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
    epoch_label(start, end)              → „2021-23" / „2024-сега" от границите
    perceived_inflation_reading(series)  → усещаната инфлация + епохалният ѝ контекст
    inflation_voices(snapshot)           → двата гласа, готови за двете повърхности
    rents_epochs_reading(series)         → наемите през трите сравними епохи
    housing_hypotheses(snapshot)         → двете хипотези за жилищния бум, с ЖИВИ числа
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
    EPOCH_NAMES_BG,
    EPOCHS,
    EUROSTAT_DATABROWSER,
    INFLATION_ANCHOR_COLORS,
    LENS_SUBJECTS_BG,
    POST_HYPERINFLATION_END,
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
    """Линкът на серията се разклонява по източник — един вход за дисплея.

    ИЗВЕДЕНАТА серия (`source: "derived"`, мандат №54) няма собствен
    първоизточник — нейното „id" е РЕЦЕПТА, не адрес. Затова тук се връща
    празен низ и лицето я показва без линк: по-добре без линк, отколкото с
    линк, който сочи някъде, откъдето числото не идва. Съставките ѝ си имат
    свои редове със свои линкове.
    """
    src = (source or "").strip().lower()
    if src == "derived":
        return ""
    if src == "ecb":
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
# ⚠ Мандат №55: границите вече ЖИВЕЯТ в `config.EPOCHS`. Двете имена долу
# остават като ТЪНКИ ПСЕВДОНИМИ — нищо не се чупи по import, но литералът е
# един за целия дашборд.
PERCEIVED_KEY = "BG_INFL_PERCEIVED"
CRISIS_EPOCH_START, CRISIS_EPOCH_END = EPOCHS["crisis"]


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


def epoch_label(
    start: str = CRISIS_EPOCH_START, end: Optional[str] = CRISIS_EPOCH_END
) -> str:
    """`2021-01-01`, `2023-12-31` → „2021-23" — етикетът се ИЗВЕЖДА, не се зашива.

    ОТВОРЕНАТА епоха (`end=None`, мандат №55) чете „2024-сега": границата ѝ е
    последното наблюдение, не година, която някой трябва да помни да мести.
    """
    a = pd.Timestamp(start)
    if end is None:
        return f"{a.year}-сега"
    b = pd.Timestamp(end)
    return f"{a.year}-{str(b.year)[-2:]}"


# Старото име (мандат №48) — тънък псевдоним, за да не се чупи нито един import.
crisis_epoch_label = epoch_label


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

    label = epoch_label(epoch_start, epoch_end)
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


# ═════════════════════════════════════════════════════════════════════════════
# ДВЕТЕ ХИПОТЕЗИ ЗА КРЕДИТНО-ЖИЛИЩНИЯ БУМ — ЖИВИ (мандат №54)
# ═════════════════════════════════════════════════════════════════════════════
# До №54 блокът беше ръчна снимка с дата: числата се преписваха на две
# повърхности (методологията и context експортът) и остаряваха мълчаливо, а
# едно от тях се оказа сдвоило най-свеж кредитен сток с по-стар БВП. Сега
# кредитната страна е ЖИВ дериват (`BG_CREDIT_GDP_HH`), а този блок е ЕДИНИЯТ
# източник, който двете повърхности ЦИТИРАТ — прецедентът е `inflation_voices`.
#
# Забраната остава кодирана: нито едно изречение тук не отсъжда коя хипотеза е
# вярната. Уредът вижда съвпадението, не причината.

HOUSING_RATIO_KEY = "BG_CREDIT_GDP_HH"
HOUSING_CREDIT_KEY = "BG_LOANS_HH"
HOUSING_NGDP_KEY = "BG_NGDP"
HOUSING_RENTS_KEY = "BG_RENTS"

# Реперът „преди голямата криза": последното тримесечие на 2008 — моментът,
# с който се сравнява днешното ниво.
PRE_CRISIS_QUARTER = "2008-10-01"
# Котвата на темпа: дъното на сегашната вълна (краят на 2022).
PACE_ANCHOR_QUARTER = "2022-10-01"
# Прозорецът, в който „връх" значи и „свит знаменател": рецесията 2009-10 сви
# БВП, а кредитният сток не се сви със същия темп — съотношението скочи, без
# някой да е взел нов заем. Върхът вътре в прозореца пътува с тази уговорка.
CRISIS_DENOMINATOR_WINDOW = ("2008-07-01", "2010-12-31")
CRISIS_DENOMINATOR_NOTE = (
    "свит знаменател в кризата 2009-10: съотношението скочи без нов кредит"
)
# Спокойната епоха, спрямо която се чете наемният темп. Псевдоним на
# `config.EPOCHS["calm"]` от мандат №55 — литералът вече е един за дашборда.
CALM_EPOCH = EPOCHS["calm"]

# ── РЪЧНАТА СНИМКА, която №54 НЕ дерайва ─────────────────────────────────────
# Заместващата хипотеза стъпва на съотношението „компенсации срещу цени на
# жилищата" от 2015 насам. То е ръчна сверка с ДАТА (мандат №51) и остава
# такова нарочно: №54 дерайва само кредитната страна. Литералите стоят ТУК,
# с етикета си, вместо да се преписват на две повърхности.
SUBSTITUTION_SNAPSHOT = {
    "as_of": "29.07.2026",
    "since_year": 2015,
    "compensation_pct": 213,
    "hpi_pct": 176,
    "caveat": "агрегатна МАСА, не заплата на човек",
}

# Историческият урок, който пътува с ливъриджната хипотеза.
LEVERAGE_LESSON = (
    "Мотивът на купувача не е защитата: и owner-occupier бум с реални доходи "
    "(Ирландия 2005-07) завършва зле — уязвимостта е ливъриджът на новите "
    "ценови нива."
)

# Изречението, което пази равностойността. Формулировката е нарочно без думата
# „победител" — уредът не участва в състезание, той просто не отсъжда.
HOUSING_EQUIVALENCE = (
    "Двете четения стоят РАВНОСТОЙНО: уредът вижда СЪВПАДЕНИЕТО (цената на "
    "актива и кредитът се движат заедно), но не отсъжда коя от двете е "
    "причината. Нито една не е установена."
)


def _quarter_label(ts) -> str:
    """`2009-10-01` → „2009Q4" — тримесечието както се говори."""
    return str(pd.Timestamp(ts).to_period("Q"))


def _at(series: pd.Series, when: str) -> Optional[float]:
    """Стойността на точна дата, или None — без интерполация и без съседи."""
    try:
        ts = pd.Timestamp(when)
    except Exception:
        return None
    if ts not in series.index:
        return None
    return float(series.loc[ts])


def credit_gdp_reading(series: Optional[pd.Series]) -> Optional[dict]:
    """Кредит/БВП: къде сме, къде е върхът, откога и с какъв темп се качва.

    Всяко число идва от самата серия. „Върхът" е МАКСИМУМЪТ на историята ѝ, не
    прозорец по вкус — ако утре днешната точка го надмине, изречението се сменя
    само (`peak_is_now`).
    """
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    if s.empty or not isinstance(s.index, pd.DatetimeIndex):
        return None

    value = float(s.iloc[-1])
    last_ts = s.index[-1]
    peak_ts = s.idxmax()
    peak = float(s.loc[peak_ts])
    peak_is_now = peak_ts == last_ts

    lo, hi = CRISIS_DENOMINATOR_WINDOW
    peak_in_crisis = pd.Timestamp(lo) <= peak_ts <= pd.Timestamp(hi)

    pre_crisis = _at(s, PRE_CRISIS_QUARTER)
    pace_from = _at(s, PACE_ANCHOR_QUARTER)
    pace = None
    if pace_from is not None:
        years = (last_ts - pd.Timestamp(PACE_ANCHOR_QUARTER)).days / 365.25
        if years > 0:
            pace = round((value - pace_from) / years, 1)

    parts = [f"Кредит домакинства/БВП: {value:.1f}% ({_quarter_label(last_ts)})"]
    if peak_is_now:
        parts.append(" — това е най-високото в историята на серията")
    else:
        where = "под" if value < peak else "над"
        parts.append(
            f" — {where} цикличния връх {peak:.1f}% "
            f"({_quarter_label(peak_ts)})"
        )
        if peak_in_crisis:
            parts.append(f" [{CRISIS_DENOMINATOR_NOTE}]")
    if pre_crisis is not None:
        diff = value - pre_crisis
        rel = "около" if abs(diff) < 1.0 else ("над" if diff > 0 else "под")
        parts.append(
            f"; {rel} нивото от {_quarter_label(PRE_CRISIS_QUARTER)} "
            f"({pre_crisis:.1f}%)"
        )
    if pace is not None and pace_from is not None:
        parts.append(
            f"; темп {pace:+.1f} пп/год. от {_quarter_label(PACE_ANCHOR_QUARTER)} "
            f"({pace_from:.1f}%)"
        )
    parts.append(".")

    return {
        "key": HOUSING_RATIO_KEY,
        "value": round(value, 1),
        "last_date": _quarter_label(last_ts),
        "n": int(len(s)),
        "peak_value": round(peak, 1),
        "peak_date": _quarter_label(peak_ts),
        "peak_is_now": bool(peak_is_now),
        "peak_in_crisis": bool(peak_in_crisis),
        "peak_note": CRISIS_DENOMINATOR_NOTE if peak_in_crisis else "",
        "pre_crisis_value": None if pre_crisis is None else round(pre_crisis, 1),
        "pre_crisis_date": _quarter_label(PRE_CRISIS_QUARTER),
        "pace_pp_per_year": pace,
        "pace_from_value": None if pace_from is None else round(pace_from, 1),
        "pace_from_date": _quarter_label(PACE_ANCHOR_QUARTER),
        "sentence": "".join(parts),
    }


def credit_gdp_gap(
    snapshot: dict, catalog: Optional[dict] = None
) -> Optional[dict]:
    """Разривът „кредитен ръст − номинален ръст" — в ПОКАЗВАНИТЕ числа.

    Двете страни се четат след каталожната си трансформация, за да е разривът
    точно разликата на двете числа, които стоят на таблото. Иначе експортът би
    твърдял разлика, която читателят не може да сметне сам.
    """
    catalog = SERIES_CATALOG if catalog is None else catalog
    spec_credit, spec_ngdp = catalog.get(HOUSING_CREDIT_KEY), catalog.get(HOUSING_NGDP_KEY)
    if not spec_credit or not spec_ngdp:
        return None

    credit = _last_transformed(snapshot, HOUSING_CREDIT_KEY, spec_credit)
    ngdp = _last_transformed(snapshot, HOUSING_NGDP_KEY, spec_ngdp)
    if credit.empty or ngdp.empty:
        return None

    # Разривът се смята от ПОКАЗВАНИТЕ (закръглени) числа, не от суровите:
    # иначе експортът би твърдял разлика, която читателят не може да сметне
    # сам от двете числа пред очите си.
    c_val = round(float(credit.iloc[-1]), 1)
    g_val = round(float(ngdp.iloc[-1]), 1)
    gap = round(c_val - g_val, 1)
    return {
        "credit_yoy": c_val,
        "credit_date": _quarter_label(credit.index[-1]),
        "ngdp_yoy": g_val,
        "ngdp_date": _quarter_label(ngdp.index[-1]),
        "gap_pp": gap,
        "sentence": (
            f"Разрив „кредит домакинства − номинален БВП“: {c_val:.1f}% г/г "
            f"({_quarter_label(credit.index[-1])}) срещу {g_val:.1f}% г/г "
            f"({_quarter_label(ngdp.index[-1])}) = {gap:+.1f} пп."
        ),
    }


# ═════════════════════════════════════════════════════════════════════════════
# НАЕМИТЕ ПРЕЗ ЕПОХИТЕ — епохният прочит (мандат №55)
# ═════════════════════════════════════════════════════════════════════════════
# До №55 наемите се четяха срещу ЕДНА епоха (спокойната 2015-19) и от това
# излизаше едно вярно, но полу-изречение: „кратно над спокойната норма". То не
# казваше кое е ГОРЕЩОТО сравнение — че днешният темп стои НАД медианата на
# самата инфлационна криза, т.е. наемната инфлация след кризата не спря, а се
# ускори. Затова прочитът минава през ТРИТЕ сравними епохи наведнъж.
#
# Прецедентът е `perceived_inflation_reading` (мандат №48): нула зашити
# литерали, всяка претенция УСЛОВНА. Ако утре наемите слязат под кризисната
# медиана, изречението се сменя САМО — никой не пипа код.
#
# Уговорката за опашката също е ИЗВЕДЕНА, не зашита: залепя се само когато
# серията наистина тръгва отпреди края на хиперинфлационната опашка.

# Кои епохи са СРАВНИМИ (редът е редът на четене: норма → криза → днес).
RENTS_EPOCH_KEYS = ("calm", "crisis", "current")


def _epoch_stats(s: pd.Series, key: str, start: str,
                 end: Optional[str]) -> Optional[dict]:
    """{key, name_bg, label, median, max, min, n} за един прозорец от серията.

    Отворената епоха (`end is None`) се затваря на ПОСЛЕДНОТО наблюдение, а не
    на днешната дата — прозорецът е на данните, не на календара.
    """
    lo = pd.Timestamp(start)
    hi = pd.Timestamp(end) if end is not None else s.index[-1]
    part = s[(s.index >= lo) & (s.index <= hi)]
    if part.empty:
        return None
    return {
        "key": key,
        "name_bg": EPOCH_NAMES_BG.get(key, key),
        "label": epoch_label(start, end),
        "median": round(float(part.median()), 1),
        "max": round(float(part.max()), 1),
        "min": round(float(part.min()), 1),
        "n": int(len(part)),
    }


def rents_epochs_reading(
    series: Optional[pd.Series],
    *,
    epochs: Optional[dict] = None,
    tail_end: str = POST_HYPERINFLATION_END,
) -> Optional[dict]:
    """Наемите през трите сравними епохи — детерминистично от самата серия.

    Връща `{value, last_date, n, epochs, by_key, claims, tail, sentence}`.
    Медианите и максимумите се СМЯТАТ, етикетите се ИЗВЕЖДАТ от границите.

    Претенциите са УСЛОВНИ (кодирана честност, прецедентът на „нива като
    2021-23"):
      · „над медианата на кризисната епоха" — САМО ако `value ≥` тази медиана;
        иначе изречението казва „под“ и думите „над медианата“ ги няма;
      · кратността спрямо спокойната се СМЯТА от показваните (закръглени) числа,
        за да може читателят да я провери сам, и носи „над" само когато е ≥1;
      · откатът от върха на текущата епоха е ОПИСАТЕЛЕН (`value < epoch max`).

    Уговорката за следхиперинфлационната опашка се залепя само ако серията
    наистина тръгва отпреди `tail_end` — серия от 2005 нататък не я носи.
    """
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    if s.empty or not isinstance(s.index, pd.DatetimeIndex):
        return None

    epochs = EPOCHS if epochs is None else epochs
    value = float(s.iloc[-1])
    rows = [
        st for st in (
            _epoch_stats(s, key, *epochs[key])
            for key in RENTS_EPOCH_KEYS if key in epochs
        ) if st is not None
    ]
    by_key = {st["key"]: st for st in rows}
    calm, crisis, current = (by_key.get(k) for k in ("calm", "crisis", "current"))

    above_crisis = crisis is not None and value >= crisis["median"]
    multiple = None
    if calm is not None and calm["median"] > 0:
        multiple = round(round(value, 1) / calm["median"], 1)
    at_peak = current is not None and round(value, 1) >= current["max"]

    # ── Опашката: уговорка, не епоха ─────────────────────────────────────────
    tail = None
    tail_ts = pd.Timestamp(tail_end)
    if s.index[0] <= tail_ts:
        part = s[s.index <= tail_ts]
        tail = {
            "label": f"{s.index[0].year}-{tail_ts.year}",
            "median": round(float(part.median()), 1),
            "max": round(float(part.max()), 1),
            "n": int(len(part)),
            "note": (
                f"⚠ Опашката {s.index[0].year}-{tail_ts.year} (макс "
                f"{float(part.max()):.1f}% г/г) е следхиперинфлационна и НЕ "
                f"влиза в сравненията."
            ),
        }

    parts = [f"Наемите: {value:.1f}% г/г ({s.index[-1].strftime('%Y-%m')})"]
    if crisis is not None:
        where = "над" if above_crisis else "под"
        parts.append(
            f" — {where} медианата на {crisis['name_bg']} епоха "
            f"{crisis['label']} ({crisis['median']:.1f}%)"
        )
    if multiple is not None:
        rel = "над" if multiple >= 1 else "спрямо"
        parts.append(
            f"; {multiple:.1f}× {rel} {calm['name_bg']} {calm['label']} "
            f"({calm['median']:.1f}%)"
        )
    if current is not None:
        where = "на върха на" if at_peak else "с откат от върха на"
        parts.append(
            f"; {where} {current['name_bg']} епоха {current['label']} "
            f"({current['max']:.1f}%)"
        )
    parts.append(".")
    if tail is not None:
        parts.append(f" {tail['note']}")

    return {
        "key": HOUSING_RENTS_KEY,
        "value": round(value, 1),
        "last_date": s.index[-1].strftime("%Y-%m"),
        "n": int(len(s)),
        "epochs": rows,
        "by_key": by_key,
        "claims": {
            "above_crisis_median": bool(above_crisis),
            "multiple_of_calm": multiple,
            "at_current_peak": bool(at_peak),
            "off_current_peak": bool(current is not None and not at_peak),
        },
        "tail": tail,
        "sentence": "".join(parts),
    }


def rents_reading(
    snapshot: dict, catalog: Optional[dict] = None
) -> Optional[dict]:
    """Наемите срещу спокойната си норма — дискриминаторът на заместващата.

    ⚠ Мандат №55: спокойната медиана НЕ се смята повторно тук. Тя идва от
    `rents_epochs_reading` — ЕДИН източник, за да не могат хипотезният ред и
    епохният прочит да се разминат по число, докато стоят на едно лице.
    """
    catalog = SERIES_CATALOG if catalog is None else catalog
    spec = catalog.get(HOUSING_RENTS_KEY)
    if not spec:
        return None
    s = _last_transformed(snapshot, HOUSING_RENTS_KEY, spec)
    if s.empty:
        return None

    epochs = rents_epochs_reading(s)
    if epochs is None:
        return None

    value = float(s.iloc[-1])
    calm = (epochs["by_key"] or {}).get("calm")
    calm_median = calm["median"] if calm else None
    label = calm["label"] if calm else epoch_label(*CALM_EPOCH)
    cooling = calm_median is not None and value <= calm_median

    reading = f"наемите растат с {value:.1f}% г/г"
    if calm_median is not None:
        reading += f" при медиана {calm_median:.1f}% за {label}"
    parts = [reading[0].upper() + reading[1:]]
    if calm_median is not None:
        parts.append(" — наемният пазар НЕ се охлажда" if not cooling
                     else " — наемният пазар се охлажда")
    parts.append(".")

    return {
        "key": HOUSING_RENTS_KEY,
        "value": round(value, 1),
        "reading": reading,
        "last_date": epochs["last_date"],
        "calm_median": calm_median,
        "calm_label": label,
        "cooling": bool(cooling),
        "epochs": epochs,
        "sentence": "".join(parts),
    }


def _substitution_hypothesis(rents: Optional[dict]) -> dict:
    """Заместващата: доходите изместват наема с покупка."""
    snap = SUBSTITUTION_SNAPSHOT
    claim = (
        f"растящите доходи изместват наема с покупка, т.е. търсенето е "
        f"потребителско, а не спекулативно — компенсацията на наетите е "
        f"+{snap['compensation_pct']}% срещу +{snap['hpi_pct']}% на цените на "
        f"жилищата от {snap['since_year']} насам "
        f"(ръчна сверка към {snap['as_of']}; {snap['caveat']})."
    )
    falsifier = (
        "Пада, ако наемният пазар не се охлажда: бягство от наема би свило "
        "наемното търсене."
    )
    if rents:
        falsifier += f" Живо: {rents['reading']}"
        falsifier += (
            " — условието тегли СРЕЩУ нея."
            if not rents["cooling"] else
            " — условието е в нейна полза."
        )
    return {
        "key": "substitution",
        "name": "заместващата",
        "is_live": False,
        "claim": claim,
        "sentence": f"Заместващата: {claim}",
        "falsifier": falsifier,
    }


def _leverage_hypothesis(
    ratio: Optional[dict], gap: Optional[dict]
) -> dict:
    """Ливъриджната: цените се качват на кредит."""
    claim = "цените се качват на кредит."
    if ratio:
        claim += f" {ratio['sentence']}"
    if gap:
        claim += f" {gap['sentence']}"

    falsifier = (
        "Пада, ако съотношението кредит/БВП спре да се качва и разривът спрямо "
        "номиналния ръст се затвори."
    )
    live = []
    if ratio and ratio.get("pace_pp_per_year") is not None:
        live.append(f"темпът е {ratio['pace_pp_per_year']:+.1f} пп/год.")
    if gap:
        live.append(f"разривът е {gap['gap_pp']:+.1f} пп")
    if live:
        rising = bool(ratio and (ratio.get("pace_pp_per_year") or 0) > 0)
        widening = bool(gap and gap["gap_pp"] > 0)
        state = ("нито едното не е налице" if (rising and widening)
                 else "условието е частично налице" if (rising or widening)
                 else "условието е налице")
        falsifier += f" Живо: {' и '.join(live)} — {state}."
    return {
        "key": "leverage",
        "name": "ливъриджната",
        "is_live": True,
        "claim": claim,
        "sentence": f"Ливъриджната: {claim}",
        "falsifier": falsifier,
        "lesson": LEVERAGE_LESSON,
    }


def _revision_note(ratio: Optional[dict]) -> str:
    """Честната ревизия (мандат №54 §0б) — неутрално, с живото число.

    Класът на грешката се именува, не се крие: ръчната сверка сдвояваше
    най-свежия кредитен сток с по-стар БВП. Живата серия го прави невъзможно,
    защото ражда тримесечие само когато и двете страни са налични.
    """
    note = (
        "Ревизия (мандат №54, 29.07.2026): кредитната страна вече е ЖИВ дериват "
        "на тримесечно изравнена конвенция и замества ръчната сверка отпреди "
        "нея. Ръчната сверка е сдвоявала най-свежия кредитен сток с по-стар БВП "
        "и е давала по-високо ниво и по-бърз темп; живата серия ражда "
        "тримесечие само когато и двете страни са налични."
    )
    if ratio and not ratio["peak_is_now"] and ratio["value"] < ratio["peak_value"]:
        note += (
            f" Следствие за разказа: ливъриджната хипотеза губи най-острата си "
            f"реплика — днешните {ratio['value']:.1f}% са ПОД цикличния връх "
            f"{ratio['peak_value']:.1f}% ({ratio['peak_date']}), не над него — "
            f"но пази посоката."
        )
    return note


def housing_hypotheses(
    snapshot: dict, catalog: Optional[dict] = None
) -> dict:
    """Двете хипотези за кредитно-жилищния бум, готови за ДВЕТЕ повърхности.

    Връща `{"ratio", "gap", "rents", "rents_epochs", "hypotheses", "revision",
    "equivalence", "available"}`. Методологичната страница и `briefing_context`
    ЦИТИРАТ оттук (ФОРМА-КАНОН: един източник), затова не могат да се разминат
    по число или по формулировка.

    `rents_epochs` (мандат №55) е СЪЩИЯТ обект, който виси и вътре в `rents` —
    изнесен на върха само за да го четат повърхностите на едно ниво. Не е втора
    сметка: спокойната медиана в наемния ред ИДВА оттам.
    """
    catalog = SERIES_CATALOG if catalog is None else catalog

    ratio = credit_gdp_reading((snapshot or {}).get(HOUSING_RATIO_KEY))
    gap = credit_gdp_gap(snapshot or {}, catalog)
    rents = rents_reading(snapshot or {}, catalog)

    return {
        "available": bool(ratio or gap or rents),
        "ratio": ratio,
        "gap": gap,
        "rents": rents,
        "rents_epochs": (rents or {}).get("epochs"),
        "hypotheses": [
            _substitution_hypothesis(rents),
            _leverage_hypothesis(ratio, gap),
        ],
        "revision": _revision_note(ratio),
        "equivalence": HOUSING_EQUIVALENCE,
    }
