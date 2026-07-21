"""
core/scorer.py
==============
Изчислява макроикономически резултати (scores) от времеви редове.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from config import MACRO_REGIMES, MODULE_WEIGHTS, HISTORY_START
from catalog.polarity import polarity_for
from core.primitives import apply_transform

def get_percentile_score(series: pd.Series, value: float, invert: bool = False) -> float:
    """Изчислява percentile rank на стойност спрямо историческия ред."""
    if series.empty or pd.isna(value):
        return 50.0
        
    # Изчистване на NaN
    clean_series = series.dropna()
    if len(clean_series) < 5:
        return 50.0
        
    pct = (clean_series < value).mean() * 100.0
    
    if invert:
        pct = 100.0 - pct
        
    return pct

def score_series(s_raw: pd.Series, transform: str, invert: bool) -> dict:
    """Трансформира и скорира една серия."""
    if s_raw.empty:
        return {"score": 50.0, "value": None, "z_score": 0.0}
        
    # Филтрираме по HISTORY_START
    s = s_raw[s_raw.index >= pd.Timestamp(HISTORY_START)]
    if s.empty:
        s = s_raw  # Fallback към цялата история
        
    s_transformed = apply_transform(s, transform)
    s_clean = s_transformed.dropna()
    
    if s_clean.empty:
        return {"score": 50.0, "value": None, "z_score": 0.0}
        
    latest_val = s_clean.iloc[-1]
    score = get_percentile_score(s_clean, latest_val, invert)
    
    # Z-score за допълнителен контекст
    mean = s_clean.mean()
    std = s_clean.std()
    z = (latest_val - mean) / std if std > 0 else 0.0
    if invert:
        z = -z
        
    return {
        "score": float(score),
        "value": float(latest_val),
        "z_score": float(z),
        "last_date": s_clean.index[-1].strftime("%Y-%m-%d")
    }

def compute_module_scores(catalog: dict, snapshot: dict[str, pd.Series]) -> dict:
    """Изчислява score за всяка леща (module)."""
    lens_scores = {l: [] for l in MODULE_WEIGHTS.keys()}
    
    for key, spec in catalog.items():
        if key not in snapshot:
            continue
            
        s_raw = snapshot[key]
        invert = not polarity_for(key)
        
        result = score_series(s_raw, spec["transform"], invert)
        
        for l in spec.get("lens", []):
            if l in lens_scores:
                lens_scores[l].append(result["score"])
                
    # Усредняваме scores във всяка леща
    final_scores = {}
    for l, scores in lens_scores.items():
        if scores:
            final_scores[l] = float(np.mean(scores))
        else:
            final_scores[l] = 50.0  # Неутрален
            
    return final_scores

def compute_composite_score(module_scores: dict) -> float:
    """Изчислява общия макро score на база теглата."""
    total_weight = sum(MODULE_WEIGHTS.values())
    weighted_sum = sum(module_scores.get(m, 50.0) * w for m, w in MODULE_WEIGHTS.items())
    
    return float(weighted_sum / total_weight)

def get_regime(score: float) -> dict:
    """Връща режима според score."""
    for threshold, name, color in MACRO_REGIMES:
        if score >= threshold:
            return {"name": name, "color": color, "score": score}
            
    # Fallback
    threshold, name, color = MACRO_REGIMES[-1]
    return {"name": name, "color": color, "score": score}
