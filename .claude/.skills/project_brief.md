# Проект: Eval-система для invoice-генератора (под вакансию Finom — Product Data Scientist, AI Evaluation & Quality)

## Цель проекта
Мини-проект для резюме под конкретную вакансию. Не просто "invoice generator", а демонстрация eval-loop мышления: датасеты (capability + regression), иерархия метрик, LLM-judges, статистика, production-simulation dashboard, бизнес-метрики.

Ключевая цитата из JD, под которую весь проект заточен:
> "your AI agent is only as good as your eval loop"
> "translate numbers into decisions – weekly syncs, clear trade-offs, no dashboards for their own sake"

Стек, который стоит явно использовать/упомянуть: **Python, SQL, Databricks, DeepEval, Claude Code** (AI-assisted coding — их дефолтная среда разработки, стоит вести весь процесс через Claude Code).

## Базовый проект
Существующий опенсорс-репозиторий генерации инвойсов из неструктурированного текста — берём за основу (код есть, рабочий). Наша задача — НЕ дорабатывать генератор, а построить вокруг него полноценную eval-инфраструктуру.

## Таймлайн
Быстрый MVP — несколько дней.

## Иерархия метрик (зафиксировано)

### Layer 0 — Intent & Completeness Gate (собственный компонент поверх baseline, НЕ часть их кода)

Baseline (`parseInvoiceFromText`) не имеет guardrail: любой текст, даже нерелевантный, приводит к попытке extraction и возможной галлюцинации JSON. Это найденный gap, который мы закрываем своим wrapper-слоем перед вызовом их функции.

Два последовательных решения:

**Шаг 1 — Is-invoice-intent classifier (бинарный)**
- Определяет: хочет ли человек вообще создать инвойс (да/нет)
- Ground truth: метка `is_invoice_request: true/false` на каждом синтетическом примере
- Метрики: **False Positive rate** (создали инвойс из нерелевантного текста → галлюцинация, дорогая ошибка, риск отправки мусорного инвойса клиенту) и **False Negative rate** (отказали, хотя человек хотел → дешёвая ошибка, просто re-prompt/friction) считаются раздельно, не сворачиваются в один F1 — именно асимметрия FP/FN дальше напрямую формирует вход для Layer 6

**Шаг 2 — Data sufficiency check (только если Шаг 1 = "да")**
Три класса:
- **No data** — нет ключевых полей вообще → нельзя генерировать, запросить заново
- **Partial** — что-то есть, но не хватает критичного (например есть items, нет clientName) → нужно уточнение конкретно недостающего поля
- **Complete** — всё есть → можно генерировать

Метрика: multi-class classification quality (в т.ч. отдельно частота "переспросили зря" vs "пропустили нехватку данных" — тоже friction-сигнал) + отдельно точность указания, каких именно полей не хватает (это ближе к LLM-judge, чем к точной классификации).

**Как встраивается в пайплайн**
Layer 0 — фильтр на входе, ДО Layer 1. Только примеры со статусом "complete" идут в Layer 1-2 (field/document extraction accuracy). Примеры "no data"/"partial" получают отдельную ветку метрик (правильно ли распознан их статус), не проверяются на field accuracy.

**Датасет должен включать отдельный сегмент** out-of-scope/nonsense текстов (не про инвойсы вообще) — специально для теста Шага 1.

### Layer 1 — Field-level
Для каждого поля инвойса (сумма, дата, поставщик, номер, позиции, валюта):
- Exact match — строгие поля (номер, валюта)
- Numeric tolerance match — суммы/даты (например ±0.01, разные форматы дат как эквивалентные)
- LLM-as-judge semantic match — свободный текст (название поставщика, описания позиций)

Выход: per-field score → **error rate per field type**

### Layer 2 — Document-level
- Weighted field score (критичные поля — сумма/поставщик — весят больше)
- **Resolution rate** = % документов, где все критичные поля верны без вмешательства человека
- **Critical error rate** = % документов с ошибкой в критичном поле

### Layer 3 — Segment-level
Те же метрики (resolution rate, error rate) в разрезе по:
- сложности входа (чистый / шумный / edge-case)
- типу документа (email, chat-текст и т.п.)

Это реализация "mine failure patterns from real traffic" на синтетических сегментах.

