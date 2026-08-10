# invoice-transform

Eval-система для AI-генерации инвойсов из неструктурированного текста. Портфолио-проект (см. `.claude/.skills/project_brief.md` для полного брифа).

**→ [`DATA_MAP.md`](DATA_MAP.md)** — где какие данные лежат, как связаны, и как дашборд их читает. Если непонятно, откуда взялась цифра на дашборде — начните оттуда.

## Статус

| Слой | Статус |
|---|---|
| Layer 0 — Intent & Completeness Gate | ✅ реализован, протестирован, прогнан на всех 600 строках датасета |
| Layer 1 — Field-level | ✅ реализован (judge-free fuzzy match для свободного текста; `evals/judges/field_judge.py` — опциональный LLM-judge re-score, не в дефолтном пути) |
| Layer 2 — Document-level (+ бывший Layer 3 segment-level, см. ниже) | ✅ реализован |
| Layer 4 — Production-simulation | ⚠️ частично: `latency_stats()` готов, но реальных таймингов ещё не собрано (используется явно помеченный `LATENCY_ESTIMATE_MS`); CSAT/thumbs — `csat_proxy_stub()`, экстраполяция от critical_error_rate, НЕ вызов judge; batch trend — сознательно не реализован (был только один полный прогон, трендить нечего) |
| Layer 5 — Statistical layer | ⛔ не реализован (TODO) |
| Layer 6 — Business Impact | ⛔ не реализован (TODO) |

Генератор (`generator/base_generator.py`) реализован — обёртка над Gemini (промпт скопирован из Finvoice-AI `aiController.js`), парсинг намеренно хрупкий, чтобы измерять реальный parse-failure rate, а не маскировать его.

**Layer 3 (segment-level) слит в Layer 2**: `evals/layer2_document.py::by_group()` покрывает разбивку resolution rate / critical error rate по сегментам и типам документа — отдельного `layer3_segment.py` больше нет. Бриф этого пока не отражает (см. TODO там).

Дашборд (`dashboard/app.py`) рендерит Layer 0-2 из сохранённых `eval_runs/*.json`; Layer 3-6 — плейсхолдер "Not implemented yet".

Тесты: `pytest` — 60 passed, 3 skipped (Layer 6 traceability-тест и форма generator-теста ждут своих слоёв).

## Структура

- `generator/` — сам преобразователь: `base_generator.py` (raw text → invoice JSON, Gemini), `intent_gate.py` / `completeness_gate.py` (Layer 0 guardrail поверх baseline), `pipeline.py` (склеивает всё в один вызов).
- `evals/` — eval-иерархия: `layer0_intent_gate.py`, `layer0_completeness_gate.py`, `layer1_field.py`, `layer2_document.py`, `layer4_production_sim.py`, `layer5_statistics.py` (TODO), `business_layer.py` (TODO, Layer 6) + `judges/` (DeepEval GEval) + `runner.py` (оркестратор, пишет `eval_runs/`).
- `data/` — схема данных (`schema.py`), загрузчики (`loaders.py`), синтетический датасет в `data/synthetic/` (см. `dataset_manifest.md` и `generation_notes.md` там же).
- `dashboard/` — Streamlit-дашборд + SQL-слой (Databricks) — заготовка.
- `config/` — явные "экспертные" допущения (severity weights, business assumptions, сегменты); часть значений всё ещё placeholder (0.0), см. комментарии в файлах.
- `tests/` — тесты по модулям, актуальный статус см. выше.
- `notebooks/` — история прототипирования (неисправленный SROIE-баг, см. `CLAUDE.md`).
- `scripts/` — CLI-запуск eval-пайплайна и вспомогательные прогоны.
- `eval_runs/` — сохранённые результаты прогонов (gitignored).

## Методология и история решений

- `DATA_MAP.md` — карта данных: пайплайн целиком, схема `metrics_dict`, что дашборд откуда читает.
- `CHANGELOG.md` — ручной журнал значимых решений (данные + алгоритм), не полагается на git log.
- `data/synthetic/dataset_manifest.md`, `data/synthetic/generation_notes.md`, `.claude/.skills/*.md` — как и почему собран датасет.
- Assumptions и trade-off'ы по каждому слою — в докстрингах соответствующих модулей (например `evals/layer1_field.py`, `evals/layer4_production_sim.py`).

## TODO

Layer 5 (статистика/judge stability), Layer 6 (бизнес-метрики), реальные latency-замеры, CSAT через настоящий judge, README-методология по Layer 5-6 — по мере реализации.
