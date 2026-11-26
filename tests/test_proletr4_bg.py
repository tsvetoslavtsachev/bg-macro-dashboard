"""ПРОЛЕТР4, България (26.11.2026, реш. Ц. БГ-1 до БГ-4 „Да, приемам ги“).

Пазят: тавана ±6 на серия преди сбора и застоялите извън сбора (БГ-1), спреда към Бунда като
изведена серия (БГ-2) и файла със серии по схемата на семейството (БГ-4).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from catalog.series import SERIES_CATALOG, validate_catalog
from core.scorer import SERIES_Z_CAP, compute_lens_reports
from sources.derived import bund_spread, derive_series

NEW_SCORED = {
    "BG_SERVICES_CONF": ("growth", "sentiment"), "BG_CONS_CONF": ("growth", "sentiment"),
    "BG_RETAIL": ("growth", "consumption"), "BG_PPI": ("inflation", "producer"),
    "BG_EMPLOYMENT": ("labor", "employment"), "BG_BUND_SPREAD": ("credit", "spreads"),
}


def test_catalog_valid_with_the_new_rows():
    assert validate_catalog() == []
    for k, (lens, pg) in NEW_SCORED.items():
        assert SERIES_CATALOG[k]["lens"] == [lens] and SERIES_CATALOG[k]["peer_group"] == pg
    assert SERIES_CATALOG["DE_LT_RATE"]["context_only"] is True


def _monthly(values, end="2026-10-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def _mini_catalog():
    base = {"region": "BG", "tags": [], "transform": "level", "is_rate": False,
            "historical_start": "2000-01-01", "typical_release": "x", "revision_prone": False,
            "narrative_hint": "", "source": "eurostat", "id": "x", "name_en": "x", "name_bg": "x"}
    return {
        "A": {**base, "lens": ["external"], "peer_group": "g1", "release_schedule": "monthly"},
        "B": {**base, "lens": ["external"], "peer_group": "g2", "release_schedule": "monthly"},
        "C": {**base, "lens": ["external"], "peer_group": "g3", "release_schedule": "monthly"},
    }


def test_series_z_capped_before_the_lens_sum(monkeypatch):
    import core.scorer as sc
    monkeypatch.setattr(sc, "polarity_for", lambda key, lens=None: +1)
    rng = np.random.default_rng(0)
    calm = list(rng.normal(0, 1, 160))
    wild = calm[:-1] + [500.0]
    snap = {"A": _monthly(wild), "B": _monthly(calm), "C": _monthly(calm)}
    rep = compute_lens_reports(_mini_catalog(), snap)["external"]
    a = next(s for s in rep["series"] if s["key"] == "A")
    assert a["health_z"] > SERIES_Z_CAP and a["capped"] is True     # показва суровото
    g1 = next(p for p in rep["peer_groups"] if p["name"] == "g1")
    assert g1["health_z"] == SERIES_Z_CAP                           # сборът вижда тавана


def test_stale_series_shown_but_not_summed(monkeypatch):
    import core.scorer as sc
    monkeypatch.setattr(sc, "polarity_for", lambda key, lens=None: +1)
    rng = np.random.default_rng(1)
    vals = list(rng.normal(0, 1, 160))
    snap = {"A": _monthly(vals, end="2026-01-01"), "B": _monthly(vals), "C": _monthly(vals)}
    rep = compute_lens_reports(_mini_catalog(), snap)["external"]
    a = next(s for s in rep["series"] if s["key"] == "A")
    assert a["stale"] is True
    g1 = next(p for p in rep["peer_groups"] if p["name"] == "g1")
    assert g1["health_z"] is None and rep["n_series"] == 2


def test_bund_spread_only_where_both_sides_exist():
    bg = _monthly([3.0, 3.2, 3.6], end="2026-10-01")
    de = _monthly([2.5, 2.6], end="2026-09-01")
    s = bund_spread(bg, de)
    assert list(s.index) == [pd.Timestamp("2026-08-01"), pd.Timestamp("2026-09-01")]
    assert list(s.values) == [50.0, 60.0]
    assert bund_spread(bg, None) is None


def test_derive_series_adds_the_spread():
    snap = {"BG_LT_RATE": _monthly([3.0, 3.1]), "DE_LT_RATE": _monthly([2.4, 2.44])}
    out = derive_series(snap)
    assert round(float(out["BG_BUND_SPREAD"].iloc[-1]), 1) == 66.0


def test_series_data_schema_and_region():
    from export.series_data import SERIES_DATA_KEYS, LATEST_KEYS, build_series_data
    snap = {"BG_ESI": _monthly(list(np.linspace(90, 110, 140))),
            "BG_BUND_SPREAD": _monthly(list(np.linspace(50, 120, 140)))}
    d = build_series_data(snapshot=snap, lens_reports=None, today=date(2026, 11, 26))
    assert tuple(d) == SERIES_DATA_KEYS and d["region"] == "BG"
    assert set(d["series"]) == {"BG_ESI", "BG_BUND_SPREAD"}
    lt = d["series"]["BG_BUND_SPREAD"]["latest"]
    assert tuple(lt) == LATEST_KEYS and lt["stale"] is False
    assert d["series"]["BG_BUND_SPREAD"]["meta"]["change_kind"] == "absolute"
