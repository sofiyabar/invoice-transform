# invoice-transform

Eval-система для AI-генерации инвойсов из неструктурированного текста. Портфолио-проект (см. `.claude/.skills/project_brief.md` для полного брифа).

Статус: каркас проекта (структура папок/модулей), логика слоёв ещё не реализована.

## Структура

- `generator/` — сам преобразователь (raw text → invoice JSON). Реализация/выбор подхода — TODO.
- `evals/` — 6-слойная eval-иерархия (field-level, document-level, segment-level, production-simulation, statistics, business impact) + LLM-judges.
- `data/` — схема данных, загрузчики датасетов, генерация синтетики.
- `dashboard/` — Streamlit-дашборд + SQL-слой (Databricks).
- `config/` — явные "экспертные" допущения (severity weights, business assumptions, сегменты).
- `tests/` — тесты по одному файлу на модуль.
- `notebooks/` — история прототипирования.
- `scripts/` — CLI-запуск eval-пайплайна.
- `eval_runs/` — сохранённые результаты прогонов (gitignored).

## TODO

Методология, обоснование метрик, борьба с шумом, assumptions — будут дописаны по мере реализации.
