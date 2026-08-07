# Шаги для Claude Code: генерация eval-датасета

Контекст: см. `project_brief.md` (иерархия метрик) и `data_generation_process.md` (дизайн пайплайна и промпты). Файл-источник: `converted_invoice_dataset.xlsx` (67 строк, колонки `Input`, `Final_Output` — `Final_Output` не используем, схема не совпадает с нашей).

## Шаг 1 — Извлечь сущности из Input (полуавтоматически)
- Прочитать `converted_invoice_dataset.xlsx`, колонка `Input` (сырой OCR-текст шаблонов инвойсов)
- Для каждой из 67 строк с помощью LLM извлечь в JSON только то, что реально присутствует в тексте:
  ```json
  {"clientName": "...|null", "email": "...|null", "address": "...|null",
   "items": [{"name": "...", "quantity": N, "unitPrice": N}]}
  ```
- Поля, которых нет в исходном тексте — `null`, и сразу помечаются как `naturally_missing`, не как удалённые
- Сохранить как `entity_pool.jsonl` (67 записей), каждая с `source_row_id`
- Важно: не использовать `Final_Output` из файла — его схема (`BILL_TO`, `INVOICE_NUMBER` и т.п.) не совпадает с целевой и нестабильна между строками
- Сделать быстрый выборочный ручной спот-чек (5-10 записей) на точность извлечения, прежде чем идти дальше

## Шаг 2 — Контролируемое зашумление (deletion tiers)
- Для каждой записи из `entity_pool.jsonl` сгенерировать 3 варианта:
  - `tier=clean` — без удалений
  - `tier=noisy` — случайно удалить 1-2 присутствующих поля (из тех, что не null)
  - `tier=edge` — удалить 3+ полей, либо удалить целиком одну из позиций items (если items больше одной)
- Удаление — только полей, которые реально были не-null (нельзя "удалить" то, что уже naturally_missing)
- Логировать `removed_fields` отдельно от `naturally_missing_fields`
- Результат: `entity_pool_with_tiers.jsonl` (~67 × 3 ≈ 200 записей)

## Шаг 3 — Генерация текста (LLM paraphrasing)
- Для каждой записи из Шага 2 сгенерировать 2 текстовых варианта с разными `style` (случайно/по очереди из: `formal_email`, `casual_note`, `chat_message`)
- Использовать точный промпт из `data_generation_process.md`, раздел "Шаг 4 — Генерация текста" (Stage C prompt)
- В FACTS-блок промпта передавать только поля, которые НЕ входят ни в `removed_fields`, ни в `naturally_missing_fields`
- Результат: `extraction_dataset.jsonl` (~400 записей), каждая запись:
  ```json
  {"id": "...", "raw_text": "...", "ground_truth": {...},
   "removed_fields": [...], "naturally_missing_fields": [...],
   "segment": "clean|noisy|edge", "style": "...",
   "source_row_id": "...", "generation_model": "...",
   "generation_prompt_version": "v1"}
  ```

## Шаг 4 — Генерация Layer 0 данных (out-of-scope и no-data)
- Сгенерировать ~50-70 out-of-scope примеров промптом из `data_generation_process.md` (Stage D, out-of-scope) → `is_invoice_request: false`
- Сгенерировать ~50-70 no-data/vague примеров тем же разделом (Stage D, no-data) → `is_invoice_request: true`, `sufficiency_label: none`
- Сохранить как `layer0_dataset.jsonl`, с той же базовой структурой полей, где применимо (`ground_truth: null` для этих случаев)

## Шаг 5 — Валидация
- Автоматическая проверка: каждый `raw_text` из `extraction_dataset.jsonl` не содержит полей из `removed_fields`/`naturally_missing_fields` (грубая эвристика — просто проверить отсутствие точных строковых значений, где это применимо, например для email/имени)
- Ручной спот-чек на ~15-20 случайных записях: сверить `raw_text` vs `ground_truth` — не потеряны ли факты, не добавлено ли лишнего
- Проверить распределение сегментов (clean/noisy/edge) и стилей — не должно быть сильного перекоса

## Шаг 6 — Финальная сборка
- Объединить `extraction_dataset.jsonl` + `layer0_dataset.jsonl` в единый `eval_dataset.jsonl`
- Добавить `dataset_manifest.md` с итоговой статистикой: общее количество записей, разбивка по segment/style/is_invoice_request/sufficiency_label, дата генерации, использованная модель
- Это финальный артефакт, на котором дальше строится eval-пайплайн (Layer 0-6 из `project_brief.md`)

## Что не делать на этом этапе
- Не трогать сам код `parseInvoiceFromText` (тестируемая система) — только данные
- Не использовать `Final_Output` из исходного xlsx как ground truth
- Не пропускать логирование `removed_fields`/`naturally_missing_fields` — без него error rate в eval будет некорректным
