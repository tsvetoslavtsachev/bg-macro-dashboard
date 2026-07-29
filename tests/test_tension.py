"""
tests/test_tension.py
=====================
Тензионният слой К1 „Погасяването" + наемите като втора контекстна серия
(мандат №51).

Два гейта носят цялата писта:

1. **Формулата** — работният пример на живия ред (Скаут-факт на мандата, сметнат
   независимо от Fable) трябва да излиза ТОЧНО: ratio ≈ 0.493, външният +5.2,
   трудът −4.8, фискалът +2.7. Ако падне, вграденият К1 мери нещо друго от
   това, което П4 тества.
2. **Композитът е НЕДОКОСНАТ** — К1 е ПРОЧИТ върху лещовите score-ове, а
   наемите са контекст извън всяка леща. И двете добавки трябва да оставят
   композита и всеки лещов score бит-в-бит същите.

Всичко живо работи върху КОМИТНАТИЯ кеш (`get_snapshot` не пипа мрежата).
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from analysis import tension as tension_mod
from analysis.lens_history import (
    ROW_LIVE,
    ROW_QUARTER,
    append_journal,
    build_history,
    history_columns,
    journal_columns,
    load_journal,
)
from analysis.tension import (
    ENERGY_FLOOR,
    SIX_TO_SEVEN_NOTE,
    anchors_note,
    annihilation,
    epoch_ratio_stats,
    price_str,
    price_table,
    ratio_str,
)
from catalog.series import SERIES_CATALOG, series_by_source, validate_catalog
from config import MODULE_WEIGHTS
from core.scorer import compute_composite_score, compute_lens_reports
from sources import build_adapters
from sources.manual_seed import splice_loans

RENTS = "BG_RENTS"

# Работният пример от Скаут-фактите на мандата — живият ред на 29.07.2026.
# Пинва се като ФИКСТУРА (не се чете от данните), за да съди формулата, а не
# седмичната порция числа.
WORKED_SCORES = {
    "inflation": 34.8, "labor": 75.8, "growth": 47.1, "credit": 40.8,
    "external": 2.3, "property": 62.3, "fiscal": 20.5,
}


def _reports(scores: dict) -> dict:
    return {lens: {"score": score} for lens, score in scores.items()}


# ═════════════════════════════════════════════════════════════════════════════
# ФОРМУЛАТА — работният пример
# ═════════════════════════════════════════════════════════════════════════════

def test_the_worked_example_from_the_mandate_comes_out_exactly():
    """L = (34.8, 75.8, 47.1, 40.8, 2.3, 62.3, 20.5) при теглата на №50.

    Сверка по веригата: нето 9.42 → композит 40.58 ≈ живото 40.6 · енергия
    18.56 · **ratio 0.493**. LOO цените: външният +5.2 · трудът −4.8 ·
    фискалът +2.7 (Скаут-факт, сметнат независимо от Fable).
    """
    t = annihilation(_reports(WORKED_SCORES))

    assert t["net"] == pytest.approx(9.42, abs=0.01)
    assert t["composite"] == pytest.approx(40.58, abs=0.01)
    assert t["energy"] == pytest.approx(18.56, abs=0.01)
    assert t["ratio"] == pytest.approx(0.493, abs=0.001)
    assert t["nd"] is False
    assert t["n_lenses"] == 7

    assert t["prices"]["external"] == pytest.approx(5.2, abs=0.05)
    assert t["prices"]["labor"] == pytest.approx(-4.8, abs=0.05)
    assert t["prices"]["fiscal"] == pytest.approx(2.7, abs=0.05)


def test_the_worked_example_names_the_payer_and_the_supporter():
    """Изречението е ЧЕТИМАТА част — то носи и двамата виновници с цените им."""
    t = annihilation(_reports(WORKED_SCORES))

    assert t["top_payer"]["lens"] == "external"
    assert t["top_supporter"]["lens"] == "labor"
    assert "външният сектор (+5.2 т.)" in t["sentence"]
    assert "пазарът на труда (-4.8 т.)" in t["sentence"]
    assert t["sentence"].startswith("49% от лещовата енергия се погасява")


def test_the_leave_one_out_price_is_the_composite_without_the_lens():
    """Цена = композит БЕЗ лещата − композит С нея, с ренормализирани тегла.

    Плюс значи „махнеш ли я, композитът се качва", т.е. лещата ТЕЖИ. Проверката
    е срещу независимо пресметнат композит без лещата, не срещу самата функция.
    """
    t = annihilation(_reports(WORKED_SCORES))
    rest = [l for l in MODULE_WEIGHTS if l != "external"]
    wsum = sum(MODULE_WEIGHTS[l] for l in rest)
    manual = sum(WORKED_SCORES[l] * MODULE_WEIGHTS[l] for l in rest) / wsum

    assert manual - t["composite"] == pytest.approx(t["prices"]["external"], abs=1e-3)
    assert manual > t["composite"], "външният тежи → без него композитът се качва"


def test_the_falsifier_marks_the_composite_corridor_of_the_pivot():
    """Под 0.50 напрежението престава да доминира — коридорът се смята, не гадае."""
    t = annihilation(_reports(WORKED_SCORES))
    f = t["falsifier"]

    assert f["net"] == pytest.approx(0.5 * t["energy"], abs=1e-6)
    assert f["composite_low"] == pytest.approx(50.0 - f["net"], abs=0.05)
    assert f["composite_high"] == pytest.approx(50.0 + f["net"], abs=0.05)
    # И числово: точно на границата съотношението е 0.50
    assert 1.0 - f["net"] / t["energy"] == pytest.approx(0.50, abs=1e-9)


# ═════════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНИЕТО НА ПОКАЗАНИЕТО
# ═════════════════════════════════════════════════════════════════════════════

def test_a_consensus_reading_annihilates_nothing():
    """Всички лещи от една страна → нищо не се погасява (К1 = 0).

    Точно това прави К1 честен при срив: тогава композитът НЕ замазва.
    """
    t = annihilation(_reports({l: 20.0 for l in MODULE_WEIGHTS}))
    assert t["ratio"] == pytest.approx(0.0, abs=1e-9)
    assert t["composite"] == pytest.approx(20.0, abs=1e-9)


def test_perfectly_opposed_lenses_annihilate_everything():
    """Симетрично воюващи сили → композит точно 50 при максимална енергия."""
    scores = {"inflation": 90.0, "growth": 10.0, "labor": 90.0, "credit": 10.0,
              "external": 90.0, "property": 10.0, "fiscal": 50.0}
    t = annihilation(_reports(scores))
    assert t["composite"] == pytest.approx(50.0, abs=1e-9)
    assert t["ratio"] == pytest.approx(1.0, abs=1e-9)


def test_a_weak_field_refuses_to_produce_a_reading():
    """Енергия под прага → „н.д.", НЕ нула: малък знаменател не ражда показание."""
    t = annihilation(_reports({l: 51.0 for l in MODULE_WEIGHTS}))
    assert t["energy"] < ENERGY_FLOOR
    assert t["nd"] is True
    assert t["ratio"] is None
    assert "н.д." in t["sentence"]
    assert ratio_str(t) == "н.д."


