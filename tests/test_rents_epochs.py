"""
tests/test_rents_epochs.py
==========================
Наемите през епохите + консолидацията на епохните граници (мандат №55).

Четири гейта носят пистата:

1. **Числата са ЖИВИ** — медианите и максимумите се смятат от серията, не се
   преписват. Затова тестът съди РЕЛАЦИИТЕ (сега ≥ кризисната медиана · сега
   > 5× спокойната · сега < максимума на текущата епоха) и държи котвите с
   допуск, вместо да пинва точка, която следващият месец мести.
2. **Претенциите са УСЛОВНИ** — синтетична серия, при която условието не важи,
   НЕ произнася „над медианата". Кодирана честност, не стилистична молба.
3. **Един източник** — спокойната медиана в наемния ред на `housing_hypotheses`
   е ТОЧНО тази на епохния прочит (числово равенство), а двете повърхности
   носят ТОЧНО изречението му.
4. **Консолидацията** — епохните граници живеят в `config.EPOCHS`; `display` и
   `tension` ги четат оттам и литералите не се завръщат в двата модула.

⚠ Отклонение от скаут-котвите на мандата, документирано тук нарочно: §0 назова
опашката „1998-2000, макс 359.4". Прозорецът на кода е ОТВОРЕН отляво (началото
на серията → `POST_HYPERINFLATION_END`), защото фенсът трябва да покрива цялото
начало: най-голямото хиперинфлационно число (**566.0% г/г, 1997-12**) стои точно
в месеца, който скаутският прозорец изрязваше. Затова живият прочит чете
„1997-2000 (макс 566.0%)". Смисълът на уговорката не се мени — само става цяла.

Всичко живо работи върху КОМИТНАТИЯ кеш — нула мрежови заявки.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import analysis.tension as tension_mod
import core.display as display_mod
from catalog.series import SERIES_CATALOG, series_by_source
from config import EPOCH_NAMES_BG, EPOCHS, POST_HYPERINFLATION_END
from core.display import (
    epoch_label,
    housing_hypotheses,
    rents_epochs_reading,
)
from core.scorer import compute_composite_score, compute_lens_reports, get_regime
from sources import build_adapters
from sources.derived import derive_series
from sources.manual_seed import splice_loans

RENTS = "BG_RENTS"
ROOT = Path(__file__).parents[1]


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


@pytest.fixture(scope="module")
def reading(cache_snapshot):
    return rents_epochs_reading(cache_snapshot[RENTS])


# ═════════════════════════════════════════════════════════════════════════════
# КОНСОЛИДАЦИЯТА — епохните граници на ЕДНО място
# ═════════════════════════════════════════════════════════════════════════════

def test_the_epoch_bounds_in_config_are_exactly_the_old_literals():
    """Консолидацията е ПРЕМЕСТВАНЕ, не преизмисляне: границите са същите."""
    assert EPOCHS["calm"] == ("2015-01-01", "2019-12-31")
    assert EPOCHS["crisis"] == ("2021-01-01", "2023-12-31")
    assert EPOCHS["current"] == ("2024-01-01", None)
    assert set(EPOCH_NAMES_BG) == set(EPOCHS)


def test_display_and_tension_read_the_bounds_from_config():
    """Псевдонимите оцеляват (нищо не се чупи по import) и сочат към config."""
    assert (display_mod.CRISIS_EPOCH_START,
            display_mod.CRISIS_EPOCH_END) == EPOCHS["crisis"]
    assert display_mod.CALM_EPOCH == EPOCHS["calm"]
    assert (tension_mod.CALM_EPOCH_START,
            tension_mod.CALM_EPOCH_END) == EPOCHS["calm"]


def test_the_epoch_literals_do_not_come_back_into_the_two_modules():
    """Пинът срещу тихото завръщане: датите се четат, не се пишат наново.

    Ако утре някой напише „2015-01-01" пряко в `display` или `tension`,
    консолидацията е мъртва и това пада — точно тук, а не мандат по-късно.
    """
    for module in ("core/display.py", "analysis/tension.py"):
        text = (ROOT / module).read_text(encoding="utf-8")
        for lo, hi in EPOCHS.values():
            assert f'"{lo}"' not in text, f"{module} държи литерал {lo}"
            if hi is not None:
                assert f'"{hi}"' not in text, f"{module} държи литерал {hi}"


def test_the_open_epoch_label_says_now_instead_of_a_year_someone_must_move():
    assert epoch_label("2021-01-01", "2023-12-31") == "2021-23"
    assert epoch_label("2015-01-01", "2019-12-31") == "2015-19"
    assert epoch_label("2024-01-01", None) == "2024-сега"


# ═════════════════════════════════════════════════════════════════════════════
# ЖИВИЯТ ПРОЧИТ — от комитнатия кеш
# ═════════════════════════════════════════════════════════════════════════════

def test_the_three_comparable_epochs_match_the_mandate_anchors(reading):
    """Живо проверено 29.07.2026 — котвите с допуск, не точка."""
    by_key = reading["by_key"]
    assert [e["key"] for e in reading["epochs"]] == ["calm", "crisis", "current"]

    assert by_key["calm"]["median"] == pytest.approx(1.0, abs=0.2)
    assert by_key["crisis"]["median"] == pytest.approx(6.6, abs=0.3)
    assert by_key["current"]["median"] == pytest.approx(7.9, abs=0.3)
    assert by_key["calm"]["n"] == 60          # 5 години × 12 месеца
    assert by_key["crisis"]["n"] == 36        # 3 години × 12 месеца


def test_the_finding_survives_as_a_relation_not_as_a_number(reading):
    """СТРОГИТЕ неравенства на мандата — присъдата, не снимката.

    Наемната инфлация след кризата не спря, а се ускори: днешният темп стои НАД
    медианата на самата инфлационна криза и кратно над спокойната норма, но под
    върха на текущата епоха (лек откат).
    """
    value = reading["value"]
    by_key = reading["by_key"]

    assert value >= by_key["crisis"]["median"]
    assert value > 5 * by_key["calm"]["median"]
    assert value < by_key["current"]["max"]


def test_the_live_claims_are_the_ones_the_numbers_allow(reading):
    assert reading["claims"]["above_crisis_median"] is True
    assert reading["claims"]["multiple_of_calm"] > 5
    assert reading["claims"]["at_current_peak"] is False
    assert reading["claims"]["off_current_peak"] is True


def test_the_multiple_is_computable_from_the_two_printed_numbers(reading):
    """Читателят трябва да може да я сметне сам от числата пред очите си."""
    calm_median = reading["by_key"]["calm"]["median"]
    assert reading["claims"]["multiple_of_calm"] == round(
        reading["value"] / calm_median, 1
    )


def test_the_sentence_carries_all_three_epochs_and_the_tail_caveat(reading):
    sentence = reading["sentence"]
    for e in reading["epochs"]:
        assert e["label"] in sentence, e["label"]
    assert "над медианата на кризисната епоха" in sentence
    assert "с откат от върха" in sentence
    assert "следхиперинфлационна" in sentence
    assert "НЕ влиза в сравненията" in sentence


def test_the_tail_is_a_caveat_not_a_comparable_epoch(reading):
    """Опашката НЕ е в списъка епохи — тя е фенс, не съперник."""
    assert [e["key"] for e in reading["epochs"]] == list(
        k for k in ("calm", "crisis", "current")
    )
    tail = reading["tail"]
    assert tail is not None
    assert tail["max"] > 100          # тризначни проценти — друг свят
    assert tail["label"].endswith(str(pd.Timestamp(POST_HYPERINFLATION_END).year))


# ═════════════════════════════════════════════════════════════════════════════
# УСЛОВНОСТТА — синтетично, без данни
# ═════════════════════════════════════════════════════════════════════════════

def _series(calm: float, crisis: float, current: float, now: float,
            start: str = "1997-12-01") -> pd.Series:
    """Серия с познати епохи: постоянна стойност във всяка, `now` накрая."""
    idx = pd.date_range(start, "2026-06-01", freq="MS")
    values = []
    for ts in idx:
        if ts <= pd.Timestamp(POST_HYPERINFLATION_END):
            values.append(300.0)
        elif pd.Timestamp("2015-01-01") <= ts <= pd.Timestamp("2019-12-31"):
            values.append(calm)
        elif pd.Timestamp("2021-01-01") <= ts <= pd.Timestamp("2023-12-31"):
            values.append(crisis)
        elif ts >= pd.Timestamp("2024-01-01"):
            values.append(current)
        else:
            values.append(2.0)
    s = pd.Series(values, index=idx)
    s.iloc[-1] = now
    return s


def test_a_cool_series_does_not_claim_to_be_above_the_crisis_median():
    """Условието не важи → претенцията не се произнася. Точка."""
    cool = rents_epochs_reading(_series(calm=1.0, crisis=6.0, current=3.0, now=2.0))

    assert cool["claims"]["above_crisis_median"] is False
    assert "над медианата" not in cool["sentence"]
    assert "под медианата на кризисната епоха" in cool["sentence"]


def test_a_hot_series_does_claim_it():
    hot = rents_epochs_reading(_series(calm=1.0, crisis=6.0, current=8.0, now=9.0))

    assert hot["claims"]["above_crisis_median"] is True
    assert "над медианата на кризисната епоха" in hot["sentence"]


def test_a_value_at_the_epoch_peak_says_so_instead_of_inventing_a_pullback():
    peak = rents_epochs_reading(_series(calm=1.0, crisis=6.0, current=8.0, now=8.0))

    assert peak["claims"]["at_current_peak"] is True
    assert "на върха на текущата епоха" in peak["sentence"]
    assert "с откат" not in peak["sentence"]


def test_a_series_that_starts_after_the_tail_does_not_carry_the_caveat():
    """Серия от 2005+ няма хиперинфлационна опашка — уговорката не се лепи."""
    young = rents_epochs_reading(
        _series(calm=1.0, crisis=6.0, current=8.0, now=9.0, start="2005-01-01")
    )

    assert young["tail"] is None
    assert "следхиперинфлационна" not in young["sentence"]


def test_a_multiple_below_one_does_not_say_above():
    """Кратността се СМЯТА; думата „над" е условна, не украса."""
    below = rents_epochs_reading(_series(calm=4.0, crisis=6.0, current=3.0, now=2.0))

    assert below["claims"]["multiple_of_calm"] < 1
    assert "× над спокойната" not in below["sentence"]
    assert "× спрямо спокойната" in below["sentence"]


