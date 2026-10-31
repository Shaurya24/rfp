"""Agentic RFP Evaluation & Supplier Ranking - Streamlit UI."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from src import db, llm
from src.document_tool import DocumentError, extract_pdf_text
from src.orchestrator import run_evaluation, validate_inputs

ROOT = Path(__file__).parent
SAMPLE_DIR = ROOT / "sample_rfps"
SAMPLE_META = {  # name, submission date, experience rating (0-10)
    "Apex_Systems_RFP.pdf": ("Apex Systems", date(2026, 3, 2), 8.0),
    "BrightPath_Tech_RFP.pdf": ("BrightPath Tech", date(2026, 3, 4), 5.5),
    "NexaWorks_RFP.pdf": ("NexaWorks", date(2026, 3, 3), 7.5),
    "Orbit_Digital_RFP.pdf": ("Orbit Digital", date(2026, 3, 1), 9.0),
}

st.set_page_config(page_title="Agentic RFP Evaluation", page_icon="📑", layout="wide")


@st.cache_resource
def _init():
    db.init_db()
    return True


@st.cache_data(show_spinner=False)
def _preview(data_hash: str, data: bytes):
    """Cached extraction used for upfront validation messages."""
    try:
        ex = extract_pdf_text(data)
        return {"ok": True, "pages": ex["pages"], "chars": ex["chars"], "msg": ""}
    except DocumentError as exc:
        return {"ok": False, "pages": 0, "chars": 0, "msg": str(exc)}


def _secret(name: str):
    try:
        return st.secrets.get(name) or os.environ.get(name)
    except Exception:
        return os.environ.get(name)


def _guess_name(filename: str) -> str:
    stem = re.sub(r"(?i)[_\- ]*rfp[_\- ]*(response)?$", "", Path(filename).stem)
    return stem.replace("_", " ").strip().title()


_init()
if "_goto" in st.session_state:                    # allows programmatic page switch
    st.session_state["page"] = st.session_state.pop("_goto")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("📑 Agentic RFP Evaluator")
    page = st.radio("Navigate", ["1 · Criteria", "2 · Supplier input", "3 · Results"], key="page")
    st.divider()
    st.subheader("AI layer")
    default_provider = llm.ANTHROPIC if _secret("ANTHROPIC_API_KEY") else llm.DEMO
    provider = st.selectbox("Provider", llm.PROVIDERS, index=llm.PROVIDERS.index(default_provider))
    model = st.text_input("Model", value=llm.DEFAULT_MODELS[provider], key=f"model_{provider}",
                          disabled=provider == llm.DEMO)
    api_key = None
    if provider != llm.DEMO:
        key_name = "ANTHROPIC_API_KEY" if provider == llm.ANTHROPIC else "OPENAI_API_KEY"
        api_key = _secret(key_name)
        if api_key:
            st.caption(f"✅ {key_name} found in secrets/environment.")
        else:
            api_key = st.text_input(f"{key_name}", type="password",
                                    help="Kept in memory for this session only.")
    else:
        st.caption("⚠️ Demo mode uses a deterministic keyword heuristic - **not an LLM**. "
                   "Select a provider and add an API key for real evidence-grounded scoring.")

# ------------------------------------------------------------------- page 1
if page.startswith("1"):
    st.header("Evaluation criteria")
    st.caption("Loaded from SQLite (`evaluation_criteria`). Changes apply to the next evaluation run - no code changes needed.")
    all_c = db.get_criteria(active_only=False)
    active = [c for c in all_c if c["is_active"]]
    total = sum(c["weight"] for c in active)
    c1, c2, c3 = st.columns(3)
    c1.metric("Active criteria", len(active))
    c2.metric("Total active weight", f"{total:g}%")
    c3.metric("Weights valid", "✅ 100%" if abs(total - 100) < 0.01 else "⚠️ not 100%")
    if abs(total - 100) >= 0.01:
        st.warning("Active weights should total 100%. If you proceed they will be re-normalised to 100% (and a warning recorded).")
    st.dataframe(pd.DataFrame(active)[["criterion_id", "name", "description", "weight", "max_score"]]
                 if active else pd.DataFrame(), use_container_width=True, hide_index=True)

    with st.expander("✏️ Edit criteria / weights / activation"):
        df = pd.DataFrame(all_c)
        edited = st.data_editor(
            df, hide_index=True, use_container_width=True, key="crit_editor",
            disabled=["criterion_id"],
            column_config={"weight": st.column_config.NumberColumn("weight (%)", min_value=0, max_value=100, step=1),
                           "max_score": st.column_config.NumberColumn(min_value=1, max_value=100),
                           "is_active": st.column_config.CheckboxColumn("active")})
        if st.button("Save criteria", type="primary"):
            bad = edited[(edited["name"].fillna("").str.strip() == "") | edited["weight"].isna() | edited["max_score"].isna()]
            if len(bad):
                st.error("Every criterion needs a name, weight and max score.")
            else:
                db.update_criteria(edited.to_dict("records"))
                st.success("Saved.")
                st.rerun()

# ------------------------------------------------------------------- page 2
elif page.startswith("2"):
    st.header("Supplier input")
    criteria = db.get_criteria()
    st.caption(f"Will evaluate against {len(criteria)} active criteria: " +
               (", ".join(c["name"] for c in criteria) or "none"))

    uploads = st.file_uploader("Upload supplier RFP responses (PDF)", type=["pdf"], accept_multiple_files=True)
    use_samples = st.checkbox("Also include the 4 bundled synthetic sample RFPs", value=not uploads)
    use_blank = st.checkbox("…and the blank/scanned edge-case PDF (to see validation)", value=False,
                            disabled=not use_samples)

    sources = []   # (key, filename, bytes, default name, default date, default rating)
    for f in uploads or []:
        data = f.getvalue()
        sources.append((hashlib.md5(data).hexdigest()[:10], f.name, data, _guess_name(f.name), date.today(), 5.0))
    if use_samples:
        for fn, (n, d, r) in SAMPLE_META.items():
            data = (SAMPLE_DIR / fn).read_bytes()
            sources.append(("s_" + fn, fn, data, n, d, r))
        if use_blank:
            data = (SAMPLE_DIR / "EDGE_blank_scanned_RFP.pdf").read_bytes()
            sources.append(("s_blank", "EDGE_blank_scanned_RFP.pdf", data, "Blank Scan Co", date(2026, 3, 5), 5.0))

    docs, file_errors = [], []
    if sources:
        st.subheader("Supplier metadata")
        hdr = st.columns([2.2, 2, 1.6, 1.4, 1.6])
        for h, t in zip(hdr, ["File", "Supplier name", "Submission date", "Experience (0-10)", "PDF check"]):
            h.markdown(f"**{t}**")
    for key, fname, data, dname, ddate, drating in sources:
        cols = st.columns([2.2, 2, 1.6, 1.4, 1.6])
        cols[0].write(fname)
        name = cols[1].text_input("name", value=dname, key=f"n_{key}", label_visibility="collapsed")
        sdate = cols[2].date_input("date", value=ddate, key=f"d_{key}", label_visibility="collapsed")
        rating = cols[3].number_input("rating", 0.0, 10.0, float(drating), 0.5, key=f"r_{key}",
                                      label_visibility="collapsed")
        prev = _preview(hashlib.md5(data).hexdigest(), data)
        if prev["ok"]:
            cols[4].success(f"{prev['pages']} pp · {prev['chars']:,} chars")
        else:
            cols[4].error("Unreadable")
            file_errors.append(f"{fname}: {prev['msg']} Remove this file or upload a text-based PDF.")
        docs.append({"filename": fname, "data": data, "supplier_name": name,
                     "submission_date": sdate, "experience_rating": rating})

    errors = validate_inputs(docs, criteria) if (docs or True) else []
    if provider != llm.DEMO and not api_key:
        errors.append(f"Enter an API key for {provider} (or switch to Demo mode).")
    errors = file_errors + errors
    for e in errors:
        st.error(e)
    total = sum(c["weight"] for c in criteria)
    if criteria and abs(total - 100) >= 0.01:
        st.warning(f"Active weights total {total:g}%; they will be re-normalised to 100%.")

    if st.button("🚀 Evaluate suppliers", type="primary", disabled=bool(errors)):
        bar = st.progress(0.0, text="Starting…")
        try:
            client = llm.make_client(provider, api_key, model)
            result = run_evaluation(docs, client, provider, model,
                                    progress=lambda f, m: bar.progress(min(f, 1.0), text=m))
            st.session_state["run_id"] = result["rfp_run_id"]
            st.session_state["_goto"] = "3 · Results"
            st.rerun()
        except Exception as exc:
            bar.empty()
            st.error(f"Evaluation failed: {exc}")

# ------------------------------------------------------------------- page 3
else:
    st.header("Results")
    runs = db.list_runs()
    if not runs:
        st.info("No completed runs yet. Go to **2 · Supplier input** and click *Evaluate suppliers*.")
        st.stop()
    completed = [r for r in runs if r["status"] == "COMPLETED"]
    if not completed:
        st.warning("No completed runs yet - the latest run failed. See Run details after a successful run.")
        st.stop()
    ids = [r["rfp_run_id"] for r in completed]
    default = ids.index(st.session_state["run_id"]) if st.session_state.get("run_id") in ids else 0
    run_id = st.selectbox("Run", ids, index=default,
                          format_func=lambda i: f"{i}  ·  {next(r for r in completed if r['rfp_run_id']==i)['provider']}")
    run = db.get_run(run_id)
    t_lead, t_card, t_matrix, t_run = st.tabs(["🏆 Leaderboard", "🔍 Detailed scorecard",
                                                "📊 Comparison matrix", "🧾 Run details"])

    with t_lead:
        lb = pd.DataFrame(run["leaderboard"]).rename(columns={
            "rank": "Rank", "supplier_name": "Supplier", "absolute_score": "Absolute score (/100)",
            "ppi": "PPI", "submission_date": "Submission date", "experience_rating": "Experience rating"})
        st.dataframe(lb, use_container_width=True, hide_index=True)
        winner = run["leaderboard"][0]
        st.success(f"**{winner['supplier_name']}** ranks #1 with PPI {winner['ppi']:.2f} "
                   f"(absolute score {winner['absolute_score']:.2f}).")
        st.bar_chart(lb.set_index("Supplier")[["Absolute score (/100)", "PPI"]])
        st.markdown("**Why this order?**  \nTie-break rule: " + run["tie_break_rule"])
        for line in run["tie_break_explanations"]:
            st.markdown(f"- {line}")

    with t_card:
        names = [s["supplier_name"] for s in run["suppliers"]]
        pick = st.selectbox("Supplier", names)
        s = next(x for x in run["suppliers"] if x["supplier_name"] == pick)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Final rank", f"#{s['final_rank']}")
        m2.metric("Absolute score", f"{s['absolute_score']:.2f}")
        m3.metric("PPI", f"{s['ppi']:.2f}")
        m4.metric("Submitted / experience", f"{s['submission_date']} / {s['experience_rating']:g}")
        if s["tie_break_note"]:
            st.info(s["tie_break_note"])
        rows = pd.DataFrame(s["criteria"])
        view = rows[["criterion", "weight", "score", "max_score", "benchmark", "gap", "relative_pct",
                     "weighted_points", "ppi_points", "status"]].rename(columns={
            "criterion": "Criterion", "weight": "Weight %", "score": "Score", "max_score": "Max",
            "benchmark": "Benchmark", "gap": "Gap", "relative_pct": "Relative %",
            "weighted_points": "Weighted pts", "ppi_points": "PPI pts", "status": "Status"})
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.caption("Weighted pts = score / max × weight.  Gap = score − benchmark.  Relative % = score / benchmark × 100.  "
                   "PPI pts = relative % × weight.")
        st.subheader("Justification and evidence")
        for r in s["criteria"]:
            with st.expander(f"{r['criterion']} — {r['score']:g}/{r['max_score']:g}"):
                st.markdown(f"**Justification:** {r['justification'] or '—'}")
                st.markdown(f"**Evidence:** {('> ' + r['evidence']) if r['evidence'] else '_none cited_'}")
        if s["risks"]:
            st.subheader("Risks identified")
            for rk in s["risks"]:
                st.markdown(f"- {rk}")
        if s["overall_summary"]:
            st.markdown(f"**Summary:** {s['overall_summary']}")
        if s["warnings"]:
            with st.expander(f"⚠️ {len(s['warnings'])} warning(s) for this supplier"):
                for w in s["warnings"]:
                    st.markdown(f"- {w}")

    with t_matrix:
        st.caption("Raw criterion scores (benchmark = best valid score per criterion).")
        mat = {s["supplier_name"]: {r["criterion"]: r["score"] for r in s["criteria"]} for s in run["suppliers"]}
        df = pd.DataFrame(mat)
        df["Benchmark"] = [next(r["benchmark"] for r in run["suppliers"][0]["criteria"] if r["criterion"] == i) for i in df.index]
        st.dataframe(df, use_container_width=True)
        rel = {s["supplier_name"]: {r["criterion"]: r["relative_pct"] for r in s["criteria"]} for s in run["suppliers"]}
        st.caption("Relative performance % vs benchmark")
        st.dataframe(pd.DataFrame(rel).round(1), use_container_width=True)

    with t_run:
        st.markdown(f"**RFP_RUN_ID:** `{run['rfp_run_id']}`")
        st.markdown(f"**Created:** {run['created_at']}  ·  **Status:** {run['status']}  ·  "
                    f"**AI layer:** {run['provider']} / {run['model']}")
        st.markdown("**Criteria snapshot used**")
        st.dataframe(pd.DataFrame(run["criteria"])[["criterion_id", "name", "weight", "max_score"]],
                     use_container_width=True, hide_index=True)
        st.markdown(f"**Warnings ({len(run['warnings'])})**")
        if run["warnings"]:
            for w in run["warnings"]:
                st.markdown(f"- ⚠️ {w}")
        else:
            st.caption("None.")
        st.markdown("**Tie-break rule**  \n" + run["tie_break_rule"])
        for line in run["tie_break_explanations"]:
            st.markdown(f"- {line}")
        with st.expander("Agent trace (orchestrator steps)"):
            st.dataframe(pd.DataFrame(run.get("agent_trace", [])), use_container_width=True, hide_index=True)
        st.download_button("⬇️ Download complete result (JSON)", data=json.dumps(run, indent=2),
                           file_name=f"{run['rfp_run_id']}.json", mime="application/json", type="primary")