def test_a_missing_lens_drops_out_and_the_weights_renormalize():
    """Празната леща изпада — същото правило като в композита, не „неутрално 50"."""
    scores = dict(WORKED_SCORES)
    del scores["fiscal"]
    reports = _reports(scores)
    reports["fiscal"] = {"score": None}

    t = annihilation(reports)
    assert t["n_lenses"] == 6
    assert "fiscal" not in t["prices"]

    wsum = sum(MODULE_WEIGHTS[l] for l in scores)
    manual = sum(scores[l] * MODULE_WEIGHTS[l] for l in scores) / wsum
    assert t["composite"] == pytest.approx(manual, abs=1e-3)


def test_an_empty_report_set_says_so_instead_of_inventing_a_number():
    t = annihilation({})
    assert t["ratio"] is None and t["nd"] is True
    assert t["prices"] == {}
    assert "мълчи" in t["sentence"]


def test_the_price_table_is_sorted_from_the_payer_to_the_supporter():
    rows = price_table(annihilation(_reports(WORKED_SCORES)))
    assert [r["lens"] for r in rows][0] == "external"
    assert [r["lens"] for r in rows][-1] == "labor"
    assert rows == sorted(rows, key=lambda r: r["price"], reverse=True)


def test_a_rounded_zero_price_is_shown_without_a_false_sign():
    """„-0.0" изглежда като дефект; смисълът е „тази леща не мести композита"."""
    assert price_str(-0.03) == "0.0"
    assert price_str(5.22) == "+5.2"
    assert price_str(-4.80) == "-4.8"
    assert price_str(None) == "—"


