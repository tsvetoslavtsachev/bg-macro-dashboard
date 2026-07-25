"""
tests/test_briefing_context.py
==============================
Горивото на скила `macro-deep-brief-bg` (мандат №38 §А4).

Числата в експорта идват от скоринга — нула ръчни константи. Ако таблицата и
`--status` се разминат, анализът за клиент тръгва от лъжа.
"""
from datetime import date

import pandas as pd
import pytest

from catalog.series import SERIES_CATALOG
from config import LENS_NAMES_BG
from core.scorer import compute_composite_score, compute_lens_reports, get_regime
from export.briefing_context import DATA_QUALITY_NOTES, generate_briefing_context


@pytest.fixture
def context(tmp_path):
    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}

    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path / "briefing_context_2026-07-24.md"
    generate_briefing_context(
        snapshot=snapshot,
        lens_reports=reports,
        composite=composite,
        regime=get_regime(composite),
        output_path=str(out),
        today=date(2026, 7, 24),
    )
    return out.read_text(encoding="utf-8"), reports, composite


def test_context_file_is_written(context):
    text, _, _ = context
    assert text.startswith("# 🇧🇬 Bulgarian Macro Dashboard")
    assert "**Дата:** 2026-07-24" in text


def test_context_stays_compact_like_the_china_model(context):
    """~6-8 KB за 10 серии — не 44-килобайтовият EU експорт."""
    text, _, _ = context
    assert len(text.encode("utf-8")) < 12_000


def test_context_carries_all_five_lenses(context):
    text, _, _ = context
    for name in LENS_NAMES_BG.values():
        assert f"## {name}" in text
        assert f"| {name} |" in text


def test_context_composite_matches_the_scoring(context):
    text, _, composite = context
    assert f"## Композитен Macro Score: {composite:.1f} / 100" in text


def test_context_series_scores_match_the_scoring(context):
    text, reports, _ = context
    for rep in reports.values():
        for s in rep["series"]:
            if s["score"] is not None:
                assert f"| {s['name_bg']} |" in text
                assert f"| {s['score']:.1f} |" in text


def test_context_tables_have_the_mandated_columns(context):
    text, _, _ = context
    assert "| Показател | Стойност | Score | Данни към |" in text


def test_context_carries_the_narrative_hints(context):
    text, _, _ = context
    hint = SERIES_CATALOG["BG_HICP"]["narrative_hint"]
    assert hint in text


def test_context_limits_hints_to_two_per_lens(context):
    text, _, _ = context
    growth_section = text.split("## Растеж")[1].split("---")[0]
    bullets = [l for l in growth_section.splitlines() if l.startswith("- ")]
    assert len(bullets) <= 2


def test_context_carries_the_data_quality_notes(context):
    text, _, _ = context
    assert "## ⚠ Бележки за качеството на данните" in text
    assert len(DATA_QUALITY_NOTES) >= 6


def test_data_quality_notes_name_the_known_traps():
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("prc_hicp_minr", "4-тримесечна плъзгаща", "ei_bssi_m_r2",
                  "s_adj=CA", "01.01.2026", "заплатите"):
        assert token in joined, token


# ── Фаза 3.1: новите контактни точки (мандат №39 §А5) ────────────────────────

def test_notes_name_the_ecb_source_and_the_bnb_seed_it_is_spliced_to():
    """Мандат №41: бележката вече описва ШЕВА, не късия прозорец."""
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("BSI", "01.2022", "редономинационен", "Кредитна динамика",
                  "2005Q4", "≤0.5%", "тримесечие"):
        assert token in joined, token


def test_notes_no_longer_claim_a_short_window_for_the_loans():
    """Честността се обръща: „нормата е върху къс бум прозорец“ вече е неистина."""
    joined = " ".join(DATA_QUALITY_NOTES)
    assert "къс, изцяло бум" not in joined
    assert "ПОДЦЕНЯВА" not in joined


