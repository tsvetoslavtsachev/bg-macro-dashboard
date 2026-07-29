"""
tests/test_derived.py
=====================
Първата ИЗВЕДЕНА серия + живият хипотезен блок (мандат №54).

Три гейта носят пистата:

1. **Конвенцията** — кредитен сток ÷ 4-тримесечна СУМА на номиналния БВП, само
   тримесечия с ДВЕТЕ страни налични. Точно тази забрана прави невъзможна
   грешката, която ръчната сверка правеше: сдвояване на най-свеж кредитен сток
   с по-стар БВП. Затова тестът съди РЕЛАЦИЯТА (последната точка на ratio-то не
   изпреварва последното БВП тримесечие), не само числото.
2. **Правото на отказ** — липсва ли съставка, серията НЕ се ражда; нищо не
   гърми и нищо не се измисля.
3. **Един източник** — числата в `housing_hypotheses` са същите като в серията,
   а двете повърхности (методологията и context експортът) ги ЦИТИРАТ.

⚠ Отклонение от скаут-котвите на мандата, документирано тук нарочно: §0 назова
върха „26.2% на 2009Q4", защото гледаше прозореца ПРЕДИ 2010. Максимумът на
цялата серия е един плато-марк по-нататък — **26.3% на 2010Q2** (2009Q4 чете
26.2). Кодът взима МАКСИМУМА на историята, не прозорец по вкус, затова тук се
пинва живото. Присъдата на мандата не се мени: днешните 24.9% са ПОД върха и в
двете четения — „проби върха" не оцелява никъде.

Всичко живо работи върху КОМИТНАТИЯ кеш — нула мрежови заявки.
"""
from datetime import date

import pandas as pd
import pytest

from catalog.series import SERIES_CATALOG, series_by_source
from core.display import (
    HOUSING_EQUIVALENCE,
    PACE_ANCHOR_QUARTER,
    SUBSTITUTION_SNAPSHOT,
    credit_gdp_gap,
    credit_gdp_reading,
    housing_hypotheses,
)
from core.scorer import compute_composite_score, compute_lens_reports, get_regime
from sources import build_adapters
from sources.derived import CREDIT_GDP_HH, credit_to_gdp, derive_series
from sources.manual_seed import splice_loans

RATIO = CREDIT_GDP_HH
NGDP = "BG_NGDP"
CREDIT = "BG_LOANS_HH"

# Забраненият токен на ревизията: най-острата реплика на ливъриджната хипотеза
# отпадна и не бива да се прероди на нито едно лице.
FORBIDDEN_CLAIM = "проби върха"


@pytest.fixture(scope="module")
def cache_snapshot():
    """Снапшот от комитнатия кеш по ЖИВИЯ път: fetch → splice → derive."""
    snapshot = {}
    for source_name, adapter in build_adapters().items():
        keys = [spec["_key"] for spec in series_by_source(source_name)]
        snapshot.update(adapter.get_snapshot(keys))
    snapshot = derive_series(splice_loans(snapshot))
    if len(snapshot) < len(SERIES_CATALOG):
        pytest.skip("кешът в data/ е непълен — тестът иска комитнатия кеш")
    return snapshot


# ═════════════════════════════════════════════════════════════════════════════
# КОНВЕНЦИЯТА — синтетично, без данни
# ═════════════════════════════════════════════════════════════════════════════

def _quarters(start: str, n: int, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq=freq)


def test_the_ratio_is_the_stock_over_the_four_quarter_sum():
    """Работният пример: сток 100 срещу 4×50 = 200 → 50%.

    Двете конвенции нарочно се разминават — БВП сяда на ПЪРВИЯ месец на
    тримесечието, кредитът на ПОСЛЕДНИЯ. Изравняването е по тримесечие.
    """
    gdp = pd.Series([50.0] * 8, index=_quarters("2024-01-01", 8, "QS-JAN"))
    stock = pd.Series([100.0] * 8, index=_quarters("2024-03-01", 8, "QS-MAR"))

    ratio = credit_to_gdp(stock, gdp)
    assert ratio is not None
    assert float(ratio.iloc[-1]) == pytest.approx(50.0)
    # Първите три тримесечия нямат пълна 4Q сума → изпадат сами.
    assert len(ratio) == 5
    assert ratio.index[0] == pd.Timestamp("2024-10-01")


