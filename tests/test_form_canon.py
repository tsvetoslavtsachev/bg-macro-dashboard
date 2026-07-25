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
from config import (
    LENS_BADGE_COLORS,
    LENS_BADGES_BG,
    LENS_LINE_COLORS,
    LENS_NAMES_BG,
    LENS_SUBJECTS_BG,
    MODULE_WEIGHTS,
)
from core.display import (
    databrowser_url,
    ecb_series_url,
    is_stale,
    months_old,
    source_url,
    verdict_sentence,
)
from export.weekly_briefing import generate_html


# ── Линк на всяко име ────────────────────────────────────────────────────────

def test_databrowser_url_uses_the_dataset_before_the_query():
    url = databrowser_url("namq_10_gdp?geo=BG&unit=CLV_PCH_SM")
    assert url == (
        "https://ec.europa.eu/eurostat/databrowser/view/namq_10_gdp/default/table?lang=en"
    )


def test_every_catalog_series_yields_a_first_source_url():
    """Всяко име води към ПЪРВОИЗТОЧНИКА си — Eurostat или ЕЦБ, не смес."""
    expected_prefix = {
        "eurostat": "https://ec.europa.eu/eurostat/databrowser/view/",
        "ecb": "https://data.ecb.europa.eu/data/datasets/",
    }
    for key, spec in SERIES_CATALOG.items():
        source = spec["source"]
        assert source in expected_prefix, key
        url = source_url(source, spec["id"])
        assert url.startswith(expected_prefix[source]), key


def test_databrowser_url_is_empty_for_a_missing_id():
    assert databrowser_url("") == ""


# ── Линкът се разклонява по източник (мандат №39 §А4) ────────────────────────

def test_ecb_url_repeats_the_dataset_prefix_in_the_key():
    """Живо проверено 25.07.2026: без префикса на набора адресът е 404."""
    url = ecb_series_url("BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E")
    assert url == (
        "https://data.ecb.europa.eu/data/datasets/BSI/"
        "BSI.M.BG.N.A.A20.A.1.U6.2240.Z01.E"
    )


def test_mir_series_url_carries_the_mir_prefix_not_bsi():
    """Мандат №42: линк-функцията е GENERIC по набор, не зашита за BSI.

    Живо проверено 26.07.2026 — този адрес връща 200.
    """
    spec = SERIES_CATALOG["BG_LENDING_RATE"]
    url = source_url(spec["source"], spec["id"])
    assert url == (
        "https://data.ecb.europa.eu/data/datasets/MIR/"
        "MIR.M.BG.B.A2A.A.R.A.2240.EUR.N"
    )
    assert "/BSI/" not in url


def test_ecb_url_is_generic_across_datasets():
    """Всеки набор минава по същия шаблон — нищо не е hardcoded."""
    for flow, key in (("BSI", "M.BG.X"), ("MIR", "M.BG.Y"), ("FM", "D.BG.Z")):
        assert ecb_series_url(f"{flow}/{key}") == (
            f"https://data.ecb.europa.eu/data/datasets/{flow}/{flow}.{key}"
        )


def test_source_url_sends_eurostat_series_to_the_databrowser():
    spec = SERIES_CATALOG["BG_GDP_YOY"]
    assert source_url(spec["source"], spec["id"]) == databrowser_url(spec["id"])


def test_source_url_sends_ecb_series_to_the_data_portal():
    spec = SERIES_CATALOG["BG_LOANS_NFC"]
    url = source_url(spec["source"], spec["id"])
    assert "data.ecb.europa.eu" in url
    assert "eurostat" not in url


def test_ecb_url_falls_back_to_search_without_a_dataset_and_key():
    """Каталожно id без '/' не се разлага — вместо счупен линк даваме търсене."""
    url = ecb_series_url("M.BG.N.A.A20.A.1.U6.2240.Z01.E")
    assert url.startswith("https://data.ecb.europa.eu/search-results?searchTerm=")
    assert ecb_series_url("") == ""


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
        "растеж", "инфлация", "труд", "кредит", "външен", "имоти"
    }


def test_every_lens_has_a_colour_in_the_single_palette():
    """Мандат №43: палитрата беше на ТРИ места (CSS + два JS речника). Сега е
    една — и всяка леща от теглата има ред в нея."""
    for lens in MODULE_WEIGHTS:
        assert lens in LENS_LINE_COLORS, lens
        assert lens in LENS_BADGE_COLORS, lens
        bg, fg = LENS_BADGE_COLORS[lens]
        assert bg.startswith("#") and fg.startswith("#"), lens


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
        assert source_url(spec["source"], spec["id"]) in rendered


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