### Layer 4 — Production-simulation
- **Latency** — время генерации на документ
- **CSAT / thumbs-up-down proxy** — второй LLM-judge играет роль ревьюера, ставит 👍/👎 "принял бы без правки" + confidence score. ВАЖНО: явно пометить в README как proxy, не настоящий CSAT
- Trend/drift view — метрики по батчам данных (имитация мониторинга во времени)

### Layer 5 — Statistical layer (сквозной, применяется ко всем уровням выше)
- Confidence intervals на resolution rate (bootstrap, т.к. выборка небольшая)
- Judge stability check — прогон judge несколько раз на одном кейсе, variance/agreement (kappa) — показывает понимание non-determinism
- Statistical significance при сравнении сегментов (например "чистые" vs "шумные" — реальна разница или шум)

### Layer 6 — Business Impact (derived layer, читает ТОЛЬКО выходы Layer 1-5, ничего не считает "с нуля")

| Business KPI | Формула | Вход из какого слоя |
|---|---|---|
| Hallucination / trust risk cost | `FP_rate × volume × avg_cost_per_bad_invoice_sent` | FP rate (intent gate) ← Layer 0 |
| Friction / re-prompt cost | `(FN_rate + partial_misclass_rate) × volume × avg_reprompt_cost` | FN rate + partial misclassification ← Layer 0 |
| Cost of manual review | `(1 − resolution_rate) × volume × avg_review_min × hourly_rate` | resolution_rate ← Layer 2 |
| Expected cost of critical errors | `Σ (critical_error_rate_by_field × field_severity_$) × volume` | error_rate ← Layer 1, severity — конфиг-справочник (assumption, не measured) |
| Segment risk exposure | `Σ_segment (volume_share × critical_error_rate_segment × avg_error_cost)` | error_rate by segment ← Layer 3 |
| Infra/SLA cost | `latency_p95 × compute_cost_per_sec × volume` + штраф при превышении SLA | latency ← Layer 4 |
| Churn risk proxy | `f(thumbs_down_rate)` — монотонная шкала "% users likely to abandon feature" | CSAT-proxy ← Layer 4 |
| Net value at current quality | savings_from_automation − cost_of_manual_review − expected_error_cost − infra_cost − hallucination_cost − friction_cost | агрегация всего выше |

Архитектурное требование: Layer 6 реализовать отдельным модулем (например `business_layer.py`), который принимает `metrics_dict` из нижних слоёв и возвращает `business_dict`. Полная трассируемость: любая $-цифра должна прослеживаться до конкретной eval-метрики. Severity weights — единственное место с "экспертным" вводом, явно помечено как assumption/config.

## Датасеты — что искать (в процессе поиска)
Приоритет:
1. Готовые invoice-датасеты с ground truth (SROIE, CORD, FUNSD, Kaggle invoice datasets) — дают эталонные поля, можно самой зашумить в неструктурированный текст
2. Email/переписка с деловым контекстом — Enron Email Dataset (фильтр по invoice/payment/amount due) — ближе всего к реальному "текст → инвойс" кейсу
3. Синтетические/near-invoice датасеты на HuggingFace (теги: invoice extraction, invoice NER, financial document extraction)
4. Чаты/тикеты поддержки с billing-темой — для "шумного/разговорного" сегмента
5. Многоязычные/мультивалютные инвойсы — для edge-case сегмента

Что не хватает — генерировать синтетически (LLM-генератор текста + parallel ground truth JSON), с явным разделением на категории сложности (чистые / шумные / edge-case), чтобы сразу питать Layer 3.

## Что обязательно учесть при реализации
- Каждый уровень иерархии должен быть явно подписан в коде/README, какой метрике из JD он соответствует (resolution rate, CSAT, thumbs up/down, error rate, latency, LLM-as-judge)
- Business layer (6) не должен дублировать расчёты — только агрегировать нижние слои, для трассируемости
- Proxy-метрики (CSAT, thumbs-up/down через judge) — явно обозначать как симуляцию, не выдавать за реальные пользовательские данные (честность = плюс для аналитика)
- Judge stability — обязательно показать (variance/kappa при повторных прогонах), это прямое попадание в must-have "understanding what a noisy metric is"
- Итоговый README должен содержать методологию: почему такие метрики, как боролись с noise, какие assumptions сделаны
- Дашборд — быстрый вариант (Streamlit/Plotly), Databricks Community Edition — для честного SQL-слоя
- Весь процесс разработки вести через Claude Code — это прямое попадание в их культуру ("AI-assisted coding is our default authoring environment")
