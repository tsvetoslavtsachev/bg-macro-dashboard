"""
tests/test_form_canon.py
========================
ФОРМА-КАНОН пасът на повърхността (мандат №38 §А5).

Изводът първо · линк на всяко име към първоизточника · обяснение на място ·
един речник · методология при уреда · застоялото наблюдение маркирано.
"""
import html as _html
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


def test_html_explains_the_property_lens_and_its_resolved_polarity(rendered):
    """ФОРМА-КАНОН: обяснението стои ПРИ уреда. След №47 двузначността е
    РЕШЕНА — лицето вече не я обявява за отворен въпрос."""
    assert "<h4>Имоти и строителство</h4>" in rendered
    for token in ("prices", "activity", "pipeline", "решена",
                  "разрешителните", "риск утре", "4-тримесечна плъзгаща"):
        assert token in rendered, token
    assert "под преглед" not in rendered


# ── Мандат №47: оптималните зони + термометърът ──────────────────────────────

def test_html_methodology_explains_the_optimal_zones(rendered):
    """Числото не пътува без обяснението си: зони, наклон, provenance, гейт."""
    from catalog.polarity import OPT_PROVENANCE, OPT_SOURCE_NOTE

    assert "<h4>Оптималните зони и температурата</h4>" in rendered
    assert OPT_SOURCE_NOTE in rendered
    for token in ("оптимална зона", "плато", "1σ", "не участват"):
        assert token in rendered, token
    for provenance in OPT_PROVENANCE.values():
        assert _html.escape(provenance) in rendered


def test_html_methodology_prints_the_zone_table_from_the_polarity_map(rendered):
    """Праговете се ГЕНЕРИРАТ от POLARITY — нула преписани числа в лицето."""
    from analysis.temperature import zone_table

    for z in zone_table(SERIES_CATALOG):
        assert f"<td>{z['lo']:.0f} … {z['hi']:.0f}%</td>" in rendered, z["key"]
        assert f"<td>{z['s']:.0f} пп</td>" in rendered, z["key"]


def test_html_hero_carries_the_overheating_badge(rendered_with_temp):
    """Баджът до режимния етикет: „Прегряване: N/5" + tooltip кой гори."""
    html, temp = rendered_with_temp
    assert f"Прегряване: {temp['n_hot']}/{temp['n_total']}" in html
    assert 'class="temp-badge temp-warm"' in html
    for e in temp["hot"]:
        assert _html.escape(e["name_bg"]) in html
        assert f"{e['value']:.1f} (зона до {e['hi']:.0f})" in html


def test_the_badge_colour_follows_the_count(tmp_path):
    """Сиво при 0 · оранж 1-2 · червено ≥3 — нивото идва от temp_level."""
    from export.weekly_briefing import _temp_badge_html

    assert _temp_badge_html({"n_hot": 0, "n_total": 5, "hot": []}).count("temp-cold") == 1
    assert "не е над зоната си" in _temp_badge_html({"n_hot": 0, "n_total": 5, "hot": []})
    warm = _temp_badge_html({"n_hot": 2, "n_total": 5,
                             "hot": [{"name_bg": "Х", "value": 21.0, "hi": 12.0}]})
    assert "temp-warm" in warm
    hot = _temp_badge_html({"n_hot": 4, "n_total": 5,
                            "hot": [{"name_bg": "Х", "value": 21.0, "hi": 12.0}]})
    assert "temp-hot" in hot
    assert _temp_badge_html(None) == ""


def test_html_film_carries_the_temperature_band(rendered_with_temp):
    """Лентата под филма: барове 0-5 по кварталните редове + подпис."""
    html, _ = rendered_with_temp
    assert '"temp":' in html
    assert "Температурата: колко бум-серии са над зоната си" in html
    assert "абсолютни котви — валидни и назад" in html
    assert 'id="film-temp-note"' in html
    assert 'yaxis: "y2"' in html


