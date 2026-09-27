"""Analysis-driven style rules (MViser#4): ChordSpec facts -> style overrides.

Pure functions; compiled once per chord event, read by scene resolution.
"""

from __future__ import annotations

from typing import Any

from .harmony import ChordSpec
from .motion import PRESETS

RULE_FIELDS = ("quality", "function", "roman", "diatonic", "microtonal", "notation", "root")
RULE_SETTINGS = ("background_color", "text_color", "motion", "pulse")


class StyleRuleError(ValueError):
    pass


def chord_facts(spec: ChordSpec) -> dict[str, Any]:
    a = spec.analysis
    return {
        "quality": spec.quality or a.get("identified", {}).get("quality"),
        "function": a.get("function"),
        "roman": a.get("roman"),
        "diatonic": a.get("diatonic"),
        "microtonal": a.get("microtonal", not spec.is_12tet),
        "notation": spec.source.get("notation"),
        "root": spec.root_name,
    }


def validate_rules(rules: Any, check_color) -> list[dict[str, Any]]:
    if rules is None:
        return []
    if not isinstance(rules, list):
        raise StyleRuleError("style.rules must be a list")
    out = []
    for i, rule in enumerate(rules):
        where = f"style.rules[{i}]"
        if not isinstance(rule, dict) or not isinstance(rule.get("when"), dict) or not isinstance(rule.get("set"), dict):
            raise StyleRuleError(f"{where}: needs 'when' and 'set' mappings")
        for field in rule["when"]:
            if field not in RULE_FIELDS:
                raise StyleRuleError(f"{where}.when.{field}: unknown field (allowed: {RULE_FIELDS})")
        settings = dict(rule["set"])
        for key, value in settings.items():
            if key not in RULE_SETTINGS:
                raise StyleRuleError(f"{where}.set.{key}: unknown setting (allowed: {RULE_SETTINGS})")
            if key.endswith("_color"):
                settings[key] = check_color(value, f"{where}.set.{key}")
            elif key == "motion" and value not in PRESETS:
                raise StyleRuleError(f"{where}.set.motion: must be one of {PRESETS}")
            elif key == "pulse" and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                raise StyleRuleError(f"{where}.set.pulse: must be a non-negative number")
        out.append({"when": dict(rule["when"]), "set": settings})
    return out


def _matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches(e, actual) for e in expected)
    return expected == actual


def match_rules(spec: ChordSpec, rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Settings of the first rule whose every `when` field matches; {} if none."""
    facts = chord_facts(spec)
    for rule in rules:
        if all(_matches(v, facts[k]) for k, v in rule["when"].items()):
            return dict(rule["set"])
    return {}
