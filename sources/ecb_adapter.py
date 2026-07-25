"""
sources/ecb_adapter.py
======================
ECB Data Portal SDMX REST адаптер.

Портнат от `dashboards/eu-macro-dashboard/sources/ecb_adapter.py` — същият
формат, същият parser — но лежи върху БГ-версията на `BaseAdapter`
(`fetch_series(source_id)`, кеш-път като единствен аргумент).

Защо е тук: БНБ кредитната статистика не се публикува в Eurostat, а в набора
**BSI** на ECB Data Portal (България репортва в BSI като част от еврозоната).

Endpoint (без автентикация):
  {base}/data/{flowref}/{key}?format=jsondata

  base    = config.ECB_API_BASE ("https://data-api.ecb.europa.eu/service")
  flowref = кодът на набора (BSI, ICP, FM, EXR, …)
  key     = точково-разделените стойности на измеренията

Каталожна конвенция:
  Серията носи source="ecb" и id="<flowref>/<key>", напр.
  "BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E". Адаптерът разцепва на първото '/'.

Отговор: SDMX-JSON 1.0 — https://data-api.ecb.europa.eu/help

Кеш: `data/ecb_cache.json` (комитва се, БГ конвенцията). TTL по
`release_schedule` през `sources/_base.py`.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd
import requests

from config import ECB_API_BASE
from sources._base import BaseAdapter

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = "data/ecb_cache.json"
DEFAULT_TIMEOUT = 30                 # секунди
RETRY_BACKOFF = [1, 3]               # секунди между опитите при преходна грешка
USER_AGENT = "bg-macro-dashboard/0.1"


# ═════════════════════════════════════════════════════════════════════════════
# Период
# ═════════════════════════════════════════════════════════════════════════════

def parse_ecb_period(period: str) -> Optional[pd.Timestamp]:
    """ECB period string → pd.Timestamp на ПЪРВИЯ ден на периода.

    Форматите по честота:
      "2026-05"     месечен
      "2026-Q1"     тримесечен
      "2026"        годишен
      "2026-W03"    седмичен
      "2026-05-15"  дневен

    None при непознат формат — викащият пропуска наблюдението.
    """
    if not isinstance(period, str):
        return None
    period = period.strip()
    if not period:
        return None
    try:
        if "Q" in period:
            year, q = period.split("-Q")
            return pd.Timestamp(year=int(year), month=(int(q) - 1) * 3 + 1, day=1)
        if "W" in period:
            year, w = period.split("-W")
            return pd.Timestamp.fromisocalendar(int(year), int(w), 1)
        if len(period) == 4:
            return pd.Timestamp(year=int(period), month=1, day=1)
        ts = pd.to_datetime(period, errors="coerce")
        return None if pd.isna(ts) else ts
    except (ValueError, AttributeError):
        return None


# ═════════════════════════════════════════════════════════════════════════════
# SDMX-JSON parser
# ═════════════════════════════════════════════════════════════════════════════

def parse_sdmx_json(payload: dict) -> pd.Series:
    """SDMX-JSON 1.0 → pd.Series (индекс = началото на периода).

    Очакваната структура:
      {"dataSets": [{"series": {"0:0:…": {"observations": {"0": [val, …]}}}}],
       "structure": {"dimensions": {"observation": [{"values": [{"id": "2026-05"}, …]}]}}}

    Празен отговор → празна серия. Липсващо измерение на наблюденията →
    ValueError (структурна изненада, не празнота).
    """
    if not isinstance(payload, dict):
        raise ValueError("ECB SDMX отговор: очакваше се обект")

    datasets = payload.get("dataSets") or []
    if not datasets:
        return pd.Series(dtype=float)

    series_dict = (datasets[0] or {}).get("series") or {}
    if not series_dict:
        return pd.Series(dtype=float)

    structure = payload.get("structure") or {}
    dims = (structure.get("dimensions") or {}).get("observation") or []
    if not dims:
        raise ValueError("ECB SDMX отговор: липсва измерение на наблюденията")

    period_strings = [v.get("id", "") for v in (dims[0].get("values") or [])]

    first_key = next(iter(series_dict))
    if len(series_dict) > 1:
        logger.warning(
            "ECB отговорът носи %d серии; каталогът дефинира една — вземаме %s",
            len(series_dict), first_key,
        )
    observations = (series_dict[first_key] or {}).get("observations") or {}

    data: dict[pd.Timestamp, float] = {}
    for obs_idx, obs_array in observations.items():
        try:
            idx = int(obs_idx)
            if idx >= len(period_strings):
                continue
            ts = parse_ecb_period(period_strings[idx])
            if ts is None:
                continue
            value = obs_array[0] if obs_array else None
            if value is None:
                continue
            data[ts] = float(value)
        except (ValueError, TypeError, IndexError) as e:
            logger.debug("Пропуснато наблюдение %s: %s", obs_idx, e)
            continue

    if not data:
        return pd.Series(dtype=float)
    return pd.Series(data).sort_index()


# ═════════════════════════════════════════════════════════════════════════════
# Адаптер
# ═════════════════════════════════════════════════════════════════════════════

class EcbAdapter(BaseAdapter):
    """ECB Data Portal SDMX REST адаптер (кеш + ретраи)."""

    SOURCE_NAME = "ecb"

    def __init__(
        self,
        cache_path: str = DEFAULT_CACHE_PATH,
        base_url: str = ECB_API_BASE,
        timeout: int = DEFAULT_TIMEOUT,
        retry_backoff: Optional[list] = None,
    ):
        super().__init__(cache_path)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_backoff = list(RETRY_BACKOFF if retry_backoff is None else retry_backoff)
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })

    def _build_url(self, source_id: str) -> str:
        """"<flowref>/<key>" → пълният API адрес."""
        cid = (source_id or "").strip()
        if "/" not in cid:
            raise ValueError(
                f"ECB source_id трябва да е '<flowref>/<key>' — получено: '{source_id}'"
            )
        flowref, key = cid.split("/", 1)
        if not flowref.strip() or not key.strip():
            raise ValueError(
                f"ECB source_id трябва да е '<flowref>/<key>' — получено: '{source_id}'"
            )
        return f"{self.base_url}/data/{flowref.strip()}/{key.strip()}?format=jsondata"

    def fetch_series(self, source_id: str) -> pd.Series:
        url = self._build_url(source_id)
        logger.debug("ECB GET %s", url)

        last_error: Optional[Exception] = None
        for attempt in range(len(self.retry_backoff) + 1):
            try:
                response = self._session.get(url, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                last_error = RuntimeError(f"ECB мрежова грешка: {e}")
            else:
                if response.status_code == 404:
                    # 404 е присъда за ключа, не преходна грешка — не се повтаря.
                    raise ValueError(f"ECB 404 Not Found: {source_id}")
                if response.status_code >= 500:
                    last_error = RuntimeError(
                        f"ECB HTTP {response.status_code}: {response.text[:200]}"
                    )
                elif response.status_code >= 400:
                    raise RuntimeError(
                        f"ECB HTTP {response.status_code}: {response.text[:200]}"
                    )
                else:
                    try:
                        payload = response.json()
                    except ValueError as e:
                        raise RuntimeError(f"ECB невалиден JSON: {e}") from e
                    return parse_sdmx_json(payload)

            if attempt < len(self.retry_backoff):
                time.sleep(self.retry_backoff[attempt])

        raise last_error if last_error else RuntimeError("ECB: неуспешно извличане")
