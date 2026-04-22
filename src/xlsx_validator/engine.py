from typing import List

import pandas as pd

from .models import ValidationErrorRow
from .rules import Rule


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

    def run(self) -> List[ValidationErrorRow]:
        self.validate_schema()
        errors: List[ValidationErrorRow] = []
        row_rules = [rule for rule in self.rules if rule.uses_row_validation()]
        dataframe_rules = [rule for rule in self.rules if not rule.uses_row_validation()]

        for _, row in self.dataframe.iterrows():
            for rule in row_rules:
                error = rule.validate(row)
                if error is not None:
                    errors.append(error)

        for rule in dataframe_rules:
            errors.extend(rule.validate_dataframe(self.dataframe))
        return errors
