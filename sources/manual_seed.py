"""
sources/manual_seed.py
======================
Дългата кредитна памет: БНБ seed (2005Q4+) зашит с ЕЦБ BSI (2022+).

Проблемът, който решава: ЕЦБ Data Portal държи българските кредитни салда само
от 01.2022 — три и половина години, при това изцяло в бум период. Норма върху
такъв прозорец подценява екстремността. Първоизточникът (БНБ „Кредитна
динамика“) публикува същите редове **тримесечно от 2005Q4**; seed-ът е
екстрахиран веднъж (`scripts/extract_bnb_seed.py`) и живее като комитнат CSV.

Дизайнът:
  1. API-то е месечно → взимат се само наблюденията от месеци 3/6/9/12, т.е.
     ЗАВЪРШЕНИТЕ тримесечия. Частичното текущо тримесечие не влиза — иначе
     „последната точка“ би сравнявала два месеца с три.
  2. Seed тримесечията ПРЕДИ първото API тримесечие се слагат отпред.
  3. Шевът се валидира на ВСИЧКИ общи тримесечия: |seed − api| / |api| ≤ 0.5%.
     Нарушение → ValueError, не warning. Двата източника трябва да са един и
     същ поток (БНБ репортва тези данни към ЕЦБ); разминаване значи, че
     дефиницията се е разпаднала и лещата вече не мери каквото твърди.

Цената на този дизайн: кредитната леща се опреснява на ТРИМЕСЕЧИЕ, не месечно.
Купеното срещу нея: пълна 10-годишна норма вместо къс бум прозорец.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
SEED_CSV = BASE_DIR / "data" / "manual" / "bnb_loans_history.csv"

# Ключ в seed-а → ключ в каталога.
SEED_TO_CATALOG = {
    "NFC": "BG_LOANS_NFC",
    "HH": "BG_LOANS_HH",
}

QUARTER_END_MONTHS = (3, 6, 9, 12)
SEAM_TOLERANCE = 0.005          # 0.5% — прагът на мандата


def load_seed(path: Optional[Path | str] = None) -> dict[str, pd.Series]:
    """CSV → {каталожен ключ: тримесечна серия в млн. EUR}.

    Липсващ файл → FileNotFoundError. Seed-ът е предпоставка за кредитната
    леща; тихото му изчезване би върнало късия прозорец без никой да разбере.
    """
    csv_path = Path(path or SEED_CSV)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Липсва БНБ seed-ът: {csv_path}. Пусни scripts/extract_bnb_seed.py "
            f"върху суровината в data/manual/raw/."
        )

    df = pd.read_csv(csv_path, comment="#", parse_dates=["date"])
    missing = {"date", "series", "value_meur"} - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path.name}: липсват колони {sorted(missing)}")

    out: dict[str, pd.Series] = {}
    for seed_key, catalog_key in SEED_TO_CATALOG.items():
        part = df[df["series"] == seed_key]
        if part.empty:
            raise ValueError(f"{csv_path.name}: няма редове за серия '{seed_key}'")
        s = pd.Series(
            part["value_meur"].astype(float).values,
            index=pd.DatetimeIndex(part["date"]),
            name=catalog_key,
        ).sort_index()
        bad = [d for d in s.index if d.month not in QUARTER_END_MONTHS]
        if bad:
            raise ValueError(
                f"{csv_path.name} ({seed_key}): {len(bad)} дати извън края на "
                f"тримесечие, първата е {bad[0].date()}."
            )
        out[catalog_key] = s
    return out


def to_quarterly(s: pd.Series) -> pd.Series:
    """Месечни стокове → тримесечни: само месеци 3/6/9/12.

    Така частичното текущо тримесечие изпада само по себе си — щом месец 6 още
    го няма, второто тримесечие не се появява.
    """
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    if not isinstance(s.index, pd.DatetimeIndex):
        raise TypeError("to_quarterly очаква времеви индекс")
    q = s[s.index.month.isin(QUARTER_END_MONTHS)].dropna().sort_index()
    return q


def validate_seam(
    key: str,
    seed_q: pd.Series,
    api_q: pd.Series,
    tolerance: float = SEAM_TOLERANCE,
) -> list[pd.Timestamp]:
    """Сверява двата източника на ВСИЧКИ общи тримесечия. Връща общите дати.

    Разминаване над `tolerance` → ValueError с квартала и двете стойности.
    Нула общи тримесечия → също ValueError: шев без припокриване е шев без
    проверка.
    """
    common = seed_q.index.intersection(api_q.index)
    if len(common) == 0:
        raise ValueError(
            f"{key}: seed-ът и API-то нямат нито едно общо тримесечие — шевът "
            f"е непроверим (seed {seed_q.index.min()}…{seed_q.index.max()}, "
            f"api {api_q.index.min()}…{api_q.index.max()})."
        )

    for ts in common:
        seed_v = float(seed_q.loc[ts])
        api_v = float(api_q.loc[ts])
        denom = abs(api_v)
        rel = abs(seed_v - api_v) / denom if denom else (0.0 if seed_v == api_v else float("inf"))
        if rel > tolerance:
            raise ValueError(
                f"{key}: шевът се разпада на {ts.date()} — БНБ seed {seed_v:,.3f} "
                f"срещу ЕЦБ BSI {api_v:,.3f} млн. EUR ({rel:.2%} разлика, "
                f"допустимо {tolerance:.2%}). Дефинициите вече не съвпадат."
            )
    return list(common)


def splice_series(
    key: str,
    seed_q: pd.Series,
    api: Optional[pd.Series],
    tolerance: float = SEAM_TOLERANCE,
) -> pd.Series:
    """Един ключ: seed отпред + завършените API тримесечия отзад."""
    api_q = to_quarterly(api) if api is not None else pd.Series(dtype=float)

    if api_q.empty:
        logger.warning(
            "%s: няма завършено тримесечие от ЕЦБ BSI — лещата тръгва само на "
            "БНБ seed-а (до %s).", key, seed_q.index[-1].date() if len(seed_q) else "—",
        )
        return seed_q.copy()

    validate_seam(key, seed_q, api_q, tolerance)

    head = seed_q[seed_q.index < api_q.index[0]]
    spliced = pd.concat([head, api_q]).sort_index()
    spliced.name = key
    return spliced


def splice_loans(
    snapshot: dict[str, pd.Series],
    seed: Optional[dict[str, pd.Series]] = None,
    tolerance: float = SEAM_TOLERANCE,
) -> dict[str, pd.Series]:
    """Единното място, където кредитните серии стават дълги и тримесечни.

    Вика се веднъж след `_build_snapshot`, за да получат ВСИЧКИ консуматори
    (status, HTML, context export) едно и също число.
    """
    seed = seed if seed is not None else load_seed()
    for key, seed_q in seed.items():
        spliced = splice_series(key, seed_q, snapshot.get(key), tolerance)
        snapshot[key] = spliced
        logger.info(
            "%s: %d тримесечия %s → %s (БНБ seed + ЕЦБ BSI)",
            key, len(spliced), spliced.index[0].date(), spliced.index[-1].date(),
        )
    return snapshot
