from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .conditions import ConditionEvaluator
from .models import ValidationErrorRow
from .utils import (
    collect_columns_values,
    is_empty,
    normalize_scalar,
    parse_numeric_bounds,
    parse_date_value,
    parse_time_value,
)


class Rule(ABC):
    rule_type: str = ""
    required_fields: List[str] = []

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        self.payload = payload
        self.defaults = defaults
        self.rule_id = payload.get("id", "unknown_rule")
        self.description = payload.get("description", "")
        self.severity = payload.get("severity", "error")
        self.error_message = payload.get("error_message", f"Rule failed: {self.rule_id}")
        self.skip_if_empty = bool(payload.get("skip_if_empty", True))
        self.when = payload.get("when")
        self.condition_evaluator = ConditionEvaluator()
        self._validate_schema()

    def _validate_schema(self) -> None:
        for field in self.required_fields:
            if field not in self.payload:
                raise ValueError(f"Rule {self.rule_id} is missing field: {field}")

    def should_run(self, row: pd.Series) -> bool:
        return self.condition_evaluator.evaluate(row, self.when)

    def uses_row_validation(self) -> bool:
        return True

    def validate_dataframe(self, dataframe: pd.DataFrame) -> List[ValidationErrorRow]:
        return []

    @abstractmethod
    def involved_columns(self) -> List[str]:
        pass

    @abstractmethod
    def is_failed(self, row: pd.Series) -> bool:
        pass

    def validate(self, row: pd.Series) -> Optional[ValidationErrorRow]:
        if not self.should_run(row):
            return None
        if not self.is_failed(row):
            return None
        columns = self.involved_columns()
        screening_number, randomization_number, initials = _extract_row_identifiers(row)
        return ValidationErrorRow(
            row_number=int(row.name) + 2,
            screening_number=screening_number,
            randomization_number=randomization_number,
            initials=initials,
            rule_id=self.rule_id,
            severity=self.severity,
            error_message=self.error_message,
            description=self.description,
            columns=columns,
            values=collect_columns_values(row, columns),
        )

    def get_date_format(self) -> Optional[str]:
        return (
            self.payload.get("date_format")
            or self.payload.get("column_format")
            or self.defaults.get("date_format")
        )

    def get_time_format(self) -> Optional[str]:
        return (
            self.payload.get("time_format")
            or self.payload.get("column_format")
            or self.defaults.get("time_format")
        )


