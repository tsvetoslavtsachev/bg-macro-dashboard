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


@pytest.fixture(scope="module")
def live_context(tmp_path_factory):
    """Живият експорт 1:1 по `run.py::cmd_export_context` — от комитнатия кеш,
    с ВСИЧКИ живи секции (историята + WoW от журнала + температурата +
    тензията). Нула мрежови заявки; датата е пинната за детерминизъм.
    """
    from analysis.lens_history import build_history, load_journal, wow_delta
    from analysis.temperature import temperature
    from analysis.tension import annihilation
    from catalog.series import series_by_source
    from sources import build_adapters
    from sources.derived import derive_series
    from sources.manual_seed import splice_loans

    snapshot = {}
    for source_name, adapter in build_adapters().items():
        keys = [spec["_key"] for spec in series_by_source(source_name)]
        snapshot.update(adapter.get_snapshot(keys))
    # Живата верига (мандат №54): splice → derive. Проверката за пълнота е СЛЕД
    # нея — изведената серия не идва от адаптер.
    snapshot = derive_series(splice_loans(snapshot))
    if len(snapshot) < len(SERIES_CATALOG):
        pytest.skip("кешът в data/ е непълен — тестът иска комитнатия кеш")

    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path_factory.mktemp("live_ctx") / "briefing_context.md"
    generate_briefing_context(
        snapshot=snapshot,
        lens_reports=reports,
        composite=composite,
        regime=get_regime(composite),
        output_path=str(out),
        today=date(2026, 7, 29),
        history=build_history(SERIES_CATALOG, snapshot),
        wow=wow_delta(load_journal()),
        temp=temperature(SERIES_CATALOG, snapshot),
        tension=annihilation(reports),
    )
    return out.read_text(encoding="utf-8")


def test_the_live_context_stays_compact_like_the_china_model(live_context):
    """Компактният фамилен модел — не 44-килобайтовият EU експорт.

    Таванът СЛЕДВА броя лещи, компактността остава принципът. При 5 лещи беше
    12 000 (живият файл ~11 100). Мандат №43 добавя шеста лещова секция + двете
    ѝ бележки за качеството → 14 300. Мандат №45 добавя секцията „Композитът
    през времето" → 18 000. Мандати №47 (температурата) и №48 (котвите) заедно
    → 22 000. Мандат №50 (седмата леща + фискалните бележки) → 28 000
    (чекър-фикс при проверяващия: изпълнителят имаше забрана да пипа тавана).
    Дупката от №50 („тестът мери фикстура, живият файл не се пази") е ЗАТВОРЕНА
    с чип-билета на Ц. 29.07.2026: мери се ЖИВИЯТ състав — комитнатият кеш +
    всички живи секции, 1:1 по `run.py::cmd_export_context`.

    ⚠ Мандат №54 вдига тавана 40 000 → **46 000** и КАЗВА защо, вместо да го
    вдигне по навик: живият файл ПРЕДИ мандата вече беше **38 144** байта (не
    35 300 — №53 добави провенанса на балонната двойка и старият коментар
    остана назад), а мандатът добавя **+4 725**: живия блок „Двете хипотези"
    под имотната леща и пренаписаната бележка за конвенцията и ревизията.
    Живото след №54 е **42 869** байта. Духът е СЪЩИЯТ: тревога, не бюджет —
    числото е там, за да ГРЪМНЕ при следващата НОВА секция, не при седмичната
    порция числа.
    """
    assert len(live_context.encode("utf-8")) < 46_000


def test_context_carries_every_lens(context):
    """Речникът е един — колкото лещи има в него, толкова секции има в експорта.

    Тестът е по РЕЧНИКА, не по числото 5 или 6: шестата леща влезе, без да се
    пипа тук, а седмата ще влезе по същия начин.
    """
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
    for token in ("lending", "yields", "external_balance", "lending_cost"):
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


# ── Мандат №43: имотната леща ────────────────────────────────────────────────

