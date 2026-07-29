"""
tests/test_methodology_page.py
==============================
Методологията на СОБСТВЕНА страница (мандат №52).

Гейтът тук е един: съдържанието е ПРЕМЕСТЕНО, не изтрито. Затова списъкът
на заглавията е закотвен ПОИМЕННО (не като брой) — точно както стоеше на
лицето преди мандата. Ако утре една секция изчезне в рефактор, тестът казва
коя.

Останалите методологични асерции живеят при своите теми (`test_form_canon`,
`test_tension`) — просто вече гледат тази страница, а не `index.html`.
"""
import pandas as pd
import pytest

from catalog.series import SERIES_CATALOG
from export.methodology import (
    BACK_LINK_LABEL,
    METHODOLOGY_HREF,
    METHODOLOGY_TEASER,
    METHODOLOGY_TITLE,
    generate_methodology,
)
from export.page_style import BASE_CSS
from export.weekly_briefing import generate_html


# Списъкът, преписан от лицето ПРЕДИ мандата (`<details class="methodology">`,
# HEAD f0dff29). Не се генерира от кода — иначе би се съгласявал сам със себе си.
FACE_SECTIONS_BEFORE_52 = [
    "Скалата 0–100",
    "Инфлацията се мери като отклонение от 2%",
    "Инфлацията: двата гласа",
    "Усещаната инфлация — контекст, не компонент",
    "Текущата сметка е 4-тримесечна плъзгаща",
    "Композитът",
    "Оптималните зони и температурата",
    "Тензионният слой (К1 „Погасяването“)",
    "Имоти и строителство",
    "Държавните финанси",
    "As-of дисциплина",
    "Дългата кредитна памет",
    "Цената на кредита",
    "Филмът на композита",
    "Къс прозорец",
]


@pytest.fixture
def page(tmp_path):
    out = tmp_path / "methodology.html"
    generate_methodology(str(out))
    return out.read_text(encoding="utf-8")


def _face(tmp_path):
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    out = tmp_path / "index.html"
    generate_html(snapshot, reports, composite, get_regime(composite), str(out))
    return out.read_text(encoding="utf-8")


def test_the_page_is_generated_as_a_standalone_document(tmp_path):
    out = tmp_path / "methodology.html"
    generate_methodology(str(out))

    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert f"<title>{METHODOLOGY_TITLE}" in html
    assert 'lang="bg"' in html


def test_the_page_carries_every_section_the_face_used_to_carry(page):
    """Преместено, не пренаписано: всяко заглавие от лицето е ТУК."""
    for title in FACE_SECTIONS_BEFORE_52:
        assert f"<h4>{title}</h4>" in page, title
    assert page.count("<h4>") == len(FACE_SECTIONS_BEFORE_52)


def test_the_page_leads_back_to_the_dashboard(page):
    """Относителен линк — работи и на Pages, и локално през file://."""
    assert f'<a class="back-link" href="index.html">{BACK_LINK_LABEL}</a>' in page
    assert "http://localhost" not in page
    assert "file:///" not in page


def test_the_page_and_the_face_share_one_stylesheet(page, tmp_path):
    """№43 корен-прецедентът: общият стил е ЕДНА константа, не две копия."""
    assert BASE_CSS in page
    assert BASE_CSS in _face(tmp_path)


def test_the_face_keeps_the_link_card_and_drops_the_block(tmp_path):
    face = _face(tmp_path)
    assert '<details class="methodology"' not in face
    assert f'<a class="page-link" href="{METHODOLOGY_HREF}">' in face
    assert METHODOLOGY_TEASER in face
    # Обяснението на място (tooltips-ите на сериите) НЕ е мърдало
    assert 'class="ind-name" title=' in face


def test_the_face_no_longer_carries_the_moved_prose(tmp_path):
    """Ако някой ден блокът се върне тихо, това пада."""
    face = _face(tmp_path)
    for token in ("1.4826 · MAD", "детектор на криза", "две живи хипотези",
                  "Маастрихтските", "score_journal.csv"):
        assert token not in face, token


def test_both_pages_are_byte_identical_on_a_second_run(tmp_path):
    """Двоен пуск → нула диф. Иначе всеки ритуал би раждал шумен комит."""
    from core.scorer import compute_composite_score, compute_lens_reports, get_regime

    idx = pd.date_range(end="2026-06-01", periods=300, freq="MS")
    snapshot = {key: pd.Series([1.0, 3.0] * 150, index=idx) for key in SERIES_CATALOG}
    reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    composite = compute_composite_score({l: r["score"] for l, r in reports.items()})
    regime = get_regime(composite)

    first, second = [], []
    for bucket, name in ((first, "a"), (second, "b")):
        d = tmp_path / name
        d.mkdir()
        generate_html(snapshot, reports, composite, regime, str(d / "index.html"))
        generate_methodology(str(d / "methodology.html"))
        bucket.append((d / "index.html").read_bytes())
        bucket.append((d / "methodology.html").read_bytes())

    assert first[0] == second[0]
    assert first[1] == second[1]
