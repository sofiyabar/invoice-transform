# Changelog

Ручной журнал изменений — на автоматизацию (git log) не полагаемся, пишем сюда
руками при значимых изменениях. Два независимых трека:

- **Данные для оценки** — датасет(ы), ground truth, разметка сегментов, всё в `data/`.
- **Алгоритм** — генератор под оценкой (`generator/`) и сама eval-логика (`evals/`, `config/`).

Формат записи: `### YYYY-MM-DD`, дальше маркированный список, что изменилось и почему
(если причина не очевидна из самого изменения).

## Итерации улучшений (до / рекомендации / после)

Отдельно от хронологического лога ниже — срез по конкретному компоненту: baseline-метрики
("до"), что предлагается поправить ("рекомендации"), и результат после правки ("после").
Одна подсекция на компонент, обновляется на месте (не append-only), а не переписывается
заново при каждой итерации.

### Layer 0, Step 1 — is-invoice-intent классификатор (`generator/intent_gate.py`)

**До** (2026-08-09, полный прогон на всех 600 строках, `eval_runs/20260809T224815Z_layer0_intent_gate.json`)
- accuracy 98.2%, **FP rate 0.0%** (0/144), FN rate 2.4% (11/456)
- Корневая причина части FN (минимум `nodata_019`, `nodata_024`, вероятно
  `row_006_noisy_a`): промпт неявно требует "describes completed work...
  implies an invoice should be generated" — подмешивает критерий
  **достаточности данных** (это работа Step 2) в решение Step 1. Пример:
  *"I need to send an invoice out but haven't sorted the particulars yet."*
  — `is_invoice_request: true` по ground truth, классификатор ответил `false`.
- Остальные ~8/11 FN — на noisy/edge сегментах, похоже на естественную
  трудность формулировок, не системная причина.

**Рекомендации** (ещё не применены)
1. Переформулировать промпт: убрать "describes completed work" как условие.
   Step 1 должен отвечать только на "хочет ли человек инвойс", не на
   "хватает ли данных, чтобы его построить" — например, "Answer yes if the
   sender is asking for, or clearly wants, an invoice created for them — even
   if they haven't given any details yet".
2. После правки обязательно перепрогнать **весь** датасет, не только позитивный
   класс — ослабление критерия рискует поднять FP rate выше 0%, это надо
   явно проверить, а не предполагать.
3. Отдельно посчитать метрики на подмножестве строк с `sufficiency_label: "none"`
   (они специально нацелены на эту грань) — до/после, чтобы видеть эффект точечно,
   а не только в общей сумме по 600 строкам.

**После**
*(не заполнено — обновить после того, как промпт поправлен и датасет прогнан заново)*

## Данные для оценки

### 2026-08-03
- Сгенерирован синтетический eval-датасет: 600 записей с `ground_truth` в
  `data/synthetic/eval_dataset.jsonl` (+ вспомогательные `entity_pool*.jsonl`,
  `layer0_dataset.jsonl`, `robustness_dataset.jsonl`). Заменяет ранее рассматривавшийся
  путь через SROIE (`priyank-m/SROIE_2019_text_recognition` — брошен из-за отсутствия
  поля `words`, датасет с этим багом остался в `notebooks/` как история, не как рабочий путь).

### 2026-08-10
- **Переразметка `sufficiency_label` под Layer 0 Step 2**: при обсуждении, какие
  поля считать критичными для "хватает ли данных" (`no data`/`partial`/`complete`),
  решили — `clientName`, `items`, `address` критичны, **`email` нет**. Датасет был
  размечен по старому правилу, где отсутствие только `email` тоже давало `partial`.
  Нашли 64 такие строки (`removed_fields`/`naturally_missing_fields` == `{email}`
  ровно, ничего больше не пропущено) — переписали им `sufficiency_label`
  `partial` → `complete`. Остальные комбинации (только `address` — 12 строк,
  `email`+`address` вместе — 96 строк) **оставлены `partial`** — `address`
  по-прежнему критичен, тронули только чистый "не хватает email".
  - `partial`: 304 → 240, `complete`: 28 → 92 (остальные метки не тронуты).
  - Бэкап до правки: `data/synthetic/eval_dataset.jsonl.bak_20260810_before_email_relabel`.
  - Правило критичности (`clientName`+`items`+`address` критичны, `email` нет)
    ещё нужно перенести в саму логику Step 2, когда её будем писать — сейчас
    поправлен только датасет, не код.
