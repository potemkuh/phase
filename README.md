# XLSX Validator (OOP)

Проект для валидации `xlsx/csv` по правилам из `YAML`.

## Структура проекта

```text
phase/
  validator.py
  rules.yml
  requirements.txt
  README.md
  src/
    xlsx_validator/
      __init__.py
      __main__.py
      cli.py
      io.py
      engine.py
      factory.py
      rules.py
      conditions.py
      models.py
      utils.py
```

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Запуск

### Вариант 1 (корневой скрипт)

```bash
python validator.py --input "data.xlsx" --rules "rules.yml" --output "errors.xlsx"
```

### Вариант 2 (модуль)

```bash
python -m src.xlsx_validator --input "data.xlsx" --rules "rules.yml" --output "errors.xlsx"
```

Если у файла несколько листов:

```bash
python validator.py --input "data.xlsx" --rules "rules.yml" --sheet "Sheet1" --output "errors.xlsx"

# Если вверху есть служебные строки (тексты вопросов и т.п.)
python validator.py --input "data.xlsx" --rules "rules.yml" --sheet "Main" --skip-rows 1 --output "errors.xlsx"
```

По умолчанию валидатор уже запускается с 3-й строки:
- 1-я строка используется как заголовки колонок
- 2-я строка (описания) пропускается
- начиная с 3-й строки идут данные для проверки (`--skip-rows 1`)

## Формат rules.yml

```yaml
version: 1
defaults:
  date_format: "%Y-%m-%d"
  time_format: "%H:%M"

rules:
  - id: sex_allowed_values
    type: value_in
    target_column: SCR_DEMO_SEX
    allowed_values: ["Женский", "Мужской"]
    error_message: "Недопустимое значение SCR_DEMO_SEX"
```

Для `value_in` и `value_in_if` можно указывать:
- `target_column` (одна колонка), **или**
- `target_columns` (список колонок).

Оба ключа одновременно использовать нельзя.

Для `not_empty` тоже можно указывать:
- `target_column` (одна колонка), **или**
- `target_columns` (список колонок).

Для `date_between` тоже можно указывать:
- `target_column` (одна дата), **или**
- `target_columns` (список дат, все сравниваются с одним `ref_column` и тем же диапазоном).

## Условия `when`: одно и составные

`when` поддерживает как одно условие, так и составные логические блоки:

- `all` — все вложенные условия должны быть истинны (AND)
- `any` — хотя бы одно вложенное условие истинно (OR)
- `not` — инвертирует вложенное условие (NOT)

Пример зависимости одновременно от пола, возраста и номера центра (`site#`):

```yaml
- id: sex_age_site_rule
  type: value_in_if
  target_column: SCR_PREGN_ORRES_PREGN
  allowed_values:
    - Отрицательный
  when:
    all:
      - column: SCR_DEMO_SEX
        operator: equals
        value: Женский
      - column: AGE
        operator: number_between
        value:
          min: 18
          max: 45
      - column: site#
        operator: in
        value: [101, 205, 330]
  skip_if_empty: false
  error_message: "Правило действует только для женщин 18-45 из центров 101/205/330"
```

## Поддерживаемые типы правил

- `value_in`
- `value_in_if`
- `value_in_many`
- `required_if`
- `empty`
- `empty_if`
- `not_empty`
- `any_not_empty`
- `text_starts_with`
- `text_starts_with_many`
- `number_greater_than`
- `number_less_than`
- `number_less_or_equal`
- `number_between`
- `date_equal`
- `date_equal_any`
- `date_between`
- `time_between`
- `time_greater_or_equal`
- `time_after_ref_if_date_equal_many`
- `unique_if`

## Пример `value_in_many`

`value_in_many` проверяет сразу несколько колонок на вхождение в один и тот же список допустимых значений.

```yaml
- id: status_for_many_columns
  type: value_in_many
  target_columns:
    - LAB_RESULT_A
    - LAB_RESULT_B
    - LAB_RESULT_C
  allowed_values: ["Норма", "Отклонение"]
  skip_if_empty: true
  error_message: "Значение должно быть Норма или Отклонение"
```

## Пример `unique_if`

`unique_if` проверяет, что значения в `target_column` уникальны среди строк, где `when=true`.
Если `skip_if_empty: true`, пустые значения не участвуют в проверке на дубликаты.

```yaml
- id: unique_patient_per_site
  type: unique_if
  target_column: PATIENT_CODE
  when:
    column: site#
    operator: in
    value: [101, 205, 330]
  skip_if_empty: true
  error_message: "PATIENT_CODE должен быть уникален в выбранных центрах"
```

## Пример `any_not_empty`

`any_not_empty` проверяет, что хотя бы одна колонка из `target_columns` заполнена.
Ошибка возникает только если пустые все перечисленные поля.

```yaml
- id: at_least_one_contact
  type: any_not_empty
  target_columns:
    - PHONE
    - EMAIL
  error_message: "Хотя бы одно из полей PHONE или EMAIL должно быть заполнено"
```

## Числовые диапазоны в ячейке

Для числовых правил и условий допускаются значения ячеек в формате диапазона:

- `2-3`
- `2 - 3`
- `5-2` (обратный порядок тоже поддерживается и нормализуется в `2..5`)

Это работает для:
- правил `number_between`, `number_greater_than`, `number_less_than`, `number_less_or_equal`;
- условий `when` с операторами `number_between`, `number_not_between`, `greater_than`, `greater_or_equal`, `less_than`, `less_or_equal`.

Пример:

```yaml
- id: urine_wbc_in_range
  type: number_between
  target_column: SCR_URINE_LBORRES_URWBC
  min_value: 0
  max_value: 5
  skip_if_empty: true
  error_message: "SCR_URINE_LBORRES_URWBC должно быть в диапазоне 0..5"
```

## Логика `date_between`

Проверяется выражение:

`min_days <= (target_column - ref_column) <= max_days`

Примеры:

- диапазон `0..14` дней
- точный сдвиг `+1` день через `min_days: 1` и `max_days: 1`
- точный сдвиг `+2` дня через `min_days: 2` и `max_days: 2`

## Отчет об ошибках

На выходе создается `errors.xlsx` (или `errors.csv`) с полями:

- `Screening #`
- `Randomization #`
- `Initials`
- `row_number`
- `rule_id`
- `severity`
- `error_message`
- `values`

## Как добавить новый тип правила (OOP)

### 1) Создать класс в `src/xlsx_validator/rules.py`

Нужно унаследоваться от `Rule` и реализовать:

- `rule_type`
- `required_fields`
- `involved_columns()`
- `is_failed(row)`

Пример:

```python
class NotEmptyRule(Rule):
    rule_type = "not_empty"
    required_fields = ["target_column"]

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        return is_empty(row.get(self.payload["target_column"]))
```

### 2) Зарегистрировать класс в `src/xlsx_validator/factory.py`

Добавить в `RuleFactory._registry`:

```python
NotEmptyRule.rule_type: NotEmptyRule
```

### 3) Добавить правило в `rules.yml`

```yaml
- id: some_rule
  type: not_empty
  target_column: SOME_COLUMN
  error_message: "Поле не должно быть пустым"
```

После этого тип сразу будет доступен в рантайме.

## Частые ошибки

- `references missing columns` — в Excel нет колонки из правила.
- `Unsupported rule type` — тип не зарегистрирован в `RuleFactory`.
- `min_days cannot be greater than max_days` — некорректный диапазон.