# ── Мандат №43: лицето носи ШЕСТТЕ лещи, нищо не е зашито на пет ─────────────

def test_html_draws_one_module_bar_per_lens(rendered):
    """Модул-баровете се броят по MODULE_WEIGHTS, не по зашит списък."""
    assert rendered.count('class="mod-label"') == len(MODULE_WEIGHTS)
    for name in LENS_NAMES_BG.values():
        assert f'<div class="mod-label">{name}</div>' in rendered


def test_html_carries_a_badge_class_and_colour_for_every_lens(rendered):
    for lens, (bg, fg) in LENS_BADGE_COLORS.items():
        assert f".lens-{lens} {{ background:{bg}; color:{fg}; }}" in rendered
    assert '<span class="lens-badge lens-property">имоти</span>' in rendered


def test_html_radar_and_chart_palette_know_every_lens(rendered):
    """Радарът чете BG_NAMES, графиките — LENS_COLORS/LENS_BG. И трите речника
    се сериализират от config, затова шестата леща влиза навсякъде наведнъж."""
    for lens, color in LENS_LINE_COLORS.items():
        assert f'"{lens}": "{color}"' in rendered
    assert '"property": "Имоти и строителство"' in rendered
    assert '"property": "rgba(251,146,60,0.08)"' in rendered


def test_html_methodology_names_the_lens_count_and_the_rebalance(rendered):
    """„Претеглена средна на петте лещи“ щеше да стане тиха неистина."""
    assert "Претеглена средна на шестте лещи" in rendered
    assert "петте лещи" not in rendered
    assert "имоти и строителство 15%" in rendered
    assert "не се сравнява" in rendered


def test_html_explains_the_property_lens_and_its_ambiguous_polarity(rendered):
    """ФОРМА-КАНОН: обяснението стои ПРИ уреда. Бум-полярността е под преглед и
    лицето го казва, вместо да я представя за уредено решение."""
    assert "<h4>Имоти и строителство</h4>" in rendered
    for token in ("prices", "activity", "pipeline", "под преглед",
                  "разрешителните", "риск утре"):
        assert token in rendered, token


def test_html_property_rows_link_to_the_eurostat_datasets(rendered):
    for key in ("BG_HPI", "BG_CONSTR", "BG_PERMITS"):
        spec = SERIES_CATALOG[key]
        assert source_url(spec["source"], spec["id"]) in rendered, key


def test_html_flags_a_short_window_with_a_tooltip(tmp_path):
    """Мандат №39 §А3: ⚠ + едно изречение защо нормата не е 10-годишна."""
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    short_idx = pd.date_range(end="2026-05-01", periods=41, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    snapshot["BG_LOANS_NFC"] = pd.Series([1.0, 3.0] * 20 + [7.0], index=short_idx)

    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path / "index.html"
    generate_html(snapshot, reports, composite, get_regime(composite), str(out))
    html = out.read_text(encoding="utf-8")

    assert 'class="thin"' in html
    assert "z-ът подценява екстремността" in html
    assert "къс прозорец (от " in html


def test_html_does_not_flag_a_thin_window_when_every_series_is_long(rendered):
    assert 'class="thin" title=' not in rendered


def test_html_explains_the_credit_splice_in_the_methodology(rendered):
    """Обяснението стои ПРИ уреда, не в друг документ (ФОРМА-КАНОН).

    Мандат №41: лицето вече описва ШЕВА (БНБ seed + ЕЦБ BSI), а не късия
    прозорец — иначе методологията щеше да твърди нещо, което вече не е вярно.
    """
    assert "Дългата кредитна памет" in rendered
    assert "2005Q4" in rendered
    assert "01.2022" in rendered
    assert "0.5%" in rendered


def test_html_keeps_the_generic_thin_window_explanation(rendered):
    """⚠ механизмът остава — просто вече не сочи към кредитните серии."""
    assert "Къс прозорец" in rendered
    assert "подценява екстремността" in rendered


def test_html_footer_names_the_ecb_portal(rendered):
    assert "data.ecb.europa.eu" in rendered
    assert "ec.europa.eu/eurostat" in rendered


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
