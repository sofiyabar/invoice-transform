# invoice-transform

Eval-система для AI-генерации инвойсов из неструктурированного текста. Портфолио-проект (см. `.claude/.skills/project_brief.md` для полного брифа).

**→ [`ABOUT.md`](ABOUT.md)** — цель проекта и методология, для тех, кто впервые открывает репозиторий.

**→ [`DATA_MAP.md`](DATA_MAP.md)** — где какие данные лежат, как связаны, и как дашборд их читает. Если непонятно, откуда взялась цифра на дашборде — начните оттуда.

## Статус

Слои раньше назывались по номеру (Layer 0…Layer 6), теперь — по смыслу; бриф (`.claude/.skills/project_brief.md`) ещё использует старую нумерацию, см. таблицу соответствия в `CLAUDE.md`.

| Секция | Статус |
|---|---|
| Intake Gate (Intent & Completeness) | ✅ реализован, протестирован, прогнан на всех 600 строках датасета |
| Field Accuracy | ✅ реализован (judge-free fuzzy match для свободного текста; `evals/judges/field_judge.py` — опциональный LLM-judge re-score, не в дефолтном пути) |
| Document Accuracy (+ бывший Layer 3 segment-level, см. ниже) | ✅ реализован |
| Production Simulation | ⚠️ частично: `latency_stats()` готов, но реальных таймингов ещё не собрано (используется явно помеченный `LATENCY_ESTIMATE_MS`); CSAT/thumbs — `csat_proxy_stub()`, экстраполяция от critical_error_rate, НЕ вызов judge; batch trend — сознательно не реализован (был только один полный прогон, трендить нечего) |
| *(бывший Layer 5, статистика)* | удалён — реализовывался, потом убран целиком: значимость по сегментам не отвечала на реальный вопрос проекта (см. `CLAUDE.md` "Known open decisions") |
| Business Impact | ✅ реализован — интерактивный P&L/unit-economics дашборд с ползунками в сайдбаре |

Генератор (`generator/base_generator.py`) реализован — обёртка над Gemini (промпт скопирован из Finvoice-AI `aiController.js`), парсинг намеренно хрупкий, чтобы измерять реальный parse-failure rate, а не маскировать его.

**Layer 3 (segment-level) слит в Document Accuracy**: `evals/document_accuracy.py::by_group()` покрывает разбивку resolution rate / critical error rate по сегментам и типам документа — отдельного `layer3_segment.py` больше нет. Бриф этого пока не отражает (см. TODO там).

Дашборд (`dashboard/app.py`) рендерит все 5 секций из сохранённых `eval_runs/*.json`; Business Impact дополнительно пересчитывается вживую от значений в сайдбаре.

Тесты: `pytest` — 68 passed, 1 skipped (форма generator-теста ждёт решения по output-shape).

## Структура

- `generator/` — сам преобразователь: `base_generator.py` (raw text → invoice JSON, Gemini), `intent_gate.py` / `completeness_gate.py` (Intake guardrail поверх baseline), `pipeline.py` (склеивает всё в один вызов).
- `evals/` — eval-иерархия: `intake_intent_gate.py`, `intake_completeness_gate.py`, `field_accuracy.py`, `document_accuracy.py`, `production_simulation.py`, `business_impact.py` + `judges/` (DeepEval GEval) + `runner.py` (оркестратор, пишет `eval_runs/`).
- `data/` — схема данных (`schema.py`), загрузчики (`loaders.py`), синтетический датасет в `data/synthetic/` (см. `dataset_manifest.md` и `generation_notes.md` там же).
- `dashboard/` — Streamlit-дашборд.
- `config/` — явные "экспертные" допущения (severity weights, business assumptions, сегменты); часть значений всё ещё placeholder (0.0, инфра/SLA), см. комментарии в файлах.
- `tests/` — тесты по модулям, актуальный статус см. выше.
- `notebooks/` — история прототипирования (неисправленный SROIE-баг, см. `CLAUDE.md`).
- `scripts/` — CLI-запуск eval-пайплайна и вспомогательные прогоны.
- `eval_runs/` — сохранённые результаты прогонов (gitignored).

## Методология и история решений

- `DATA_MAP.md` — карта данных: пайплайн целиком, схема `metrics_dict`, что дашборд откуда читает.
- `CHANGELOG.md` — ручной журнал значимых решений (данные + алгоритм), не полагается на git log; использует старую нумерацию слоёв (Layer N) в записях, сделанных до переименования — это исторический журнал, задним числом не переписывался.
- `data/synthetic/dataset_manifest.md`, `data/synthetic/generation_notes.md`, `.claude/.skills/*.md` — как и почему собран датасет.
- Assumptions и trade-off'ы по каждой секции — в докстрингах соответствующих модулей (например `evals/field_accuracy.py`, `evals/production_simulation.py`).

## TODO

Реальные latency-замеры, CSAT через настоящий judge, `infra_sla_cost`/`churn_risk_proxy`/`segment_risk_exposure` в Business Impact (нет собранных бизнес-вводных) — по мере реализации.