def test_property_lens_section_lists_all_three_series(context):
    """Шестата леща стига до експорта с трите си крака, не като едно име."""
    text, _, _ = context
    section = text.split(f"## {LENS_NAMES_BG['property']}")[1].split("\n---\n")[0]
    for key in ("BG_HPI", "BG_CONSTR", "BG_PERMITS"):
        assert SERIES_CATALOG[key]["name_bg"] in section, key


def test_notes_explain_the_property_lens_and_its_three_peer_groups():
    """Анализаторът трябва да знае, че `имоти` е ТРИ различни въпроса."""
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("prc_hpi_q", "sts_copr_m", "sts_cobp_q",
                  "prices", "activity", "pipeline"):
        assert token in joined, token


def test_notes_warn_that_the_composite_was_rebalanced():
    """Смяна на СЪСТАВА, не само на теглата — иначе някой ще сравни 45.1 с 39.7
    като че ли е същият уред."""
    joined = " ".join(DATA_QUALITY_NOTES)
    assert "РЕБАЛАНСИРАН" in joined
    assert "не го сравнявай механично" in joined


# ── Мандат №47: бум-полярностите са РЕШЕНИ ───────────────────────────────────

def test_notes_declare_the_boom_polarities_resolved_not_pending():
    """Уговорката „ПОД ПРЕГЛЕД / Фаза 3" беше вярна до №47; след него е неистина.

    Скилът чете ТЕЗИ бележки — ако те още говорят за отложено решение, анализът
    ще обяснява числото с логика, която уредът вече не ползва.
    """
    joined = " ".join(DATA_QUALITY_NOTES)
    assert "ПОД ПРЕГЛЕД" not in joined
    assert "Фаза 3" not in joined
    assert joined.count("мандат №47") >= 3
    assert "ОПТИМАЛНА ЗОНА" in joined


def test_notes_carry_the_zone_numbers_and_their_anchors():
    """Праговете пътуват с провенанса си, не като голи числа."""
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("0–13%", "0–12%", "0–10%", "номиналния БВП ръст",
                  "доходен ръст", "конвергентния таван"):
        assert token in joined, token


def test_notes_explain_the_new_permits_transform():
    """Числото на разрешителните вече е ДРУГО — таблицата чете плъзгащата."""
    joined = " ".join(DATA_QUALITY_NOTES)
    assert "yoy_roll4" in joined
    assert "4-тримесечна плъзгаща" in joined
    assert "Строителната продукция ОСТАВА +1" in joined


# ── Мандат №50: седмата леща (държавни финанси) ──────────────────────────────

def test_fiscal_lens_section_lists_both_series(context):
    """Седмата леща стига до експорта с двата си крака — потокът и стокът."""
    text, _, _ = context
    section = text.split(f"## {LENS_NAMES_BG['fiscal']}")[1].split("\n---\n")[0]
    for key in ("BG_GOV_BALANCE", "BG_GOV_DEBT"):
        assert SERIES_CATALOG[key]["name_bg"] in section, key


def test_notes_explain_the_budget_balance_mechanics(context):
    """Анализаторът трябва да знае знака, изглаждането и защо НЕ е сезонно."""
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("gov_10q_ggnfa", "B9", "плюсът е ИЗЛИШЪК", "s_adj=NSA",
                  "празни за България", "−4.70"):
        assert token in joined, token


def test_notes_explain_the_debt_level_versus_drift_honesty(context):
    """Нивото е сред най-ниските в ЕС — уредът мери ДРЕЙФА, не класацията.

    Без тази уговорка скорът 14.2 се чете като „България е задлъжняла", което е
    точно обратното на истината за абсолютното ниво.
    """
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("gov_10q_ggdebt", "НАЙ-НИСКИТЕ нива в ЕС", "ДРЕЙФА",
                  "Маастрихтските 3% / 60%", "НЕ прагове в скоринга",
                  "fiscal_balance", "debt"):
        assert token in joined, token


def test_context_declares_the_second_consecutive_composition_change(context):
    """Втора поредна смяна на състава — казва се, вместо да се крие в делтата."""
    text, _, _ = context
    assert "Съставът се смени ОТНОВО с мандат №50" in text
    assert "Разложи трите" in text
    assert text.index("мандат №50") < text.index(f"## {LENS_NAMES_BG['growth']}")


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


