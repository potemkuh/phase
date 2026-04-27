from datetime import date, datetime, time
import re
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def parse_numeric_bounds(value: Any) -> Tuple[Optional[float], Optional[float]]:
    normalized = normalize_scalar(value)
    if is_empty(normalized):
        return None, None

    if isinstance(normalized, (int, float)):
        number = float(normalized)
        return number, number

    if isinstance(normalized, str):
        text = normalized.replace(",", ".").strip()
        # Accept ranges like "2-3", "2 - 3", "5-2" (order can be reversed).
        range_match = re.match(
            r"^\s*([+-]?\d+(?:\.\d+)?)\s*[-–—]\s*([+-]?\d+(?:\.\d+)?)\s*$",
            text,
        )
        if range_match:
            left = float(range_match.group(1))
            right = float(range_match.group(2))
            return (left, right) if left <= right else (right, left)
        try:
            number = float(text)
            return number, number
        except ValueError:
            return None, None

    try:
        number = float(normalized)
        return number, number
    except (TypeError, ValueError):
        return None, None


def parse_date_value(value: Any, date_format: Optional[str]) -> Optional[date]:
    if is_empty(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    parsed = pd.to_datetime(value, format=date_format, errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def parse_time_value(value: Any, time_format: Optional[str]) -> Optional[datetime]:
    if is_empty(value):
        return None

    # Нормализуем все значения к одной "фиктивной" дате,
    # чтобы сравнивать только время суток (часы, минуты, секунды),
    # независимо от исходной календарной даты в ячейке.
    base_date = datetime(1900, 1, 1)

    if isinstance(value, pd.Timestamp):
        dt = value.to_pydatetime()
    elif isinstance(value, datetime):
        dt = value
    elif isinstance(value, time):
        # Время без даты из Excel: считаем его временем в базовый день
        dt = datetime(1900, 1, 1, value.hour, value.minute, value.second)
    else:
        parsed = pd.to_datetime(value, format=time_format, errors="coerce")
        if pd.isna(parsed):
            parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        dt = parsed.to_pydatetime()

    return datetime(base_date.year, base_date.month, base_date.day, dt.hour, dt.minute, dt.second)


def collect_columns_values(row: pd.Series, columns: Iterable[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for col in columns:
        result[col] = row.get(col)
    return result
