"""
analysis/temperature.py
=======================
ТЕМПЕРАТУРНИЯТ СЛОЙ — колко бум-серии са НАД зоната си (мандат №47, П2).

Защо отделен слой, а не още едно число в скора:

  · Скорът е ГЛАДЪК и двупосочен — той пада и при прегряване, и при криза, и
    двете падания изглеждат еднакво на 0–100 скалата. „Кредитът е на 40" не
    казва дали заемите тичат, или са замръзнали.
  · Температурата брои САМО горното нарушение: колко от петте бум-серии стоят
    над горния праг на зоната си. Под lo е криза/кредитен крънч — той се чете
    в скора, не в термометъра. Един уред, един въпрос.
  · Праговете са АБСОЛЮТНИ (`catalog/polarity.py`, фиксирани от данни-пас
    28.07.2026), затова числото е смятаемо и НАЗАД без look-ahead: 2007 не
    знае нищо за 2026. Точно това прави приемния гейт възможен —
    2006H2-2008 свети 4-5/5, 2015-2019 мълчи 0/20.

Един източник за „кои са бум-сериите": `TEMP_SERIES` се ИЗВЕЖДА от POLARITY
(всички OPT ключове). Шеста OPT серия утре влиза и в скоринга, и в термометъра
наведнъж — няма втори списък, който да остане назад.

Честност при липсваща стойност: серия без наблюдение към дадената дата НЕ се
брои в `n_total` за тази дата. Ранните маркове на реконструкцията показват
„2/4", а не „2/5" — знаменателят казва колко уред реално стои зад числото.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from catalog.polarity import OPT_PROVENANCE, opt_keys, opt_zone, polarity_for
from core.primitives import apply_transform

# Бум-сериите — изведени от полярностната карта, не преписани (виж докстринга).
TEMP_SERIES: list[str] = opt_keys()


def zone_table(catalog: Optional[dict] = None) -> list[dict]:
    """[{key, name_bg, lo, hi, s, provenance}] — зоните такива, каквито са в кода.

    Лицето и briefing_context рисуват ОТТУК, за да не се преписват прагове по
    места (ФОРМА-КАНОН: един речник).
    """
    rows: list[dict] = []
    for key in TEMP_SERIES:
        lo, hi, width = opt_zone(polarity_for(key))
        spec = (catalog or {}).get(key, {})
        rows.append({
            "key": key,
            "name_bg": spec.get("name_bg", key),
            "lo": lo,
            "hi": hi,
            "s": width,
            "provenance": OPT_PROVENANCE.get(key, ""),
        })
    return rows


def temperature(
    catalog: dict,
    snapshot: dict[str, pd.Series],
    *,
    at: Optional[pd.Timestamp] = None,
) -> dict[str, Any]:
    """Колко бум-серии горят към дадения момент.

    Връща `{n_hot, n_total, hot: [...], cold: [...], as_of}`. `hot` са сериите
    НАД `hi` (прегряването — това, което брои термометърът), `cold` — тези под
    `lo` (кризата; изнесени за контекст, не се броят в `n_hot`).

    `at` реже суровата серия по ПЕРИОДНАТА дата преди трансформацията — същата
    семантика като реконструираната история, затова числото е сравнимо назад.
    """
    hot: list[dict] = []
    cold: list[dict] = []
    n_total = 0
    as_of: Optional[pd.Timestamp] = None

    for key in TEMP_SERIES:
        spec = catalog.get(key)
        if spec is None:
            continue
        raw = snapshot.get(key)
        if raw is None or len(raw) == 0:
            continue
        if at is not None:
            raw = raw[raw.index <= at]
        transformed = apply_transform(raw, spec.get("transform", "level")).dropna()
        if transformed.empty:
            continue      # няма стойност → серията не се брои в знаменателя

        value = float(transformed.iloc[-1])
        last = transformed.index[-1]
        n_total += 1
        as_of = last if as_of is None else max(as_of, last)

        lo, hi, width = opt_zone(polarity_for(key))
        entry = {
            "key": key,
            "name_bg": spec.get("name_bg", key),
            "value": round(value, 2),
            "lo": lo,
            "hi": hi,
            "s": width,
            "last_date": last.strftime("%Y-%m-%d") if hasattr(last, "strftime") else str(last),
        }
        if value > hi:
            hot.append(entry)
        elif value < lo:
            cold.append(entry)

    return {
        "n_hot": len(hot),
        "n_total": n_total,
        "hot": hot,
        "cold": cold,
        "as_of": as_of.strftime("%Y-%m-%d") if as_of is not None else None,
    }


def hot_keys_str(temp: Optional[dict]) -> str:
    """Кой гори, компактно: „BG_LOANS_HH+BG_HPI" (празно при нула)."""
    if not temp:
        return ""
    return "+".join(e["key"] for e in temp.get("hot", []))


def temp_level(n_hot: int) -> str:
    """Трите нива на термометъра: `cold` (0) · `warm` (1-2) · `hot` (≥3).

    Един източник за цвета — лицето чете нивото оттук, не преизмисля прагове.
    """
    if n_hot <= 0:
        return "cold"
    if n_hot <= 2:
        return "warm"
    return "hot"
