from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .utils import is_empty, normalize_scalar


class ConditionEvaluator:
    def evaluate(self, row: pd.Series, when: Optional[Dict[str, Any]]) -> bool:
        if not when:
            return True

        column = when.get("column")
        operator = (when.get("operator") or "equals").strip().lower()
        expected = when.get("value")
        actual = normalize_scalar(row.get(column))

        if operator == "equals":
            return actual == expected
        if operator == "not_equals":
            return actual != expected
        if operator == "equals_column":
            if not isinstance(expected, str):
                return False
            other_value = normalize_scalar(row.get(expected))
            return actual == other_value
        if operator == "not_equals_column":
            if not isinstance(expected, str):
                return False
            other_value = normalize_scalar(row.get(expected))
            return actual != other_value
        if operator == "in":
            if not isinstance(expected, list):
                return False
            return actual in expected
        if operator == "not_in":
            if not isinstance(expected, list):
                return False
            return actual not in expected
        if operator == "is_empty":
            return is_empty(actual)
        if operator == "is_not_empty":
            return not is_empty(actual)
        if operator == "starts_with":
            if is_empty(actual) or expected is None:
                return False
            if isinstance(expected, list):
                prefixes = [str(prefix) for prefix in expected if prefix is not None]
                if not prefixes:
                    return False
                return any(str(actual).startswith(prefix) for prefix in prefixes)
            return str(actual).startswith(str(expected))
        if operator == "greater_than":
            actual_num = _to_float(actual)
            expected_num = _to_float(expected)
            return actual_num is not None and expected_num is not None and actual_num > expected_num
        if operator == "greater_or_equal":
            actual_num = _to_float(actual)
            expected_num = _to_float(expected)
            return actual_num is not None and expected_num is not None and actual_num >= expected_num
        if operator == "less_than":
            actual_num = _to_float(actual)
            expected_num = _to_float(expected)
            return actual_num is not None and expected_num is not None and actual_num < expected_num
        if operator == "less_or_equal":
            actual_num = _to_float(actual)
            expected_num = _to_float(expected)
            return actual_num is not None and expected_num is not None and actual_num <= expected_num
        if operator == "number_between":
            actual_num = _to_float(actual)
            min_value, max_value = _parse_between_bounds(expected)
            if actual_num is None or min_value is None or max_value is None:
                return False
            return min_value <= actual_num <= max_value
        if operator == "number_not_between":
            actual_num = _to_float(actual)
            min_value, max_value = _parse_between_bounds(expected)
            if actual_num is None or min_value is None or max_value is None:
                return False
            return not (min_value <= actual_num <= max_value)

        raise ValueError(f"Unsupported when.operator: {operator}")


def _to_float(value: Any) -> Optional[float]:
    normalized = normalize_scalar(value)
    if isinstance(normalized, str):
        normalized = normalized.replace(",", ".")
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _parse_between_bounds(value: Any) -> Tuple[Optional[float], Optional[float]]:
    if isinstance(value, dict):
        min_value = _to_float(value.get("min"))
        max_value = _to_float(value.get("max"))
        return min_value, max_value
    if isinstance(value, list) and len(value) == 2:
        min_value = _to_float(value[0])
        max_value = _to_float(value[1])
        return min_value, max_value
    return None, None
