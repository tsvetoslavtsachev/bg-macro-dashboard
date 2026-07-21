"""
core/primitives.py
==================
Математически примитиви за макро анализ.
"""
import numpy as np
import pandas as pd
from typing import Optional

def compute_yoy_pct(series: pd.Series) -> pd.Series:
    """Изчислява Year-over-Year процентно изменение."""
    if series.empty:
        return series
        
    freq = pd.infer_freq(series.index)
    periods = 12
    if freq:
        if freq.startswith('Q'):
            periods = 4
        elif freq.startswith('A'):
            periods = 1
            
    # Fallback to manual shift if frequency inference fails
    if not freq:
        # Check median days between points
        diffs = series.index.to_series().diff().dt.days.median()
        if diffs > 80 and diffs < 100:  # Quarterly
            periods = 4
        elif diffs > 350:  # Annual
            periods = 1
            
    return series.pct_change(periods=periods) * 100.0

def compute_mom_pct(series: pd.Series) -> pd.Series:
    """Изчислява Month-over-Month (или период-към-период) процентно изменение."""
    return series.pct_change(periods=1) * 100.0

def compute_qoq_pct(series: pd.Series) -> pd.Series:
    """Изчислява Quarter-over-Quarter процентно изменение."""
    return series.pct_change(periods=1) * 100.0

def compute_z_score(series: pd.Series, window: int = None) -> pd.Series:
    """Изчислява Z-score (ролиращ или върху цялата серия)."""
    if window:
        mean = series.rolling(window=window, min_periods=window//2).mean()
        std = series.rolling(window=window, min_periods=window//2).std()
    else:
        mean = series.mean()
        std = series.std()
        
    # Prevent division by zero
    std = std.replace(0, np.nan)
    return (series - mean) / std

def apply_transform(series: pd.Series, transform: str) -> pd.Series:
    """Прилага трансформация според каталога."""
    if series.empty:
        return series
        
    if transform == "level":
        return series
    elif transform == "yoy_pct":
        return compute_yoy_pct(series)
    elif transform == "mom_pct":
        return compute_mom_pct(series)
    elif transform == "qoq_pct":
        return compute_qoq_pct(series)
    elif transform == "z_score":
        return compute_z_score(series)
    elif transform == "first_diff":
        return series.diff()
        
    return series
