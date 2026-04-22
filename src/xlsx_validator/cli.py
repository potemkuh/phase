import argparse
from pathlib import Path
from typing import Optional

from .engine import ValidationEngine
from .factory import RuleFactory
from .io import ConfigLoader, DataReader, ReportWriter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate XLSX/CSV by YAML rules.")
    parser.add_argument("--input", required=True, help="Path to source data file (.xlsx/.csv)")
    parser.add_argument("--rules", required=True, help="Path to rules YAML file")
    parser.add_argument(
        "--output",
        default="errors.xlsx",
        help="Path to output report (.xlsx/.csv), default: errors.xlsx",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Excel sheet name or index (optional, default first sheet)",
    )
    parser.add_argument(
        "--skip-rows",
        type=int,
        default=1,
        help="Number of rows to skip after header row (default: 1, validation starts from row 3)",
    )
    return parser.parse_args()


def run_validation(
    input_path: Path,
    rules_path: Path,
    output_path: Path,
    sheet: Optional[str] = None,
    skip_rows: int = 0,
) -> int:
    data = DataReader.read_table(input_path=input_path, sheet=sheet, skip_rows=skip_rows)
    config = ConfigLoader.load_rules(path=rules_path)
    defaults = config.get("defaults", {}) or {}
    rules_payload = config.get("rules", []) or []
    rules = RuleFactory.create_rules(rules_payload=rules_payload, defaults=defaults)

    engine = ValidationEngine(dataframe=data, rules=rules)
    errors = engine.run()
    ReportWriter.write_errors(errors=errors, output_path=output_path)

    print(f"Rows checked: {len(data)}")
    print(f"Errors found: {len(errors)}")
    print(f"Report saved: {output_path}")
    return 0


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    rules_path = Path(args.rules)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return 2
    if not rules_path.exists():
        print(f"Rules file not found: {rules_path}")
        return 2

    try:
        return run_validation(
            input_path=input_path,
            rules_path=rules_path,
            output_path=output_path,
            sheet=args.sheet,
            skip_rows=args.skip_rows,
        )
    except Exception as exc:
        print(f"Validation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