def test_notes_describe_the_new_lens_composition_not_single_series():
    """Едносерийната уговорка вече НЕ е вярна за кредит/външен."""
    joined = " ".join(DATA_QUALITY_NOTES)
    assert "не е едносериен" in joined
    for token in ("lending", "yields", "current_account", "trade", "lending_cost"):
        assert token in joined, token


# ── Мандат №42: цената на кредита ────────────────────────────────────────────

def test_notes_explain_that_the_lending_rate_is_new_business_not_stocks():
    """Анализаторът трябва да знае КОЯ лихва чете, преди да я ползва."""
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("MIR", "НОВ БИЗНЕС", "2007-01"):
        assert token in joined, token


def test_notes_name_the_rejected_alternatives_and_the_bnb_reference():
    """Отхвърлените варианти се документират — иначе следващият ги „открива“
    пак и ги слага мълчаливо."""
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("2019-12", "s_ir_loan_oa_nfc_bg", "РЕФЕРЕНЦИЯ"):
        assert token in joined, token


def test_credit_lens_section_lists_all_four_series(context):
    text, _, _ = context
    credit_section = text.split(f"## {LENS_NAMES_BG['credit']}")[1].split("\n---\n")[0]
    for key in ("BG_LT_RATE", "BG_LENDING_RATE", "BG_LOANS_NFC", "BG_LOANS_HH"):
        assert SERIES_CATALOG[key]["name_bg"] in credit_section, key


def test_short_window_series_get_a_note_in_the_export(tmp_path):
    """Флагът от скоринга стига до бележките — не се губи по пътя."""
    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    short_idx = pd.date_range(end="2026-05-01", periods=41, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    snapshot["BG_LOANS_NFC"] = pd.Series([1.0, 3.0] * 20 + [7.0], index=short_idx)

    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path / "ctx.md"
    generate_briefing_context(
        snapshot=snapshot, lens_reports=reports, composite=composite,
        regime=get_regime(composite), output_path=str(out), today=date(2026, 7, 24),
    )
    text = out.read_text(encoding="utf-8")

    assert "къс прозорец (от " in text
    assert "z-ът подценява екстремността" in text
    assert SERIES_CATALOG["BG_LOANS_NFC"]["name_bg"] in text


def test_no_short_window_note_when_every_series_is_long(context):
    """Бележката е динамична — изчезва сама, когато прозорецът порасне."""
    text, _, _ = context
    assert "z-ът подценява екстремността" not in text


def test_footer_names_both_sources(context):
    text, _, _ = context
    last = text.splitlines()[-1]
    assert "Eurostat" in last
    assert "BSI" in last


def test_context_footer_names_the_source(context):
    text, _, _ = context
    assert "Eurostat" in text.splitlines()[-1]


def test_context_explains_that_the_scale_changed(context):
    """Новото число НЕ се сравнява 1:1 със старите percentile четения."""
    text, _, _ = context
    assert "50 = близката 10-годишна норма" in text
    assert "us/eu/china-macro-dashboard" in text


def test_context_flags_a_stale_observation(tmp_path):
    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    old_idx = pd.date_range(end="2020-01-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    snapshot["BG_UNRATE"] = pd.Series([1.0, 3.0] * 150, index=old_idx)

    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path / "ctx.md"
    generate_briefing_context(
        snapshot=snapshot, lens_reports=reports, composite=composite,
        regime=get_regime(composite), output_path=str(out), today=date(2026, 7, 24),
    )
    assert "⚠ 2020-01-01" in out.read_text(encoding="utf-8")


def test_lens_rows_do_not_borrow_the_composite_regime_vocabulary(context):
    """„Инфлация — РЕЦЕСИОНЕН" е безсмислица; лещата носи лента, не режим."""
    text, _, _ = context
    lens_table = text.split("| Леща | Score | Състояние |")[1].split("\n\n")[0]
    for regime_name in ("РЕЦЕСИОНЕН", "ЕКСПАНЗИОНЕН", "ВЛОШАВАЩ СЕ"):
        assert regime_name not in lens_table
