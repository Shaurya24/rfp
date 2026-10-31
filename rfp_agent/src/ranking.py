"""Ranking Tool: all arithmetic, benchmarking, PPI, tie-breaks. Pure Python, deterministic.

The LLM never touches anything in this module.
"""
from __future__ import annotations

TIE_BREAK_RULE = (
    "1) Higher PPI  ->  2) Earlier submission date  ->  "
    "3) Higher historical experience rating  ->  4) Supplier name (A-Z)"
)
PPI_PRECISION = 6   # PPI compared after rounding, so float noise cannot change order


def effective_weights(criteria: list[dict]) -> tuple[dict[int, float], list[str]]:
    """Weights as percentages summing to 100 (re-normalised, with a warning, if they don't)."""
    total = sum(float(c["weight"]) for c in criteria)
    if total <= 0:
        raise ValueError("Active criteria weights sum to zero.")
    warnings = []
    if abs(total - 100.0) > 0.01:
        warnings.append(f"Active weights total {total:g}%, not 100%; weights were re-normalised to 100%.")
    return {c["criterion_id"]: float(c["weight"]) / total * 100.0 for c in criteria}, warnings


def _sort_key(card: dict):
    return (-round(card["ppi"], PPI_PRECISION), card["submission_date"],
            -float(card["experience_rating"]), card["supplier_name"].casefold())


def _explain_pair(a: dict, b: dict) -> tuple[str, int]:
    """Why a is ranked directly above b. Returns (text, deciding rule number)."""
    if round(a["ppi"], PPI_PRECISION) != round(b["ppi"], PPI_PRECISION):
        return f"{a['supplier_name']} > {b['supplier_name']}: higher PPI ({a['ppi']:.2f} vs {b['ppi']:.2f}).", 1
    base = f"PPI tied at {a['ppi']:.2f}; "
    if a["submission_date"] != b["submission_date"]:
        return (base + f"{a['supplier_name']} > {b['supplier_name']}: earlier submission "
                f"({a['submission_date']} vs {b['submission_date']}).", 2)
    if float(a["experience_rating"]) != float(b["experience_rating"]):
        return (base + f"same date; {a['supplier_name']} > {b['supplier_name']}: higher experience rating "
                f"({a['experience_rating']:g} vs {b['experience_rating']:g}).", 3)
    return (base + f"same date and experience; {a['supplier_name']} > {b['supplier_name']}: "
            f"name ascending.", 4)


def compute_run(suppliers: list[dict], criteria: list[dict]) -> dict:
    """
    suppliers: [{supplier_name, submission_date (ISO), experience_rating,
                 scores: {criterion_id: {score, valid, ...}}, ...}]
    Returns {suppliers (ranked, scorecards), benchmarks, tie_break_explanations, warnings}.
    """
    w_eff, warnings = effective_weights(criteria)

    # Step 1 - criterion benchmark = highest VALID score across suppliers
    benchmarks: dict[int, float] = {}
    for c in criteria:
        cid = c["criterion_id"]
        valid = [s["scores"][cid]["score"] for s in suppliers if s["scores"][cid]["valid"]]
        benchmarks[cid] = max(valid) if valid else 0.0

    cards = []
    for s in suppliers:
        rows, absolute, ppi = [], 0.0, 0.0
        for c in criteria:
            cid, mx, w = c["criterion_id"], float(c["max_score"]), w_eff[c["criterion_id"]]
            r = s["scores"][cid]
            score, bench = float(r["score"]), benchmarks[cid]
            weighted_points = score / mx * w                      # absolute weighted score part
            gap = score - bench                                   # 0 for leader, else negative
            rel = min(score / bench * 100.0, 100.0) if bench > 0 else 100.0   # zero benchmark -> 100
            ppi_part = rel * w / 100.0
            absolute += weighted_points
            ppi += ppi_part
            rows.append({
                "criterion_id": cid, "criterion": c["name"], "weight": round(w, 4),
                "max_score": mx, "score": score, "benchmark": bench, "gap": round(gap, 4),
                "relative_pct": round(rel, 4), "weighted_points": round(weighted_points, 4),
                "ppi_points": round(ppi_part, 4), "status": r["status"],
                "justification": r["justification"], "evidence": r["evidence"],
            })
        cards.append({**{k: v for k, v in s.items() if k != "scores"},
                      "absolute_score": round(absolute, 4), "ppi": round(ppi, 4), "criteria": rows})

    # Step 2 - stable deterministic sort, THEN sequential ranks
    cards.sort(key=_sort_key)
    explanations = []
    for i, card in enumerate(cards, start=1):
        card["final_rank"] = i
        card["tie_break_note"] = ""
    for a, b in zip(cards, cards[1:]):
        text, rule = _explain_pair(a, b)
        explanations.append(text)
        if rule > 1:
            a["tie_break_note"] = b["tie_break_note"] = f"Tie-break rule {rule} applied vs adjacent supplier."
    return {"suppliers": cards, "benchmarks": benchmarks,
            "tie_break_explanations": explanations, "warnings": warnings}
