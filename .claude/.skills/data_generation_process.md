# Процесс генерации синтетических данных для eval-датасета

## Идея
Не выдумывать инвойсы "с нуля" (это даёт нереалистичные/предвзятые данные), а брать **реальные структурированные инвойсы** как источник ground truth и генерировать вокруг них естественный неструктурированный текст — с контролируемым зашумлением.

## Пайплайн (по шагам)

**Шаг 1 — Источник реальных инвойсов**
Источник: Kaggle "Invoice NER Dataset" (`nikitpatel/invoice-ner-dataset`) — реальные тексты инвойсов (полуструктурированные, из PDF/изображений) с оригинальной JSON-разметкой полей (`INVOICE_NUMBER`, `TOTAL_AMOUNT`, `BILL_TO` и т.п.). Схема оригинальной разметки НЕ совпадает с нашей — используем только сырой текст как основу, разметку делаем свою.

**Шаг 2 — Ручная разметка на целевую схему**
Из сырого текста инвойса вручную извлекаем и записываем ground truth под нужную модели схему:
```json
{
  "clientName": "...",
  "email": "...",
  "address": "...",
  "items": [{"name": "...", "quantity": N, "unitPrice": N}]
}
```
Причина ручной разметки, а не автоматического маппинга: оригинальные поля датасета не покрывают напрямую clientName/email/address/items (это другая схема сущностей, например BILL_TO — не всегда то же самое, что clientName в понимании тестируемой модели). Ручная разметка даёт более точный и достоверный ground truth, чем эвристический маппинг.

Практически: с учётом сжатого таймлайна (несколько дней на MVP) размечаем вручную ограниченную, но осмысленную выборку (порядка 30-50 исходных инвойсов) — этого достаточно, чтобы после Шага 3-4 (удаление полей + генерация нескольких текстовых вариаций на каждый) получить датасет в несколько сотен примеров.

**Шаг 3 — Контролируемое удаление полей (для шума)**
Для каждого примера случайно (по заданному распределению) удаляем 0, 1-2 или 3+ полей/значений. Ключевое: **факт и список удалённых полей логируется как метаданные**, не теряется.
Это создаёт три сегмента естественным образом:
- 0 удалено → **clean**
- 1-2 удалено → **noisy**
- 3+ или структурная аномалия (несколько клиентов, странные форматы цены) → **edge-case**

**Шаг 4 — Генерация текста (LLM paraphrasing)**
Оставшиеся (не удалённые) факты передаются в LLM с прямым заданием — написать письмо/заметку про выполненную работу для клиента (не мета-инструкция "притворись, что ты..." — прямая задача даёт более естественный текст).

Финальный промпт (Stage C):
```
SYSTEM:
Write a short {style} describing work that was completed or products that were
delivered to a client, as if the sender now needs to bill the client for it.
Mention the client's details and what was provided, based only on the facts below.

STRICT RULES:
1. Use ONLY the facts provided below. Do not invent or add any client name, email,
   address, item, quantity, or price that is not explicitly given.
2. Include every fact that is given — do not omit anything provided.
3. Do not use JSON, bullet points, tables, or labeled fields (e.g. no "Client:" or
   "Email:"). Write flowing natural language only.
4. Preserve numbers exactly as given.
5. Do not reference invoice templates, design, or colors — only the actual
   business facts.
6. Output ONLY the message text. No preamble, no explanation, no quotes.

STYLE: {style}
  — formal_email: professional business email, includes greeting and sign-off
  — casual_note: short informal note, like a quick memo to self or colleague
  — chat_message: casual chat/messenger style, brief

FACTS:
Client name: {clientName | "[not provided]"}
Client email: {email | "[not provided]"}
Client address: {address | "[not provided]"}
Items delivered:
{for each item: "- {name}, quantity {quantity}, unit price {unitPrice}"}

Write the message now.
```

Поля, помеченные как удалённые (Шаг 3) или **naturally_missing** (изначально отсутствовавшие в исходном инвойсе — Шаг 2), просто не передаются в блок FACTS — это автоматически создаёт "недостающие данные" в тексте без отдельной логики.

Это даёт `raw_text`.

**Шаг 5 — Отдельная генерация для Layer 0 (intent gate)**
Не парафраз фактов — прямая генерация категории, отдельным более простым промптом:

Out-of-scope (`is_invoice_request: false`):
```
Generate a short, natural message that has NOTHING to do with creating an invoice
(e.g. a question, complaint, or unrelated request). Vary topic and tone.
```

No-data / vague (`sufficiency_label: none`):
```
Generate a short message where someone vaguely asks to create an invoice for a
client, but provides NO specific details (no name, no items, no prices).
```

**Шаг 6 — Валидация и метаданные**
Каждый итоговый пример хранится с полным контекстом генерации:
```json
{
  "id": "...",
  "raw_text": "...",
  "ground_truth": {...},
  "removed_fields": ["email"],
  "naturally_missing_fields": ["address"],
  "segment": "noisy",
  "is_invoice_request": true,
  "sufficiency_label": "partial",
  "source_invoice_id": "...",
  "generation_model": "...",
  "generation_prompt_version": "v1"
}
```
Это даёт полную трассируемость и воспроизводимость — можно перегенерировать/расширить датасет, не теряя историю решений.

## Почему это важно (для README/резюме)
- Ground truth — из реальных данных, не из воображения → меньше bias, больше доверия к метрикам
- Шум контролируемый и **размеченный** → можно отличить "модель ошиблась" от "данных физически не было" — без этого error rate был бы некорректным
- Сегментация (clean/noisy/edge-case) получается автоматически из процесса генерации, а не вручную после факта
- Полная логируемость параметров генерации — сам процесс генерации данных становится частью eval-методологии, а не черным ящиком
