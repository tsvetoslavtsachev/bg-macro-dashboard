"""
export/briefing_context.py
==========================
Markdown context export за LLM анализ (горивото на скила `macro-deep-brief-bg`).

Фамилната конвенция: `output/briefing_context_YYYY-MM-DD.md`, генериран през
`python run.py --export-context`. Форматът е компактният (China) модел —
пропорционален на 10 серии, не 44-килобайтовият EU.

Всяко число тук идва от snapshot-а/скоринга. Нула ръчни константи.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from config import LENS_BANDS, LENS_NAMES_BG
from core.display import fmt_value, is_stale

# ── ФИКСИРАНИ бележки за качеството на данните (мандат №38 §А4.4) ────────────
# Уговорките зад числата, които анализаторът трябва да знае ПРЕДИ да ги ползва.
DATA_QUALITY_NOTES = [
    "**HICP след ECOICOP-2 миграцията:** `prc_hicp_manr` е замразен на 12.2025 "
    "(legacy набор „1997-2025“). Четем наследника `prc_hicp_minr` "
    "(dimension `coicop18`, тотал `TOTAL`, базисна `TOT_X_NRG_FOOD`) — пълна история "
    "от 1997-12. Замразената серия крие следевровия скок 04-06.2026.",
    "**Текущата сметка е 4-тримесечна плъзгаща** по конвенция. Суровото тримесечие "
    "е чувствително по-волатилно (Q4'25 = −11.4%, Q1'26 = −8.8%) — на графиката "
    "остава като тънка линия, но скорът и таблиците четат плъзгащата.",
    "**ESI идва от `ei_bssi_m_r2`** (пълна история от 1993, n≈402), не от ролиращата "
    "12-месечна таблица `teibs010` — иначе „percentile спрямо историята“ сравняваше "
    "с последните 12 месеца.",
    "**Промишленото производство** се чете като г/г върху календарно изгладен индекс "
    "(`s_adj=CA`). Нивото само по себе си е сезонен трион; сезонно+календарно "
    "изгладеният вариант (SCA) дава по-мека картина на същата слабост.",
    "**Еврочленство от 01.01.2026** — следи за серийни разриви и за смяна на "
    "методология около прехода; сравненията отпреди и след датата не са автоматично "
    "хомогенни.",
    "**Полярността на заплатите е +1** (по-високи = по-силен пазар на труда) и е "
    "ПОД ПРЕГЛЕД: в прегряваща икономика бърз ръст на компенсациите е двузначен "
    "сигнал (заплатно-ценова спирала). Решението е отложено за Фаза 3.",
]


def _lens_band(score: Optional[float]) -> str:
    """Лещова лента на 0–100 скалата (същите прагове, лещов речник).

    Режимното име („ВЛОШАВАЩ СЕ") принадлежи на КОМПОЗИТА. На ниво леща то би
    твърдяло нещо, което метриката не мери — инфлационна леща „РЕЦЕСИОНЕН"
    е безсмислица. Виж config.LENS_BANDS.
    """
    if score is None:
        return "НЯМА ДАННИ"
    for threshold, label in LENS_BANDS:
        if score >= threshold:
            return label
    return LENS_BANDS[-1][1]


def _fmt_score(score: Optional[float]) -> str:
    return f"{score:.1f}" if score is not None else "—"


def generate_briefing_context(
    snapshot: dict,
    lens_reports: dict,
    composite: Optional[float],
    regime: dict,
    output_path: str,
    today: Optional[date] = None,
) -> str:
    """Генерира Markdown context и го записва. Връща пътя."""
    if today is None:
        today = date.today()

    L: list[str] = []
    L.append("# 🇧🇬 Bulgarian Macro Dashboard — Context за LLM анализ")
    L.append(f"**Дата:** {today.isoformat()}  ")
    L.append(f"**Генериран:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
    L.append(f"**Серии:** {len(snapshot)} / {sum(len(r['series']) for r in lens_reports.values())}  ")
    L.append("")
    L.append("---")
    L.append("")

    # ── Композит + лещова таблица ────────────────────────────────────────────
    L.append(f"## Композитен Macro Score: {_fmt_score(composite)} / 100")
    L.append(f"**Режим:** {regime.get('name', '—')}")
    L.append("")
    L.append("Скалата: 50 = близката 10-годишна норма на всяка серия (робастен z спрямо "
             "median ± 1.4826·MAD, притиснат през tanh). Инфлацията се мери като "
             "ОТКЛОНЕНИЕ от 2% в двете посоки, не като „ниско = добре“. Числото е "
             "сравнимо с us/eu/china-macro-dashboard (същият примитив), но НЕ с "
             "по-ранните percentile-based четения на този дашборд.")
    L.append("")
    L.append("| Леща | Score | Състояние |")
    L.append("|------|-------|-----------|")
    for lens, rep in lens_reports.items():
        name = LENS_NAMES_BG.get(lens, lens)
        L.append(f"| {name} | {_fmt_score(rep['score'])} | {_lens_band(rep['score'])} |")
    L.append("")
    L.append("---")
    L.append("")

    # ── Секция на всяка леща ─────────────────────────────────────────────────
    for lens, rep in lens_reports.items():
        L.append(f"## {LENS_NAMES_BG.get(lens, lens)}")
        L.append(f"**Score:** {_fmt_score(rep['score'])}  **Състояние:** {_lens_band(rep['score'])}")
        L.append("")
        L.append("| Показател | Стойност | Score | Данни към |")
        L.append("|-----------|----------|-------|-----------|")
        for s in rep["series"]:
            last = s.get("last_date") or "—"
            if last != "—" and is_stale(last, s.get("release_schedule", "monthly"), today):
                last = f"⚠ {last}"
            L.append(
                f"| {s['name_bg']} | {fmt_value(s)} | {_fmt_score(s.get('score'))} | {last} |"
            )
        L.append("")

        hints = [s.get("narrative_hint", "").strip() for s in rep["series"]]
        hints = [h for h in hints if h][:2]
        if hints:
            for h in hints:
                L.append(f"- {h}")
            L.append("")
        L.append("---")
        L.append("")

    # ── Бележки за качеството ────────────────────────────────────────────────
    L.append("## ⚠ Бележки за качеството на данните")
    L.append("")
    for note in DATA_QUALITY_NOTES:
        L.append(f"- {note}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("*Данни: Eurostat (НСИ и БНБ репортинг).*")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")
    print(f"✅ Context готов: {output_path}")
    return str(path)
