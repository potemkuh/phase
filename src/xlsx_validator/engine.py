from typing import List, Tuple

import pandas as pd

from .models import ValidationCheckRow, ValidationErrorRow
from .rules import Rule
from .utils import collect_columns_values


class ValidationEngine:
    def __init__(self, dataframe: pd.DataFrame, rules: List[Rule]) -> None:
        self.dataframe = dataframe
        self.rules = rules

    def validate_schema(self) -> None:
        columns = set(self.dataframe.columns)
        for rule in self.rules:
            missing = [col for col in rule.involved_columns() if col not in columns]
            if missing:
                raise ValueError(f"Rule {rule.rule_id} references missing columns: {missing}")

    def run(self) -> Tuple[List[ValidationErrorRow], List[ValidationCheckRow]]:
        self.validate_schema()
        errors: List[ValidationErrorRow] = []
        checks: List[ValidationCheckRow] = []
        row_rules = [rule for rule in self.rules if rule.uses_row_validation()]
        dataframe_rules = [rule for rule in self.rules if not rule.uses_row_validation()]

        for _, row in self.dataframe.iterrows():
            row_num = int(row.name) + 3
            screening_number = row.get("Screening #")
            randomization_number = row.get("Randomization #")
            if randomization_number is None:
                randomization_number = row.get("Randomization\xa0#")
            initials = row.get("Initials")

            for rule in row_rules:
                if rule.should_run(row):
                    columns = rule.involved_columns()
                    values = collect_columns_values(row, columns)
                    is_failed = rule.is_failed(row)

                    check = ValidationCheckRow(
                        row_number=row_num,
                        screening_number=screening_number,
                        randomization_number=randomization_number,
                        initials=initials,
                        rule_id=rule.rule_id,
                        description=rule.description,
                        severity=rule.severity,
                        columns=columns,
                        condition_when=rule.when,
                        is_failed=is_failed,
                        values=values
                    )
                    checks.append(check)

                    if is_failed:
                        error = ValidationErrorRow(
                            row_number=row_num,
                            screening_number=screening_number,
                            randomization_number=randomization_number,
                            initials=initials,
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            error_message=rule.error_message,
                            description=rule.description,
                            columns=columns,
                            values=values
                        )
                        errors.append(error)

        # Checks for dataframe_rules
        for _, row in self.dataframe.iterrows():
            row_num = int(row.name) + 3
            screening_number = row.get("Screening #")
            randomization_number = row.get("Randomization #")
            if randomization_number is None:
                randomization_number = row.get("Randomization\xa0#")
            initials = row.get("Initials")

            for rule in dataframe_rules:
                if rule.should_run(row):
                    columns = rule.involved_columns()
                    values = collect_columns_values(row, columns)
                    is_failed = rule.is_failed(row)

                    check = ValidationCheckRow(
                        row_number=row_num,
                        screening_number=screening_number,
                        randomization_number=randomization_number,
                        initials=initials,
                        rule_id=rule.rule_id,
                        description=rule.description,
                        severity=rule.severity,
                        columns=columns,
                        condition_when=rule.when,
                        is_failed=is_failed,
                        values=values
                    )
                    checks.append(check)

        for rule in dataframe_rules:
            errors.extend(rule.validate_dataframe(self.dataframe))

        return errors, checks
