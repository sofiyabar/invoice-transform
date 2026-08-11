# Data Map

## 1. Обзор

В проекте четыре вида данных:

| Данные | Что это | Где хранится |
|---|---|---|
| Датасет | тестовые записи с заранее известным правильным ответом | `data/synthetic/eval_dataset.jsonl` |
| Предсказания | ответы системы на записи датасета | `data/synthetic/generator_predictions.jsonl` |
| Конфиг | параметры, заданные вручную, не выводимые из других данных | `config/*.yaml` |
| Результат оценки | числа, полученные при сравнении предсказаний с правильными ответами | `eval_runs/*_metrics.json` |

Результат оценки строится из Датасета и Предсказаний (плюс Конфиг — для ещё не реализованной
части, Layer 6) и отображается на дашборде. Разделы 2–5 описывают каждый вид данных подробно,
раздел 6 — как дашборд использует результат оценки.

## 2. Датасет — `data/synthetic/eval_dataset.jsonl`

600 записей. **Запись** — одна строка файла: входной текст плюс всё, что о нём заранее
известно. Ключевые поля записи:

| Поле | Тип | Значение |
|---|---|---|
| `id` | строка | идентификатор записи |
| `raw_text` | строка | входной текст |
| `is_invoice_request` | true/false | правильный ответ на вопрос "это просьба сделать инвойс?" |
| `sufficiency_label` | `none` / `partial` / `complete` | правильный ответ на вопрос "хватает ли данных для инвойса?" |
| `ground_truth` | объект или пусто | **правильный ответ** для полей инвойса: `{clientName, email, address, items: [{name, quantity, unitPrice}]}`. Пусто, если инвойс в принципе не построить (мусорный текст или нет данных) |
| `segment` | `clean` / `noisy` / `edge` | насколько сложен текст: чистый, с помехами, или нетипичный пограничный случай |
| `style` | `formal_email` / `casual_note` / `chat_message` | форма текста |

Полный список полей, включая служебные (`removed_fields`, `source_row_id` и т.п.) —
`data/synthetic/dataset_manifest.md`.

## 3. Предсказания — `data/synthetic/generator_predictions.jsonl`

600 записей, по одной на каждую запись датасета. **Предсказание** — то, что система вернула
для данной записи.

| Поле | Тип | Значение |
|---|---|---|
| `id` | строка | ссылка на запись датасета |
| `segment` | как в датасете | |
| `ok` | true/false | получилось ли получить ответ от системы |
| `prediction` | объект | та же структура, что `ground_truth` в датасете: `{clientName, email, address, items}` |
| `error` | строка, если `ok=false` | причина сбоя |

## 4. Конфиг — `config/*.yaml`

| Файл | Поля | Значение |
|---|---|---|
| `severity_weights.yaml` | `clientName`, `email`, `address`, `items` (числа, $) | во сколько долларов оценивается ошибка в каждом поле |
| `business_assumptions.yaml` | `hourly_rate_usd`, `avg_review_min`, `volume_docs_per_period`, `compute_cost_per_sec_usd`, `sla_latency_p95_seconds`, `sla_penalty_usd` | стоимость часа проверки, объём документов, штраф за SLA |
| `segments.yaml` | `segments`, `doc_types` | допустимые значения для `segment`/`style` из раздела 2 |

Оба файла с $-значениями заполнены реальными числами частично: `hourly_rate_usd`,
`avg_review_min`, `volume_docs_per_period` и все поля `severity_weights.yaml` — да; SLA/
compute-поля — ещё нет (`0.0`).

## 5. Результат оценки — `eval_runs/*_metrics.json`

Один файл на один прогон оценки. Строится сравнением Предсказаний с Датасетом (раздел 2 vs
раздел 3), плюс Конфиг для последнего блока.

```
metrics_dict
├── run_id                 когда прогон запущен
├── config                  как прогон был запущен (сколько записей, какая модель)
├── layer0
│   ├── intent_gate            насколько верно определено is_invoice_request (§5.1)
│   └── completeness_gate      насколько верно определено sufficiency_label (§5.2)
├── layer1                   насколько верно извлечены поля ground_truth (§5.3)
├── layer2                   готовность документа целиком (§5.4)
├── layer4                   производственная симуляция (§5.5)
└── layer6                   деньги — не реализовано (§5.6)
```

