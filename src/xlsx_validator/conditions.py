from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from .utils import is_empty, normalize_scalar, parse_numeric_bounds


class ConditionEvaluator:
    def evaluate(self, row: pd.Series, when: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]) -> bool:
        if not when:
            return True

        if isinstance(when, list):
            return all(self.evaluate(row, condition) for condition in when)

        if "all" in when:
            conditions = when.get("all")
            if not isinstance(conditions, list) or not conditions:
                return False
            return all(self.evaluate(row, condition) for condition in conditions)

        if "any" in when:
            conditions = when.get("any")
            if not isinstance(conditions, list) or not conditions:
                return False
            return any(self.evaluate(row, condition) for condition in conditions)

        if "not" in when:
            condition = when.get("not")
            if not isinstance(condition, dict):
                return False
            return not self.evaluate(row, condition)

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
            _, actual_max = parse_numeric_bounds(actual)
            expected_num = _to_float(expected)
            return actual_max is not None and expected_num is not None and actual_max > expected_num
        if operator == "greater_or_equal":
            _, actual_max = parse_numeric_bounds(actual)
            expected_num = _to_float(expected)
            return actual_max is not None and expected_num is not None and actual_max >= expected_num
        if operator == "less_than":
            actual_min, _ = parse_numeric_bounds(actual)
            expected_num = _to_float(expected)
            return actual_min is not None and expected_num is not None and actual_min < expected_num
        if operator == "less_or_equal":
            actual_min, _ = parse_numeric_bounds(actual)
            expected_num = _to_float(expected)
            return actual_min is not None and expected_num is not None and actual_min <= expected_num
        if operator == "number_between":
            actual_min, actual_max = parse_numeric_bounds(actual)
            min_value, max_value = _parse_between_bounds(expected)
            if actual_min is None or actual_max is None or min_value is None or max_value is None:
                return False
            return not (actual_max < min_value or actual_min > max_value)
        if operator == "number_not_between":
            actual_min, actual_max = parse_numeric_bounds(actual)
            min_value, max_value = _parse_between_bounds(expected)
            if actual_min is None or actual_max is None or min_value is None or max_value is None:
                return False
            return actual_max < min_value or actual_min > max_value

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