def test_a_fresher_credit_quarter_does_not_produce_a_ratio():
    """ГЕЙТЪТ на мандата: свеж кредит + застоял БВП = никакво число.

    Точно това сдвояване надуваше ръчната сверка. Серията отказва да го
    произведе — тримесечие без ДВЕТЕ страни просто не се ражда.
    """
    gdp = pd.Series([50.0] * 8, index=_quarters("2024-01-01", 8, "QS-JAN"))
    stock = pd.Series([100.0] * 9, index=_quarters("2024-03-01", 9, "QS-MAR"))

    ratio = credit_to_gdp(stock, gdp)
    assert ratio.index[-1].to_period("Q") == gdp.index[-1].to_period("Q")
    assert ratio.index[-1].to_period("Q") < stock.index[-1].to_period("Q")


def test_the_series_refuses_to_be_born_without_an_ingredient():
    """Право на отказ — без грешка, без warning-шум, без фалшив ред."""
    gdp = pd.Series([50.0] * 8, index=_quarters("2024-01-01", 8, "QS-JAN"))

    assert credit_to_gdp(None, gdp) is None
    assert credit_to_gdp(pd.Series(dtype=float), gdp) is None
    assert credit_to_gdp(gdp, None) is None
    assert credit_to_gdp(gdp, pd.Series(dtype=float)) is None


def test_derive_series_drops_the_key_when_an_ingredient_disappears(cache_snapshot):
    """Махаме НБВП → серията я НЯМА, нищо не гърми (и старата не остава)."""
    snapshot = dict(cache_snapshot)
    assert RATIO in snapshot
    snapshot.pop(NGDP)

    out = derive_series(snapshot)
    assert RATIO not in out
    assert out is snapshot


def test_derive_series_is_idempotent(cache_snapshot):
    """Втори пуск върху същия снапшот дава същата серия, точка по точка."""
    once = derive_series(dict(cache_snapshot))[RATIO]
    twice = derive_series(derive_series(dict(cache_snapshot)))[RATIO]
    pd.testing.assert_series_equal(once, twice)


# ═════════════════════════════════════════════════════════════════════════════
# ЖИВИТЕ КОТВИ — от комитнатия кеш
# ═════════════════════════════════════════════════════════════════════════════

def test_the_live_ratio_matches_the_mandate_anchors(cache_snapshot):
    """Живо проверено 29.07.2026: 24.9% на 2026Q1, n=82 от 2005Q4."""
    s = cache_snapshot[RATIO].dropna()
    assert len(s) >= 80
    assert s.index[-1] == pd.Timestamp("2026-01-01")
    assert float(s.iloc[-1]) == pytest.approx(24.9, abs=0.15)


def test_today_sits_below_the_cyclical_peak_not_above_it(cache_snapshot):
    """ЦЕНТРАЛНАТА присъда на ревизията — СТРОГО неравенство, не approx.

    Върхът е максимумът на историята (виж докстринга на модула за отклонението
    от скаут-котвата 2009Q4). Той е в кризата 2009-10, когато знаменателят се
    сви — уговорката пътува с числото.
    """
    s = cache_snapshot[RATIO].dropna()
    peak_ts = s.idxmax()

    assert float(s.loc[peak_ts]) == pytest.approx(26.3, abs=0.15)
    assert str(peak_ts.to_period("Q")) == "2010Q2"
    assert float(s.iloc[-1]) < float(s.loc[peak_ts])
    assert pd.Timestamp("2008-07-01") <= peak_ts <= pd.Timestamp("2010-12-31")


def test_the_ratio_is_higher_than_at_the_start_of_the_current_wave(cache_snapshot):
    """Посоката оцелява ревизията: съотношението се качва от 2022 насам."""
    s = cache_snapshot[RATIO].dropna()
    assert float(s.iloc[-1]) > float(s.loc[PACE_ANCHOR_QUARTER])
    assert float(s.loc[PACE_ANCHOR_QUARTER]) == pytest.approx(19.7, abs=0.15)


def test_the_last_ratio_point_follows_the_gdp_quarter_not_the_credit_one(cache_snapshot):
    """Обвързващата съставка е знаменателят — това е СМИСЪЛЪТ на конвенцията."""
    ratio_q = cache_snapshot[RATIO].dropna().index[-1].to_period("Q")
    gdp_q = cache_snapshot[NGDP].dropna().index[-1].to_period("Q")
    credit_q = cache_snapshot[CREDIT].dropna().index[-1].to_period("Q")

    assert ratio_q <= gdp_q
    assert credit_q > gdp_q, "кредитът наистина изпреварва — иначе гейтът е празен"
    assert ratio_q < credit_q