def test_the_reading_is_none_without_data():
    assert rents_epochs_reading(None) is None
    assert rents_epochs_reading(pd.Series(dtype="float64")) is None


def test_the_reading_is_deterministic(cache_snapshot):
    a = rents_epochs_reading(cache_snapshot[RENTS])
    b = rents_epochs_reading(cache_snapshot[RENTS])
    assert a["sentence"] == b["sentence"]
    assert a["epochs"] == b["epochs"]


# ═════════════════════════════════════════════════════════════════════════════
# ЕДИН ИЗТОЧНИК — хипотезният ред и двете повърхности
# ═════════════════════════════════════════════════════════════════════════════

def test_the_hypothesis_row_reads_the_calm_median_from_the_epoch_reading(
        cache_snapshot, reading):
    """Числово равенство, не два пътя до едно и също число."""
    h = housing_hypotheses(cache_snapshot)

    assert h["rents"]["calm_median"] == reading["by_key"]["calm"]["median"]
    assert h["rents"]["calm_label"] == reading["by_key"]["calm"]["label"]
    assert h["rents_epochs"] is h["rents"]["epochs"]
    assert h["rents"]["epochs"]["sentence"] == reading["sentence"]


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

    out = tmp_path_factory.mktemp("pages55")
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


def test_both_surfaces_carry_exactly_the_sentence_of_the_reading(live_pages):
    import html as _html

    methodology, context, housing = live_pages
    sentence = housing["rents_epochs"]["sentence"]

    assert sentence in context
    assert _html.escape(sentence) in methodology