# ── Мандат №48: котвеният прочит + усещаната инфлация ────────────────────────

def test_context_carries_the_anchor_block_under_the_inflation_table(context):
    """Вторият глас пътува с експорта — иначе скилът чете само U-score-а."""
    text, _, _ = context
    section = text.split(f"## {LENS_NAMES_BG['inflation']}")[1].split("\n---\n")[0]

    assert "**Котвеният прочит (абсолютни пп от целта):**" in section
    assert section.index("| Показател |") < section.index("Котвеният прочит")
    for key in ("BG_HICP", "BG_HICP_CORE"):
        assert SERIES_CATALOG[key]["name_bg"] in section, key
    assert "целта (2%)" in section
    assert "зона" in section


def test_context_anchor_block_repeats_that_the_composite_is_untouched(context):
    from core.display import ANCHOR_DISCLAIMER

    text, _, _ = context
    assert ANCHOR_DISCLAIMER in text


def test_context_carries_the_perceived_inflation_row(context):
    """Контекстната серия няма лещова секция — влиза през котвения блок."""
    text, _, _ = context
    assert "Усещаната (ЕК анкета):" in text
    assert "баланс, не процент" in text
    assert "извън композита" in text


def test_context_does_not_score_the_perceived_series(context):
    """Тя няма score никъде — иначе някой ще я цитира като компонент."""
    text, reports, _ = context
    scored = {s["key"] for rep in reports.values() for s in rep["series"]}
    assert "BG_INFL_PERCEIVED" not in scored


def test_notes_explain_the_two_voices_and_the_fixed_zones():
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("ДВА гласа", "котвеният прочит", "≤1 пп", ">2 пп",
                  "НЕ са калибрирани по историята"):
        assert token in joined, token


def test_notes_explain_the_perceived_series_and_name_the_menu_candidate():
    """Балансът НЕ е процент, серията е извън композита, а съседът е меню."""
    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("ei_bsco_m", "BS-PT-LY", "БАЛАНС, не",
                  "context_only", "BS-PT-NY", "МЕНЮ-КАНДИДАТ", "2001-05"):
        assert token in joined, token


# ── Мандат №45: композитът през времето ──────────────────────────────────────

@pytest.fixture
def context_with_history(tmp_path):
    """Контекстът както го строи `run.py --export-context`: с история и WoW."""
    from analysis.lens_history import build_history

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    history = build_history(SERIES_CATALOG, snapshot, grid_start="2020-12-01")
    wow = {
        "date": "2026-07-28",
        "prev_date": "2026-07-21",
        "composite_delta": -1.4,
        "lens_deltas": {"growth": 2.5, "inflation": -0.3, "labor": 0.0,
                        "credit": -6.1, "external": 0.4, "property": 1.0},
        "composition_changed": False,
    }
    out = tmp_path / "ctx.md"
    generate_briefing_context(
        snapshot=snapshot, lens_reports=reports, composite=composite,
        regime=get_regime(composite), output_path=str(out), today=date(2026, 7, 28),
        history=history, wow=wow,
    )
    return out.read_text(encoding="utf-8"), history


def test_context_carries_the_history_section(context_with_history):
    text, _ = context_with_history
    assert "## Композитът през времето — реконструирана история [не PIT]" in text


def test_context_history_section_carries_the_honesty_label(context_with_history):
    """Скилът цитира числата с уговорката — затова тя пътува с тях."""
    from analysis.lens_history import HONESTY_LABEL

    text, _ = context_with_history
    assert HONESTY_LABEL in text
    assert "не point-in-time" in text


def test_context_history_section_sits_after_the_lens_table(context_with_history):
    text, _ = context_with_history
    assert text.index("| Леща | Score | Състояние |") < text.index("## Композитът през времето")
    assert text.index("## Композитът през времето") < text.index(f"## {LENS_NAMES_BG['growth']}")