def test_the_six_to_seven_declaration_is_one_source_and_says_what_it_must():
    """Декларацията пътува с всяко показание — затова живее на ЕДНО място."""
    assert "6-лещовата" in SIX_TO_SEVEN_NOTE
    assert "7-лещовия" in SIX_TO_SEVEN_NOTE
    assert "не се сравняват 1:1" in SIX_TO_SEVEN_NOTE
    assert SIX_TO_SEVEN_NOTE in anchors_note(None)


# ═════════════════════════════════════════════════════════════════════════════
# ЖИВОТО СЪСТОЯНИЕ — от КОМИТНАТИЯ кеш
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def cache_snapshot():
    snapshot = {}
    for source_name, adapter in build_adapters().items():
        keys = [spec["_key"] for spec in series_by_source(source_name)]
        snapshot.update(adapter.get_snapshot(keys))
    if len(snapshot) < len(SERIES_CATALOG):
        pytest.skip("кешът в data/ е непълен — тестът иска комитнатия кеш")
    return splice_loans(snapshot)


@pytest.fixture(scope="module")
def live_history(cache_snapshot):
    return build_history(SERIES_CATALOG, cache_snapshot)


def test_the_history_carries_the_tension_column(live_history):
    assert "k1_ratio" in history_columns()
    assert "k1_ratio" in live_history.columns
    assert live_history["k1_ratio"].dtype == np.float64


def test_the_live_row_tension_equals_the_live_computation(cache_snapshot, live_history):
    """ГЕЙТЪТ: колоната на живия ред == `annihilation` върху живите доклади.

    Консистентност, не зашито число — така тестът съди двигателя всяка седмица,
    вместо да гърми при всяка нова порция данни.
    """
    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    live = annihilation(reports)
    assert float(live_history["k1_ratio"].iloc[-1]) == live["ratio"]
    assert live_history["row_type"].iloc[-1] == ROW_LIVE


def test_every_row_tension_is_recomputable_from_its_own_score_columns(live_history):
    """Колоната не може да се разсинхронизира с реда — смята се от него."""
    for ts, row in live_history.iterrows():
        scores = {l: row[f"score_{l}"] for l in MODULE_WEIGHTS
                  if pd.notna(row[f"score_{l}"])}
        expected = annihilation(_reports(scores))["ratio"]
        stored = row["k1_ratio"]
        if expected is None:
            assert pd.isna(stored), ts
        else:
            assert float(stored) == pytest.approx(expected, abs=1e-9), ts


def test_the_calm_epoch_reads_far_lower_than_the_current_wave(live_history):
    """Санитетът на 2015-19 — и ИЗМЕРЕНОТО, декларирано, не преписаното.

    ⚠ На 6-лещовата история (П4) спокойната епоха е ≈0.008. На живия 7-лещов
    уред измереното е **0.271** (n=20), защото фискалната леща стои на 8-31 в
    2015-17, докато останалите шест са на 55-90 — тя добавя погасена енергия,
    която старият уред не е виждал. Втората половина на епохата (2018-19), в
    която фискалната леща се качва при останалите, чете **0.016** — там мекият
    праг „< 0.10" на мандата оцелява.

    Затова гейтът тук е РЕЛАТИВЕН (спокойната епоха срещу днешната вълна) плюс
    абсолютният праг върху 2018-19. Числата са мерени 29.07.2026 върху
    комитнатия кеш.
    """
    q = live_history[live_history["row_type"] == ROW_QUARTER]
    calm = q.loc["2015-01-01":"2019-12-31", "k1_ratio"].dropna()
    calm_late = q.loc["2018-01-01":"2019-12-31", "k1_ratio"].dropna()
    wave = q.loc["2024-01-01":, "k1_ratio"].dropna()

    assert len(calm) == 20 and len(calm_late) == 8 and len(wave) >= 8
    assert float(calm_late.mean()) < 0.10           # мекият праг на мандата
    assert float(calm.mean()) < 0.5 * float(wave.mean())
    assert float(calm.mean()) < 0.45


def test_the_measured_calm_epoch_travels_with_the_p4_anchors(live_history):
    """Котвите се цитират като 6-лещови, а живото се МЕРИ — двете едно до друго."""
    stats = epoch_ratio_stats(live_history)
    assert stats["label"] == "2015-19"
    assert stats["n"] == 20

    note = anchors_note(live_history)
    assert "0.008" in note and "0.995" in note
    assert f"{stats['mean']:.3f}" in note
    assert SIX_TO_SEVEN_NOTE in note