(`layer3`, `layer5` всегда пустые — их содержимое перенесено в `layer2`.)

### 5.1 `layer0.intent_gate`

| Поле | Значение |
|---|---|
| `aggregate.accuracy` | доля записей, где `is_invoice_request` определено верно |
| `aggregate.fp_rate` | доля не-инвойсов, ошибочно принятых за инвойс-запрос — дорогая ошибка |
| `aggregate.fn_rate` | доля инвойс-запросов, ошибочно отклонённых — дешёвая ошибка |

### 5.2 `layer0.completeness_gate`

| Поле | Значение |
|---|---|
| `aggregate_sufficiency.accuracy` | доля записей, где `sufficiency_label` определён верно |
| `aggregate_sufficiency.missed_shortage_rate` | доля случаев, где данных на самом деле не хватало, а система решила, что хватает |
| `aggregate_sufficiency.asked_unnecessarily_rate` | доля случаев, где данных хватало, а система попросила уточнить |
| `aggregate_missing_fields.{precision,recall,f1}` | точность указания, каких именно полей не хватает |

### 5.3 `layer1` — сравнение `prediction` с `ground_truth`

| Поле | Значение |
|---|---|
| `field_scores.<поле>.error_rate` | доля записей, где это поле (`clientName`, `email`, `address`, `items.*`) не совпало с `ground_truth` |
| `parse_failure_rate` | доля предсказаний, которые вообще нельзя прочитать как `{clientName, email, address, items}` |

### 5.4 `layer2` — готовность документа целиком

Критичными считаются `clientName` и `items` — ошибка в них делает документ непригодным без
проверки человеком; `email`/`address` некритичны.

| Поле | Значение |
|---|---|
| `resolution_rate` | доля документов, где `clientName` и `items` оба совпали с `ground_truth` |
| `critical_error_rate` | `1 − resolution_rate` |
| `resolution_rate_ci` | диапазон, в который с высокой вероятностью попадает истинное значение `resolution_rate` на полной генеральной совокупности |
| `by_segment`, `by_doc_type` | те же поля, посчитанные отдельно для каждого значения `segment`/`style` из раздела 2, плюс `p_value_vs_baseline` — вероятность, что разница со значением-базой случайна |

### 5.5 `layer4` — производственная симуляция

| Поле | Значение |
|---|---|
| `technical_error_rate` | доля предсказаний с `ok=false` |
| `latency.{p50,p95,mean}` | время обработки одной записи, в миллисекундах — оценка, не измерено |
| `csat_proxy.thumbs_down_rate` | доля предположительно недовольных пользователей, вычисленная из `critical_error_rate` — не опрос реальных людей |

### 5.6 `layer6` — деньги

Не реализовано. Должен использовать `severity_weights.yaml` и `business_assumptions.yaml`
(раздел 4) вместе с `layer1`/`layer2`, чтобы посчитать стоимость ошибок и экономию. Формулы —
`.claude/.skills/project_brief.md`, раздел Layer 6.

## 6. Дашборд

| Вкладка | Поле `metrics_dict` | Что показывает |
|---|---|---|
| Layer 0 | `layer0` | §5.1–5.2 |
| Layer 1 | `layer1` | §5.3 |
| Layer 2 | `layer2` | §5.4 |
| Layer 3 | — | пусто, см. Layer 2 |
| Layer 4 | `layer4` | §5.5 |
| Layer 5 | — | пусто, см. Layer 2 |
| Layer 6 | — | §5.6, не реализовано |

## 7. Где искать больше

| Документ | Что в нём |
|---|---|
| `data/synthetic/dataset_manifest.md` | Полное описание полей `eval_dataset.jsonl` |
| `data/synthetic/generation_notes.md` | Как именно собран датасет |
| `CHANGELOG.md` | История решений и изменений |
| `.claude/.skills/project_brief.md` | Зачем нужен проект, формулы для Layer 6 |
| `README.md` | Что уже реализовано, что нет |
| `CLAUDE.md` | Структура кода и модулей |