def test_context_reports_the_weekly_deltas_from_the_journal(context_with_history):
    text, _ = context_with_history
    assert "**Какво се смени (жив журнал):**" in text
    assert "-1.4 спрямо 2026-07-21" in text
    assert "-6.1" in text          # кредитът е най-голямото движение → в топ-3


def test_context_ranks_the_lens_deltas_by_size(context_with_history):
    """Топ-3 по |Δ|, не по азбучен ред — иначе най-важното пада най-долу."""
    text, _ = context_with_history
    block = text.split("**Какво се смени (жив журнал):**")[1].split("**Къде сме")[0]
    lines = [l for l in block.splitlines() if l.startswith("- ")]
    assert len(lines) == 4                      # композит + 3 лещи
    assert LENS_NAMES_BG["credit"] in lines[1]  # |−6.1| е най-голямото
    assert LENS_NAMES_BG["growth"] in lines[2]  # |+2.5| второто


def test_context_says_so_when_the_journal_has_no_delta_yet(tmp_path):
    from analysis.lens_history import build_history

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    history = build_history(SERIES_CATALOG, snapshot, grid_start="2024-12-01")
    out = tmp_path / "ctx.md"
    generate_briefing_context(
        snapshot=snapshot, lens_reports=reports, composite=composite,
        regime=get_regime(composite), output_path=str(out), today=date(2026, 7, 28),
        history=history, wow=None,
    )
    assert "Първи запис в живия журнал" in out.read_text(encoding="utf-8")


def test_context_places_the_current_composite_against_the_reconstruction(context_with_history):
    text, history = context_with_history
    from analysis.lens_history import history_stats

    stats = history_stats(history)
    assert f"{stats['percentile']:.1f}% от {stats['n_quarters']} тримесечни точки" in text
    assert f"Най-ниско: {stats['min_value']:.1f} на {stats['min_date']}" in text
    assert f"Най-високо: {stats['max_value']:.1f} на {stats['max_date']}" in text


def test_context_carries_the_yearly_table(context_with_history):
    """Числата идват от решетката — нула ръчни константи."""
    from analysis.lens_history import yearly_table

    text, history = context_with_history
    assert "| Година | Среден композит | Тримесечни точки |" in text
    for row in yearly_table(history):
        assert f"| {row['year']} | {row['mean_composite']:.1f} | {row['n']} |" in text


def test_context_repeats_the_short_norm_caveat(context_with_history):
    """Ранните редове стъпват на по-къси норми — уговорката пътува с таблицата."""
    text, _ = context_with_history
    assert "ПО-КЪСИ норми" in text
    assert "ориентир, не калибрация" in text


def test_context_without_history_stays_unchanged(context):
    """Старият път (без история) не расте нова секция."""
    text, _, _ = context
    assert "## Композитът през времето" not in text


# ── Мандат №47: температурният слой в експорта ───────────────────────────────

@pytest.fixture
def context_with_temperature(tmp_path):
    """Контекстът както го строи `--export-context`: с температурата вътре."""
    from analysis.temperature import temperature

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    snapshot["BG_HPI"] = pd.Series([14.8] * 300, index=idx)        # готов г/г темп
    snapshot["BG_LOANS_HH"] = pd.Series(
        [100.0 * (1.21 ** (i / 12.0)) for i in range(300)], index=idx
    )
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    temp = temperature(SERIES_CATALOG, snapshot)
    out = tmp_path / "ctx.md"
    generate_briefing_context(
        snapshot=snapshot, lens_reports=reports, composite=composite,
        regime=get_regime(composite), output_path=str(out), today=date(2026, 7, 28),
        temp=temp,
    )
    return out.read_text(encoding="utf-8"), temp


def test_context_carries_the_temperature_section(context_with_temperature):
    text, temp = context_with_temperature
    assert (f"## Температурният слой: {temp['n_hot']}/{temp['n_total']} "
            f"бум-серии над зоната си") in text
    assert temp["n_hot"] == 2


def test_context_names_which_series_burn_with_value_and_threshold(context_with_temperature):
    text, temp = context_with_temperature
    for e in temp["hot"]:
        assert f"{e['name_bg']}: **{e['value']:.1f}** при праг {e['hi']:.0f}" in text


