"""
sources/eurostat_adapter.py
===========================
Eurostat REST API adapter (JSON-stat 2.0 format).
"""
from __future__ import annotations
import logging
import re
from typing import Any, Optional
import pandas as pd
import requests

from sources._base import BaseAdapter
from config import EUROSTAT_API_BASE

logger = logging.getLogger(__name__)

# Период parsing
_MONTHLY_M_RE = re.compile(r"^(\d{4})M(\d{2})$")            
_MONTHLY_DASH_RE = re.compile(r"^(\d{4})-(\d{2})$")         
_QUARTERLY_Q_RE = re.compile(r"^(\d{4})Q([1-4])$")          
_QUARTERLY_DASH_RE = re.compile(r"^(\d{4})-Q([1-4])$")      
_ANNUAL_RE = re.compile(r"^(\d{4})$")                       

def parse_eurostat_period(period: str) -> Optional[pd.Timestamp]:
    period = period.strip()
    
    m = _MONTHLY_M_RE.match(period) or _MONTHLY_DASH_RE.match(period)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
        
    m = _QUARTERLY_Q_RE.match(period) or _QUARTERLY_DASH_RE.match(period)
    if m:
        month = (int(m.group(2)) - 1) * 3 + 1
        return pd.Timestamp(year=int(m.group(1)), month=month, day=1)
        
    m = _ANNUAL_RE.match(period)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=1, day=1)
        
    return None

class EurostatAdapter(BaseAdapter):
    def __init__(self):
        super().__init__("data/eurostat_cache.json")

    def fetch_series(self, source_id: str) -> pd.Series:
        url = f"{EUROSTAT_API_BASE}/{source_id}"
        
        headers = {"User-Agent": "bg-macro-dashboard/0.1"}
        resp = requests.get(url, timeout=30, headers=headers)
        resp.raise_for_status()
        
        data = resp.json()
        
        if "dimension" not in data or "value" not in data:
            raise ValueError("Invalid JSON-stat format")
            
        time_dim = data["dimension"].get("time")
        if not time_dim:
            raise ValueError("No 'time' dimension found")
            
        # Extract periods
        periods = []
        if "category" in time_dim and "index" in time_dim["category"]:
            idx_dict = time_dim["category"]["index"]
            # Some responses have list, some dict
            if isinstance(idx_dict, list):
                periods = idx_dict
            else:
                periods = [k for k, v in sorted(idx_dict.items(), key=lambda item: item[1])]
                
        # Parse values
        values_dict = data["value"]
        
        s_data = {}
        for i, period_str in enumerate(periods):
            idx_str = str(i)
            if idx_str in values_dict and values_dict[idx_str] is not None:
                dt = parse_eurostat_period(period_str)
                if dt:
                    s_data[dt] = float(values_dict[idx_str])
                    
        s = pd.Series(s_data)
        if not s.empty:
            s = s.sort_index()
            
        return s
