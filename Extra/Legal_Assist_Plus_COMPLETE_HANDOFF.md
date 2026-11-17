# Legal Assist+ — COMPLETE PROJECT HANDOFF DOCUMENT
*(Formerly named: LegalMind AI → NyayaSetu → Legal Assist+ [FINAL])*

**PURPOSE OF THIS DOCUMENT:** This is written so that a brand-new Claude chat, with zero prior context and NO access to the actual project folder (it's too large to upload), can resume work immediately with full understanding — of what exists, why every decision was made, what's broken vs. working, and exactly what to do next. Nothing should need to be re-explained. Paste this entire document as the first message in a new chat.

**How to use this doc:** Read Part A first for the core concept (don't lose this). Part N at the very end tells you the single next action. Everything in between is reference detail, organized so you can jump to what's relevant.

---

# PART A: PROJECT IDENTITY & CORE CONCEPT (read this first)

## A1. Title
**Legal Assist+** (final name, after LegalMind AI → NyayaSetu → Legal Assist+)

## A2. What This Project IS — don't let this narrow back down
Legal Assist+ has **two integrated capabilities**:

1. **General Legal Q&A** — user asks a question about Indian law, system retrieves relevant statute text (and now also real case law), and an LLM generates a grounded, cited, plain-language answer. Never answers from memory — always retrieval-grounded.

2. **Document Upload & Risk Analysis (THE CORE ORIGINAL IDEA — this is the heart of the project, not a side feature)** — a user uploads THEIR OWN document (contract, rental agreement, employment agreement), and the system:
   - Proactively scans EVERY clause (not just reactive Q&A)
   - Flags risk level per clause (None/Low/Medium/High) with plain-language explanation and legal reasoning
   - Cites relevant Indian law per clause where applicable
   - Checks the document against a checklist of standard protections and flags what's MISSING
   - Answers follow-up questions combining BOTH the user's own document AND the general legal knowledge base
   - Explicitly framed as informational/risk-flagging, NOT a lawyer replacement for high-stakes decisions

**CRITICAL — do not lose this framing:** the user explicitly pushed back once on the project staying too narrowly scoped to "just document Q&A." Their words: *"our project will be working as a lawyer it should identify the mistakes or the wrong this and many more tasks as the lawyers do... think of what lawyer does and help its clients the same our project should be able to do."* Keep expanding the "acts like a lawyer" feature set (risk flagging, missing-clause detection, plain-language explanation, practical answers to practical questions) — don't shrink this back to simple Q&A.

## A3. Problem Statement
- Legal documents are lengthy, dense, inaccessible to non-lawyers
- India replaced IPC/CrPC/Indian Evidence Act with BNS/BNSS/BSA on 1 July 2024 — most people and tools are working from outdated law
- Generic AI chatbots (ChatGPT, Gemini) hallucinate legal citations — real documented harm from this (lawyers sanctioned for AI-fabricated case law)
- People sign contracts without understanding risky clauses because professional legal review is expensive/inaccessible
- Existing tools are either professional-grade+expensive (Manupatra, SCC Online, CaseMine) or free+unreliable (generic chatbots) — nothing combines free + accurate + document-review

## A4. Differentiation / Novelty (for report, interview, presentation)
No reviewed research or existing product combines: (1) verified, hallucination-resistant Indian statutory Q&A, AND (2) proactive personal-document risk review, in one system. This gap was identified via literature review of 6 papers (see Part L).

---

# PART B: CURRENT SYSTEM ARCHITECTURE (as of this handoff)

```
                    ┌──────────────────────────────┐
                    │  data/statutes/cleaned/       │
                    │  19 structured JSON files     │
                    │  (BNS, BNSS, BSA, IPC, CrPC,  │
                    │  Evidence Act, Constitution,  │
                    │  9 Central Acts, 2 Maharashtra│
                    │  Acts) = 5,005 chunks         │
                    └───────────────┬────────────────┘
                                    │
                    ┌──────────────────────────────┐
                    │  data/judgments/               │
                    │  IL-PCSR + OpenNyAI (also       │
                    │  KanoonGPT, IL-TUR downloaded   │
                    │  but IL-TUR not yet integrated) │
                    │  = 1,537 judgment chunks sampled │
                    │  RANDOMLY (seed=42) from full set│
                    └───────────────┬────────────────┘
                                    │
                           build_vector_db.py
                        (combines statutes + judgments,
                         tags jurisdiction, chunk_type)
                                    │
                                    ▼
                    ┌──────────────────────────────┐
                    │  data/vector_db/                │
                    │  legal_index.faiss               │
                    │  chunk_metadata.pkl               │
                    │  6,542 total chunks, MiniLM       │
                    │  embeddings, dim 384               │
                    └───────────────┬────────────────┘
                                    │
                ┌────────────────────┴────────────────────┐
                │                                            │
                ▼                                            ▼
    query_legal_assist.py                      analyze_document.py
    (general Q&A, terminal-testable)            (document upload + review,
    - hybrid retrieval (semantic +               terminal-testable)
      exact section/article match)              - clause splitting
    - jurisdiction filter                       - dual retrieval (clauses + law)
    - judgment vs statute citation format        - full automatic risk review
                                                  - missing-clause checklist
                                                  - jurisdiction filter
                                                  - judgment vs statute citation format
                │                                            │
                └────────────────────┬────────────────────┘
                                     │
                                     ▼
                            translation_utils.py
                     (PARTIALLY BROKEN — see Part F for status.
                      Currently uses Groq for translation, NOT
                      fully verified working. Multilingual
                      deferred — Option A chosen.)
                                     │
                                     ▼
                                  app.py
                    (Streamlit frontend — WORKING, live-connected
                     to all backend logic above, not a mockup)
```

## B1. Complete File Inventory (project root folder: `Legal Assist +`, now at path `C:\Users\ASUS\Code\Legal Assist +` — NOTE: path changed partway through the project from an OneDrive path, this caused venv breakage once, see Part G)

| File | Purpose | Status |
|---|---|---|
| `requirements.txt` | Python package list | Current |
| `.env` | `GROQ_API_KEY` (gitignored) | Set up |
| `.gitignore` | Excludes venv, models, judgments, raw_pdfs, chat_history.json, test/ | Current, working |
| `.streamlit/config.toml` | Navy/blue theme config | Current |
| `setup_datasets.py` | Original HF dataset downloader | Done, ran once, historical |
| `retry_missing_datasets.py`, `retry_iltur_configs.py` | One-off retry scripts for gated datasets | Done, historical, moved to `Extra/` folder |
| `clean_documents.py` | Original generic cleaning script | Superseded — actual cleaning done via separate Claude chat sessions with a structured prompt |
| `build_vector_db.py` | **ACTIVE** — builds the combined statute+judgment vector DB | Current, working, see Part C for full detail |
| `query_legal_assist.py` | **ACTIVE** — general Q&A engine (terminal + imported by app.py) | Current, working, extensively tested |
| `analyze_document.py` | **ACTIVE** — document analysis engine (terminal + imported by app.py) | Current, working, extensively tested |
| `translation_utils.py` | Translation layer for multilingual | **DEFERRED/BROKEN** — see Part F |
| `app.py` | **ACTIVE** — Streamlit frontend, imports from both analyze_document.py and query_legal_assist.py | Current, working EXCEPT multilingual portion |
| `test/Sample_Consulting_Services_Agreement.pdf` | Test document used throughout development | Keep for retesting |

**File independence note:** `query_legal_assist.py` and `analyze_document.py` are independent — neither imports the other. Both import from each other's... NO WAIT — correction: `translation_utils.py` imports `ask_llm` FROM `analyze_document.py` (reuses its retry-safe LLM-calling function). `app.py` imports from ALL THREE (`analyze_document.py`, `query_legal_assist.py`, `translation_utils.py`). All four scripts read from `data/vector_db/` which is built once by `build_vector_db.py`.

---

# PART C: build_vector_db.py — FULL DETAIL

## C1. What it does
1. Loads all 19 statute JSON files from `data/statutes/cleaned/`, tags each chunk with:
   - `act_name`, `section_number`, `section_title`, `text`
   - `jurisdiction`: auto-detected as "Central" or a specific state name (currently only "Maharashtra" detected) by scanning the Act name against a `STATE_KEYWORDS` list
   - `chunk_type`: `"statute"`
2. Loads judgment/case-law data from `data/judgments/`:
   - **IL-PCSR**: loaded via `datasets.load_from_disk()`, uses the `train_queries` split, **randomly shuffled (seed=42)** then sampled up to `MAX_JUDGMENTS_PER_SOURCE = 800`. Fields used: `case_title`→`act_name`, `id`→`number`, `date`→part of `title`, `text`→`text` (truncated to `JUDGMENT_TEXT_MAX_CHARS = 3000` chars), `jurisdiction` field used if present else "Central". Blank-title rows are skipped.
   - **OpenNyAI**: same pattern, `train` split, same random sampling, fields `Titles`→`act_name`, `Text`→`text`, `Court_Name_Normalized`/`Court_Name`→part of `title`, `Case_Type`→part of `title`. Jurisdiction always "Central" (no clean state field in this dataset). Blank-title rows skipped.
   - Both tagged `chunk_type: "judgment"`
   - **KanoonGPT and IL-TUR datasets are downloaded to disk but NOT YET integrated into this build script** — this is a real, actionable gap, not done yet (see Part N for priority).
3. Combines statute chunks + judgment chunks into one list
4. Generates embeddings using `all-MiniLM-L6-v2` (Sentence-Transformers)
5. Builds a FAISS `IndexFlatL2` index
6. Saves `legal_index.faiss` and `chunk_metadata.pkl` to `data/vector_db/`

## C2. Current actual numbers (last confirmed successful run)
```
Loaded 5005 total chunks from 19 file(s).
Jurisdictions detected: ['Central', 'Maharashtra']
Loading judgment/case-law datasets...
  [ok] IL-PCSR: loaded 737 case chunks
  [ok] OpenNyAI: loaded 800 case chunks
Total judgment chunks loaded: 1537
Combined total: 5005 statute chunks + 1537 judgment chunks = 6542 chunks
Built FAISS index with 6542 vectors of dimension 384.
```
(Note: IL-PCSR returned 737, not the full 800 requested — some rows were skipped, likely blank titles or short text filtered out. This is expected/fine.)

## C3. Why random sampling was necessary (real bug that was found and fixed)
**Original bug:** judgment loaders used `.select(range(500))` — i.e., literally the first N rows of each dataset. Testing revealed these were NOT representative (clustered around 2019-2020 tax/property cases) — a dowry-death test question found zero relevant judgments despite 1,000 cases being indexed, because none of the sampled cases happened to be on that topic.
**Fix applied:** changed to `.shuffle(seed=JUDGMENT_SAMPLE_SEED).select(range(...))` — random sampling across the full dataset, with a fixed seed for reproducibility. Also increased sample size from 500→800 per source. Also added blank-title filtering (some rows had empty case titles, producing unusable/confusing chunks).
**Verification after fix:** asked "Has the Supreme Court interpreted dowry death cases?" — system correctly found and cited "State Of U.P vs Ashok Kumar Srivastava, 1992" with accurate legal reasoning (correctly noted the case predates Section 304B's enactment, so didn't overclaim what it interpreted). This confirmed the fix worked.

## C4. Embedding model decision — MiniLM over InLegalBERT (important, evidence-based)
**What was tried:** hypothesized that InLegalBERT (pretrained on 5.4M Indian legal documents) would outperform a general-purpose embedding model.
**Test method:** rebuilt the entire vector DB with InLegalBERT instead of MiniLM, reran the SAME test questions used with MiniLM, compared retrieval quality directly.
**Result:** InLegalBERT performed MEASURABLY WORSE. Concrete example: "What does the Maharashtra Rent Control Act say about eviction of tenants?" — with MiniLM, correctly retrieved Sections 45, 46, 42, 37, 18 (all directly relevant). With InLegalBERT, retrieved irrelevant Constitution sections and missed the actual eviction provisions. Same pattern on "burden of proof" and "dying declaration" test questions.
**Why this happened:** InLegalBERT was pretrained for language understanding (fill-in-the-blank tasks) on legal text, but was never fine-tuned specifically to produce good sentence-level embeddings for semantic similarity/retrieval. MiniLM, despite being general-purpose, WAS specifically trained via contrastive learning for exactly this retrieval task.
**Decision:** `all-MiniLM-L6-v2` is the final, current embedding model. InLegalBERT remains downloaded in `data/models/` but is UNUSED.
**Value for report/interview:** this is a strong, specific, evidence-based engineering story — "hypothesized X, tested it, found it performed worse, reverted based on data."

## C5. Distance threshold calibration (evidence-based, not guessed)
**Method:** ran 15+ test questions with the threshold effectively disabled, recorded actual FAISS L2 distances for known-good matches vs. known-irrelevant matches.
**Data found:** genuine correct matches scored 0.35–0.72 consistently. Weak/no-match cases (where the system correctly said "I don't have this information") scored 0.86–1.03.
**Final calibrated values:**
- `query_legal_assist.py`: `DISTANCE_THRESHOLD = 1.0`
- `analyze_document.py` (law retrieval only): `LAW_DISTANCE_THRESHOLD = 0.85` — set STRICTER than the general Q&A tool, because in document-review context, citing wrong-domain law (e.g., Motor Vehicles Act showing up for a consulting-contract liability question, which actually happened during testing) is worse than citing no law at all.

---

# PART D: query_legal_assist.py — FULL DETAIL

## D1. Core pipeline
1. `load_everything()` — loads FAISS index, chunk metadata, embedding model, Groq client (also reused by `analyze_document.py` and `app.py`)
2. `retrieve(question, index, chunks, embed_model, top_k=5, jurisdiction_filter=None)`:
   - `exact_section_lookup()` — regex checks for "Section X" / "Article X" in the question, guarantees that exact chunk is included (fixes a real bug, see D2)
   - Semantic search via FAISS, filtered by `DISTANCE_THRESHOLD = 1.0`
   - If `jurisdiction_filter` is set (e.g. "Maharashtra" or "Central"), over-fetches candidates (`top_k * 4`) then filters to chunks where `jurisdiction in ("Central", jurisdiction_filter)` — Central law ALWAYS included regardless of filter, since Central and State law apply simultaneously in India
   - Combines exact + semantic results, deduplicated
3. `build_prompt(question, retrieved_chunks)` — constructs the LLM prompt with STRICT rules (see D3)
4. `ask_llm(prompt, groq_client, max_tokens=...)` — calls Groq, with retry-with-backoff on rate limits (defined in `analyze_document.py`, imported)

## D2. Real bug found and fixed: exact-number retrieval gap
**Bug:** asking "What was Section 420 of the IPC?" initially retrieved Section 50 (a definitions clause) instead of Section 420 (confirmed present in the data), because semantic embeddings don't weight numeric tokens like "420" strongly.
**Fix:** added `exact_section_lookup()` — regex `r'\b(?:section|article)\s+(\d+[A-Za-z]?)\b'` matches the question, guarantees that exact chunk is included in retrieval results alongside semantic results.
**IMPORTANT — this same bug had to be fixed TWICE:** initially only added to `query_legal_assist.py`'s law-section retrieval. Later discovered `analyze_document.py`'s document-CLAUSE retrieval had the SAME gap (asking "Summarize clause 7" returned completely wrong clauses). Fixed by adding the identical exact-match pattern to `retrieve_clauses()` in `analyze_document.py` too. **Lesson/reminder: if this class of fix is ever needed again, check BOTH files, not just one.**

## D3. Prompt engineering — current rules (after real user feedback fixes)
The original prompt caused three real problems, found via live testing, all now fixed:
1. **Raw `<br>` tags showing as literal text** — LLM was emitting HTML inside markdown tables. Fixed: prompt explicitly forbids raw HTML tags (`<br>`, `<b>`, `<div>`, etc.), AND `app.py` has a defensive `clean_answer_text()` function that strips/converts any stray HTML even if the LLM slips up.
2. **Overuse of markdown tables for simple answers** — prompt now explicitly says: tables ONLY for genuine 3+ item side-by-side comparisons, plain prose/bullets otherwise.
3. **Not directly answering the practical question asked** — e.g., asked "What happens if I resign within the first year?", the system was reciting clause text instead of giving a direct answer. Fixed: prompt now REQUIRES a direct 2-4 sentence answer to the actual question FIRST, before any supporting clause/law detail.
4. Citations distinguish statute (`[Source N - Statute] Act Name, Section X`) vs. judgment (`[Source N - Court Judgment] Case Name (Court, Date)`) — prompt explicitly instructs not to blend statutory law with judicial interpretation as if they're the same kind of authority.

## D4. Testing history summary
Tested extensively across 20+ questions: basic factual lookup, cross-Act reasoning, old-law↔new-law mapping (IPC→BNS etc.), jurisdiction-specific (Maharashtra), plain-language explanation, procedural questions, and DELIBERATELY ADVERSARIAL questions (fake section numbers like "Section 999 of the BNS", a fictional "Indian Traffic Act"). **Result: 100% correct refusal rate on all adversarial/fabricated questions across all testing rounds** — this is the single most validated, defensible claim about the whole project.

**Status: considered stable, well-tested, essentially DONE** (aside from the not-yet-integrated judgment datasets, see Part N).

---

# PART E: analyze_document.py — FULL DETAIL

## E1. Core pipeline (two modes)

### Mode 1: Automatic Full Review (runs immediately on document upload)
1. `extract_text_from_pdf()` (pdfplumber) → `split_into_clauses()` (regex-based, handles "1.", "1)", "Clause 1" numbering styles, falls back to paragraph splitting if no numbering found)
2. `embed_clauses()` — embeds each clause using the same MiniLM model
3. `run_full_review()` loops through clauses in batches of `CLAUSE_BATCH_SIZE = 2` (reduced from 4 to avoid rate limits and response truncation):
   - `review_clause_batch()` — for each batch, retrieves relevant law per clause (`retrieve_law()`), sends to LLM asking for risk level (None/Low/Medium/High) + plain explanation + legal reasoning, with explicit instruction: no tables, no HTML
   - `check_missing_clauses()` — compares the WHOLE document against a `STANDARD_CLAUSE_CHECKLIST` (termination, dispute resolution, governing law, liability cap, confidentiality, force majeure, payment terms, renewal, indemnity) — uses COMPACT 120-char-per-clause summaries (not full text) to save tokens/stay under rate limits
4. Between each batch call: `time.sleep(2)` to stay under Groq's rate limit

### Mode 2: Follow-up Q&A (after the automatic review)
- `retrieve_clauses()` (document's own clauses, with exact-clause-number matching — see D2) + `retrieve_law()` (general legal knowledge base) retrieved TOGETHER
- `build_combined_prompt()` — combines both sources, same strict formatting/direct-answer rules as D3
- Answers combine "what your document says" + "what the law says"

## E2. All bugs found and fixed during testing (chronological, all CONFIRMED fixed as of last test)

1. **Groq rate limit crash (429 error)** — free tier caps at 8,000 tokens/minute. Fixed: `ask_llm()` in this file has retry-with-backoff (waits `8 * (attempt+1)` seconds, up to 4 retries), reduced batch size, explicit `max_tokens` per call type, paced `time.sleep()` between batches, compact missing-clause-check prompt.
2. **Empty LLM response bug** — occasionally returned completely blank. Fixed: `ask_llm()` detects empty/None content, retries automatically, falls back to a clear message after retries exhausted.
3. **Answer truncation (mid-sentence cutoffs)** — `max_tokens` was too low in multiple places. FINAL VALUES: clause-batch review = 1300, missing-clause check = 1000, follow-up Q&A = 2048.
4. **CRITICAL: wrong clause retrieved** ("Summarize clause 7" returned Clauses 15, 1, 3) — see D2, fixed by adding exact-match to `retrieve_clauses()`.
5. **Wrong-domain law citations** (Motor Vehicles Act showing up for a consulting-contract liability question) — mitigated (not eliminated — inherent limitation of embedding search) by tightening `LAW_DISTANCE_THRESHOLD` to 0.85 for this file specifically.

## E3. Validated test results (real, from actual runs on `test/Sample_Consulting_Services_Agreement.pdf`, a 16-clause document)
- Correctly flagged: one-sided indemnification clause (cited Indian Contract Act Sections 222, 224), biased arbitrator-appointment clause (Client unilaterally picks arbitrator — cited Arbitration and Conciliation Act 1996, gave actionable negotiation recommendation), liquidated damages concern (cited Sections 73/74), low liability cap concern (cited Consumer Protection Act Section 85)
- Did NOT manufacture risk on genuinely standard clauses (Force Majeure, Entire Agreement correctly marked low/no risk)
- Missing-clause check correctly identified absent late-payment-penalty terms
- Follow-up Q&A correctly answered practical questions: "What happens if I resign within the first year?", "Is the termination clause fair to both parties?", "What if the Company pays me late?", "Find the most one-sided clause in this document" — all with direct answers + correct supporting detail
- **One known minor limitation (documented, not fixed):** missing-clause check occasionally produces a false positive (once flagged "renewal terms" as missing when the clause actually DID mention renewal, just past the 120-char compact-summary cutoff) — acceptable, documented tradeoff for staying under rate limits

**Status: considered stable and working, well-tested.**

---

# PART F: MULTILINGUAL SUPPORT — CURRENT BROKEN/DEFERRED STATUS (important, don't waste time re-discovering this)

## F1. Decision History (full chain, so it's not re-litigated)
1. Original pending decision (from way back): whether to switch from Groq to Gemini for the whole project when building multilingual — DECIDED: keep Groq for everything, add a SEPARATE translation layer only (lower risk)
2. First implementation: used `deep-translator` library (free, unofficial Google Translate scraper)
3. **Problem found:** `deep_translator.exceptions.TooManyRequests` — Google was rate-limiting the IP from repeated testing. Added retry-with-backoff — still hit rate limits.
4. **Decision: abandon `deep-translator` entirely.** Rewrote `translation_utils.py` to use Groq itself for translation (reuses the already-proven-stable `ask_llm()` from `analyze_document.py`, no new API/library, no new rate-limit surface).
5. **Groq-based version was built and files were verified syntactically correct**, BUT when tested in the live app, STILL produced wrong results (same wrong case-law citation as before) — root cause was NOT fully confirmed before the decision to defer. Leading hypothesis was stale/cached Streamlit session or old chat history being displayed (persistent `data/chat_history.json` was suspected of showing OLD results from before the fix), but this was never conclusively verified due to time constraints.
6. **FINAL DECISION (most recent): Option A — DEFER multilingual entirely.** Move to Phase 5. Do not spend more time on this right now.

## F2. Exact current state of the code (for whoever picks this up later)
- `translation_utils.py` currently contains the **Groq-based version** (not the broken `deep-translator` version) — imports `ask_llm` from `analyze_document.py`, has `translate_to_english()` and `translate_from_english()`, supports English/Hindi/Marathi
- `app.py` currently has the language selector wired in, and calls to `translate_to_english()`/`translate_from_english()` include the `groq_client` parameter correctly (this was verified via `Select-String` checks — confirmed NO `deep_translator` references remain, confirmed `groq_client` IS passed correctly)
- **Despite the code being syntactically correct and using the more reliable Groq approach, live testing still showed the SAME wrong result as the broken deep-translator version.** This was never root-caused. Leading theories (untested):
  - Streamlit wasn't fully restarted (old process still running old code)
  - `data/chat_history.json` was replaying old saved wrong answers rather than generating new ones
  - Possibly a real bug in the Groq-based translation logic itself that wasn't caught

## F3. What to do about this (whenever multilingual is picked back up)
1. FIRST: `Remove-Item data\chat_history.json` to eliminate the stale-history theory entirely
2. FULLY kill any running Streamlit process (`Get-Process | Where-Object {$_.ProcessName -like "*streamlit*"} | Stop-Process -Force`) before restarting
3. Test with a question NEVER asked before (not a repeat of "चेक बाउंस होने पर क्या होता है?" which has a contaminated history)
4. If it STILL fails after those two steps, THEN there's a genuine code bug in the Groq-based translation logic worth debugging from scratch
5. Known acceptable limitation either way: even a working version won't be "legal-specialist-grade" translation — this is a reasonable, document-worthy tradeoff, not a flaw

## F4. Supported languages (as currently coded, untested)
English (default/no-op), Hindi (`hi`), Marathi (`mr`) — easily extensible, just add to the `SUPPORTED_LANGUAGES` dict

**STATUS: DO NOT spend more time on this unless explicitly returning to it. Phase 4 is considered complete WITHOUT this feature.**

---

# PART G: ENVIRONMENT & INFRASTRUCTURE — FULL DETAIL (extensive troubleshooting history, so these don't get re-debugged from scratch)

## G1. Current environment facts
- **OS:** Windows
- **Current project path:** `C:\Users\ASUS\Code\Legal Assist +` (CHANGED partway through from an earlier `C:\Users\ASUS\OneDrive\Desktop\Code\Legal Assist +` path — this move broke the venv once, see G3)
- **Python version:** 3.11.0 (deliberately downgraded from 3.14 — see G2)
- **Editor:** VS Code
- **Virtual environment:** `venv/` folder, created with `py -3.11 -m venv venv`

## G2. Why Python 3.11, not 3.14 (resolved, don't redo)
Python 3.14 was too new — caused Windows "Application Control policy" (Smart App Control, confirmed ON via `Get-MpComputerStatus`) to block `pyarrow`'s DLL, cascading into `sentence-transformers`/`datasets` import failures. Switching to Python 3.11 fixed this permanently since ML packages have far more mature, trusted builds for 3.11. **User does NOT have admin rights on this machine** (confirmed via failed `Add-MpPreference` attempt), so Defender exclusions aren't available — Python version downgrade was the actual working fix.

## G3. Recurring category of bug: pandas/torch/pyarrow import failures
This happened MULTIPLE times across the project (different specific packages each time — pyarrow, then numpy, then torch, then pandas again after a venv rebuild). Root causes varied:
- Sometimes genuine Windows Application Control DLL blocking (fixed by Python 3.11 downgrade, see G2)
- Sometimes a broken half-installed state from an interrupted `pip uninstall`/`pip install` due to a `PermissionError: Access is denied` (caused by VS Code holding file handles open — fix: fully close VS Code, not just the terminal, then redo `pip install -r requirements.txt` plus the extra packages)
- **General fix pattern that worked repeatedly:** `pip uninstall <package> -y` then `pip install <package> --force-reinstall --no-cache-dir`, and if that fails, fully close VS Code entirely (not just terminal tabs) before retrying, since its Python extension keeps venv files open in the background
- **If venv gets fully broken:** nuke and rebuild: `deactivate` → `Remove-Item -Recurse -Force venv` → `py -3.11 -m venv venv` → `venv\Scripts\activate` → `pip install -r requirements.txt` → `pip install groq python-dotenv faiss-cpu pdfplumber streamlit`

## G4. The `torchvision` Streamlit startup noise (HARMLESS, don't troubleshoot this again)
Every `streamlit run app.py` prints DOZENS of `ModuleNotFoundError: No module named 'torchvision'` tracebacks referencing `transformers.models.*.image_processing_*`. **This is 100% harmless** — Streamlit's dev-mode file watcher scans every installed package (including dozens of unused `transformers` vision-model submodules) at startup, and `torchvision` was never installed because this project only does text embeddings. The actual app works fine despite this wall of text. If it's visually annoying, can add `fileWatcherType = "none"` under `[server]` in `.streamlit/config.toml` (tradeoff: lose auto-reload on code changes).

## G5. Virtual environment path-breakage (if the project folder ever moves again)
Moving/renaming the project folder breaks the venv (`pyvenv.cfg` and other internal files store absolute paths). Symptom: `No pyvenv.cfg file` error even though the file physically exists. **Fix: always recreate the venv fresh after moving the folder** — don't try to repair it in place.

## G6. Git/GitHub history (resolved, current state is clean)
- Repo: `https://github.com/AyeshaChaush/Legal-Assist-.git`, branch `main`
- **Had a serious issue:** early commits accidentally included large files (InLegalBERT model ~500MB etc.) before `.gitignore` properly excluded `data/models/`, `data/judgments/`, `data/raw_pdfs/` — this caused `git push` to fail with out-of-memory errors trying to compress/push bloated history.
- **Fix applied:** fully wiped git history (`Remove-Item -Recurse -Force .git`) and did a clean `git init` + `git add .` + commit + `git push -u origin main --force` with the CORRECT `.gitignore` already in place. This worked (confirmed: repo now has 34 files, no large binaries).
- Subsequent pushes also hit transient network timeouts (HTTP 408, connection reset) — fixed by `git config http.postBuffer 524288000` and `git config --global http.version HTTP/1.1`, then simple retry.
- **Current .gitignore contents:**
```
venv/
__pycache__/
*.pyc
.env
data/models/
data/judgments/
data/raw_pdfs/
data/chat_history.json
test/
```
- **Current git status: clean, pushed, no outstanding uncommitted multilingual changes** (user has NOT yet committed the Groq-based translation_utils.py rewrite — this is a loose end, see Part N)

## G7. API keys / external services
- **Groq API key** in `.env` as `GROQ_API_KEY` — free tier, 8,000 tokens/minute rate limit (actively managed in code via batching/pacing/retry)
- **Current Groq model:** `openai/gpt-oss-20b` (chosen because the account's available model list — checked via `client.models.list()` — had NO plain Llama models available; options were `allam-2-7b`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `groq/compound`/`compound-mini`, plus unusable audio/TTS/safety models). `openai/gpt-oss-120b` noted as a "higher quality, slower" swap-in option for final demo if desired — NOT currently used.
- **Hugging Face account** set up, access token used for `hf auth login` (note: `huggingface-cli` is deprecated, use `hf` command instead)

## G8. Installed packages (cumulative)
```
datasets, huggingface_hub, transformers, sentence-transformers, requests,
beautifulsoup4, tqdm, fastapi, uvicorn, groq, python-dotenv, faiss-cpu,
pdfplumber, numpy, streamlit, deep-translator (NO LONGER USED but may still
be installed — harmless if left, translation_utils.py no longer imports it)
```

---

# PART H: COMPLETE DATASET INVENTORY

## H1. Statute JSON files (19 files, in `data/statutes/cleaned/`, 5,005 chunks total)
| File | Sections | Verification status |
|---|---|---|
| BSA_2023.json | 170 | Verified via TOC cross-validation parsing method |
| Constitution_of_India_merged.json | 1,142 | User merged from 9 original PDF chunks |
| BNS_2023_structured.json | ~358 | Structured |
| BNSS_2023_structured.json | ~531 | Structured |
| Indian_Penal_Code_1860_structured.json | 567 | VERIFIED complete, no duplicates, Section 420 confirmed present |
| Code_of_Criminal_Procedure_1973_structured.json | 534 entries/484 unique sections | VERIFIED complete (first attempt only had 43 sections, was discarded and redone) |
| Legal_Assist_Indian_Evidence_Act_1872_CLEAN.json | 185 entries/167 unique sections | VERIFIED complete, no gaps |
| consumer_protection_act_2019.json | — | Structured |
| information_technology_act_2000.json | — | Structured |
| Motor_Vehicles_Act_1988_structured.json | — | Structured |
| indian_contract_act_1872.json | — | Structured |
| Negotiable_Instruments_Act_1881_structured.json | — | Structured |
| Protection_of_Women_from_Domestic_Violence_Act_2005_structured.json | — | Structured |
| Protection_of_Children_from_Sexual_Offences_Act_2012_structured.json | — | Structured |
| hindu_marriage_act_1955.json | — | Structured |
| Legal_Assist_Right_to_Information_Act_2005_CLEAN.json | — | Was initially broken/empty, redone and fixed |
| payment_and_settlement_systems_act_2007.json | 3 | Correctly small (genuinely short amendment act) |
| Maharashtra_Rent_Control_Act_1999_structured.json | ~60 | Verified; a DUPLICATE file was found and deleted (kept this version over the other) |
| Legal_Assist_Maharashtra_Land_Revenue_Code_1966_structured.json | — | Structured |

**Schema:**
```json
{
  "act_name": "string",
  "section_number": "string",
  "section_title": "string",
  "text": "string",
  "chapter": "string (optional)"
}
```
(`build_vector_db.py` adds `jurisdiction` and `chunk_type` fields on top of this when building the index — the raw JSON files themselves don't have these.)

## H2. Judgment/case-law datasets (Hugging Face)
| Dataset | Size | Access | Integration status |
|---|---|---|---|
| IL-PCSR | 5,017 train/627 dev/627 test | `Exploration-Lab/IL-PCSR` (gated, approved) | **INTEGRATED** — 737 randomly sampled chunks in current vector DB |
| OpenNyAI | 11,970 judgments | `opennyaiorg/InJudgements_dataset` (gated, approved) | **INTEGRATED** — 800 randomly sampled chunks in current vector DB |
| KanoonGPT | — | `KanoonGPT/indian-case-laws` | Downloaded, **NOT YET integrated** into build_vector_db.py |
| IL-TUR (lsi, pcr, summ configs) | summ: 7,030 train/100 test | `Exploration-Lab/IL-TUR` (gated, approved) | Downloaded (3 of 8 configs: lsi, pcr, summ), **NOT YET integrated** |
| CUAD (contract clauses) | — | `theatticusproject/cuad-qa` | FAILED to download (HF deprecated "dataset loading scripts" for this repo) — deprioritized, not core-blocking |

## H3. Embedding models
| Model | Status |
|---|---|
| `all-MiniLM-L6-v2` | **ACTIVE, in production use** |
| `InLegalBERT` (`law-ai/InLegalBERT`) | Downloaded, tested, empirically WORSE at retrieval, NOT used (see C4) |

---

# PART I: HOW DATA WAS CLEANED (methodology, for report writing)

1. Statutes were downloaded as PDFs manually from India Code portal / NCRB SANKALAN
2. Structured into JSON using **SEPARATE Claude chat sessions** with a standardized cleaning prompt (not a local Python script) — instructed to extract section number/title/text, output as JSON, rule: "do not paraphrase, keep original wording"
3. **Validation method developed and proven on BSA specifically**: raw text parsed by FIRST extracting the Act's own Table of Contents to get an authoritative sequential list of section numbers, THEN searching for each section's position in the body text in that exact order — this avoided naive regex pattern-matching being confused by cross-references like "as mentioned in section 35" appearing mid-text in a DIFFERENT section
4. **Verification performed on every uploaded file**: entry count, duplicate section number check, gap detection (comparing found section numbers against expected numeric range), spot-checking known important sections (e.g. confirmed IPC Section 420 present; confirmed CrPC Sections 41/154/161/164/173/207/313/437/438 all present)
5. **Two real data-quality bugs caught this way and fixed:** an empty/broken RTI Act JSON file (redone), an incomplete CrPC file with only 43 of 484 sections (redone, second attempt fully complete)

---

# PART J: NOVELTIES — STATUS TRACKING TABLE

| Novelty (from original project brainstorm) | Status |
|---|---|
| Hybrid + Adaptive Retrieval | **Built** — exact-number + semantic hybrid, proven necessary by real bugs found during testing. "Adaptive" (query-complexity-based parameter tuning) not done. |
| Knowledge-Graph-Augmented RAG | Not started |
| Explainable AI layer | **Partially built** — sources shown with relevance scores/distances before answers in both scripts. More visual polish possible later. |
| Hallucination/groundedness verification | **Built and extensively validated** — 100% correct refusal rate across 20+ adversarial tests |
| Contract/Document Clause Risk Analysis | **Built — this IS the core feature now**, expanded well beyond "nice to have" into a full proactive document review engine |
| Jurisdiction-aware reasoning engine | **BUILT AND VERIFIED WORKING** — Central vs. Maharashtra filtering confirmed via side-by-side test showing different results per jurisdiction selection |
| Legal Procedure/Workflow Generator | Not started |
| Multilingual + Voice Support | **ATTEMPTED, DEFERRED/BROKEN** — see Part F in full |
| Agentic Orchestration (routing to sub-indexes) | Not started |
| India-specific old↔new law mapping | Data is in place (IPC/CrPC/Evidence Act all structured and indexed), verified working via "Has the Evidence Act been repealed" and "What was Section 420 IPC" test questions — no separate structured mapping TABLE exists, the LLM answers this correctly by having both old and new Act text available in retrieval |
| DigiLocker, NJDG, legal literacy mode | Not started |

---

# PART K: SDG MAPPING REPORT (completed as a side deliverable)

A separate academic deliverable — "SDG Mapping Justification Report" — was completed using an institution-provided Word template, filled in with:
- **Primary SDG: Goal 16 (Peace, Justice and Strong Institutions)**, Target 16.3 ("Promote the rule of law... ensure equal access to justice for all")
- **Secondary SDG: Goal 10 (Reduced Inequalities)**, Target 10.3
- Full problem statement, direct-connection justification, novelty/sustainability justification, and an impact table (societal/environmental/economic/stakeholder) were written based on real project facts (open-source stack, no model training from scratch, free-tier APIs, etc.)
- Validation/testing results table uses the REAL validated figure: "100% refusal rate on adversarial queries, across 20+ adversarial test questions"
- **Still needs manual completion by the user:** Project ID, Academic Year, Team Member Names & IDs, Department, Project Type selection (EDI/ERI/Major Project), measured average response time (not actually benchmarked yet), and an inserted screenshot/architecture diagram image
- The filled file is `SDG_Mapping_Justification_Report_LegalAssist.docx` — if this is needed again and lost, it can be regenerated from the original uploaded template (`SDG_Mapping_Justification_Report_Template.docx`) using the same XML-editing approach (unzip docx → find/replace exact placeholder text in `word/document.xml`, being careful to escape `&` as `&amp;` in any replacement text — this caused one bug that had to be fixed → rezip)

---

# PART L: RESEARCH / LITERATURE REFERENCES (for report citations)

1. **LawPal: A RAG-Based System for Enhanced Legal Accessibility in India** (2025) — `arxiv.org/html/2502.16573v1` — closest existing comparable system
2. **Domain-Partitioned Hybrid RAG for Legal Reasoning: Toward Modular and Explainable Legal AI for India** (2026) — `arxiv.org/pdf/2602.23371`
3. **HyPA-RAG: Hybrid Parameter-Adaptive RAG for Legal/Policy** (2024) — `arxiv.org/pdf/2409.09046`
4. **LegalBench-RAG: A Benchmark for RAG in the Legal Domain** (2024) — `arxiv.org/abs/2408.10343`
5. **Bridging Legal Knowledge and AI: RAG with Vector Stores, Knowledge Graphs, and Hierarchical NMF** (2025) — `arxiv.org/pdf/2502.20364`
6. **Where Does Legal AI Fail? Evaluating RAG Pipelines** (ACM CIKM, 2024) — `dl.acm.org/doi/10.1145/3746252.3761151`

**Gap identified:** none of the above combine general statutory Q&A with proactive personal-document risk review — this is Legal Assist+'s specific differentiation.

---

# PART M: COMPETITOR ANALYSIS & SECURITY/UPDATE ARCHITECTURE DECISIONS (still valid, unchanged from early planning, not yet implemented)

## M1. Competitor landscape (for literature review section)
Manupatra/SCC Online/CaseMine = powerful but costly/professional-only. VIDUR AI/BharatLaw.AI = newer, free-tier, still maturing. ChatGPT/Gemini = free but hallucination-prone, no citations, no BNS/BNSS awareness, no document-specific risk analysis.

## M2. Security architecture decision (PLANNED, NOT YET BUILT — this is Phase 5)
Decided early in planning, still the plan: **AES-256 encryption + JWT auth + RBAC + auto-deletion as the PRIMARY confidentiality layer** for uploaded documents. **Blockchain (SHA-256 hash anchoring) ONLY for tamper-evidence/integrity proof** — never for storing or exposing actual document content. Reasoning: blockchain is designed for transparency/immutability, not secrecy; encryption solves the actual stated problem (confidentiality). One-line summary for presentations: *"We secure user documents using encryption and access control as the main layer, and use blockchain only to verify document integrity — not to store or expose actual content."*

## M3. Real-time law update pipeline (PLANNED, NOT YET BUILT — this is Phase 6)
India Code/e-Gazette have NO public API (confirmed via research). Planned design: scheduled scraper (not true real-time) + change detection (compare against stored version) + human-review admin panel before re-embedding + "last verified" timestamp shown to users. Call this a "scheduled update pipeline" in the report, not "real-time" — more honest and still credit-worthy.

---

# PART N: WHAT TO DO NEXT (the single most important part of this document)

## N1. Immediate loose ends to close first (quick, low-effort)
1. **Commit the current uncommitted state.** As of this handoff, the Groq-based `translation_utils.py` rewrite and related `app.py` changes have NOT been committed to git yet. Run:
   ```
   git add .
   git commit -m "Add Groq-based translation layer (deferred/unverified — see handoff doc Part F)"
   git push
   ```
   Do this even though multilingual is deferred/broken — it's still real work worth preserving in history, and prevents it from being lost or re-done from scratch later.

## N2. Recommended next phase: Phase 5 — Security
This was the explicit next-phase decision before this handoff. Concrete tasks, in a sensible order:
1. AES-256 encryption for uploaded documents (Python `cryptography` library) — encrypt at rest, decrypt only in-memory for processing
2. JWT-based authentication (login/signup) — note: `app.py` currently has a VISUAL-ONLY login screen (email/password fields, disabled Login button, working "Continue as Guest") — this needs to become functionally real
3. Role-based access control / per-user document isolation
4. Auto-deletion policy for uploaded documents (e.g. delete after N days or on session end)
5. SHA-256 hash generation + lightweight blockchain anchoring (Hyperledger Fabric testnet, or even a simple database table for a demo-scale substitute) for document integrity proof — NOT for storing content, see M2
6. DPDP Act 2023 compliance basics (consent language, deletion rights messaging)

## N3. Other backlog items (not urgent, pick up when relevant)
- Integrate KanoonGPT and IL-TUR (lsi/pcr/summ) judgment datasets into `build_vector_db.py` (currently downloaded but unused — same pattern as IL-PCSR/OpenNyAI integration, should be a fairly mechanical addition following the existing `load_il_pcsr_chunks()`/`load_opennyai_chunks()` pattern)
- Resolve the multilingual support (see Part F in full for exact next debugging steps)
- Phase 6: real-time law update scraper (see M3)
- Phase 7: migrate frontend from Streamlit to React for final/production deployment (Streamlit was explicitly chosen for speed during development; React was always the planned final step, not a replacement needed urgently)
- Phase 8: formal evaluation (30-50 question test set with measured accuracy), baseline comparison vs. plain ChatGPT (no RAG) to demonstrate hallucination reduction quantitatively, final report write-up incorporating all the decision-log reasoning in this document (genuinely strong material — the MiniLM-vs-InLegalBERT experiment and the hybrid-retrieval bug-discovery story in particular)
- Measure and record actual average response time (needed to complete the SDG report's testing table, currently a placeholder)
- Insert an actual architecture diagram image into the SDG report (currently a text placeholder)

## N4. Presentation/communication guidance (already used once for a mid-sem review, reusable)
- Lead with the problem + why it matters (BNS/BNSS transition, hallucination risk)
- Highlight 2-3 technically interesting decisions, not everything: the MiniLM-vs-InLegalBERT empirical finding, the hybrid retrieval fix born from a real bug, the jurisdiction-filter bug-and-fix story, the security architecture reasoning
- Be upfront about limitations: scoped to a sample of judgment data (not exhaustive), "scheduled" not "real-time" updates (planned), no custom model training (deliberate, correct scoping decision)
- Do NOT mention in presentations: specific pip/torch/pandas debugging sagas, environment setup minutiae, git history cleanup — these are expected table-stakes, not differentiators, even though they consumed significant real development time

---

*END OF HANDOFF DOCUMENT. This captures the complete state of Legal Assist+ as of the end of Phase 4 (minus multilingual), with Phase 5 (Security) as the recommended next step. Paste this entire document as the first message in a new chat to resume with zero loss of context.*
