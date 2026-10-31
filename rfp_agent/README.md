# Agentic RFP Evaluation & Supplier Ranking

An AI-assisted Streamlit app that reads supplier RFP PDFs, scores each against configurable
criteria with an LLM, then ranks suppliers with **transparent, deterministic Python**
(weighted score, peer benchmark, Peer Performance Index, tie-breaks). Results persist in SQLite.

> **Design rule:** the LLM only judges proposal *content*. Arithmetic, benchmarks, tie-breaks and ranks
> are never done by the LLM.

## Quick start (local)
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts/generate_sample_pdfs.py                # optional: regenerate sample PDFs
python scripts/seed_db.py                             # optional: app also auto-seeds on start
streamlit run app.py
pytest -q                                             # 17 unit / end-to-end tests
```
No API key? Pick **Demo (offline heuristic)** in the sidebar - a keyword scorer, *not* an LLM.
For real scoring set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) in `.streamlit/secrets.toml`
(see `secrets.toml.example`) or paste it in the sidebar.

## Deploy on Streamlit Community Cloud
1. Push this folder to a **public GitHub repo** (the `sample_rfps/` PDFs must be committed).
2. Go to <https://share.streamlit.io> -> **New app** -> pick the repo, branch `main`, main file `app.py`.
3. **Advanced settings -> Secrets**: add `ANTHROPIC_API_KEY = "sk-ant-..."`. (Python 3.12 recommended.)
4. Deploy, open the URL, and submit it. The DB is auto-created and seeded on first load.
   Note: Cloud storage is ephemeral - run history resets on reboot; download the JSON to keep results.

## Architecture
```
Streamlit UI (app.py)
   |  documents + metadata
   v
Orchestrator Agent (src/orchestrator.py)  --- controls order, logs an agent trace
   1 Setup    -> SQLite: load ACTIVE criteria (reloaded at every run)
   2 Batch    -> SQLite: create RFP_RUN_ID
   3 Evaluate -> Document Tool (pypdf) -> Evaluation Agent (LLM, JSON) -> Validation Tool
   4 Score / Benchmark / PPI / Rank -> Ranking Tool (deterministic Python)
   5 Persist  -> SQLite: rfp_runs + supplier_results (one transaction)
```
| Component | File | LLM? |
|---|---|---|
| Orchestrator | `src/orchestrator.py` | no |
| Document Tool | `src/document_tool.py` | no |
| Evaluation Agent | `src/llm.py` | **yes** (Claude / OpenAI / demo) |
| Validation Tool | `src/validation.py` (Pydantic + custom) | no |
| Ranking Tool | `src/ranking.py` | no |
| Persistence | `src/db.py` | no |

## Formulas
Let `w_i` = criterion weight re-normalised to total 100, `s_i` = validated score, `max_i` = max score,
`B_i` = benchmark = highest **valid** score for criterion *i* across all suppliers in the run.

| Metric | Formula |
|---|---|
| Absolute weighted score | `sum( s_i / max_i * w_i )` (0-100) |
| Criterion gap | `s_i - B_i` (0 for the leader, otherwise negative) |
| Relative performance % | `s_i / B_i * 100` (if `B_i = 0` -> **100**, nobody outperforms anybody) |
| Peer Performance Index (PPI) | `sum( relative_i * w_i ) / 100` |

**Tie-break (stable sort, then ranks 1..n):** higher PPI -> earlier submission date -> higher experience
rating -> supplier name A-Z. PPI is compared after rounding to 6 dp so float noise cannot change order.
The UI explains each adjacent pair ("PPI tied at 80.00; earlier submission ...").

## Validation & normalisation (never trusts the LLM)
- Invalid / truncated JSON -> tolerant parser, one automatic retry with a corrective instruction.
- Missing criterion -> score 0, flagged `missing`, warning recorded (excluded from benchmark candidates).
- Non-numeric score (`"7/10"` -> 7, `"n/a"` -> invalid) / NaN / null -> handled with warnings.
- Out-of-range score -> **clipped** to `[0, max]`; unknown, duplicate or malformed criteria ignored.
- Max score always comes from the DB, not from the LLM. Score without evidence -> warning.
- Unreadable / scanned PDF -> blocked in the UI before running; if it still fails, supplier scores 0 + warning.
- Weights not totalling 100 -> UI warning and re-normalisation (recorded in run warnings).

## Assumptions
- Experience rating is on a 0-10 scale entered by the user; dates are ISO dates.
- Supplier names are unique (case-insensitive) within a run.
- Documents are text-based PDFs (no OCR); text is capped at 60,000 characters per supplier.
- Benchmarks are relative to the suppliers in the **same run** - add/remove a supplier and PPI changes.
- The LLM's scores can vary between runs; given the *same validated scorecards* the formulas and ordering
  are fully reproducible (see `test_end_to_end_and_persistence`).

## SQLite schema
`evaluation_criteria(criterion_id, name, description, weight, max_score, is_active)` ·
`rfp_runs(rfp_run_id, created_at, status, provider, model, criteria_snapshot, warnings, run_json)` ·
`supplier_results(rfp_run_id, supplier_name, submission_date, experience_rating, absolute_score, ppi, final_rank, source_file, result_json)`

## Synthetic data
`sample_rfps/` has four fictional 2-3 page proposals (Apex Systems, BrightPath Tech, NexaWorks, Orbit Digital)
with deliberately different strengths, prices, schedules and gaps, plus `EDGE_blank_scanned_RFP.pdf`
(no text) for the validation demo. `sample_output/sample_run_demo_mode.json` is an exported run made in
**demo mode** - replace it with an export from your own real-LLM run before submitting.

## Demo script (for the short video)
1. **Criteria** page: show weights (100%) -> edit a weight, save.
2. **Supplier input**: load the 4 samples -> **Evaluate** -> leaderboard.
3. Open a **scorecard**: benchmark, gap, relative %, evidence. **Run details**: run id, trace, JSON download.
4. **Error case:** tick the blank-PDF checkbox (blocked with a message), or clear a supplier name, or set weights to 80%
   and show the re-normalisation warning.

## Screenshots
Add after deployment to `docs/screenshots/` and link here: leaderboard, scorecard, run details.

## Folder structure
```
app.py  requirements.txt  requirements-dev.txt  README.md
src/        db.py document_tool.py llm.py validation.py ranking.py orchestrator.py
scripts/    seed_db.py generate_sample_pdfs.py
sample_rfps/  sample_output/  tests/  data/  .streamlit/
```