# ═════════════════════════════════════════════════════════════════════════════
# ЖУРНАЛЪТ
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def reports_and_composite(cache_snapshot):
    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    composite = compute_composite_score(
        {lens: rep["score"] for lens, rep in reports.items()}
    )
    return reports, composite


def test_the_journal_records_the_tension_of_the_run(reports_and_composite, tmp_path):
    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    journal = append_journal(reports, composite, today=date(2026, 7, 29), path=path)

    assert "k1_ratio" in journal_columns()
    assert float(journal["k1_ratio"].iloc[0]) == annihilation(reports)["ratio"]


def test_the_new_column_leaves_the_old_journal_rows_empty_not_zero(
        reports_and_composite, tmp_path):
    """Нулата тук би значела „уредът е мерил и е намерил нула погасяване"."""
    import csv

    reports, composite = reports_and_composite
    path = tmp_path / "journal.csv"
    old_cols = [c for c in journal_columns() if c != "k1_ratio"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(old_cols)
        w.writerow(["2026-07-28" if c == "date" else "" for c in old_cols])

    journal = append_journal(reports, composite, today=date(2026, 7, 29), path=path)
    assert list(journal.columns) == journal_columns()
    assert pd.isna(journal["k1_ratio"].iloc[0])          # старият ред мълчи
    assert not pd.isna(journal["k1_ratio"].iloc[1])      # новият говори
    assert pd.isna(load_journal(path)["k1_ratio"].iloc[0])


# ═════════════════════════════════════════════════════════════════════════════
# ГЕЙТЪТ-ЗВЕЗДА — композитът е БИТ-В-БИТ недокоснат
# ═════════════════════════════════════════════════════════════════════════════

def _synthetic_snapshot(n: int = 300, seed: int = 13) -> dict:
    idx = pd.date_range(end="2026-06-01", periods=n, freq="MS")
    rng = np.random.RandomState(seed)
    return {
        key: pd.Series(50.0 + np.cumsum(rng.normal(0, 0.6, n)), index=idx)
        for key in SERIES_CATALOG
    }


def test_the_rents_series_does_not_move_a_single_lens_or_the_composite():
    """Каталог СЪС и БЕЗ наемите → бит-в-бит равни. Не approx — ТОЧНО."""
    snapshot = _synthetic_snapshot()
    without = {k: v for k, v in SERIES_CATALOG.items() if k != RENTS}

    rep_with = compute_lens_reports(SERIES_CATALOG, snapshot)
    rep_without = compute_lens_reports(without, snapshot)

    for lens in rep_with:
        assert rep_with[lens]["score"] == rep_without[lens]["score"], lens
        assert rep_with[lens]["health_z"] == rep_without[lens]["health_z"], lens
        assert rep_with[lens]["n_series"] == rep_without[lens]["n_series"], lens

    comp_with = compute_composite_score({l: r["score"] for l, r in rep_with.items()})
    comp_without = compute_composite_score(
        {l: r["score"] for l, r in rep_without.items()})
    assert comp_with == comp_without


def test_the_rents_series_never_reaches_a_lens_report():
    reports = compute_lens_reports(SERIES_CATALOG, _synthetic_snapshot())
    scored = {s["key"] for rep in reports.values() for s in rep["series"]}
    assert RENTS not in scored
    assert "BG_HPI" in scored


def test_the_tension_layer_is_a_reading_not_an_input_to_the_composite():
    """К1 чете score-овете и не ги пипа — композитът е същият преди и след.

    Гейтът е механичен: докладите се сравняват с копие ПРЕДИ извикването и
    композитът се преизчислява след него.
    """
    snapshot = _synthetic_snapshot()
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    before = {l: (r["score"], r["health_z"]) for l, r in reports.items()}
    comp_before = compute_composite_score({l: r["score"] for l, r in reports.items()})

    annihilation(reports)

    after = {l: (r["score"], r["health_z"]) for l, r in reports.items()}
    comp_after = compute_composite_score({l: r["score"] for l, r in reports.items()})
    assert after == before
    assert comp_after == comp_before


def test_the_reconstructed_composite_is_untouched_by_the_rents_series():
    """И филмът мери същия уред — колоната `composite` не мърда от контекста."""
    snapshot = _synthetic_snapshot()
    without = {k: v for k, v in SERIES_CATALOG.items() if k != RENTS}
    a = build_history(SERIES_CATALOG, snapshot, grid_start="2024-12-01")
    b = build_history(without, snapshot, grid_start="2024-12-01")
    pd.testing.assert_series_equal(a["composite"], b["composite"])
    pd.testing.assert_series_equal(a["k1_ratio"], b["k1_ratio"])


# ═════════════════════════════════════════════════════════════════════════════
# КАТАЛОГЪТ — наемите като ВТОРА контекстна серия
# ═════════════════════════════════════════════════════════════════════════════

def test_catalog_carries_twenty_one_series_of_which_two_are_context():
    """20 след М50 + наемите на М51; уредът, който произвежда композита, е 19."""
    assert len(SERIES_CATALOG) == 21
    context = [k for k, v in SERIES_CATALOG.items() if v.get("context_only")]
    assert sorted(context) == ["BG_INFL_PERCEIVED", "BG_RENTS"]
    scored = [k for k, v in SERIES_CATALOG.items() if not v.get("context_only")]
    assert len(scored) == 19
    assert validate_catalog() == []


def test_the_rents_series_reads_the_hicp_rent_component():
    """Точният набор е решение на мандата — пинва се, за да не се преоткрива."""
    spec = SERIES_CATALOG[RENTS]
    assert spec["source"] == "eurostat"
    assert spec["id"] == "prc_hicp_minr?geo=BG&coicop18=CP041&unit=RCH_A"
    assert spec["transform"] == "level"      # серията ИДВА като г/г ставка
    assert spec["is_rate"] is True
    assert spec["release_schedule"] == "monthly"
    assert spec["lens"] == []
    assert spec["context_only"] is True
    assert spec["peer_group"] == "context"


def test_the_rents_series_is_in_the_committed_cache(cache_snapshot):
    """Живо проверено 29.07.2026: 10.1 @06.2026, n=343 от 1997-12."""
    s = cache_snapshot[RENTS].dropna()
    assert len(s) >= 340
    assert s.index[0] == pd.Timestamp("1997-12-01")
    assert s.index[-1] == pd.Timestamp("2026-06-01")
    assert float(s.iloc[-1]) == pytest.approx(10.1)


def test_the_rents_do_not_confirm_the_substitution_hypothesis(cache_snapshot):
    """Дискриминаторът, заради който серията изобщо влиза: наемите растат.

    „Бягство от наема" би искало обяснение през свиващо се наемно търсене —
    вместо това наемите са кратно над спокойната епоха. Тестът съди РЕЛАЦИЯТА
    (сега >> 2015-19), не зашито число.
    """
    s = cache_snapshot[RENTS].dropna()
    calm = s[(s.index >= "2015-01-01") & (s.index <= "2019-12-31")]
    assert float(calm.median()) < 3.0
    assert float(s.iloc[-1]) > 3 * float(calm.median())


# ═════════════════════════════════════════════════════════════════════════════
# ЛИЦАТА — smoke
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def rendered(cache_snapshot, live_history, tmp_path_factory):
    """Лицето, както го строи `run.py --briefing` (с тензия и история)."""
    from core.scorer import get_regime
    from export.weekly_briefing import generate_html

    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path_factory.mktemp("html") / "index.html"
    generate_html(cache_snapshot, reports, composite, get_regime(composite), str(out),
                  history=live_history, wow=None,
                  tension=annihilation(reports))
    return out.read_text(encoding="utf-8")


def test_html_carries_the_tension_row_under_the_verdict(rendered, cache_snapshot):
    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    t = annihilation(reports)

    assert 'class="tension-row"' in rendered
    assert f'⚖ {t["sentence"]}' in rendered
    assert rendered.index("class=\"verdict\"") < rendered.index('class="tension-row"')


def test_the_tension_row_tooltip_carries_the_receipt_and_the_declaration(rendered):
    for token in ("leave-one-out", "плюс = тежи, минус = крепи",
                  "Показанието пада под 0.50", SIX_TO_SEVEN_NOTE,
                  "as-of четенето живее в одитната следа"):
        assert token in rendered, token


def test_html_methodology_explains_the_tension_layer(rendered):
    assert "<h4>Тензионният слой (К1 „Погасяването“)</h4>" in rendered
    for token in ("не оцелява до нетното отклонение", "детектор на криза",
                  "leave-one-out аукцион", "0.008", "0.995"):
        assert token in rendered, token


def test_html_methodology_carries_both_housing_hypotheses_without_a_winner(rendered):
    """Двете пътеки стоят РАВНОСТОЙНО — с числа, с фалсификатори, без победител."""
    for token in ("две живи хипотези", "заместващата", "ливъриджната",
                  "+213%", "+176%", "26.3%", "24.6%", "+9пп",
                  "Фалсификаторите", "Ирландия 2005-07", "29.07.2026"):
        assert token in rendered, token
    for forbidden in ("хипотезата е потвърдена", "доказва, че", "установено е"):
        assert forbidden not in rendered, forbidden


def test_html_draws_the_tension_line_on_its_own_right_axis(rendered):
    assert '"name": "Погасена енергия (К1)"' in rendered
    assert 'yaxis: "y3"' in rendered
    assert 'overlaying: "y"' in rendered
    assert 'side: "right"' in rendered
    assert "connectgaps: false" in rendered      # „н.д." къса линията, не рисува 0


def test_html_shows_the_rents_as_a_context_series(rendered):
    from config import CONTEXT_BADGE_BG, CONTEXT_SCORE_NOTE

    assert SERIES_CATALOG[RENTS]["name_bg"] in rendered
    assert f'class="ctx-score" title="{CONTEXT_SCORE_NOTE}">—</td>' in rendered
    assert f'<span class="lens-badge lens-context">{CONTEXT_BADGE_BG}</span>' in rendered


@pytest.fixture(scope="module")
def context_text(cache_snapshot, live_history, tmp_path_factory):
    from analysis.temperature import temperature
    from core.scorer import get_regime
    from export.briefing_context import generate_briefing_context

    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path_factory.mktemp("ctx") / "ctx.md"
    generate_briefing_context(
        snapshot=cache_snapshot, lens_reports=reports, composite=composite,
        regime=get_regime(composite), output_path=str(out), today=date(2026, 7, 29),
        history=live_history, temp=temperature(SERIES_CATALOG, cache_snapshot),
        tension=annihilation(reports),
    )
    return out.read_text(encoding="utf-8")


def test_context_carries_the_tension_block_with_the_full_receipt(context_text,
                                                                cache_snapshot):
    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    t = annihilation(reports)

    assert f"## Тензионният слой (К1 „Погасяването“): {ratio_str(t)}" in context_text
    assert t["sentence"] in context_text
    assert t["falsifier"]["sentence"] in context_text
    for row in price_table(t):
        assert f"| {price_str(row['price'])} |" in context_text
    assert SIX_TO_SEVEN_NOTE in context_text


def test_context_tension_block_sits_after_the_temperature(context_text):
    """Редът на четене: термометърът (какво гори) → тензията (кой кого изяжда)."""
    assert (context_text.index("## Температурният слой")
            < context_text.index("## Тензионният слой"))


def test_context_without_a_tension_skips_the_block(cache_snapshot, tmp_path):
    """Старият път (без тензия) не расте празна секция."""
    from core.scorer import get_regime
    from export.briefing_context import generate_briefing_context

    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path / "ctx.md"
    generate_briefing_context(
        snapshot=cache_snapshot, lens_reports=reports, composite=composite,
        regime=get_regime(composite), output_path=str(out), today=date(2026, 7, 29),
    )
    assert "## Тензионният слой" not in out.read_text(encoding="utf-8")


def test_the_notes_carry_the_tension_the_hypotheses_and_the_rents():
    from export.briefing_context import DATA_QUALITY_NOTES

    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("К1 „Погасяването“", "лъжливото средно, не кризата",
                  "6-лещовата", "7-лещовия", "н.д.",
                  "РАВНОСТОЙНИ", "+213%", "+176%", "26.3%", "24.6%", "+9пп",
                  "Фалсификатори", "не обявявай победител", "29.07.2026",
                  "BG_RENTS", "coicop18=CP041", "prc_hicp_midx", "n=343",
                  "context_only"):
        assert token in joined, token


def test_the_module_declares_its_semantics_in_the_docstring():
    """Мандатът иска семантиката ДЕКЛАРИРАНА при кода, не само в receipt-а."""
    doc = tension_mod.__doc__
    assert "ЛЪЖЛИВОТО СРЕДНО" in doc
    assert "6→7" in doc
    assert "ENERGY_FLOOR" in doc