class ValueInRule(Rule):
    rule_type = "value_in"
    required_fields = ["allowed_values"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        target_column = self.payload.get("target_column")
        target_columns = self.payload.get("target_columns")
        if target_column is not None and target_columns is not None:
            raise ValueError(f"{self.rule_id}: specify either target_column or target_columns, not both")
        if target_columns is not None:
            if not isinstance(target_columns, list) or not target_columns:
                raise ValueError(f"{self.rule_id}: target_columns must be a non-empty list")
            self._target_columns: List[str] = target_columns
        elif target_column is not None:
            self._target_columns = [target_column]
        else:
            raise ValueError(f"{self.rule_id}: required field missing: target_column or target_columns")

    def involved_columns(self) -> List[str]:
        return list(self._target_columns)

    def _failed_columns(self, row: pd.Series) -> List[str]:
        allowed = self.payload.get("allowed_values", [])
        failed: List[str] = []
        for column in self._target_columns:
            value = normalize_scalar(row.get(column))
            if is_empty(value):
                if not self.skip_if_empty:
                    failed.append(column)
                continue
            if value not in allowed:
                failed.append(column)
        return failed

    def is_failed(self, row: pd.Series) -> bool:
        return bool(self._failed_columns(row))

    def uses_row_validation(self) -> bool:
        # Emit one error row per failed column, similar to other multi-column rules.
        return False

    def validate_dataframe(self, dataframe: pd.DataFrame) -> List[ValidationErrorRow]:
        errors: List[ValidationErrorRow] = []
        for _, row in dataframe.iterrows():
            if not self.should_run(row):
                continue
            failed_columns = self._failed_columns(row)
            if not failed_columns:
                continue
            screening_number, randomization_number, initials = _extract_row_identifiers(row)
            for column in failed_columns:
                errors.append(
                    ValidationErrorRow(
                        row_number=int(row.name) + 2,
                        screening_number=screening_number,
                        randomization_number=randomization_number,
                        initials=initials,
                        rule_id=self.rule_id,
                        severity=self.severity,
                        error_message=self.error_message,
                        description=self.description,
                        columns=[column],
                        values=collect_columns_values(row, [column]),
                    )
                )
        return errors

    def validate(self, row: pd.Series) -> Optional[ValidationErrorRow]:
        if not self.should_run(row):
            return None
        failed_columns = self._failed_columns(row)
        if not failed_columns:
            return None
        screening_number, randomization_number, initials = _extract_row_identifiers(row)
        return ValidationErrorRow(
            row_number=int(row.name) + 2,
            screening_number=screening_number,
            randomization_number=randomization_number,
            initials=initials,
            rule_id=self.rule_id,
            severity=self.severity,
            error_message=self.error_message,
            description=self.description,
            columns=failed_columns,
            values=collect_columns_values(row, failed_columns),
        )


class ValueInIfRule(ValueInRule):
    rule_type = "value_in_if"
    required_fields = ["allowed_values", "when"]


class ValueInIfOrderedRule(Rule):
    """Several value_in_if branches sharing one target and one source column; first matching when wins."""

    rule_type = "value_in_if_ordered"
    required_fields = ["target_column", "source_column", "cases"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        self._target_column = str(payload["target_column"])
        self._source_column = str(payload["source_column"])
        cases = payload.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError(f"{self.rule_id}: cases must be a non-empty list")
        for idx, case in enumerate(cases):
            if not isinstance(case, dict):
                raise ValueError(f"{self.rule_id}: cases[{idx}] must be an object")
            when_part = case.get("when")
            if not isinstance(when_part, dict):
                raise ValueError(f"{self.rule_id}: cases[{idx}].when must be an object")
            if "column" in when_part:
                raise ValueError(f"{self.rule_id}: cases[{idx}].when must not include column (use source_column)")
            if "allowed_values" not in case:
                raise ValueError(f"{self.rule_id}: cases[{idx}] is missing allowed_values")
            allowed = case.get("allowed_values")
            if not isinstance(allowed, list) or not allowed:
                raise ValueError(f"{self.rule_id}: cases[{idx}].allowed_values must be a non-empty list")
        self._cases: List[Dict[str, Any]] = cases

    def involved_columns(self) -> List[str]:
        return [self._target_column, self._source_column]

    def is_failed(self, row: pd.Series) -> bool:
        return self._validate_row(row) is not None

    def _first_matching_case(self, row: pd.Series) -> Optional[Dict[str, Any]]:
        for case in self._cases:
            when_part = case["when"]
            full_when = {**when_part, "column": self._source_column}
            if self.condition_evaluator.evaluate(row, full_when):
                return case
        return None

    def _validate_row(self, row: pd.Series) -> Optional[ValidationErrorRow]:
        case = self._first_matching_case(row)
        if case is None:
            return None
        value = normalize_scalar(row.get(self._target_column))
        allowed = case.get("allowed_values", [])
        if is_empty(value):
            if self.skip_if_empty:
                return None
        elif value in allowed:
            return None

        err_msg = case.get("error_message") or self.error_message
        columns = [self._target_column, self._source_column]
        screening_number, randomization_number, initials = _extract_row_identifiers(row)
        return ValidationErrorRow(
            row_number=int(row.name) + 2,
            screening_number=screening_number,
            randomization_number=randomization_number,
            initials=initials,
            rule_id=self.rule_id,
            severity=self.severity,
            error_message=err_msg,
            description=self.description,
            columns=columns,
            values=collect_columns_values(row, columns),
        )

    def validate(self, row: pd.Series) -> Optional[ValidationErrorRow]:
        if not self.should_run(row):
            return None
        return self._validate_row(row)


class ValueInManyRule(Rule):
    rule_type = "value_in_many"
    required_fields = ["target_columns", "allowed_values"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        target_columns = self.payload.get("target_columns")
        if not isinstance(target_columns, list) or not target_columns:
            raise ValueError(f"{self.rule_id}: target_columns must be a non-empty list")

    def involved_columns(self) -> List[str]:
        return self.payload["target_columns"]

    def _failed_columns(self, row: pd.Series) -> List[str]:
        allowed = self.payload.get("allowed_values", [])
        failed: List[str] = []
        for column in self.payload["target_columns"]:
            value = normalize_scalar(row.get(column))
            if is_empty(value):
                if not self.skip_if_empty:
                    failed.append(column)
                continue
            if value not in allowed:
                failed.append(column)
        return failed

    def is_failed(self, row: pd.Series) -> bool:
        return bool(self._failed_columns(row))

    def validate(self, row: pd.Series) -> Optional[ValidationErrorRow]:
        if not self.should_run(row):
            return None
        failed_columns = self._failed_columns(row)
        if not failed_columns:
            return None
        screening_number, randomization_number, initials = _extract_row_identifiers(row)
        return ValidationErrorRow(
            row_number=int(row.name) + 2,
            screening_number=screening_number,
            randomization_number=randomization_number,
            initials=initials,
            rule_id=self.rule_id,
            severity=self.severity,
            error_message=self.error_message,
            description=self.description,
            columns=failed_columns,
            values=collect_columns_values(row, failed_columns),
        )


class RequiredIfRule(Rule):
    rule_type = "required_if"
    required_fields = ["when"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        tc = self.payload.get("target_column")
        tcs = self.payload.get("target_columns")
        if tc is not None and tcs is not None:
            raise ValueError(f"{self.rule_id}: specify either target_column or target_columns, not both")
        if tcs is not None:
            if not isinstance(tcs, list) or not tcs:
                raise ValueError(f"{self.rule_id}: target_columns must be a non-empty list")
            self._target_columns: List[str] = tcs
        elif tc is not None:
            self._target_columns = [tc]
        else:
            raise ValueError(f"{self.rule_id}: required field missing: target_column or target_columns")

    def involved_columns(self) -> List[str]:
        return list(self._target_columns)

    def _failed_columns(self, row: pd.Series) -> List[str]:
        failed: List[str] = []
        for column in self._target_columns:
            if is_empty(row.get(column)):
                failed.append(column)
        return failed

    def is_failed(self, row: pd.Series) -> bool:
        return bool(self._failed_columns(row))

    def uses_row_validation(self) -> bool:
        return False

    def validate_dataframe(self, dataframe: pd.DataFrame) -> List[ValidationErrorRow]:
        errors: List[ValidationErrorRow] = []
        for _, row in dataframe.iterrows():
            if not self.should_run(row):
                continue
            failed_columns = self._failed_columns(row)
            if not failed_columns:
                continue
            screening_number, randomization_number, initials = _extract_row_identifiers(row)
            for column in failed_columns:
                errors.append(
                    ValidationErrorRow(
                        row_number=int(row.name) + 2,
                        screening_number=screening_number,
                        randomization_number=randomization_number,
                        initials=initials,
                        rule_id=self.rule_id,
                        severity=self.severity,
                        error_message=self.error_message,
                        description=self.description,
                        columns=[column],
                        values=collect_columns_values(row, [column]),
                    )
                )
        return errors


class EmptyIfRule(Rule):
    rule_type = "empty_if"
    required_fields = ["target_column", "when"]

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        return not is_empty(row.get(self.payload["target_column"]))


class EmptyRule(Rule):
    rule_type = "empty"
    required_fields = ["target_column"]

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        return not is_empty(row.get(self.payload["target_column"]))


class NotEmptyRule(Rule):
    rule_type = "not_empty"
    required_fields = []

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        target_column = self.payload.get("target_column")
        target_columns = self.payload.get("target_columns")
        if target_column is not None and target_columns is not None:
            raise ValueError(f"{self.rule_id}: specify either target_column or target_columns, not both")
        if target_columns is not None:
            if not isinstance(target_columns, list) or not target_columns:
                raise ValueError(f"{self.rule_id}: target_columns must be a non-empty list")
            self._target_columns: List[str] = target_columns
        elif target_column is not None:
            self._target_columns = [target_column]
        else:
            raise ValueError(f"{self.rule_id}: required field missing: target_column or target_columns")

    def involved_columns(self) -> List[str]:
        return list(self._target_columns)

    def _failed_columns(self, row: pd.Series) -> List[str]:
        failed: List[str] = []
        for column in self._target_columns:
            if is_empty(row.get(column)):
                failed.append(column)
        return failed

    def is_failed(self, row: pd.Series) -> bool:
        return bool(self._failed_columns(row))

    def validate(self, row: pd.Series) -> Optional[ValidationErrorRow]:
        if not self.should_run(row):
            return None
        failed_columns = self._failed_columns(row)
        if not failed_columns:
            return None
        screening_number, randomization_number, initials = _extract_row_identifiers(row)
        return ValidationErrorRow(
            row_number=int(row.name) + 2,
            screening_number=screening_number,
            randomization_number=randomization_number,
            initials=initials,
            rule_id=self.rule_id,
            severity=self.severity,
            error_message=self.error_message,
            description=self.description,
            columns=failed_columns,
            values=collect_columns_values(row, failed_columns),
        )


class AnyNotEmptyRule(Rule):
    rule_type = "any_not_empty"
    required_fields = ["target_columns"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        target_columns = self.payload.get("target_columns")
        if not isinstance(target_columns, list) or len(target_columns) < 2:
            raise ValueError(f"{self.rule_id}: target_columns must be a list with at least 2 columns")
        self._target_columns: List[str] = target_columns

    def involved_columns(self) -> List[str]:
        return list(self._target_columns)

    def is_failed(self, row: pd.Series) -> bool:
        return all(is_empty(row.get(column)) for column in self._target_columns)


class TextStartsWithRule(Rule):
    rule_type = "text_starts_with"
    required_fields = ["target_column", "prefix"]

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        raw_value = row.get(self.payload["target_column"])
        if is_empty(raw_value):
            return not self.skip_if_empty
        value = str(normalize_scalar(raw_value))
        prefix = str(self.payload["prefix"])
        return not value.startswith(prefix)


class TextStartsWithManyRule(Rule):
    rule_type = "text_starts_with_many"
    required_fields = ["target_columns", "prefix"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        target_columns = self.payload.get("target_columns")
        if not isinstance(target_columns, list) or not target_columns:
            raise ValueError(f"{self.rule_id}: target_columns must be a non-empty list")

    def involved_columns(self) -> List[str]:
        return self.payload["target_columns"]

    def _failed_columns(self, row: pd.Series) -> List[str]:
        prefix = str(self.payload["prefix"])
        failed: List[str] = []
        for column in self.payload["target_columns"]:
            raw_value = row.get(column)
            if is_empty(raw_value):
                if not self.skip_if_empty:
                    failed.append(column)
                continue
            value = str(normalize_scalar(raw_value))
            if not value.startswith(prefix):
                failed.append(column)
        return failed

    def is_failed(self, row: pd.Series) -> bool:
        return bool(self._failed_columns(row))

    def uses_row_validation(self) -> bool:
        return False

    def validate_dataframe(self, dataframe: pd.DataFrame) -> List[ValidationErrorRow]:
        errors: List[ValidationErrorRow] = []
        for _, row in dataframe.iterrows():
            if not self.should_run(row):
                continue
            failed_columns = self._failed_columns(row)
            if not failed_columns:
                continue
            screening_number, randomization_number, initials = _extract_row_identifiers(row)
            for column in failed_columns:
                errors.append(
                    ValidationErrorRow(
                        row_number=int(row.name) + 2,
                        screening_number=screening_number,
                        randomization_number=randomization_number,
                        initials=initials,
                        rule_id=self.rule_id,
                        severity=self.severity,
                        error_message=self.error_message,
                        description=self.description,
                        columns=[column],
                        values=collect_columns_values(row, [column]),
                    )
                )
        return errors


class NumberGreaterThanRule(Rule):
    rule_type = "number_greater_than"
    required_fields = ["target_column", "value"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        self.threshold = float(self.payload["value"])

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        raw_value = row.get(self.payload["target_column"])
        if is_empty(raw_value):
            return not self.skip_if_empty
        _, numeric_max = parse_numeric_bounds(raw_value)
        if numeric_max is None:
            return True
        return numeric_max < self.threshold


class NumberLessThanRule(Rule):
    rule_type = "number_less_than"
    required_fields = ["target_column", "value"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        self.threshold = float(self.payload["value"])

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        raw_value = row.get(self.payload["target_column"])
        if is_empty(raw_value):
            return not self.skip_if_empty
        numeric_min, _ = parse_numeric_bounds(raw_value)
        if numeric_min is None:
            return True
        return numeric_min >= self.threshold


class NumberLessOrEqualRule(Rule):
    rule_type = "number_less_or_equal"
    required_fields = ["target_column", "value"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        self.threshold = float(self.payload["value"])

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        raw_value = row.get(self.payload["target_column"])
        if is_empty(raw_value):
            return not self.skip_if_empty
        numeric_min, _ = parse_numeric_bounds(raw_value)
        if numeric_min is None:
            return True
        return numeric_min > self.threshold


class NumberBetweenRule(Rule):
    rule_type = "number_between"
    required_fields = ["target_column", "min_value", "max_value"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        self.min_value = float(self.payload["min_value"])
        self.max_value = float(self.payload["max_value"])
        if self.min_value > self.max_value:
            raise ValueError(f"{self.rule_id}: min_value cannot be greater than max_value")

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        raw_value = row.get(self.payload["target_column"])
        if is_empty(raw_value):
            return not self.skip_if_empty
        value_min, value_max = parse_numeric_bounds(raw_value)
        if value_min is None or value_max is None:
            return True
        return value_max < self.min_value or value_min > self.max_value


class DateEqualRule(Rule):
    rule_type = "date_equal"
    required_fields = ["main_column", "comparative_columns"]

    def involved_columns(self) -> List[str]:
        return [self.payload["main_column"], *self.payload.get("comparative_columns", [])]

    def is_failed(self, row: pd.Series) -> bool:
        main_col = self.payload["main_column"]
        cmp_cols = self.payload.get("comparative_columns", [])
        main_date = parse_date_value(row.get(main_col), self.get_date_format())
        cmp_dates = [parse_date_value(row.get(c), self.get_date_format()) for c in cmp_cols]
        if self.skip_if_empty and (main_date is None or any(d is None for d in cmp_dates)):
            return False
        return any(d != main_date for d in cmp_dates)


class DateEqualAnyRule(Rule):
    rule_type = "date_equal_any"
    required_fields = ["main_column", "comparative_columns"]

    def involved_columns(self) -> List[str]:
        return [self.payload["main_column"], *self.payload.get("comparative_columns", [])]

    def is_failed(self, row: pd.Series) -> bool:
        main_col = self.payload["main_column"]
        cmp_cols = self.payload.get("comparative_columns", [])
        main_date = parse_date_value(row.get(main_col), self.get_date_format())
        cmp_dates = [parse_date_value(row.get(c), self.get_date_format()) for c in cmp_cols]
        available_cmp_dates = [d for d in cmp_dates if d is not None]
        if self.skip_if_empty and (main_date is None or not available_cmp_dates):
            return False
        return main_date not in available_cmp_dates


class DateBetweenRule(Rule):
    rule_type = "date_between"
    required_fields = ["ref_column", "min_days", "max_days"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        target_column = self.payload.get("target_column")
        target_columns = self.payload.get("target_columns")
        if target_column is not None and target_columns is not None:
            raise ValueError(f"{self.rule_id}: specify either target_column or target_columns, not both")
        if target_columns is not None:
            if not isinstance(target_columns, list) or not target_columns:
                raise ValueError(f"{self.rule_id}: target_columns must be a non-empty list")
            self._target_columns: List[str] = target_columns
        elif target_column is not None:
            self._target_columns = [target_column]
        else:
            raise ValueError(f"{self.rule_id}: required field missing: target_column or target_columns")
        self.min_days = int(self.payload["min_days"])
        self.max_days = int(self.payload["max_days"])
        if self.min_days > self.max_days:
            raise ValueError(f"{self.rule_id}: min_days cannot be greater than max_days")

    def involved_columns(self) -> List[str]:
        return [*self._target_columns, self.payload["ref_column"]]

    def _failed_target_columns(self, row: pd.Series) -> List[str]:
        ref_column = self.payload["ref_column"]
        ref = parse_date_value(row.get(ref_column), self.get_date_format())
        if ref is None:
            if self.skip_if_empty:
                return []
            return list(self._target_columns)

        failed: List[str] = []
        for target_column in self._target_columns:
            target = parse_date_value(row.get(target_column), self.get_date_format())
            if target is None:
                if not self.skip_if_empty:
                    failed.append(target_column)
                continue
            delta = (target - ref).days
            if not (self.min_days <= delta <= self.max_days):
                failed.append(target_column)
        return failed

    def is_failed(self, row: pd.Series) -> bool:
        return bool(self._failed_target_columns(row))

    def validate(self, row: pd.Series) -> Optional[ValidationErrorRow]:
        if not self.should_run(row):
            return None
        failed_target_columns = self._failed_target_columns(row)
        if not failed_target_columns:
            return None
        columns = list(failed_target_columns)
        ref_column = self.payload["ref_column"]
        if ref_column not in columns:
            columns.append(ref_column)
        screening_number, randomization_number, initials = _extract_row_identifiers(row)
        return ValidationErrorRow(
            row_number=int(row.name) + 2,
            screening_number=screening_number,
            randomization_number=randomization_number,
            initials=initials,
            rule_id=self.rule_id,
            severity=self.severity,
            error_message=self.error_message,
            description=self.description,
            columns=columns,
            values=collect_columns_values(row, columns),
        )


class TimeBetweenRule(Rule):
    rule_type = "time_between"
    required_fields = ["target_column", "ref_column", "min_minutes", "max_minutes"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        self.min_minutes = int(self.payload["min_minutes"])
        self.max_minutes = int(self.payload["max_minutes"])
        if self.min_minutes > self.max_minutes:
            raise ValueError(f"{self.rule_id}: min_minutes cannot be greater than max_minutes")

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"], self.payload["ref_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        target = parse_time_value(row.get(self.payload["target_column"]), self.get_time_format())
        ref = parse_time_value(row.get(self.payload["ref_column"]), self.get_time_format())
        if self.skip_if_empty and (target is None or ref is None):
            return False
        if target is None or ref is None:
            return True
        delta = int((target - ref).total_seconds() // 60)
        return not (self.min_minutes <= delta <= self.max_minutes)


class TimeGreaterOrEqualRule(Rule):
    rule_type = "time_greater_or_equal"
    required_fields = ["target_column", "ref_column"]

    def involved_columns(self) -> List[str]:
        return [self.payload["target_column"], self.payload["ref_column"]]

    def is_failed(self, row: pd.Series) -> bool:
        target = parse_time_value(row.get(self.payload["target_column"]), self.get_time_format())
        ref = parse_time_value(row.get(self.payload["ref_column"]), self.get_time_format())
        if self.skip_if_empty and (target is None or ref is None):
            return False
        if target is None or ref is None:
            return True
        return target < ref


class TimeAfterRefIfDateEqualManyRule(Rule):
    rule_type = "time_after_ref_if_date_equal_many"
    required_fields = ["pairs", "ref_date_column", "ref_time_column"]

    def __init__(self, payload: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        super().__init__(payload, defaults)
        pairs = self.payload.get("pairs")
        if not isinstance(pairs, list) or not pairs:
            raise ValueError(f"{self.rule_id}: pairs must be a non-empty list")
        parsed_pairs: List[Tuple[str, str]] = []
        for idx, pair in enumerate(pairs):
            if not isinstance(pair, dict):
                raise ValueError(f"{self.rule_id}: pairs[{idx}] must be an object")
            date_column = pair.get("date_column")
            time_column = pair.get("time_column")
            if not isinstance(date_column, str) or not date_column.strip():
                raise ValueError(f"{self.rule_id}: pairs[{idx}].date_column must be a non-empty string")
            if not isinstance(time_column, str) or not time_column.strip():
                raise ValueError(f"{self.rule_id}: pairs[{idx}].time_column must be a non-empty string")
            parsed_pairs.append((date_column, time_column))
        self._pairs = parsed_pairs

    def involved_columns(self) -> List[str]:
        columns: List[str] = [self.payload["ref_date_column"], self.payload["ref_time_column"]]
        for date_column, time_column in self._pairs:
            if date_column not in columns:
                columns.append(date_column)
            if time_column not in columns:
                columns.append(time_column)
        return columns

    def _failed_columns(self, row: pd.Series) -> List[str]:
        ref_date_column = self.payload["ref_date_column"]
        ref_time_column = self.payload["ref_time_column"]
        ref_date = parse_date_value(row.get(ref_date_column), self.get_date_format())
        ref_time = parse_time_value(row.get(ref_time_column), self.get_time_format())
        if ref_date is None or ref_time is None:
            return [] if self.skip_if_empty else [ref_date_column, ref_time_column]

        failed: List[str] = []
        for date_column, time_column in self._pairs:
            pair_date = parse_date_value(row.get(date_column), self.get_date_format())
            if pair_date != ref_date:
                continue
            pair_time = parse_time_value(row.get(time_column), self.get_time_format())
            if pair_time is None:
                if not self.skip_if_empty:
                    failed.append(time_column)
                continue
            if pair_time <= ref_time:
                failed.append(time_column)
        return failed

    def is_failed(self, row: pd.Series) -> bool:
        return bool(self._failed_columns(row))

    def uses_row_validation(self) -> bool:
        # Emit one error row per failed target time column.
        return False

    def validate_dataframe(self, dataframe: pd.DataFrame) -> List[ValidationErrorRow]:
        errors: List[ValidationErrorRow] = []
        ref_date_column = self.payload["ref_date_column"]
        ref_time_column = self.payload["ref_time_column"]

        for _, row in dataframe.iterrows():
            if not self.should_run(row):
                continue
            failed = self._failed_columns(row)
            if not failed:
                continue
            screening_number, randomization_number, initials = _extract_row_identifiers(row)
            for failed_column in failed:
                columns = [failed_column, ref_date_column, ref_time_column]
                errors.append(
                    ValidationErrorRow(
                        row_number=int(row.name) + 2,
                        screening_number=screening_number,
                        randomization_number=randomization_number,
                        initials=initials,
                        rule_id=self.rule_id,
                        severity=self.severity,
                        error_message=self.error_message,
                        description=self.description,
                        columns=columns,
                        values=collect_columns_values(row, columns),
                    )
                )
        return errors


class UniqueIfRule(Rule):
    rule_type = "unique_if"
    required_fields = ["target_column", "when"]

    def involved_columns(self) -> List[str]:
        columns = [self.payload["target_column"]]
        if isinstance(self.when, dict) and self.when.get("column"):
            columns.append(self.when["column"])
        return list(dict.fromkeys(columns))

    def uses_row_validation(self) -> bool:
        return False

    def is_failed(self, row: pd.Series) -> bool:
        return False

    def validate_dataframe(self, dataframe: pd.DataFrame) -> List[ValidationErrorRow]:
        target_column = self.payload["target_column"]
        applicable_mask = dataframe.apply(self.should_run, axis=1)
        scoped_df = dataframe[applicable_mask].copy()
        if scoped_df.empty:
            return []

        normalized_values = scoped_df[target_column].map(normalize_scalar)
        empty_mask = normalized_values.map(is_empty)
        if self.skip_if_empty:
            candidate_values = normalized_values[~empty_mask]
        else:
            candidate_values = normalized_values
        duplicate_mask = candidate_values.duplicated(keep=False)
        duplicate_indices = set(duplicate_mask[duplicate_mask].index.tolist())

        errors: List[ValidationErrorRow] = []
        for idx, row in scoped_df.iterrows():
            is_duplicate = idx in duplicate_indices
            if not is_duplicate:
                continue
            columns = self.involved_columns()
            screening_number, randomization_number, initials = _extract_row_identifiers(row)
            errors.append(
                ValidationErrorRow(
                    row_number=int(idx) + 2,
                    screening_number=screening_number,
                    randomization_number=randomization_number,
                    initials=initials,
                    rule_id=self.rule_id,
                    severity=self.severity,
                    error_message=self.error_message,
                    description=self.description,
                    columns=columns,
                    values=collect_columns_values(row, columns),
                )
            )
        return errors


def _to_float(value: Any) -> Optional[float]:
    normalized = normalize_scalar(value)
    if isinstance(normalized, str):
        normalized = normalized.replace(",", ".")
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _extract_row_identifiers(row: pd.Series) -> tuple[Optional[Any], Optional[Any], Optional[Any]]:
    screening_number = row.get("Screening #")
    randomization_number = row.get("Randomization #")
    if randomization_number is None:
        randomization_number = row.get("Randomization\xa0#")
    initials = row.get("Initials")
    return screening_number, randomization_number, initials