def test_both_surfaces_carry_the_epoch_table(live_pages):
    methodology, context, housing = live_pages
    for e in housing["rents_epochs"]["epochs"]:
        assert f"| {e['name_bg']} | {e['label']} |" in context, e["key"]
        assert f"<td>{e['label']}</td>" in methodology, e["key"]
        assert f"{e['median']:.1f}%" in methodology, e["key"]


def test_the_methodology_keeps_the_epoch_prose_inside_the_housing_section(
        live_pages):
    """Нов H4 НЕ се ражда — епохите стоят при жилищния въпрос, където им е мястото."""
    methodology, _, _ = live_pages
    assert "<h4>Имоти и строителство</h4>" in methodology
    assert (methodology.index("<h4>Имоти и строителство</h4>")
            < methodology.index("Наемите се четат през епохи")
            < methodology.index("<h4>Държавните финанси</h4>"))


def test_the_notes_describe_the_structure_and_point_at_the_live_block():
    """Бележката носи ПОЛИТИКАТА, числата стоят в живия блок (прецедент №54)."""
    from export.briefing_context import DATA_QUALITY_NOTES

    joined = " ".join(DATA_QUALITY_NOTES)
    for token in ("BG_RENTS", "ЕПОХНО", "config.EPOCHS", "Наемите през епохите",
                  "цитирай ОТТАМ", "следхиперинфлационна", "УСЛОВНИ"):
        assert token in joined, token
    # Нула замразени епохни числа в текста на бележката — те живеят в прочита.
    for frozen in ("медиана 1.0", "медиана 6.6", "медиана 7.9", "10.1%"):
        assert frozen not in joined, frozen


def test_the_composite_is_untouched_by_the_epoch_reading(cache_snapshot):
    """Наемите остават КОНТЕКСТ: епохният прочит не влиза в никоя леща."""
    assert SERIES_CATALOG[RENTS]["context_only"] is True
    assert SERIES_CATALOG[RENTS]["lens"] == []

    reports = compute_lens_reports(SERIES_CATALOG, cache_snapshot)
    assert all(
        RENTS not in [s["key"] for s in rep["series"]] for rep in reports.values()
    )
