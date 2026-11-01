"""Validation Tool: parse/validate/normalise the LLM scorecard (deterministic).

Guarantees that downstream scoring always receives exactly one numeric result
per ACTIVE criterion, with scores clipped into [0, max_score].
"""
from __future__ import annotations

import math
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError


class LLMCriterionResult(BaseModel):
    """Lenient schema: types are coerced by our own code so we can warn precisely."""
    model_config = ConfigDict(extra="ignore")
    criterion_id: Any = None
    criterion_name: Any = None
    score: Any = None
    max_score: Any = None
    justification: Any = ""
    evidence: Any = ""


def _text(value: Any, limit: int = 1500) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " | ".join(str(v) for v in value)
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def _coerce_score(value: Any, max_score: float) -> tuple[float, str, str | None]:
    """Return (score, status, warning). status: ok | clipped | invalid."""
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        return 0.0, "invalid", "score missing"
    if isinstance(value, str):
        m = re.search(r"-?\d+(?:\.\d+)?", value)
        if not m:
            return 0.0, "invalid", f"score {value!r} is not numeric"
        value = float(m.group())
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0, "invalid", f"score {value!r} is not numeric"
    if math.isnan(num) or math.isinf(num):
        return 0.0, "invalid", "score is NaN/infinite"
    if num < 0:
        return 0.0, "clipped", f"score {num:g} below 0, clipped to 0"
    if num > max_score:
        return float(max_score), "clipped", f"score {num:g} above max {max_score:g}, clipped"
    return round(num, 2), "ok", None


def _match_criterion(item: LLMCriterionResult, by_id: dict, by_name: dict):
    try:
        cid = int(float(item.criterion_id))
        if cid in by_id:
            return by_id[cid]
    except (TypeError, ValueError):
        pass
    if item.criterion_name:
        return by_name.get(str(item.criterion_name).strip().casefold())
    return None


def normalize_evaluation(raw: Any, criteria: list[dict]) -> tuple[dict, list[str]]:
    """Return (normalised, warnings). Never raises on bad LLM output."""
    warnings: list[str] = []
    by_id = {c["criterion_id"]: c for c in criteria}
    by_name = {c["name"].strip().casefold(): c for c in criteria}

    if not isinstance(raw, dict):
        warnings.append("LLM output was not a JSON object; all criteria scored 0.")
        raw = {}
    items = raw.get("criteria")
    if not isinstance(items, list):
        if raw:
            warnings.append("LLM output has no 'criteria' list; all criteria scored 0.")
        items = []

    found: dict[int, dict] = {}
    for idx, item in enumerate(items):
        try:
            res = LLMCriterionResult.model_validate(item)
        except ValidationError:
            warnings.append(f"criteria[{idx}] is malformed and was ignored.")
            continue
        crit = _match_criterion(res, by_id, by_name)
        if crit is None:
            warnings.append(f"criteria[{idx}] refers to unknown criterion "
                            f"({res.criterion_id!r}/{res.criterion_name!r}); ignored.")
            continue
        cid = crit["criterion_id"]
        if cid in found:
            warnings.append(f"Duplicate result for '{crit['name']}'; first one kept.")
            continue
        score, status, warn = _coerce_score(res.score, crit["max_score"])
        if warn:
            warnings.append(f"{crit['name']}: {warn}.")
        evidence = _text(res.evidence)
        if status != "invalid" and score > 0 and not evidence:
            warnings.append(f"{crit['name']}: score given without supporting evidence.")
        found[cid] = {"score": score, "valid": status != "invalid", "status": status,
                      "justification": _text(res.justification), "evidence": evidence}

    results = {}
    for c in criteria:
        cid = c["criterion_id"]
        if cid in found:
            results[cid] = found[cid]
        else:
            warnings.append(f"{c['name']}: no result returned; scored 0.")
            results[cid] = {"score": 0.0, "valid": False, "status": "missing",
                            "justification": "No result returned by the evaluator.", "evidence": ""}

    risks = raw.get("risks", [])
    if isinstance(risks, str):
        risks = [risks]
    elif not isinstance(risks, list):
        risks = []
    return {
        "scores": results,
        "risks": [_text(r, 400) for r in risks if _text(r)],
        "overall_summary": _text(raw.get("overall_summary"), 1500),
    }, warnings