def test_the_film_band_colours_come_from_python_not_js():
    """Нула аритметика в JS — стойността И цветът на всеки бар идват готови."""
    from analysis.lens_history import history_columns
    from analysis.temperature import TEMP_SERIES
    from export.weekly_briefing import TEMP_COLORS, _prep_film_data

    df = pd.DataFrame(
        [
            {"composite": 50.0, "temp_count": 0, "temp_hot": "", "row_type": "quarter"},
            {"composite": 51.0, "temp_count": 2, "temp_hot": "A+B", "row_type": "quarter"},
            {"composite": 52.0, "temp_count": 4, "temp_hot": "A+B+C+D", "row_type": "quarter"},
        ],
        index=pd.DatetimeIndex(["2024-03-01", "2024-06-01", "2024-09-01"], name="date"),
    ).reindex(columns=history_columns())

    band = _prep_film_data(df)["temp"]
    assert band["values"] == [0, 2, 4]
    assert band["colors"] == [
        TEMP_COLORS["cold"], TEMP_COLORS["warm"], TEMP_COLORS["hot"]
    ]
    assert band["max"] == len(TEMP_SERIES)


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


# ── Мандат №48: котвената лента + контекстната серия ─────────────────────────

def test_html_carries_the_anchor_strip_with_both_official_measures(rendered):
    """Вторият глас стои на лицето — с числото, зоната и цветната точка."""
    assert "Инфлацията с котви" in rendered
    assert 'class="anchor-card"' in rendered
    assert rendered.count('class="anchor-row"') == 2      # обща + базисна
    assert "пп над целта (2%)" in rendered or "пп под целта (2%)" in rendered
    for spec_key in ("BG_HICP", "BG_HICP_CORE"):
        assert SERIES_CATALOG[spec_key]["name_bg"] in rendered


def test_html_anchor_dots_use_the_zone_palette(rendered):
    from config import INFLATION_ANCHOR_COLORS

    used = [c for c in INFLATION_ANCHOR_COLORS.values()
            if f'class="anchor-dot" style="background:{c}"' in rendered]
    assert used, "поне една зона трябва да е оцветена от палитрата в config"


def test_html_anchor_strip_sits_right_under_the_module_bars(rendered):
    """Котвите се четат ДО компонентите на композита, не в друг край на страницата."""
    card = rendered.index('class="anchor-card"')
    assert rendered.index("Компоненти на резултата") < card
    assert card < rendered.index("Последни стойности")


def test_html_anchor_strip_says_the_composite_is_untouched(rendered):
    """Без това изречение читателят би помислил, че зоните местят числото."""
    from core.display import ANCHOR_DISCLAIMER

    assert ANCHOR_DISCLAIMER in rendered
    assert 'class="anchor-note"' in rendered


def test_html_marks_the_context_series_with_a_grey_badge_and_no_score(rendered):
    """Контекстната серия е наблюдение ДО композита — лицето го КАЗВА."""
    from config import (
        CONTEXT_BADGE_BG,
        CONTEXT_BADGE_COLORS,
        CONTEXT_LINE_COLOR,
        CONTEXT_SCORE_NOTE,
    )

    bg, fg = CONTEXT_BADGE_COLORS
    assert f".lens-context {{ background:{bg}; color:{fg}; }}" in rendered
    assert f'<span class="lens-badge lens-context">{CONTEXT_BADGE_BG}</span>' in rendered
    assert f'class="ctx-score" title="{CONTEXT_SCORE_NOTE}">—</td>' in rendered
    # Сивото стига и до графиката — контекстът не се рисува като „растеж"
    assert f'"context": "{CONTEXT_LINE_COLOR}"' in rendered


def test_html_methodology_explains_the_two_voices(rendered):
    assert "<h4>Инфлацията: двата гласа</h4>" in rendered
    assert "<h4>Усещаната инфлация — контекст, не компонент</h4>" in rendered
    for token in ("процентни пункта", "≤1 пп", "1–2 пп", "НЕ са калибрирани",
                  "баланс", "не влиза в композита"):
        assert token in rendered, token


# ── Мандат №45: филмът на композита + WoW блокът ─────────────────────────────

