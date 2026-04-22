from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ValidationErrorRow:
    row_number: int
    screening_number: Optional[Any]
    randomization_number: Optional[Any]
    initials: Optional[Any]
    rule_id: str
    severity: str
    error_message: str
    description: str
    columns: List[str]
    values: Dict[str, Any]
