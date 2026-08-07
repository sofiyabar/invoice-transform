# Changelog

Ручной журнал изменений — на автоматизацию (git log) не полагаемся, пишем сюда
руками при значимых изменениях. Два независимых трека:

- **Данные для оценки** — датасет(ы), ground truth, разметка сегментов, всё в `data/`.
- **Алгоритм** — генератор под оценкой (`generator/`) и сама eval-логика (`evals/`, `config/`).

Формат записи: `### YYYY-MM-DD`, дальше маркированный список, что изменилось и почему
(если причина не очевидна из самого изменения).

## Данные для оценки

### 2026-08-03
- Сгенерирован синтетический eval-датасет: 600 записей с `ground_truth` в
  `data/synthetic/eval_dataset.jsonl` (+ вспомогательные `entity_pool*.jsonl`,
  `layer0_dataset.jsonl`, `robustness_dataset.jsonl`). Заменяет ранее рассматривавшийся
  путь через SROIE (`priyank-m/SROIE_2019_text_recognition` — брошен из-за отсутствия
  поля `words`, датасет с этим багом остался в `notebooks/` как история, не как рабочий путь).

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