def test_context_prints_the_zone_table_with_provenance(context_with_temperature):
    """Зоните идват от POLARITY — нула ръчни константи в експорта."""
    from analysis.temperature import zone_table
    from catalog.polarity import OPT_SOURCE_NOTE

    text, _ = context_with_temperature
    for z in zone_table(SERIES_CATALOG):
        assert (f"| {z['name_bg']} | {z['lo']:.0f} … {z['hi']:.0f}% | "
                f"{z['s']:.0f} пп | {z['provenance']} |") in text
    assert OPT_SOURCE_NOTE in text


def test_context_explains_how_to_read_a_score_under_an_optimal_zone(context_with_temperature):
    """„50 = нормално" е капан при OPT: платото е ЗДРАВЕ, не неутралност."""
    from export.briefing_context import _zone_score

    text, _ = context_with_temperature
    assert f"**{_zone_score():.1f}**, не на 50" in text
    assert _zone_score() > 50.0


def test_context_says_the_thermometer_counts_only_the_upper_breach(context_with_temperature):
    text, _ = context_with_temperature
    assert "САМО нарушенията НАГОРЕ" in text
    assert "look-ahead" in text


def test_context_declares_the_composition_change_under_the_composite(context_with_temperature):
    """Композитът пада без нито едно ново данно — това се КАЗВА, не се крие."""
    text, _ = context_with_temperature
    assert "Съставът е сменен с мандат №47" in text
    assert "не се сравнява механично с четенията отпреди" in text
    assert text.index("Съставът е сменен") < text.index("## Температурният слой")


def test_context_without_a_temperature_skips_the_section(context):
    """Старият път (без термометър) не расте празна секция."""
    text, _, _ = context
    assert "## Температурният слой" not in text


# ── Мандат №53: балонната двойка в температурната секция ─────────────────────

def test_context_carries_the_bubble_pair_sentence_verbatim(context_with_temperature):
    """Един източник: експортът ЦИТИРА `bubble_pair()`, не преписва."""
    from analysis.temperature import bubble_pair

    text, temp = context_with_temperature
    pair = bubble_pair(temp)

    assert pair["active"] is True
    assert pair["sentence"] in text


def test_the_bubble_pair_reads_after_who_burns_and_before_the_tension(
    context_with_temperature,
):
    """Редът на четене: какво гори → съ-прегряване → (после) кой кого изяжда."""
    from analysis.temperature import bubble_pair

    text, temp = context_with_temperature
    assert (text.index("**Кои горят сега:**")
            < text.index(bubble_pair(temp)["sentence"])
            < text.index("**Зоните и откъде идват праговете:**"))


def test_the_bubble_pair_carries_its_provenance_next_to_the_reading(
    context_with_temperature,
):
    from analysis.temperature import BUBBLE_PAIR_PROVENANCE

    text, _ = context_with_temperature
    assert BUBBLE_PAIR_PROVENANCE in text


def test_the_quality_notes_carry_the_bubble_pair_definition_and_p4_numbers():
    """Уговорката пътува с числото: дефиниция · 8/8 · 0/20 · пенсионираният К3."""
    joined = " ".join(DATA_QUALITY_NOTES)

    assert "Балонната двойка (мандат №53)" in joined
    assert "`BG_HPI` е в `temp_hot`" in joined
    for token in ("8/8", "0/20", "25", "2007-08", "2015-19"):
        assert token in joined, token
    assert "ПЕНСИОНИРАН" in joined
    assert "0 пъти на 83 реда" in joined
    assert "29.07.2026" in joined
    assert "прогноза" in joined


def test_lens_rows_do_not_borrow_the_composite_regime_vocabulary(context):
    """„Инфлация — РЕЦЕСИОНЕН" е безсмислица; лещата носи лента, не режим."""
    text, _, _ = context
    lens_table = text.split("| Леща | Score | Състояние |")[1].split("\n\n")[0]
    for regime_name in ("РЕЦЕСИОНЕН", "ЕКСПАНЗИОНЕН", "ВЛОШАВАЩ СЕ"):
        assert regime_name not in lens_table
