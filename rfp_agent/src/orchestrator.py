"""Orchestrator Agent: controls the workflow and calls tools in the required order.

 Setup -> Batch -> Evaluate (extract -> prompt/LLM -> validate) -> Score ->
 Benchmark/PPI/Rank -> Persist.   The LLM is only used inside `evaluate_supplier`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable

from . import db
from .document_tool import DocumentError, extract_pdf_text
from .llm import evaluate_supplier
from .ranking import TIE_BREAK_RULE, compute_run
from .validation import normalize_evaluation


def validate_inputs(documents: list[dict], criteria: list[dict]) -> list[str]:
    """Return blocking error messages (empty list = OK)."""
    errors = []
    if not criteria:
        errors.append("No active evaluation criteria. Activate at least one criterion.")
    if not documents:
        errors.append("Upload at least one supplier PDF.")
    seen = set()
    for d in documents:
        n = (d.get("supplier_name") or "").strip()
        label = d.get("filename", "?")
        if not n:
            errors.append(f"{label}: supplier name is required.")
        elif n.casefold() in seen:
            errors.append(f"Duplicate supplier name '{n}'.")
        seen.add(n.casefold())
        if not isinstance(d.get("submission_date"), date):
            errors.append(f"{label}: submission date is required.")
        try:
            r = float(d.get("experience_rating"))
            if not 0 <= r <= 10:
                errors.append(f"{label}: experience rating must be between 0 and 10.")
        except (TypeError, ValueError):
            errors.append(f"{label}: experience rating must be a number.")
    return errors


def run_evaluation(documents: list[dict], client, provider: str, model: str,
                   db_path=db.DEFAULT_DB, progress: Callable[[float, str], None] | None = None) -> dict:
    """documents: [{filename, data(bytes), supplier_name, submission_date(date), experience_rating}]"""
    trace: list[dict] = []
    warnings: list[str] = []

    def log(step: str, tool: str, detail: str):
        trace.append({"step": step, "tool": tool, "detail": detail})

    def tick(frac: float, msg: str):
        if progress:
            progress(frac, msg)

    # 1. Setup: reload the LATEST active criteria from SQLite
    criteria = db.get_criteria(db_path, active_only=True)
    errors = validate_inputs(documents, criteria)
    if errors:
        raise ValueError("; ".join(errors))
    log("Setup", "SQLite", f"Loaded {len(criteria)} active criteria: " + ", ".join(c["name"] for c in criteria))

    # 2. Batch
    run_id = db.create_run(criteria, provider, model, db_path)
    log("Batch", "SQLite", f"Created {run_id} with {len(documents)} supplier document(s).")

    try:
        evaluated = []
        n = len(documents)
        for i, doc in enumerate(documents):
            name = doc["supplier_name"].strip()
            sup_warn: list[str] = []
            tick(i / (n + 1), f"Evaluating {name} ({i + 1}/{n})")

            # 3. Document Tool
            extraction = {"pages": 0, "chars": 0, "truncated": False}
            text = None
            try:
                ex = extract_pdf_text(doc["data"])
                text, extraction = ex["text"], {k: ex[k] for k in ("pages", "chars", "truncated")}
                if ex["truncated"]:
                    sup_warn.append("Document text was truncated to fit the prompt size.")
                log("Evaluate", "Document Tool", f"{name}: {ex['pages']} page(s), {ex['chars']} chars extracted.")
            except DocumentError as exc:
                sup_warn.append(f"Text extraction failed: {exc}")
                log("Evaluate", "Document Tool", f"{name}: FAILED - {exc}")

            # 4. Evaluation Agent (LLM)
            raw = None
            if text is not None:
                raw, llm_warn = evaluate_supplier(client, criteria, name, text)
                sup_warn += llm_warn
                log("Evaluate", "Evaluation Agent (LLM)", f"{name}: {'JSON received' if raw else 'no usable output'}.")

            # 5. Validation Tool
            norm, vwarn = normalize_evaluation(raw, criteria)
            sup_warn += vwarn
            log("Validate", "Validation Tool", f"{name}: {len(vwarn)} normalisation warning(s).")
            if isinstance(raw, dict) and raw.get("supplier_name") and \
                    str(raw["supplier_name"]).strip().casefold() != name.casefold():
                sup_warn.append(f"LLM returned supplier_name '{raw['supplier_name']}'; entered name '{name}' used.")

            evaluated.append({
                "supplier_name": name, "source_file": doc["filename"],
                "submission_date": doc["submission_date"].isoformat(),
                "experience_rating": float(doc["experience_rating"]),
                "scores": norm["scores"], "risks": norm["risks"], "overall_summary": norm["overall_summary"],
                "warnings": sup_warn, "extraction": extraction,
            })
            warnings += [f"[{name}] {w}" for w in sup_warn]

        # 6-8. Score, Benchmark, PPI, Rank (deterministic)
        tick(n / (n + 1), "Scoring, benchmarking and ranking")
        ranked = compute_run(evaluated, criteria)
        warnings += ranked["warnings"]
        log("Rank", "Ranking Tool", f"Benchmarks computed; ranked by: {TIE_BREAK_RULE}")

        result = {
            "rfp_run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "COMPLETED", "provider": provider, "model": model,
            "criteria": criteria, "benchmarks": ranked["benchmarks"],
            "tie_break_rule": TIE_BREAK_RULE,
            "tie_break_explanations": ranked["tie_break_explanations"],
            "warnings": warnings,
            "leaderboard": [{"rank": s["final_rank"], "supplier_name": s["supplier_name"],
                             "absolute_score": s["absolute_score"], "ppi": s["ppi"],
                             "submission_date": s["submission_date"],
                             "experience_rating": s["experience_rating"]} for s in ranked["suppliers"]],
            "suppliers": ranked["suppliers"],
        }
        # 9. Persist
        log("Persist", "SQLite", f"Saved results under {run_id}.")
        result["agent_trace"] = trace
        db.save_run(result, db_path)
        tick(1.0, "Done")
        return result
    except Exception as exc:
        db.mark_run_failed(run_id, f"{type(exc).__name__}: {exc}", db_path)
        raise
