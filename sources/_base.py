"""
sources/_base.py
================
Базов клас за адаптери за данни (Eurostat, NSI, BNB).
Осигурява кеширане, повторни опити и унифициран интерфейс.
"""
from __future__ import annotations
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import pandas as pd

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = {
    "weekly":     3,
    "monthly":   10,
    "quarterly": 30,
    "annually":  90,
}

class BaseAdapter(ABC):
    def __init__(self, cache_path: str):
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = self._load_cache()
        self._failures: list[str] = []

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache {self.cache_path}: {e}")
        return {}

    def _save_cache(self) -> None:
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache {self.cache_path}: {e}")

    def _is_stale(self, key: str, schedule: str) -> bool:
        if key not in self._cache:
            return True
        last_fetched = self._cache[key].get("last_fetched")
        if not last_fetched:
            return True
        
        try:
            dt = datetime.fromisoformat(last_fetched)
            ttl = CACHE_TTL_DAYS.get(schedule, 10)
            if datetime.utcnow() - dt > timedelta(days=ttl):
                return True
        except ValueError:
            return True
            
        return False

    @abstractmethod
    def fetch_series(self, source_id: str) -> pd.Series:
        """Извлича една серия от API-то."""
        pass

    def fetch_many(self, specs: list[dict], force: bool = False) -> dict[str, pd.Series]:
        """
        Извлича множество серии.
        specs = [{"key": "BG_GDP_YOY", "source_id": "...", "release_schedule": "quarterly"}]
        """
        results = {}
        self._failures = []
        cache_updated = False

        for spec in specs:
            key = spec.get("key", spec.get("_key"))
            source_id = spec.get("source_id", spec.get("id"))
            schedule = spec.get("release_schedule", "monthly")

            if not force and not self._is_stale(key, schedule) and "data" in self._cache.get(key, {}):
                try:
                    s = pd.Series(self._cache[key]["data"])
                    s.index = pd.to_datetime(s.index)
                    results[key] = s
                    continue
                except Exception:
                    pass

            # Fetch
            try:
                logger.info(f"Fetching {key} ({source_id})...")
                s = self.fetch_series(source_id)
                if not s.empty:
                    s = s.sort_index()
                    results[key] = s
                    
                    # Update cache
                    str_data = {d.strftime("%Y-%m-%d"): float(v) for d, v in s.items() if pd.notna(v)}
                    self._cache[key] = {
                        "source_id": source_id,
                        "schedule": schedule,
                        "last_fetched": datetime.utcnow().isoformat(),
                        "last_observation": s.index[-1].strftime("%Y-%m-%d") if not s.empty else None,
                        "n_observations": len(s),
                        "data": str_data
                    }
                    cache_updated = True
                else:
                    self._failures.append(key)
            except Exception as e:
                logger.error(f"Failed to fetch {key}: {e}")
                self._failures.append(key)
                
            time.sleep(0.5)  # Rate limiting

        if cache_updated:
            self._save_cache()

        return results

    def get_snapshot(self, keys: list[str]) -> dict[str, pd.Series]:
        """Връща сериите от кеша без мрежови заявки."""
        results = {}
        for key in keys:
            if key in self._cache and "data" in self._cache[key]:
                try:
                    s = pd.Series(self._cache[key]["data"])
                    s.index = pd.to_datetime(s.index)
                    results[key] = s
                except Exception:
                    pass
        return results

    def last_fetch_failures(self) -> list[str]:
        return self._failures
