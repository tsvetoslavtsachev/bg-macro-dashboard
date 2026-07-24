"""
tests/test_form_canon.py
========================
ФОРМА-КАНОН пасът на повърхността (мандат №38 §А5).

Изводът първо · линк на всяко име към първоизточника · обяснение на място ·
един речник · методология при уреда · застоялото наблюдение маркирано.
"""
from datetime import date

import pandas as pd
import pytest

from catalog.series import SERIES_CATALOG
from config import LENS_BADGES_BG, LENS_NAMES_BG, LENS_SUBJECTS_BG, MODULE_WEIGHTS
from core.display import databrowser_url, is_stale, months_old, verdict_sentence
from export.weekly_briefing import generate_html


# ── Линк на всяко име ────────────────────────────────────────────────────────

def test_databrowser_url_uses_the_dataset_before_the_query():
    url = databrowser_url("namq_10_gdp?geo=BG&unit=CLV_PCH_SM")
    assert url == (
        "https://ec.europa.eu/eurostat/databrowser/view/namq_10_gdp/default/table?lang=en"
    )


def test_every_catalog_series_yields_a_databrowser_url():
    for key, spec in SERIES_CATALOG.items():
        url = databrowser_url(spec["id"])
        assert url.startswith("https://ec.europa.eu/eurostat/databrowser/view/"), key
        assert "?" in spec["id"] or url  # id без query също трябва да работи


def test_databrowser_url_is_empty_for_a_missing_id():
    assert databrowser_url("") == ""


# ── Изводът първо ────────────────────────────────────────────────────────────

def _reports(**scores):
    return {lens: {"score": scores.get(lens)} for lens in MODULE_WEIGHTS}


def test_verdict_names_the_heaviest_and_the_strongest_lens():
    reports = _reports(inflation=34.8, labor=67.4, growth=47.1,
                       credit=25.4, external=4.4)
    assert verdict_sentence(reports) == (
        "Тежи външният сектор (4.4), крепи пазарът на труда (67.4)."
    )


def test_verdict_is_deterministic():
    reports = _reports(inflation=34.8, labor=67.4, growth=47.1,
                       credit=25.4, external=4.4)
    assert verdict_sentence(reports) == verdict_sentence(reports)


def test_verdict_says_so_when_there_is_nothing_to_conclude():
    assert verdict_sentence(_reports()) == "Няма достатъчно данни за извод."


def test_verdict_handles_a_single_measured_lens():
    sentence = verdict_sentence(_reports(labor=67.4))
    assert "пазарът на труда" in sentence
    assert "67.4" in sentence


# ── Един речник ──────────────────────────────────────────────────────────────

def test_one_vocabulary_covers_every_lens():
    for lens in MODULE_WEIGHTS:
        assert lens in LENS_NAMES_BG
        assert lens in LENS_BADGES_BG
        assert lens in LENS_SUBJECTS_BG


def test_lens_badges_are_bulgarian():
    assert set(LENS_BADGES_BG.values()) == {
        "растеж", "инфлация", "труд", "кредит", "външен"
    }


# ── Застояло наблюдение ──────────────────────────────────────────────────────

def test_monthly_observation_goes_stale_after_two_months():
    today = date(2026, 7, 24)
    assert is_stale("2026-06-01", "monthly", today) is False
    assert is_stale("2026-05-01", "monthly", today) is False
    assert is_stale("2026-04-01", "monthly", today) is True


def test_quarterly_observation_goes_stale_after_six_months():
    today = date(2026, 7, 24)
    assert is_stale("2026-01-01", "quarterly", today) is False
    assert is_stale("2025-12-01", "quarterly", today) is True


def test_months_old_counts_calendar_months():
    assert months_old("2026-01-01", date(2026, 7, 24)) == 6
    assert months_old(None, date(2026, 7, 24)) is None


# ── Лицето ───────────────────────────────────────────────────────────────────

@pytest.fixture
def rendered(tmp_path):
    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {
        key: pd.Series([1.0, 3.0] * 150, index=idx)
        for key in SERIES_CATALOG
    }
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime

    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path / "index.html"
    generate_html(snapshot, reports, composite, get_regime(composite), str(out))
    return out.read_text(encoding="utf-8")


def test_html_links_every_indicator_name_to_the_source(rendered):
    for spec in SERIES_CATALOG.values():
        assert databrowser_url(spec["id"]) in rendered


def test_html_carries_the_narrative_hint_as_a_tooltip(rendered):
    for spec in SERIES_CATALOG.values():
        hint = spec.get("narrative_hint", "")
        if hint:
            assert f'title="{hint}"' in rendered


def test_html_shows_the_verdict_sentence_first(rendered):
    assert 'class="verdict"' in rendered
    assert "Тежи" in rendered and "крепи" in rendered


def test_html_carries_the_methodology_block(rendered):
    assert "Как да четеш този дашборд" in rendered
    assert "<details class=\"methodology\" open>" in rendered
    assert "tanh" in rendered
    assert "U-форма" in rendered


def test_html_uses_the_bulgarian_lens_badges(rendered):
    for badge in LENS_BADGES_BG.values():
        assert f">{badge}</span>" in rendered


def test_html_module_bars_use_the_shared_vocabulary(rendered):
    for name in LENS_NAMES_BG.values():
        assert name in rendered


def test_html_flags_a_stale_observation(tmp_path):
    """Наблюдение отпреди половин година при месечна серия → ⚠."""
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    old_idx = pd.date_range(end="2020-01-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    snapshot["BG_UNRATE"] = pd.Series([1.0, 3.0] * 150, index=old_idx)

    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path / "index.html"
    generate_html(snapshot, reports, composite, get_regime(composite), str(out))
    html = out.read_text(encoding="utf-8")

    assert 'class="stale"' in html
    assert "2020-01" in html
