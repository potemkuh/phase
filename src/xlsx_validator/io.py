import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from .models import ValidationCheckRow, ValidationErrorRow
from .rules import Rule


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
    def write_report(errors: List[ValidationErrorRow], checks: List[ValidationCheckRow], output_path: Path) -> None:
        # Errors sheet data
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

        errors_df = pd.DataFrame(rows)
        suffix = output_path.suffix.lower()
        if suffix == ".csv":
            errors_df.to_csv(output_path, index=False, encoding="utf-8-sig")
            return

        # Report sheet data from checks
        report_rows = []
        for check in checks:
            target_column = check.columns[0] if check.columns else ""
            status = "Ошибка" if check.is_failed else "OK"
            report_rows.append({
                "Screening #": check.screening_number,
                "Randomization #": check.randomization_number,
                "Initials": check.initials,
                "Row Number": check.row_number,
                "Rule ID": check.rule_id,
                "Column": target_column,
                "Status": status
            })

        report_df = pd.DataFrame(report_rows)

        # Write to Excel with two sheets
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Report sheet: headers row 1, descriptions row 2, data row 3+
            report_df.to_excel(writer, sheet_name="report", index=False, header=False, startrow=2)
            worksheet_report = writer.sheets['report']
            
            headers = ["Screening #", "Randomization #", "Initials", "Row Number", "Rule ID", "Column", "Status"]
            descriptions = ["Номер скрининга", "Номер рандомизации", "Инициалы", "Номер строки", "ID правила", "Колонка", "Статус"]
            
            for col_num, header in enumerate(headers, 1):
                worksheet_report.cell(row=1, column=col_num, value=header)
            for col_num, desc in enumerate(descriptions, 1):
                worksheet_report.cell(row=2, column=col_num, value=desc)
            
            # Errors sheet
            errors_df.to_excel(writer, sheet_name="errors", index=False)