# ═════════════════════════════════════════════════════════════════════════════
# ЖИВИЯТ ХИПОТЕЗЕН БЛОК — един източник за двете повърхности
# ═════════════════════════════════════════════════════════════════════════════

def test_the_hypothesis_block_reads_the_same_numbers_as_the_series(cache_snapshot):
    s = cache_snapshot[RATIO].dropna()
    h = housing_hypotheses(cache_snapshot)

    assert h["available"] is True
    assert h["ratio"]["value"] == round(float(s.iloc[-1]), 1)
    assert h["ratio"]["peak_value"] == round(float(s.max()), 1)
    assert h["ratio"]["last_date"] == str(s.index[-1].to_period("Q"))
    assert h["ratio"]["peak_date"] == str(s.idxmax().to_period("Q"))
    assert h["ratio"]["peak_is_now"] is False
    assert h["ratio"]["peak_in_crisis"] is True
    assert h["ratio"]["pace_pp_per_year"] == pytest.approx(1.6, abs=0.15)


def test_the_gap_is_exactly_the_two_displayed_numbers(cache_snapshot):
    """Разривът трябва да е сметаем от двете числа пред очите на читателя."""
    from core.primitives import apply_transform

    gap = credit_gdp_gap(cache_snapshot)
    credit = apply_transform(
        cache_snapshot[CREDIT], SERIES_CATALOG[CREDIT]["transform"]).dropna()
    ngdp = apply_transform(
        cache_snapshot[NGDP], SERIES_CATALOG[NGDP]["transform"]).dropna()

    assert gap["credit_yoy"] == round(float(credit.iloc[-1]), 1)
    assert gap["ngdp_yoy"] == round(float(ngdp.iloc[-1]), 1)
    assert gap["gap_pp"] == round(gap["credit_yoy"] - gap["ngdp_yoy"], 1)
    assert gap["gap_pp"] == pytest.approx(7.5, abs=0.15)


def test_the_rents_stay_the_discriminator(cache_snapshot):
    h = housing_hypotheses(cache_snapshot)
    rents = h["rents"]
    assert rents["value"] == pytest.approx(10.1, abs=0.15)
    assert rents["calm_median"] == pytest.approx(1.0, abs=0.15)
    assert rents["calm_label"] == "2015-19"
    assert rents["cooling"] is False


def _all_sentences(h: dict) -> list[str]:
    out = [h["revision"], h["equivalence"]]
    for block in ("ratio", "gap", "rents"):
        if h.get(block):
            out.append(h[block]["sentence"])
    for hyp in h["hypotheses"]:
        out += [hyp["sentence"], hyp["claim"], hyp["falsifier"]]
        if hyp.get("lesson"):
            out.append(hyp["lesson"])
    return out


def test_no_sentence_declares_a_winner(cache_snapshot):
    """Забраната е КОДИРАНА в изреченията, не е стилистична молба към писача."""
    for sentence in _all_sentences(housing_hypotheses(cache_snapshot)):
        assert "побед" not in sentence.lower(), sentence
        assert "потвърд" not in sentence.lower(), sentence
        assert "доказва" not in sentence.lower(), sentence
        assert FORBIDDEN_CLAIM not in sentence, sentence


def test_the_sentences_are_deterministic(cache_snapshot):
    a = housing_hypotheses(cache_snapshot)
    b = housing_hypotheses(cache_snapshot)
    assert _all_sentences(a) == _all_sentences(b)


def test_the_revision_names_the_class_of_the_error(cache_snapshot):
    """Ревизията е неутрална: именува грешката, не се кае."""
    revision = housing_hypotheses(cache_snapshot)["revision"]
    for token in ("Ревизия", "29.07.2026", "по-стар БВП", "ПОД цикличния връх"):
        assert token in revision, token
    assert "съжал" not in revision.lower()
    assert "извин" not in revision.lower()


def test_the_hypotheses_carry_both_names_and_their_falsifiers(cache_snapshot):
    h = housing_hypotheses(cache_snapshot)
    assert [x["name"] for x in h["hypotheses"]] == ["заместващата", "ливъриджната"]
    for hyp in h["hypotheses"]:
        assert hyp["falsifier"].startswith("Пада, ако")
        assert "Живо:" in hyp["falsifier"]
    assert h["equivalence"] == HOUSING_EQUIVALENCE
    assert "РАВНОСТОЙНО" in h["equivalence"]