- **Полный пересчёт `sufficiency_label` с нуля** (тот точечный email-патч выше
  оказался недостаточным — при проверке выяснилось, что старая разметка вообще
  не следует единому правилу: например 54 строки с меткой `none` не имели ни
  одного поля в `removed_fields`/`naturally_missing_fields`, а часть строк с
  `partial` теряли вообще все критичные поля разом). Пересчитали
  `sufficiency_label` для всех 456 строк (`is_invoice_request: true`) по одному
  чёткому правилу на основе критичных полей (`clientName`, `items`, `address`;
  `email` не в счёт):
  - **`none`** — пропали **все** критичные поля
  - **`partial`** — не хватает **части** критичных полей (не всех)
  - **`complete`** — все критичные поля на месте
  - Итог: `complete` 92→**156**, `partial` 240→**230**, `none` 124→**70**
    (72 строки переразмечены сверх точечного email-патча).
  - Бэкап до пересчёта: `data/synthetic/eval_dataset.jsonl.bak_20260810_before_full_sufficiency_recompute`.

## Алгоритм

### 2026-08-06
- `generator/base_generator.py` реализован: вызывает Gemini (`gemini-2.5-flash` через
  `google-genai`), промпт скопирован дословно из `aiController.js` (Finvoice-AI, MIT).
  Парсинг ответа намеренно хрупкий (regex-стрип ```` ```json ````, `json.loads()` без
  `try/except`) — чтобы измерять реальный parse failure rate, а не маскировать его.
- Добавлен `load_dotenv()` в `base_generator.py` — ключ `GEMINI_API_KEY` подхватывается
  из `.env` автоматически, руками в окружение экспортировать не нужно.
- Smoke-test (`scripts/smoke_test_generator.py`, 2 примера из eval-датасета) подтвердил:
  API-ключ и генератор реально работают, `json.loads()` не падал. Но обнаружены два
  системных расхождения формата, которые `evals/layer1_field.py` обязан нормализовать
  при сравнении с ground truth, иначе будет ложный error rate:
  - Gemini возвращает отсутствующее поле как `""`, ground truth хранит `null`.
  - Числовые поля (`quantity`, `unitPrice`) Gemini отдаёт как `int`, ground truth — `float`.
- `evals/layer1_field.py`, `evals/layer2_document.py`, `evals/judges/field_judge.py` —
  всё ещё заглушки (`NotImplementedError`), реализация не начата.

### 2026-08-09
- Написан `scripts/generator_probe.py` — прогон генератора на стратифицированной
  выборке (`clean`/`noisy`/`edge` + non-invoice/OOS строки) с целью замерить реальный
  parse failure rate и долю format-only расхождений с ground truth до реализации
  `layer1_field.py`. По ходу аудита датасета выяснилось, что `eval_dataset.jsonl`
  смешивает invoice-строки (`ground_truth` заполнен) и non-invoice/OOS-строки
  (`ground_truth: null`, `is_invoice_request: false`) — у генератора сейчас нет
  отказного пути для вторых. Также реальные значения `segment` — `"edge"`, а не
  `"edge_case"` как в `Segment` enum в `data/schema.py` (расхождение зафиксировано,
  не исправлено — вне скоупа).
- **Важное ограничение, найденное экспериментально**: free-tier `GEMINI_API_KEY`
  даёт всего **~20 запросов в день** (не 1000, как предполагалось изначально). Первый
  прогон `generator_probe.py` (без троттлинга, 30 запросов подряд) и второй
  (с троттлингом 13с + ретраями на 429) в сумме сожгли 90+ запросов и полностью
  исчерпали дневную квоту — прогон остановлен вручную, статистика по parse failure
  rate не собрана. Дневной лимит — это узкое место, которое надо закладывать в
  дизайн любого дальнейшего массового прогона генератора (в т.ч. будущего Layer 1
  на всех 600 строках датасета): либо растягивать по дням, либо переходить на
  платный tier.
- **Квота снята**: включён billing на Google-проекте (пополнено $10) → лимит
  вырос до 1000 req/min. Старый ключ (`gemini-2.5-flash`) восстановлен как
  основной `GEMINI_API_KEY`. Побочная находка по пути: на новом (тестовом,
  free-tier без billing) ключе `gemini-2.5-flash`/`gemini-2.5-flash-lite` вообще
  недоступны новым пользователям (404 "no longer available to new users"), а
  `gemini-2.0-flash` имел `limit: 0`; рабочим был только алиас
  `gemini-flash-latest` — но и по нему, и по прямым 404-моделям, похоже,
  списывался общий скудный дневной лимит, а не отдельные по 20 на каждую модель.
  С billing вопрос снят, дальше не актуально.
- Троттлинг в `scripts/generator_probe.py` ослаблен (`MIN_CALL_INTERVAL` 13с → 0.5с)
  — на платном тарифе 13-секундный free-tier троттлинг не нужен.
- **Полный чистый прогон `generator_probe.py`** (24 invoice + 6 OOS строк, seed=42):
  **parse failure rate = 0%** на всех 24 invoice-строках. Найдены расхождения,
  которые важны для `evals/layer1_field.py` / `layer2_document.py`:
  - Новое format-расхождение (доп. к `"" vs null`, `int vs float`): **регистр**
    (`'Logo Design'` vs `'logo design'`) — нужна case-insensitive нормализация.
  - **Реальная (не форматная) деградация `items.length` по сегментам**: clean
    8/8 match, noisy 3/8, edge 0/8 — на noisy/edge генератор систематически
    теряет позиции списка (не халлюцинирует лишние, именно недосчитывает).
  - **`clientName` иногда пустой на noisy-сегменте** (не format-diff, реальный miss
    экстракции), и отдельно замечена утечка boilerplate в это поле (`"Bill Green
    Gardens"` вместо `"Green Gardens"` — зацепило "Bill to:").
  - OOS/non-invoice строки: генератор не халлюцинирует фейковый инвойс, возвращает
    пустые/null поля — но непоследовательно (то `""`, то `null` для одного и того
    же "нет данных").
  - Сырые результаты: `eval_runs/20260809T185931Z_generator_probe.json`.
- **Массовая генерация на весь датасет**: `scripts/generate_all.py` (новый) —
  прогоняет `parse_invoice_from_text` по всем 600 строкам `eval_dataset.jsonl`
  (10 параллельных воркеров, без scoring — сравнение с ground truth сознательно
  оставлено другой ветке). Результат: **596/600 успешно** (`parse failure rate
  0.67%`), 4 падения — все `JSONDecodeError` в одном и том же месте (`line 11
  column 5`), то есть один системный паттерн, а не случайный шум. Результаты:
  `data/synthetic/generator_predictions.jsonl` (не таймстемпленный — стабильный
  путь, чтобы легко находился из другой ветки; `data/synthetic/` в `.gitignore`,
  так что между ветками не потеряется, но и не расшарится через git).

### 2026-08-10
- **Layer 0, Step 1 реализован**: is-invoice-intent классификатор (бинарный:
  хочет ли автор текста вообще создать инвойс). Обнаружено, что кодовая база
  (`evals/layer1_field.py`, `evals/judges/field_judge.py`, `data/loaders.py`,
  `evals/runner.py`) уже полностью реализована в другой ветке — Layer 0
  спроектирован по образцу той же архитектуры:
  - `data/schema.py`: новая модель `IntentGateRecord` (не трогали
    `InvoiceRecord` — там `ground_truth` обязателен, а Layer 0 работает на
    всех 600 строках, включая non-invoice).
  - `data/loaders.py`: `load_intent_gate_dataset()` — грузит все 600 строк
    (в отличие от `load_synthetic_extraction()`, который фильтрует по
    `ground_truth is not None`).
  - `evals/judges/intent_judge.py` (новый): прямой вызов Anthropic (не
    DeepEval `GEval` — тому нужны expected/actual пара текстов для сравнения,
    а тут один вход и бинарное решение). Tool-use для structured bool-вывода,
    `claude-haiku-4-5` по умолчанию (как у `field_judge.py`). Клиент
    инициализируется лениво — `ANTHROPIC_API_KEY` пока пустой в `.env`, импорт
    модуля не должен из-за этого падать.
  - `evals/layer0_intent_gate.py` (новый): `classify_intent()` +
    `score_intent()` + `aggregate_intent_scores()` — зеркалит двухшаговый API
    `layer1_field.py`. **FP rate и FN rate считаются раздельно, не сворачиваются
    в F1** — по брифу у них разная цена (FP = хаpaллюцинированный инвойс
    клиенту, дорого; FN = просто re-prompt, дёшево), и Layer 6 их использует
    порознь.
  - `tests/test_layer0_intent_gate.py`: 8 тестов, judge замокан — вся логика
    (TP/TN/FP/FN классификация, арифметика rates, edge case с
    single-class ground truth) проверяется без реального API-ключа.
  - **Не сделано (сознательно)**: Step 2 (data sufficiency: no data/partial/
    complete) — следующая задача; wiring в `evals/runner.py`
    (`"layer0": None` пока не заменено); реальный прогон на датасете —
    `ANTHROPIC_API_KEY` пустой, нужен ключ для смоук-теста.
- **Пересмотр архитектуры Layer 0** (по вопросу пользователя "почему это
  judge?"): исходная раскладка была неверной. `field_judge.py` — классический
  LLM-as-judge: не производит результат, а **оценивает** уже готовый (сравнивает
  предсказание с ground truth). Intent-классификатор — наоборот: он **сам
  производит** решение из сырого текста, а сравнение с ground truth — уже
  отдельный шаг. Это ближе по роли ко второму генератору (`generator/`), а не
  к judge. Переложено:
  - `evals/judges/intent_judge.py` удалён.
  - `generator/intent_gate.py` (новый) — сама классификация
    `is_invoice_request(text) -> bool`. Раз это `generator/`, по правилу
    provider-сплита из `CLAUDE.md` — **Gemini**, не Anthropic (снимает
    необходимость в `ANTHROPIC_API_KEY` для этой конкретной части).
  - `evals/layer0_intent_gate.py` — теперь чистая сверка (`score_intent`,
    `aggregate_intent_scores`), ни одного LLM-вызова внутри, зеркалит
    `layer1_field.py` (там `score_fields`/`aggregate_scores` тоже без вызова
    генератора — сам вызов дергает `runner.py`).
  - **Реальный смоук-тест на 10 примерах** (5 positive + 5 negative,
    seed=42): **10/10 верно**, включая adversarial-кейс
    `robust_wrongfn_003` (упоминает "invoice", но не просит его создать) —
    промпт с явным разделением "упоминает" vs "просит создать" сработал.
- **Полный прогон Layer 0 Step 1 на всех 600 строках** (`scripts/run_layer0_full.py`,
  новый, зеркалит `generate_all.py`): 0 сбоёв классификации.
  **accuracy 98.2%, FP rate 0.0% (0/144), FN rate 2.4% (11/456)**. FP rate = 0
  — классификатор ни разу не сказал "да" на нерелевантный текст (самая дорогая
  ошибка по брифу) — все 11 ошибок на дешёвой стороне (FN).
  **Найдена системная причина части FN**: 2-3 из 11 (`nodata_019`, `nodata_024`,
  вероятно `row_006_noisy_a`) — это строки с `sufficiency_label: "none"`, где
  человек явно хочет инвойс (`is_invoice_request: true`), но не дал никаких
  данных ("I need to send an invoice out but haven't sorted the particulars
  yet"). Промпт в `generator/intent_gate.py` неявно требует "describes
  completed work... implies an invoice" — то есть подмешивает критерий
  достаточности данных (это работа Step 2) в решение Step 1. Не исправлено —
  надо пересмотреть формулировку промпта, когда будем делать Step 2, чтобы
  разграничить "хочет ли вообще" от "хватает ли данных".
  Результаты: `eval_runs/20260809T224815Z_layer0_intent_gate.json`.
- **Промпт `generator/intent_gate.py` переписан** по находке выше: убрано
  неявное требование "describes completed work" — теперь явно сказано
  игнорировать достаточность данных ("Only judge intent here"), с примером
  `nodata_019`-подобного текста прямо в промпте как позитивного кейса.
  Повторный прогон на датасете **не делался** (по просьбе пользователя) —
  эффект правки пока не измерен, см. "Итерации улучшений" в начале файла
  (раздел "После" всё ещё не заполнен).
- **Layer 0, Step 2 реализован** (data sufficiency: `none`/`partial`/`complete`),
  по тому же паттерну, что Step 1 — production-решение отдельно от scoring:
  - `data/schema.py`: `CRITICAL_FIELDS = ("clientName", "items", "address")`
    (`email` не критичен — см. переразметку `sufficiency_label` выше) и новая
    модель `SufficiencyGateRecord`.
  - `generator/completeness_gate.py` (новый): `check_sufficiency(fields)` +
    `missing_critical_fields(fields)` — **без единого LLM-вызова**, чистая
    функция над уже извлечёнными `InvoiceFields` (переиспользует ту же
    экстракцию, что и Layer 1, не второй независимый прогон по сырому тексту
    — решение из обсуждения выше: клиенту всё равно, из-за чего не хватает
    данных, из-за текста или из-за нашего экстрактора).
  - `data/loaders.py`: `load_sufficiency_gate_dataset()` — только
    `is_invoice_request: true` строки, ground truth (`sufficiency_label` +
    `missing_critical_fields`) считается из `removed_fields`/
    `naturally_missing_fields` тем же правилом, что и сам классификатор.
  - `evals/layer0_completeness_gate.py` (новый): `score_sufficiency` +
    `aggregate_sufficiency_scores` (accuracy + `missed_shortage_rate` —
    предсказали "полнее", чем на самом деле, опасное направление — vs
    `asked_unnecessarily_rate` — предсказали "менее полно", просто трение,
    раздельно, не в одну метрику) и `score_missing_fields` +
    `aggregate_missing_fields_scores` (precision/recall по тому, какие именно
    поля правильно помечены отсутствующими — не LLM-judge задача, как в
    брифе в общем случае, потому что и ground truth, и предсказание считаются
    одним и тем же детерминированным правилом).
  - `tests/test_completeness_gate.py` + `tests/test_layer0_completeness_gate.py`:
    16 новых тестов, все проходят без единого API-вызова — `completeness_gate.py`
    первый компонент в проекте, который вообще не требует ключа для тестов
    (детерминированная логика, не LLM).
  - **Не сделано (сознательно, как и для Step 1)**: wiring в `evals/runner.py`.
- **Полный прогон Layer 0 Step 2 на всех 456 строках** (`scripts/run_layer0_step2_full.py`,
  новый) — переиспользует уже собранные предсказания из
  `data/synthetic/generator_predictions.jsonl` (без новых LLM-вызовов, как и
  задумано). 452/456 оценено (4 пропущены — те же 4 строки с `JSONDecodeError`
  из вчерашней массовой генерации).
  - **Найден и исправлен баг** в собственном пересчёте `sufficiency_label`
    (см. выше): у 54 строк семейства `nodata_XXX` `ground_truth: null` —
    целевого инвойса для них никогда не было (текст в духе "can you whip up
    an invoice for me sometime today?" — вообще без данных). Правило
    пересчёта читало их пустые `removed_fields`/`naturally_missing_fields`
    как "ничего не потеряно" и присваивало `complete`, хотя в оригинальной
    разметке честно стояло `none`. Первый прогон Step 2 показал это как
    54 fake-ошибки `complete → none` (не мягкий соседний промах, а провал на
    два уровня сразу — сам масштаб и подсказал, что дело не в генераторе).
    Исправлено: `data/loaders.py::load_sufficiency_gate_dataset()` — для строк
    с `ground_truth: null` `missing_critical_fields` теперь всегда равен
    полному `CRITICAL_FIELDS`, не читается из `removed_fields`. Данные в
    `eval_dataset.jsonl` тоже возвращены к `none` для этих 54 строк.
    `sufficiency_label`: `complete` 156→**102**, `none` 70→**124** (после
    обоих пересчётов, `partial` не менялся — 230).
  - **Итоговые метрики после исправления**: accuracy **97.6%**,
    missed_shortage_rate **2.4%** (11/452 — не изменилось багом, это реальные
    ошибки), asked_unnecessarily_rate **0.0%** (все 54 ложных ушли вместе с
    багом), missing-fields precision/recall/F1 **1.0 / 0.98 / 0.99**.
  - Оставшиеся 11 `missed_shortage` (6× `none→partial`, 5× `partial→complete`)
    — генератор посчитал текст более полным, чем он есть на самом деле; не
    расследовано подробно, но это опасное направление ошибки (риск собрать
    инвойс без реально нужных данных) — кандидат на отдельный разбор.
  - Результаты: `eval_runs/20260809T232130Z_layer0_completeness_gate.json`.
  - **Правка фильтра**: строки для Step 2 теперь отбираются по решению
    МОДЕЛИ на Step 1 (`prediction`, из `run_layer0_full.py`), а не по ground
    truth `is_invoice_request` — в проде Step 2 видит только то, что реально
    пропустил Step 1. n: 452→**441** (11 исключены — FN-кейсы, где модель
    сказала "не инвойс"). accuracy 97.7%, missed_shortage 10/441.
    `eval_runs/20260810T002016Z_layer0_completeness_gate.json`.
  - **Разобрала все 11 `missed_shortage` до сырого текста и предсказаний —
    это поведение генератора (`base_generator.py`/промпт), не баг Step 2.**
    Ни одного false positive (генератор ни разу не сказал "не хватает", когда
    на самом деле хватало) — только false negative, два чётких паттерна:
    - **Placeholder-item вместо пустого списка** (6/11, все — `items`):
      когда в тексте нет конкретных позиций, генератор не возвращает `[]`, а
      выдумывает один фиктивный item с `quantity: 0, unitPrice: 0`. Пример
      `row_000_edge_a` — текст *"finished up that catering job"* (items
      удалены из ground truth), генератор вернул
      `[{"name": "Catering Job", "quantity": 0, "unitPrice": 0}]`. Это
      надувает `missing_critical_fields()` — список непустой, значит "есть".
    - **`clientName` выведен из домена email** (5/11): когда явного имени
      клиента нет, но есть email, генератор подставляет правдоподобное имя
      из домена вместо `null`. Пример `row_014_noisy_a` — email
      `contact@abccorp.com`, имени в тексте нет → генератор вернул
      `clientName: "ABCCorp"` (ground truth: `null`/removed).
    - Оба паттерна об одном: генератор **не любит возвращать пустоту**,
      предпочитает правдоподобную догадку явному "не знаю" — системное
      поведение, не случайный шум.
    - **Решение**: не чинить сейчас (ни в `completeness_gate.py`, ни в
      промпте) — задокументировать как есть. Это находка про качество
      генератора (relevant для Layer 1), а не про логику Step 2 — трогать
      Step 2 эвристикой под конкретно эти 11 примеров означало бы латать
      симптом, а не причину.
- **Собран end-to-end пайплайн** (`generator/pipeline.py`, новый) —
  `intent_gate` → `base_generator` → `completeness_gate` впервые вызываются
  друг за другом по-настоящему, как в реальном продукте, а не по отдельности
  в разных probe-скриптах:
  1. `is_invoice_request()` — не инвойс? останавливаемся, дальше `None`.
  2. `parse_invoice_from_text()` — извлечь поля.
  3. `check_sufficiency()` — хватает ли данных.
  - Попутно перенесла `_coerce_prediction_raw` из `evals/runner.py` в
    `generator/base_generator.py` как публичную `normalize_prediction()` —
    это часть контракта генератора (причёсывает сырой JSON под
    `InvoiceFields`), нужна и продакшен-пайплайну, и `evals/`, не только
    scoring'у. `evals/runner.py` и `scripts/run_layer0_step2_full.py`
    обновлены на импорт оттуда, дублирующий код убран.
  - `tests/test_pipeline.py`: 4 теста, все стадии замоканы.
  - **Живой прогон на 5 примерах** (3 invoice + 2 non-invoice): все
    отработали корректно — non-invoice сразу останавливались на Шаге 1,
    invoice проходили всю цепочку до `sufficiency`.
  - **Не сделано**: `evals/runner.py` пока не переключён на этот пайплайн —
    его `run()` по-прежнему дёргает только `parse_invoice_from_text()`
    напрямую и вообще не проходит через Layer 0 (`metrics_dict["layer0"]`
    всё ещё `None`). Это следующий шаг, если понадобится единый прогон всех
    слоёв разом.
- **`data/synthetic/dataset_manifest.md` обновлён/дополнен** (данные, не алгоритм,
  но фиксирую здесь раз меняла в тот же заход): актуальные (пересчитанные)
  цифры `sufficiency_label`, полный field reference по всем ключам
  `eval_dataset.jsonl`, и явная таблица "какие записи реальные, а какие
  мусорные" — `row_*` (402) реальные invoice-данные; `nodata_*` (54)
  легитимный запрос без данных; `oos_*` (60) не по теме; `robust_*` (84) —
  собственно мусор/malformed input (`gibberish`/`markup_or_code`/`spam`/
  `wrong_function`). Плюс раздел про сгенерированные артефакты
  (`generator_predictions.jsonl`, `eval_runs/*.json`) — где что лежит.

### 2026-08-12
- **Слои переименованы из номеров в то, что они делают** (модули, тесты,
  скрипты — `evals/`, `tests/`, `scripts/`), таблица соответствия ушла в
  `CLAUDE.md`:
  - `layer0_intent_gate.py` → `intake_intent_gate.py`
  - `layer0_completeness_gate.py` → `intake_completeness_gate.py`
  - `layer1_field.py` → `field_accuracy.py`
  - `layer2_document.py` → `document_accuracy.py`
  - `layer4_production_sim.py` → `production_simulation.py`
  - `business_layer.py` → `business_impact.py`
  - `run_layer0_full.py` → `run_intake_intent_full.py`,
    `run_layer0_step2_full.py` → `run_intake_completeness_full.py`
  - Причина: номера слоёв из брифа перестали что-либо объяснять сами по
    себе (Layer 3 уже слит в Layer 2, Layer 5 удалён — см. ниже), имя по
    смыслу читается без переключения на таблицу брифа.
- **Layer 3 (сегменты) слит в Document Accuracy**: `evals/layer3_segment.py`
  удалён, разбивка по сегментам/типам документа теперь —
  `evals/document_accuracy.py::by_group()`. Не новая логика, перенос уже
  случившегося решения (см. `CLAUDE.md`, раздел "Known open decisions") в
  код и историю изменений.
- **Layer 5 (статистика) удалён целиком**: `evals/layer5_statistics.py`,
  `tests/test_layer5_statistics.py`, `scripts/run_stability_check.py` —
  удалены, не заменены. Был реализован (bootstrap CI на `resolution_rate`,
  проверка значимости сегментов относительно baseline), но не отвечал на
  реальный вопрос проекта: 97%/76% шумных/edge-записей и так отсекаются
  Intake-гейтом до полной экстракции, а стохастического judge, чью
  стабильность стоило бы проверять, в проекте нет. `metrics_dict` больше не
  содержит ключа под этот слой вообще (не `null` — ключа нет).
- **Production Simulation дописан** (`evals/production_simulation.py`,
  из explicitly-labeled стабов):
  - `latency_stats(latencies_ms)` — рабочая реализация (p50/p95/mean) на
    случай, когда прогон начнёт писать реальное время на вызов; пока нигде
    не вызывается — ни в одном прогоне нет таймингов
    (`generator_predictions.jsonl` без поля времени).
  - `latency_estimate()` — явно помеченная оценка-заглушка
    (`LATENCY_ESTIMATE_MS`, типичное время ответа Gemini 2.5 Flash на
    короткий extraction-промпт), возвращает `is_estimate: True`.
  - `csat_proxy_stub(critical_error_rate)` — прокси thumbs-down rate,
    экстраполированный из `critical_error_rate` Document Accuracy +
    `CSAT_PROXY_PESSIMISM_DELTA` (0.05, предположение, что независимый
    ревьюер ловит чуть больше, чем чисто критичные поля). Помечен
    `is_stub: True` — не вызов `reviewer_judge.py` (тот всё ещё не
    реализован, нужен `ANTHROPIC_API_KEY`).
  - `batch_trend()` — сознательно оставлен `NotImplementedError`: был
    только один полный прогон датасета, тренд по одному прогону — это шум,
    а не тренд; возвращаться к этому, когда появится второй реальный прогон
    (например, после правки промпта) для сравнения.
- **Business Impact дописан** (`evals/business_impact.py`,
  `compute_business_impact()`): реализована вся P&L-формула из
  интерактивного дашборда Unit Economics —
  `Net AI Profit = Gross LTV Value - AI Run Cost - Manual Review OPEX - Quality Risk Cost`.
  Каждая денежная величина возвращается вместе с формулой и источником
  каждого входа (`metrics_dict`-путь, `config`-ключ или "sidebar" — живой
  override того же конфиг-ключа), чтобы ничего не было хардкодным числом
  без trace — см. `tests/test_business_impact.py`. Модуль по-прежнему не
  считает ни одной eval-метрики сам, только читает уже посчитанное из
  `metrics_dict` + `config/*.yaml` (граница модулей из `CLAUDE.md`
  соблюдена). Не реализовано (нет собранных бизнес-инпутов):
  `infra_sla_cost`, `churn_risk_proxy`, `segment_risk_exposure` — возвращаются
  с `value_usd: None` и явной причиной.
- **`dashboard/app.py` расширен** (+365 строк) под отрисовку доработанных
  секций Production Simulation и Business Impact (интерактивные what-if
  инпуты в сайдбаре пересчитывают P&L живьём через ту же
  `compute_business_impact()`, что и обычный прогон).
- **`ABOUT.md` добавлен** — человекочитаемое резюме проекта (цель, шаги,
  что показывает дашборд) для читателя со стороны, не из кодовой базы.
- **Документация синхронизирована** с переименованием и новым состоянием:
  `CLAUDE.md`, `README.md`, `DATA_MAP.md`, `config/*.yaml` (комментарии),
  `.claude/.skills/project_brief.md` (одна строка — аннотация про то, что
  брифовская нумерация слоёв больше не совпадает с кодом).
  - Коммит: `6275275`.