@pytest.fixture
def rendered_with_film(tmp_path):
    """Лицето с история и WoW делта — както го строи `run.py --briefing`."""
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime
    from analysis.lens_history import build_history

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    history = build_history(SERIES_CATALOG, snapshot, grid_start="2023-12-01")
    wow = {
        "date": "2026-07-28",
        "prev_date": "2026-07-21",
        "composite_delta": -1.4,
        "lens_deltas": {"growth": 2.5, "inflation": -0.3, "labor": 0.0,
                        "credit": -6.1, "external": 0.4, "property": 1.0},
        "composition_changed": False,
    }
    out = tmp_path / "index.html"
    generate_html(snapshot, reports, composite, get_regime(composite), str(out),
                  history=history, wow=wow)
    return out.read_text(encoding="utf-8")


def test_html_carries_the_film_card(rendered_with_film):
    assert "Филмът: композитът през времето" in rendered_with_film
    assert 'id="film-chart"' in rendered_with_film
    assert "FILM_DATA" in rendered_with_film


def test_html_film_carries_the_honesty_label(rendered_with_film):
    """Етикетът пътува С графиката — не в друг документ, не в footer-а."""
    from analysis.lens_history import HONESTY_LABEL

    assert HONESTY_LABEL in rendered_with_film
    assert "не point-in-time" in rendered_with_film


def test_html_carries_the_wow_block(rendered_with_film):
    assert "Какво се смени тази седмица" in rendered_with_film
    assert "WOW_DATA" in rendered_with_film
    assert "спрямо 21.07.2026" in rendered_with_film
    assert "-6.1" in rendered_with_film


def test_html_wow_block_says_so_when_the_journal_has_no_delta_yet(tmp_path):
    """Първият пуск няма с какво да се сравни — лицето го КАЗВА, не мълчи."""
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime
    from analysis.lens_history import build_history

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    history = build_history(SERIES_CATALOG, snapshot, grid_start="2024-12-01")
    out = tmp_path / "index.html"
    generate_html(snapshot, reports, composite, get_regime(composite), str(out),
                  history=history, wow=None)
    html = out.read_text(encoding="utf-8")

    assert "Какво се смени тази седмица" in html
    assert "Първи запис в живия журнал" in html


def test_html_wow_block_warns_when_the_composition_changed(tmp_path):
    """Сменен състав между двата записа → делтата се обявява за нечиста."""
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime
    from analysis.lens_history import build_history

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    history = build_history(SERIES_CATALOG, snapshot, grid_start="2024-12-01")
    wow = {
        "date": "2026-07-28", "prev_date": "2026-07-21", "composite_delta": 0.2,
        "lens_deltas": {"growth": 0.2}, "composition_changed": True,
    }
    out = tmp_path / "index.html"
    generate_html(snapshot, reports, composite, get_regime(composite), str(out),
                  history=history, wow=wow)
    html = out.read_text(encoding="utf-8")

    assert "съставът на уреда се смени между двата записа" in html
    assert "делтата не е чиста" in html


def test_html_film_explains_itself_in_the_methodology(rendered_with_film):
    assert "Филмът на композита" in rendered_with_film
    assert "реконструкция" in rendered_with_film
    assert "score_journal.csv" in rendered_with_film


def test_html_without_history_skips_the_film_card(rendered):
    """Стар пуск без история не рисува празна рамка."""
    assert "Филмът: композитът през времето" not in rendered
    assert 'id="film-chart"' not in rendered


@pytest.fixture
def rendered_with_temp(tmp_path):
    """Лицето с термометър: две серии над зоните си → „Прегряване: 2/5"."""
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime
    from analysis.lens_history import build_history
    from analysis.temperature import temperature

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    # BG_HPI е ГОТОВ г/г темп (transform=level) → 14.8% над зона 0–10
    snapshot["BG_HPI"] = pd.Series([14.8] * 300, index=idx)
    # Кредитът за домакинствата расте с 21% годишно → над зона 0–12
    snapshot["BG_LOANS_HH"] = pd.Series(
        [100.0 * (1.21 ** (i / 12.0)) for i in range(300)], index=idx
    )

    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    history = build_history(SERIES_CATALOG, snapshot, grid_start="2023-12-01")
    temp = temperature(SERIES_CATALOG, snapshot)
    out = tmp_path / "index.html"
    generate_html(snapshot, reports, composite, get_regime(composite), str(out),
                  history=history, wow=None, temp=temp)
    return out.read_text(encoding="utf-8"), temp


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