def test_the_manual_snapshot_is_labelled_as_one(cache_snapshot):
    """Компенсации срещу HPI ОСТАВАТ ръчна сверка — и го КАЗВАТ."""
    substitution = housing_hypotheses(cache_snapshot)["hypotheses"][0]
    assert substitution["is_live"] is False
    assert f"ръчна сверка към {SUBSTITUTION_SNAPSHOT['as_of']}" in substitution["claim"]
    assert f"+{SUBSTITUTION_SNAPSHOT['compensation_pct']}%" in substitution["claim"]


def test_an_empty_snapshot_produces_no_hypothesis_numbers():
    """Без данни блокът мълчи вместо да изсипе полу-рецепта."""
    h = housing_hypotheses({})
    assert h["available"] is False
    assert h["ratio"] is None and h["gap"] is None and h["rents"] is None
    assert credit_gdp_reading(None) is None


# ═════════════════════════════════════════════════════════════════════════════
# ЛИЦАТА — живите числа стигат до двете повърхности
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def live_pages(cache_snapshot, tmp_path_factory):
    """Методологията и context експортът, 1:1 по `run.py` (без мрежа)."""
    from analysis.lens_history import build_history
    from analysis.temperature import temperature
    from analysis.tension import annihilation
    from export.briefing_context import generate_briefing_context
    from export.methodology import generate_methodology

    housing = housing_hypotheses(cache_snapshot)
    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    history = build_history(SERIES_CATALOG, cache_snapshot)

    out = tmp_path_factory.mktemp("pages")
    generate_methodology(str(out / "methodology.html"), history=history,
                         housing=housing)
    generate_briefing_context(
        snapshot=cache_snapshot, lens_reports=reports, composite=composite,
        regime=get_regime(composite), output_path=str(out / "ctx.md"),
        today=date(2026, 7, 29), history=history,
        temp=temperature(SERIES_CATALOG, cache_snapshot),
        tension=annihilation(reports),
    )
    return (
        (out / "methodology.html").read_text(encoding="utf-8"),
        (out / "ctx.md").read_text(encoding="utf-8"),
        housing,
    )


def test_both_faces_carry_the_live_hypothesis_sentences(live_pages):
    """СТРУКТУРНИЯТ пин, заменил токен-пиновете на №51: повърхностите цитират
    блока дословно, вместо да преписват числа, които остаряват мълчаливо."""
    import html as _html

    methodology, context, housing = live_pages
    for hyp in housing["hypotheses"]:
        assert hyp["claim"] in context, hyp["name"]
        assert _html.escape(hyp["claim"]) in methodology, hyp["name"]
        assert hyp["falsifier"] in context, hyp["name"]
        assert _html.escape(hyp["falsifier"]) in methodology, hyp["name"]
    assert housing["revision"] in context
    assert _html.escape(housing["revision"]) in methodology
    assert housing["equivalence"] in context
    assert _html.escape(housing["equivalence"]) in methodology


def test_the_live_numbers_are_actually_printed(live_pages):
    """Числото стига до текста, не само изречението до теста."""
    methodology, context, housing = live_pages
    ratio, gap = housing["ratio"], housing["gap"]
    for text in (methodology, context):
        assert f"{ratio['value']:.1f}%" in text
        assert f"{ratio['peak_value']:.1f}%" in text
        assert ratio["peak_date"] in text
        assert f"{gap['gap_pp']:+.1f} пп" in text


def test_the_retired_claim_exists_nowhere(live_pages):
    """„Проби върха от 2008" е мъртво — на нито едно лице, в нито един източник."""
    from pathlib import Path

    methodology, context, _ = live_pages
    assert FORBIDDEN_CLAIM not in methodology
    assert FORBIDDEN_CLAIM not in context

    root = Path(__file__).parents[1]
    for name in ("README.md", "AGENT.md"):
        assert FORBIDDEN_CLAIM not in (root / name).read_text(encoding="utf-8"), name


def test_the_context_notes_point_at_the_live_block_instead_of_repeating_it():
    """Бележката вече не носи собствени числа — тя праща към живия блок."""
    from export.briefing_context import DATA_QUALITY_NOTES

    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("BG_CREDIT_GDP_HH", "BG_NGDP", "ИЗВЕДЕНА", "4-тримесечната СУМА",
                  "НЕ обявявай победител".replace("НЕ ", "не "),
                  "Двете хипотези", "ревизия", "цитирай ОТТАМ"):
        assert token.lower() in joined.lower(), token
    assert FORBIDDEN_CLAIM not in joined
