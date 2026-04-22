import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from .models import ValidationErrorRow


class ConfigLoader:
    @staticmethod
    def load_rules(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            payload = yaml.safe_load(file) or {}

        if isinstance(payload, list):
            return {"version": 1, "defaults": {}, "rules": payload}

        payload.setdefault("version", 1)
        payload.setdefault("defaults", {})
        payload.setdefault("rules", [])
        return payload


class DataReader:
    @staticmethod
    def read_table(input_path: Path, sheet: Optional[str], skip_rows: int = 0) -> pd.DataFrame:
        skip_data_rows = list(range(1, 1 + max(skip_rows, 0)))
        suffix = input_path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(input_path, header=0, skiprows=skip_data_rows)
        if suffix in {".xlsx", ".xlsm", ".xls"}:
            return pd.read_excel(
                input_path,
                sheet_name=sheet,
                header=0,
                skiprows=skip_data_rows,
            )
        raise ValueError("Unsupported input format. Use .xlsx/.xls/.xlsm or .csv")


class ReportWriter:
    @staticmethod
    def write_errors(errors: List[ValidationErrorRow], output_path: Path) -> None:
        rows = [
            {
                "Screening #": err.screening_number,
                "Randomization #": err.randomization_number,
                "Initials": err.initials,
                "row_number": err.row_number,
                "rule_id": err.rule_id,
                "severity": err.severity,
                "error_message": err.error_message,
                "values": json.dumps(err.values, ensure_ascii=False, default=str),
            }
            for err in errors
        ]

        output_df = pd.DataFrame(rows)
        suffix = output_path.suffix.lower()
        if suffix == ".csv":
            output_df.to_csv(output_path, index=False, encoding="utf-8-sig")
            return
        output_df.to_excel(output_path, index=False)
