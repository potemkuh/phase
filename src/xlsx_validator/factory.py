from typing import Any, Dict, List, Type

from .rules import (
    DateBetweenRule,
    DateEqualAnyRule,
    DateEqualRule,
    EmptyRule,
    EmptyIfRule,
    NotEmptyRule,
    TextStartsWithRule,
    TextStartsWithManyRule,
    NumberBetweenRule,
    NumberLessOrEqualRule,
    NumberLessThanRule,
    NumberGreaterThanRule,
    RequiredIfRule,
    Rule,
    TimeBetweenRule,
    TimeGreaterOrEqualRule,
    UniqueIfRule,
    ValueInIfRule,
    ValueInManyRule,
    ValueInRule,
)


class RuleFactory:
    _registry: Dict[str, Type[Rule]] = {
        ValueInRule.rule_type: ValueInRule,
        ValueInIfRule.rule_type: ValueInIfRule,
        ValueInManyRule.rule_type: ValueInManyRule,
        RequiredIfRule.rule_type: RequiredIfRule,
        EmptyRule.rule_type: EmptyRule,
        EmptyIfRule.rule_type: EmptyIfRule,
        NotEmptyRule.rule_type: NotEmptyRule,
        TextStartsWithRule.rule_type: TextStartsWithRule,
        TextStartsWithManyRule.rule_type: TextStartsWithManyRule,
        NumberGreaterThanRule.rule_type: NumberGreaterThanRule,
        NumberLessThanRule.rule_type: NumberLessThanRule,
        NumberLessOrEqualRule.rule_type: NumberLessOrEqualRule,
        NumberBetweenRule.rule_type: NumberBetweenRule,
        DateEqualRule.rule_type: DateEqualRule,
        DateEqualAnyRule.rule_type: DateEqualAnyRule,
        DateBetweenRule.rule_type: DateBetweenRule,
        TimeBetweenRule.rule_type: TimeBetweenRule,
        TimeGreaterOrEqualRule.rule_type: TimeGreaterOrEqualRule,
        UniqueIfRule.rule_type: UniqueIfRule,
    }

    @classmethod
    def create_rules(cls, rules_payload: List[Dict[str, Any]], defaults: Dict[str, Any]) -> List[Rule]:
        created: List[Rule] = []
        for payload in rules_payload:
            rule_type = (payload.get("type") or "").strip()
            if rule_type not in cls._registry:
                raise ValueError(f"Unsupported rule type in config: {rule_type}")
            rule_class = cls._registry[rule_type]
            created.append(rule_class(payload=payload, defaults=defaults))
        return created
