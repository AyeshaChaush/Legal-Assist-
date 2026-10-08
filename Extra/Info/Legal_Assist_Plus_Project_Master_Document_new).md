# Legal Assist+ — Master Project Document (v2, Full Update)
*(Formerly named: LegalMind AI → NyayaSetu → Legal Assist+ [FINAL])*

This document contains EVERY detail of the project so far — decisions, file names, test results, bugs found/fixed, and what's left. Upload/paste this at the start of a new chat to resume with zero loss of context.

**Last updated after:** Phase 4 (document upload + clause analysis) core build, with bug fixes applied.

---

# PART A: PROJECT IDENTITY & CORE CONCEPT

## A1. Project Title Evolution
1. LegalMind AI (original)
2. NyayaSetu (considered rename)
3. **Legal Assist+ (FINAL DECIDED NAME)**

## A2. What This Project Actually Is (core concept — don't lose this)
Legal Assist+ is **not just a general legal Q&A chatbot**. It has TWO core capabilities working together:

1. **General Legal Knowledge Q&A** — answers questions about Indian law (BNS, BNSS, BSA, Constitution, Central/State Acts) using RAG, grounded strictly in verified statute text, with citations.
2. **Document Upload & Analysis (THE CORE ORIGINAL IDEA — do not deprioritize this)** — a user uploads THEIR OWN document (contract, rental agreement, employment agreement, etc.), and the system acts like a lawyer reviewing it for them:
   - Proactively scans EVERY clause (not just reactive Q&A)
   - Flags risk level per clause (None/Low/Medium/High) with plain-language explanation
   - Cites relevant Indian law per clause where applicable
   - Checks the document against a checklist of standard protections and flags what's MISSING
   - Answers follow-up questions combining BOTH the user's own document AND the general legal knowledge base
   - Explicitly framed as informational/risk-flagging, NOT a replacement for a lawyer for high-stakes decisions (this framing is intentional and matches the project's own stated non-goal)

**Critical reminder for future sessions:** the user has explicitly pushed back once already on staying too narrowly scoped to "just document Q&A" — the vision is broader: **the system should do what a lawyer does for a client** — identify mistakes, flag risks, explain clauses, check compliance, not just answer isolated questions. Keep expanding this feature set; don't shrink it back down to simple Q&A.

## A3. Problem Statement
- Legal documents are lengthy and complex.
- Most people don't understand legal terminology.
- Manually searching across multiple Acts/judgments is time-consuming.
- Generic AI chatbots hallucinate legal answers (real cases of lawyers sanctioned for AI-hallucinated citations).
- Recent IPC→BNS, CrPC→BNSS, Evidence Act→BSA transition (effective 1 July 2024) adds confusion.
- People sign contracts/agreements without understanding risky clauses because consulting a lawyer for every document is expensive/inaccessible.

---

# PART B: SYSTEM ARCHITECTURE — WHAT'S ACTUALLY BUILT

## B1. High-Level Architecture (current state)

```
                    ┌─────────────────────────────┐
                    │   data/statutes/cleaned/     │
                    │   19 structured JSON files   │
                    │   (BNS, BNSS, BSA, IPC,      │
                    │   CrPC, Evidence Act,         │
                    │   Constitution, 9 Central     │
                    │   Acts, 2 Maharashtra Acts)   │
                    └──────────────┬────────────────┘
                                   │
                          build_vector_db.py
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │   data/vector_db/            │
                    │   legal_index.faiss           │
                    │   chunk_metadata.pkl          │
                    │   (5,005 chunks, MiniLM       │
                    │   embeddings, dim 384)         │
                    └──────────────┬────────────────┘
                                   │
                ┌──────────────────┴──────────────────┐
                │                                       │
                ▼                                       ▼
    query_legal_assist.py                  analyze_document.py
    (Phase 3: general Q&A)                 (Phase 4: document review)
    - User asks a legal question           - User uploads a PDF (their contract)
    - Retrieves top-5 law chunks           - Splits into clauses
      (semantic + exact section match)     - Full automatic risk review of
    - Groq LLM answers with citations        every clause + missing-clause check
                                            - Follow-up Q&A: retrieves BOTH
                                              document clauses (exact + semantic)
                                              AND law chunks, combined answer
```

## B2. Complete File Inventory (project root: `Legal Assist +` folder)

| File | Purpose | Status |
|---|---|---|
| `requirements.txt` | Python package list | Done |
| `.env` | Stores `GROQ_API_KEY` (gitignored, never committed) | Done |
| `.gitignore` | Excludes `venv/`, `__pycache__/`, `.env`, raw PDFs | Done |
| `test.py` | Original Step-1 environment sanity check | Done, no longer actively used |
| `setup_datasets.py` | Downloads Hugging Face datasets + embedding models | Done, ran once |
| `retry_missing_datasets.py` | Standalone retry for IL-TUR/OpenNyAI (gated datasets) | Done, used once |
| `retry_iltur_configs.py` | Retry IL-TUR with specific configs (lsi, pcr, summ) | Done, used once |
| `clean_documents.py` | Original generic PDF→JSON cleaning script (Phase 1) | Superseded — actual cleaning was done via a separate Claude chat using a structured prompt (see Part D) |
| `build_vector_db.py` | Chunks all statute JSONs, generates embeddings, builds FAISS index | **Active, final** |
| `query_legal_assist.py` | Phase 3: general legal Q&A RAG pipeline (terminal tool) | **Active, final** (as of last testing round) |
| `analyze_document.py` | Phase 4: document upload + full clause review + combined Q&A | **Active, final** (as of last bug-fix round — verification pending, see Part F) |

**Independence note:** `query_legal_assist.py` and `analyze_document.py` are fully independent scripts. Neither imports the other. They both separately read from `data/vector_db/` (built once by `build_vector_db.py`). Editing one never affects the other. Both use the same Groq setup and embedding model, but each has its own copy of these settings (not shared code).

## B3. Folder Structure (data/)

```
data/
├── statutes/
│   ├── cleaned/          <-- ALL 19 structured JSON files live here (see Part C)
│   ├── legacy/            <-- created but unused (legacy Acts went into cleaned/ directly)
│   └── state/              <-- created but unused (state Acts went into cleaned/ directly)
├── judgments/
│   ├── il-pcsr/            <-- 5,017 train + 627 dev + 627 test cases, statute+precedent linked
│   ├── kanoongpt/          <-- eCourts judgments with metadata
│   ├── opennyai/            <-- 11,970 judgments (Court_Name, Cites, Cited_by, Doc_url, Text, etc.)
│   └── il-tur/
│       ├── lsi/             <-- Legal Statute Identification config
│       ├── pcr/             <-- Precedent/Prior Case Retrieval config
│       └── summ/            <-- Judgment Summarization config (7,030 train, 100 test)
├── models/
│   ├── InLegalBERT/         <-- downloaded, tested, NOT currently used (see Part E decision log)
│   └── MiniLM-L6-v2/         <-- downloaded (redundant with pip-installed sentence-transformers copy)
├── vector_db/
│   ├── legal_index.faiss     <-- FAISS index, 5,005 vectors, dim 384, built with all-MiniLM-L6-v2
│   └── chunk_metadata.pkl     <-- parallel metadata (act_name, section_number, title, text) per vector
├── contracts/                 <-- created, unused (CUAD dataset download failed, deprioritized)
└── raw_pdfs/                   <-- original downloaded Act PDFs before structuring
```

---

# PART C: COMPLETE DATASET INVENTORY

## C1. Statute JSON Files (all in `data/statutes/cleaned/`, 19 files total, ~5,005 chunks)

| # | File (approximate name) | Sections | Status |
|---|---|---|---|
| 1 | BSA_2023.json | 170 | Verified clean, section-mapped against TOC |
| 2 | Constitution_of_India_merged.json | 1,142 | Merged from 9 original PDF chunks by user |
| 3 | BNS (Bharatiya Nyaya Sanhita 2023) | ~358 | Structured |
| 4 | BNSS (Bharatiya Nagarik Suraksha Sanhita 2023) | ~531 | Structured |
| 5 | Indian_Penal_Code_1860_structured.json | 567 | **Verified complete**, no duplicates, Section 420 confirmed present |
| 6 | Code_of_Criminal_Procedure_1973_structured.json | 534 entries / 484 unique sections | **Verified complete**, no gaps (first attempt only had 43 sections — was discarded and redone) |
| 7 | Legal_Assist_Indian_Evidence_Act_1872_CLEAN.json | 185 entries / 167 unique sections | **Verified complete**, no gaps |
| 8 | Consumer Protection Act, 2019 | — | Structured |
| 9 | IT Act, 2000 | — | Structured |
| 10 | Motor Vehicles Act, 1988 | — | Structured |
| 11 | Indian Contract Act, 1872 | — | Structured |
| 12 | Negotiable Instruments Act, 1881 | — | Structured |
| 13 | Protection of Women from Domestic Violence Act, 2005 | — | Structured |
| 14 | POCSO Act, 2012 | — | Structured |
| 15 | Hindu Marriage Act, 1955 | — | Structured |
| 16 | RTI Act, 2005 | — | Was initially broken/empty, **redone and fixed** |
| 17 | Payment of Wages (Amendment) Act, 2017 | 3 | Correctly small (genuinely short amendment act, not broken) |
| 18 | Maharashtra_Rent_Control_Act_1999_structured.json | ~60 | Verified; **duplicate file was found and removed** (kept this version over the lowercase-named duplicate) |
| 19 | Maharashtra Land Revenue Code, 1966 | — | Structured |

**Schema used across all files:**
```json
{
  "act_name": "string",
  "section_number": "string",
  "section_title": "string",
  "text": "string",
  "chapter": "string (optional, present in some files)"
}
```

## C2. Judgment/Case-Law Datasets (Hugging Face)

| Dataset | Size | Access method | Status |
|---|---|---|---|
| IL-PCSR | 5,017 train / 627 dev / 627 test | `Exploration-Lab/IL-PCSR` (gated, access approved) | Downloaded, verified loadable |
| KanoonGPT | — | `KanoonGPT/indian-case-laws` | Downloaded |
| OpenNyAI | 11,970 judgments | `opennyaiorg/InJudgements_dataset` (gated, access approved) | Downloaded, verified |
| IL-TUR (lsi, pcr, summ configs) | summ: 7,030 train / 100 test | `Exploration-Lab/IL-TUR` (gated, access approved) | Downloaded 3 of 8 available configs (lsi, pcr, summ — chosen as most relevant; skipped bail, lner, lmt, rr, cjpe) |
| CUAD (contract clauses) | — | `theatticusproject/cuad-qa` | **Failed** — Hugging Face deprecated "dataset loading scripts" for this repo. Not fixed, deprioritized (not core-blocking). Manual download alternative noted: atticusprojectai.org/cuad |

**Note: these judgment datasets are downloaded but NOT YET integrated into the vector database.** Only the 19 statute JSON files are currently embedded in `legal_index.faiss`. Integrating judgment data is a planned future enhancement, not yet done.

## C3. Embedding Models

| Model | Status | Decision |
|---|---|---|
| `all-MiniLM-L6-v2` | **ACTIVE — used in production** | Chosen after head-to-head empirical testing (see Part E) |
| `InLegalBERT` (`law-ai/InLegalBERT`) | Downloaded, tested, **NOT used** | Empirically performed WORSE at retrieval despite being legal-domain-specific — see decision log in Part E |

---

# PART D: HOW DATA WAS CLEANED (methodology, for the report)

1. **Statutes** (BSA, Constitution, BNS, BNSS, IPC, CrPC, Evidence Act, 9 Central Acts, 2 State Acts): PDFs downloaded manually from India Code / NCRB SANKALAN, then structured into JSON using **a separate Claude chat with a standardized cleaning prompt** (not a local Python script) — the prompt instructed extraction of section number, title, and full text, output as JSON, with the rule "do not paraphrase, keep original wording."
2. **Validation method used for BSA specifically** (as a proof of concept, done via code in this chat): raw text was parsed by first extracting the Act's own Table of Contents to get an authoritative, sequential list of section numbers, THEN searching for each section's position in the body text in that exact order. This avoided the risk of naive section-number pattern matching being confused by cross-references (e.g., "as mentioned in section 35" appearing inside the text of a different section).
3. **Verification performed on every uploaded structured file:** entry count, duplicate section number check, gap detection (comparing found section numbers against the expected numeric range), and spot-checking specific known important sections (e.g., confirmed IPC Section 420 present, confirmed CrPC Sections 41/154/161/164/173/207/313/437/438 all present).
4. **Two real data-quality bugs were caught and fixed this way:** an empty/broken RTI Act JSON (redone), and an incomplete CrPC file with only 43 of 484 sections (redone, second attempt was fully complete).

---

# PART E: KEY TECHNICAL DECISIONS & DECISION LOG (important — includes reasoning, not just outcomes)

## E1. RAG Framework: Custom-built, NOT LangChain/LlamaIndex
**Decision:** Built the entire RAG pipeline (retrieval, prompt construction, LLM calling) by hand rather than using a framework.
**Reasoning:** Learning value, debugging transparency, stronger interview talking point, fewer dependency/compatibility risks. Explicitly discussed and decided against switching mid-project. LlamaIndex/LangChain could still be considered later for narrow use (e.g., PDF loaders) but not adopted as the core engine.

## E2. LLM Provider: Groq (not Gemini, not OpenAI/Claude directly)
**Current model in use:** `openai/gpt-oss-20b` (an open-weight OpenAI model running on Groq's infrastructure)
**Why this specific model:** Groq's available model catalog changed by the time of testing — no plain Llama models were available on the account. Confirmed via `client.models.list()`. Options were: `allam-2-7b`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `groq/compound`, `groq/compound-mini`, plus audio/TTS/safety models not usable for chat. Chose `openai/gpt-oss-20b` for speed; `openai/gpt-oss-120b` noted as a "swap in for higher quality, slower" option for final demo if desired.
**PENDING DECISION carried over from earlier discussion:** Switch to (or add) Gemini specifically when building the multilingual/Bhashini feature (Phase 4 item), since Gemini has stronger Indic-language handling. The LLM call is isolated in one function (`ask_llm()`), so swapping providers is a small, contained change when the time comes. **This has NOT been done yet.**

## E3. Embedding Model: MiniLM chosen over InLegalBERT (important empirical finding)
**What happened:** Hypothesized that InLegalBERT (trained on 5.4M Indian legal documents) would outperform a general-purpose model for legal retrieval. Rebuilt the vector database with InLegalBERT and re-ran the same test questions used with MiniLM.
**Result:** InLegalBERT performed MEASURABLY WORSE. Concrete example: the question "What does the Maharashtra Rent Control Act say about eviction of tenants?" — with MiniLM, retrieval correctly found Sections 45, 46, 42, 37, 18 (all directly on-topic). With InLegalBERT, it retrieved irrelevant Constitution sections and missed the actual eviction provisions entirely. Same pattern repeated for "burden of proof" and "dying declaration" questions.
**Why this happened (understood, not just observed):** InLegalBERT was pretrained for language understanding (fill-in-the-blank style tasks) on legal text, but was never fine-tuned specifically to produce good sentence-level embeddings for semantic similarity/retrieval. MiniLM, despite being general-purpose, WAS specifically trained via contrastive learning for exactly this task — and that specialized training mattered more than domain vocabulary knowledge.
**Decision:** Reverted to `all-MiniLM-L6-v2` as the final embedding model for both `build_vector_db.py` and `query_legal_assist.py`/`analyze_document.py`. InLegalBERT remains downloaded but unused.
**Value for the report/interview:** This is a genuinely good, evidence-based engineering story — "I hypothesized X, tested it, found it performed worse, and reverted based on data rather than assumption."

## E4. Retrieval: Hybrid approach added after real evidence of pure-semantic-search failure
**Problem found:** Pure semantic (vector) search is good at matching MEANING but bad at matching exact numeric identifiers. Concrete evidence: asking "What was Section 420 of the IPC?" initially retrieved Section 50 (a definitions clause) instead of Section 420 (confirmed present in the data), because semantic embeddings don't weight numeric tokens like "420" strongly.
**Fix implemented:** Added `exact_section_lookup()` (in `query_legal_assist.py`) and equivalent `exact` clause-number matching (in `analyze_document.py`) — a regex checks if the question mentions "Section X" / "Article X" / "Clause X" and guarantees that exact match is included in retrieval results, on top of normal semantic search. This is a real, working implementation of the "hybrid retrieval" novelty planned from the very start of the project.
**A second, separate bug was found and fixed the same way:** the exact-clause-number fix was initially only added to law-section retrieval, NOT to document-clause retrieval in `analyze_document.py`. This caused "Summarize clause 7 in simple terms" to retrieve completely wrong clauses (15, 1, 3). Fixed by replicating the same exact-match pattern into `retrieve_clauses()`.

## E5. Distance Threshold Calibration (evidence-based, not guessed)
**Method:** Ran ~15+ diverse test questions with the threshold effectively disabled, recorded the actual FAISS L2 distances for known-good matches vs. known-irrelevant matches.
**Data found:** Genuine, correct matches consistently scored 0.35–0.72. Weak/no-real-match cases (where the model correctly said "I don't have this information") scored 0.86–1.03.
**Final values set:**
- `query_legal_assist.py`: `DISTANCE_THRESHOLD = 1.0`
- `analyze_document.py` (law retrieval only): `LAW_DISTANCE_THRESHOLD = 0.85` — set STRICTER than the general Q&A tool, because in a contract-review context, citing wrong-domain law (e.g., Motor Vehicles Act sections showing up for a consulting-contract liability question) is worse than citing no law at all.

## E6. Groundedness / Anti-Hallucination: Proven reliable across extensive testing, not just designed-for
Across 20+ test questions (including deliberately fake ones like "Section 999 of the BNS" and a fictional "Indian Traffic Act"), the system has CONSISTENTLY refused to hallucinate, even when retrieval pulled irrelevant chunks. This held true across both embedding models tested and both scripts. This is the single most validated, defensible claim in the whole project.

---

# PART F: TESTING HISTORY & KNOWN ISSUES

## F1. query_legal_assist.py — Test Results Summary
Extensively tested with 20+ diverse questions across categories: basic factual lookup, cross-Act reasoning, old-law↔new-law mapping, hallucination-resistance, jurisdiction-specific (Maharashtra), plain-language explanation, and procedural questions.
**Result: consistently strong.** Correct citations, correct plain-language explanations, correct refusals on fake/unanswerable questions. Two real gaps were found and CLOSED during testing:
1. IPC/CrPC/Evidence Act text was originally entirely missing from the corpus (caused "Section 420 IPC" and "has Evidence Act been repealed" to fail) — FIXED by adding those 3 Acts (see Part C1).
2. Exact section-number retrieval weakness — FIXED (see Part E4).

**This file's current status: considered stable and final as of last confirmed test round.**

## F2. analyze_document.py — Test Results Summary
Tested using a sample "Consulting Services Agreement" PDF (16 clauses) placed in a `test/` subfolder.

**What worked well (validated, not just hoped-for):**
- Full automatic review correctly flagged real, specific legal issues: one-sided indemnification clause (cited Indian Contract Act Sections 222, 224), biased arbitrator-appointment clause in dispute resolution (cited Arbitration and Conciliation Act, 1996, with an actionable negotiation recommendation), liquidated damages concern (cited Sections 73/74), low liability cap concern (cited Consumer Protection Act Section 85). Did NOT manufacture risk on genuinely standard clauses (Force Majeure, Entire Agreement correctly marked low/no risk).
- Follow-up Q&A combining document clauses + general law worked well for most questions (e.g., "does this favor Client or Consultant", "what if there's a dispute", "how much notice to quit", "does this mention arbitration").
- Missing-clause checklist correctly identified missing late-payment penalty terms.

**Bugs found and FIXED during testing (all now patched in the current file):**
1. **Groq rate limit crash (429 error)** — free tier caps at 8,000 tokens/minute; large sequential calls exceeded it. Fixed with: retry-with-backoff wrapper, reduced `CLAUSE_BATCH_SIZE` (4→2), explicit `max_tokens` limits, paced `time.sleep()` between calls, and a much smaller/compact missing-clause-check prompt (uses 120-char clause summaries instead of full text).
2. **Empty LLM response bug** — "What is Schedule A?" once returned a completely blank answer. Fixed by adding empty-response detection + automatic retry + a clear fallback message if it persists.
3. **Answer truncation (mid-sentence cutoffs)** on longer follow-up answers — `max_tokens` was too low (900, inherited from the clause-batch-review setting). Fixed by raising follow-up Q&A specifically to `max_tokens=2048`.
4. **CRITICAL: "Summarize clause 7" retrieved completely wrong clauses** (15, 1, 3 instead of 7) — root cause: document-clause retrieval was PURE semantic search with no exact-number matching, even though this exact fix had already been made for law-section retrieval. Fixed by adding the same exact-match pattern to `retrieve_clauses()`.
5. **Wrong-domain law citation** — a liability-clause question pulled irrelevant Motor Vehicles Act sections (vehicle insurance law) instead of relevant contract law. The LLM caught and correctly dismissed these in its answer, but the underlying retrieval was still wrong. Mitigated (not fully "solved" — an inherent limitation of embedding-based search) by tightening `LAW_DISTANCE_THRESHOLD` to 0.85 specifically for this script.

**STATUS: fixes have been applied to the file but NOT YET RE-VERIFIED by the user as of this document's writing.** The very next action needed is to re-run `analyze_document.py` and specifically re-test:
- "Summarize clause 7 in simple terms" (should now find Clause 7 correctly)
- "What are all the ways this agreement can end?" (should no longer cut off mid-answer)
- "Is there a limitation of liability clause?" (to confirm the tightened threshold isn't over-filtering and still surfaces relevant law when it exists)

**Minor known limitation (documented, not fixed, low priority):** the missing-clause checklist check uses only the first 120 characters of each clause to save tokens/rate-limit budget — this caused one false positive (flagged "renewal terms" as missing when Clause 3 actually did mention renewal, just past the 120-char cutoff). Worth mentioning honestly in the final report as a documented tradeoff (thoroughness vs. rate-limit cost on the free tier), not silently ignored.

**Also noted (very minor, not fixed):** the clause-splitting regex occasionally mis-numbers a trailing signature-block section as "Clause 1" again (duplicate numbering) if the PDF's signature section happens to start with a line like "1." — cosmetic issue, hasn't broken retrieval, not urgent.

---

# PART G: ENVIRONMENT & INFRASTRUCTURE DETAILS

## G1. Local Development Environment
- **OS:** Windows (user's machine: `C:\Users\ASUS\OneDrive\Desktop\Code\Legal Assist +`)
- **Editor:** VS Code
- **Python version:** **3.11.0** (deliberately downgraded from 3.14 — Python 3.14 was too new and caused a Windows "Application Control policy" security block on `pyarrow`'s DLL, blocking `sentence-transformers`/`datasets` imports entirely. Switching to Python 3.11 resolved this permanently, since ML/data packages have far more mature, widely-trusted builds for 3.11.)
- **Virtual environment:** `venv/` (created with `py -3.11 -m venv venv`)
- **Version control:** Git + GitHub, repo name `Legal-Assist-` under user `AyeshaChaush`, public repo, `main` branch. `.gitignore` covers `venv/`, `__pycache__/`, `*.pyc`, `.env`, `data/raw_pdfs/*.pdf`.

## G2. API Keys & External Services
- **Groq API key** stored in `.env` as `GROQ_API_KEY` (never committed, gitignored)
- **Groq free tier constraint:** 8,000 tokens/minute rate limit — actively managed in code via batching, pacing, and retry logic (see Part E/F)
- **Hugging Face account:** created, access token generated, used for `hf auth login` (note: `huggingface-cli` is deprecated, replaced by `hf` command)
- **Bhashini API:** NOT yet set up (planned for multilingual feature, not started)

## G3. Installed Packages (cumulative, across requirements.txt + manual installs)
```
datasets, huggingface_hub, transformers, sentence-transformers, requests,
beautifulsoup4, tqdm, fastapi, uvicorn, groq, python-dotenv, faiss-cpu, pdfplumber, numpy
```

---

# PART H: NOVELTIES — STATUS OF EACH (what's built vs. still planned)

| Novelty (from original brainstorm) | Status |
|---|---|
| Hybrid + Adaptive Retrieval | **Partially built** — exact-number + semantic hybrid implemented and proven necessary by real test failures. "Adaptive" (query-complexity-based parameter adjustment) not yet done. |
| Knowledge-Graph-Augmented RAG | Not started |
| Explainable AI layer | **Partially built** — retrieved sources are shown to the user with relevance scores/distances before the answer (implemented in both scripts). A more polished/visual version is a planned Phase 4 task. |
| Hallucination/groundedness verification | **Built and extensively validated** — the LLM prompt instruction to refuse ungrounded answers has held up across 20+ adversarial test questions in both scripts. |
| Contract/Document Clause Risk Analysis | **Built — this is now the core feature**, expanded well beyond the original "nice to have" framing into a full proactive document review engine (see Part A2, B1, F2) |
| Jurisdiction-aware reasoning engine | **Data ready** (2 Maharashtra Acts structured and in the vector DB), but no dedicated state-selector filter/UI built yet — currently relies on the LLM naturally recognizing "Maharashtra Rent Control Act" etc. from retrieval, not an explicit jurisdiction filter mechanism. Planned Phase 4 task. |
| Legal Procedure/Workflow Generator | Not started |
| Multilingual + Voice Support | Not started (this is the trigger point for the pending Groq→Gemini decision, see E2) |
| Agentic Orchestration (routing to sub-indexes) | Not started |
| India-specific accessibility (old↔new law mapping, DigiLocker, NJDG, literacy mode) | Old↔new law mapping: DATA is now in place (IPC/CrPC/Evidence Act all structured), but no explicit "mapping table" UI/logic built — currently the LLM answers this by having both old and new Act text available in retrieval, not a structured lookup table. Everything else in this category: not started. |

---

# PART I: WHAT'S NOT YET DONE (full checklist, ordered roughly by planned sequence)

### Immediate next action (before anything else):
- [ ] **Re-verify `analyze_document.py`'s latest bug fixes** by re-running the 3 specific test questions listed in Part F2, and confirm clean before considering Phase 4's document-review feature fully closed out

### Rest of Phase 4:
- [ ] Jurisdiction filter — explicit state selector / Central-vs-State applicability logic (not just implicit retrieval)
- [ ] Multilingual support (Bhashini integration) — **remember the pending Groq→Gemini decision here**
- [ ] Explainability polish — more visual/structured presentation of retrieved sources and confidence
- [ ] Consider integrating judgment/case-law datasets (IL-PCSR, OpenNyAI, KanoonGPT, IL-TUR) into the vector database — currently downloaded but NOT embedded/searchable yet
- [ ] Continue expanding "act like a lawyer" capabilities per the user's explicit direction (Part A2) — e.g., deadline/obligation extraction, comparison against "market standard" terms, negotiation-point suggestions

### Phase 5 — Security (not started):
- [ ] AES-256 encryption for uploaded documents
- [ ] JWT authentication + RBAC
- [ ] Auto-deletion policy for uploaded files
- [ ] SHA-256 hash + lightweight blockchain anchoring for document integrity (NOT for storing content — see original security decision: cybersecurity primary, blockchain only for tamper-evidence)
- [ ] DPDP Act 2023 compliance (consent, deletion rights)

### Phase 6 — Real-time law updates (not started):
- [ ] Scraper for India Code / e-Gazette (no public API exists — confirmed)
- [ ] Change detection + versioned storage
- [ ] Admin review panel before re-embedding updates
- [ ] "Last verified" timestamp shown to users

### Phase 7 — Frontend (not started):
- [ ] Currently everything is terminal/command-line only
- [ ] Needs a real UI, especially once document upload becomes user-facing (uploading via terminal `input()` prompt is not viable for a real product/demo)
- [ ] Streamlit (fast) or React (polished) — decision not yet made

### Phase 8 — Evaluation & Submission (not started):
- [ ] Formal test set (30-50 questions) with accuracy measurement
- [ ] Baseline comparison vs. plain ChatGPT (no RAG) to demonstrate hallucination reduction
- [ ] Word (.docx) formatted synopsis for official submission
- [ ] System architecture diagram
- [ ] Week-wise Gantt chart/timeline
- [ ] Final report incorporating all decision-log reasoning from Part E (this is genuinely strong material for a credit project's evaluation criteria)

---

# PART J: SUPPORTING REFERENCE MATERIAL (unchanged from earlier planning, still valid)

## J1. Security Architecture Decision (cybersecurity primary, blockchain secondary)
Full reasoning already documented and decided: AES-256 encryption + JWT + RBAC + auto-deletion as the PRIMARY confidentiality layer; SHA-256 hash anchored on a lightweight blockchain ONLY for tamper-evidence/integrity proof, never for storing or exposing actual document content. One-line summary for guide: *"We secure user documents using encryption and access control as the main layer, and use blockchain only to verify document integrity — not to store or expose actual content."*

## J2. Real-Time Law Update Pipeline (planned design, not built)
Since India Code/e-Gazette have no public API, "real-time" = a scheduled scraper + change detection + human review admin panel + "last verified" timestamp. Call this a "scheduled update pipeline" in the report, not "real-time" — more honest and still credit-worthy.

## J3. Research Papers to Cite
1. LawPal: A RAG-Based System for Enhanced Legal Accessibility in India — `arxiv.org/html/2502.16573v1`
2. Domain-Partitioned Hybrid RAG for Legal Reasoning (India) — `arxiv.org/pdf/2602.23371`
3. HyPA-RAG (adaptive RAG for legal/policy) — `arxiv.org/pdf/2409.09046`
4. LegalBench-RAG (evaluation benchmark) — `arxiv.org/abs/2408.10343`
5. Bridging Legal Knowledge and AI (knowledge graphs + RAG) — `arxiv.org/pdf/2502.20364`
6. Where Does Legal AI Fail? (ACM CIKM '24) — `dl.acm.org/doi/10.1145/3746252.3761151`

## J4. Competitor Analysis (for literature review section)
Manupatra/SCC Online/CaseMine = powerful but costly/professional-only. VIDUR AI/BharatLaw.AI = newer, free-tier, still maturing. ChatGPT/Gemini = free but hallucination-prone, no citations, no BNS/BNSS awareness, no document-specific risk analysis. **Legal Assist+'s differentiation: free + citizen-friendly + verified citations + confidential + BNS/BNSS-era correct + proactive document risk review — no single existing Indian tool combines all of these.**

## J5. Interview/Presentation Framing Guidance (already discussed, summarized)
- Lead with the problem + why it matters (BNS/BNSS transition, hallucination risk)
- Highlight 2-3 technically interesting decisions, not everything: the MiniLM-vs-InLegalBERT empirical finding (Part E3), the hybrid retrieval fix born from a real bug (Part E4), the security architecture reasoning (Part J1)
- Mention the section-parsing-via-TOC-cross-validation technique (Part D2) as a concrete, specific technical story
- Be upfront about limitations: scoped to a few Acts + 2 states, "scheduled" not "real-time" updates, no training of custom models (deliberate, correct scoping decision, not a shortcut)
- Do NOT mention: specific pip/Unicode/PowerShell debugging, environment setup minutiae, folder structure details — these are expected table-stakes, not differentiators

---

*End of master document. This is a complete state capture as of the Phase 4 document-analysis bug-fix round. The single most important next action is listed at the top of Part I. Upload/paste this file in a new chat to resume with full context.*
