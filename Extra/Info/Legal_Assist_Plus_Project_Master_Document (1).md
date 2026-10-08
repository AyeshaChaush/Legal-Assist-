# Legal Assist+ — Master Project Document
*(Formerly named: LegalMind AI → NyayaSetu → Legal Assist+ [FINAL])*

This document contains everything discussed and decided so far. Use this to resume work in a new chat without losing any detail, novelty, or decision.

---

## 1. PROJECT OVERVIEW

**Final Title:** Legal Assist+
**Subtitle (for report):** An Explainable, Secure, RAG-Based Legal Decision Support Platform for Indian Law

**One-line description:** An AI platform that answers legal queries by retrieving information ONLY from verified Indian legal sources (Constitution, BNS, BNSS, BSA, Central/State Acts, court judgments), then generates cited, explainable, plain-language answers — instead of hallucinating like generic chatbots.

**Target users:** Citizens, law students, legal professionals (not a lawyer replacement — informational support only).

### Problem Statement
- Legal documents are lengthy and complex.
- Most people don't understand legal terminology.
- Manually searching across multiple Acts/judgments is time-consuming.
- Generic AI chatbots generate incorrect/unsupported/hallucinated legal answers (real cases of lawyers sanctioned for AI-hallucinated case citations).
- Recent IPC→BNS, CrPC→BNSS, Evidence Act→BSA transition (effective 1 July 2024) adds confusion — most tools/people still reference old law.

### Proposed Solution (core feature list)
- Answer legal queries using RAG grounded strictly in verified sources
- Section-wise citations for every answer
- Plain-language explanation of legal terms/concepts
- Upload & analyze personal legal documents/contracts
- Suggest possible legal procedures (informational only, not advice)
- Multi-language (Indic) support

---

## 2. WHAT IS RAG (for report's technical background section)

RAG = Retrieval-Augmented Generation.
Two-step process:
1. **Retrieval:** On a user query, search a fixed/trusted knowledge base (vector database of legal documents) and pull the most relevant chunks.
2. **Generation:** LLM generates the answer using ONLY those retrieved chunks as grounding, and must cite them.

**Why RAG over a plain LLM chatbot:** Plain LLMs answer from memorized training data → prone to hallucination (fabricated sections/case names). RAG forces grounding in real, verified, updatable documents.

**Typical pipeline:**
Documents → chunking → embeddings → vector database → user query → semantic search → top-k relevant chunks → LLM (with those chunks as context) → cited answer.

---

## 3. NOVELTIES (to elevate beyond a "basic RAG chatbot" — REQUIRED for credit-level depth)

1. **Hybrid + Adaptive Retrieval** — combine dense vector search (semantic) with keyword/BM25 search (exact section number matching); optionally adapt retrieval depth/parameters based on query complexity (inspired by HyPA-RAG paper).
2. **Knowledge-Graph-Augmented RAG** — build a legal knowledge graph linking Section → cross-references → amendments → related judgments → definitions, for multi-hop reasoning (e.g., "which BNS section replaced this IPC section, and how have courts interpreted it?").
3. **Explainable AI (XAI) layer** — show WHY an answer was given: highlight exact matching source text, show confidence/relevance score per retrieved source, visually separate "what the law says" (retrieved text) from "AI's plain-language interpretation" (generated explanation).
4. **Hallucination / Groundedness Verification** — after generation, run a self-check step confirming every claim in the answer is actually supported by retrieved text (entailment-style check). Flag ungrounded claims.
5. **Contract/Document Clause Risk Analysis** — for uploaded documents, classify clauses and flag risky ones (one-sided termination, unusual indemnity, missing arbitration clause, etc.) with plain-language risk explanation.
6. **Jurisdiction-Aware Reasoning Engine** — tag all content as Central or State-specific; let the system explicitly state which type of law applies (see Section 6).
7. **Legal Procedure/Workflow Generator** — given a situation, generate a step-by-step procedural flow (which forum to approach, required documents, likely timeline) instead of just a paragraph answer.
8. **Multilingual + Voice Support** — Indic language translation (Bhashini) + voice input for low-literacy/rural accessibility.
9. **Agentic Orchestration (stretch/advanced novelty)** — a controller agent that routes a query to the correct sub-index (Constitution vs BNS vs case law vs state acts) rather than one flat retriever — reflects cutting-edge "modular, explainable legal AI" research direction for India.
10. **India-specific accessibility features** (see Section 7): old law ↔ new law (IPC↔BNS, CrPC↔BNSS, Evidence Act↔BSA) section mapping, DigiLocker/eSign integration, NJDG/eCourts case-status lookup, legal literacy quiz mode for students.

---

## 4. SECURITY ARCHITECTURE — CYBERSECURITY vs BLOCKCHAIN (Decision + Justification)

### Decision
**Cybersecurity = primary mechanism** (protects confidentiality of uploaded documents).
**Blockchain = secondary/optional mechanism** (only for tamper-evidence/integrity proof, NOT for storing or protecting content).

### Why NOT blockchain for confidentiality
Blockchains are designed to make data accessible/verifiable across a network — the opposite of "keep this secret." Blockchain guarantees integrity/immutability (proof a record wasn't altered), not secrecy.

### Why cybersecurity is the right primary choice
Directly solves the actual stated problem: "users upload confidential legal documents and need trust that no one else can see them."

### Comparison Table
| | Cybersecurity (encryption/access control) | Blockchain |
|---|---|---|
| Confidentiality of content | ✅ Direct fit | ❌ Not designed for this |
| Tamper-evidence | Partial | ✅ Strong |
| Implementation complexity for student project | Moderate | High (avoid full implementation; use only hash-anchoring) |
| What it actually protects | The document itself | A hash/fingerprint of the document |

### Final Hybrid Design (what to actually build)
**Layer 1 — Confidentiality (Cybersecurity, main layer):**
- AES-256 encryption of uploaded documents (at rest)
- TLS/HTTPS (in transit)
- JWT-based authentication + Role-Based Access Control (RBAC)
- Per-user data isolation (User A can never access User B's files)
- Auto-deletion/expiry policy (e.g., delete after 30 days)
- No training of AI models on user-uploaded data
- Input validation/sanitization (prevent injection attacks, malicious file uploads, malware scanning)
- Rate limiting (prevent brute force/abuse)
- Secrets management (API keys/DB credentials in environment variables, never hardcoded)
- Compliance with India's Digital Personal Data Protection (DPDP) Act, 2023 — explicit consent, right to deletion, privacy policy

**Layer 2 — Integrity (Blockchain, secondary layer):**
- Generate SHA-256 hash of each document at upload
- Anchor ONLY the hash (not the content) on a lightweight/permissioned blockchain (Hyperledger Fabric testnet is sufficient for demo — full public blockchain NOT required/not recommended)
- Purpose: prove a document wasn't tampered with after upload, without exposing its content
- For a basic/demo version, a simple database table storing hash + timestamp is an acceptable simplified substitute; full blockchain is a stretch goal

### One-line summary for guide/panel
"We secure user documents using encryption and access control (cybersecurity) as the main layer, and use blockchain only to verify document integrity — not to store or expose actual content."

---

## 5. REAL-TIME LAW UPDATE PIPELINE

### Reality check
India Code, e-Gazette, and NCRB SANKALAN do **NOT** provide public developer APIs. True "real-time" is not feasible — call this a **"scheduled update pipeline"** in the report (more honest and still fully credit-worthy).

### Feasible Pipeline Design
1. **Source only from authoritative primary sources:** India Code portal (definitive digital repository, every section linked to amendments), e-Gazette of India (official notification source), PIB press releases (for notification dates), NCRB SANKALAN (BNS/BNSS/BSA official text), state gazette portals, eCourts/NJDG (judgments).
2. **Scraper (not API):** Python script (BeautifulSoup/Selenium) that periodically (weekly/monthly) checks these sources for new notifications/amendments.
3. **Change detection:** Compare newly scraped text against currently stored version; flag differences only (avoid re-processing everything).
4. **Versioned vector store:** Store each legal provision with an effective-date range (like Git version history), so the system can distinguish "what the law says today" vs "what applied when an event occurred" — critical given the IPC→BNS transition rule (offence date determines which law applies).
5. **Human-in-the-loop validation:** Admin review panel where a reviewer approves/rejects a detected update before it's re-embedded into the vector database — realistic, safe, and demonstrates good practice for a student project (no need for 24/7 live automation).
6. **Transparency to users:** Show a "Last verified against source on [date]" badge on every answer.

### Key fact to remember for report
BNS, BNSS, and BSA were notified in the Gazette of India on 25 December 2023; most provisions came into force 1 July 2024, replacing IPC, CrPC, and the Indian Evidence Act respectively.

---

## 6. REGIONAL / JURISDICTION-WISE LAW HANDLING

### Problem
India has Central Acts + State Amendments + State-specific Acts (land, rent control, excise, agriculture) + personal laws — all varying by state/UT. Full 28-state coverage is NOT feasible for one project.

### Feasible Scoped Design
1. **Metadata tagging:** Every document chunk tagged with jurisdiction (`Central` / specific state name / UT).
2. **State selector in UI:** User picks their state (dropdown); retrieval filters by Central + selected state.
3. **Explicit applicability statement:** System must clearly state "this is a Central law, applies nationwide" vs "this varies by state; here is your state's version" — never silently pick one.
4. **Scope for demo:** Central laws (BNS, BNSS, BSA, Constitution, IT Act, Consumer Protection Act) as the main corpus (covers most citizen queries) + 2–3 states' amendments as proof-of-concept (recommend: your own state + one other).
5. **Report framing:** Present this as a "scalable architecture" — metadata-tagging design supports adding more states later even though only 2–3 are populated for the demo.

---

## 7. INDIA-SPECIFIC NOVELTIES (full list)

- Multilingual support via **Bhashini** (Govt of India initiative) / **AI4Bharat IndicTrans2** (open-source backup) — translate both queries and answers across Indic languages.
- Voice-based query input for low-literacy/rural users.
- Low-bandwidth/offline-friendly mode for uneven connectivity areas.
- **DigiLocker/eSign integration** for verifying uploaded document authenticity.
- **NJDG/eCourts integration** for real case-status lookups tied to a query.
- **Legal literacy mode for students** — quizzes/explanations mapping BNS/BNSS/BSA to old IPC/CrPC/Evidence Act sections (major current pain point for law students).
- Explicit "not legal advice" disclaimers + escalation path to verified lawyers/legal aid clinics for anything beyond informational scope.

---

## 8. COMPETITOR / EXISTING SYSTEMS ANALYSIS (for "related work" / literature review section)

| System | What it offers | Key flaws |
|---|---|---|
| **Manupatra / SCC Online** | Very complete Indian legal-tech suite (25-year-old platform) — research, case management, compliance, contracts, IPR | Expensive/paywalled, built for professionals not citizens, not conversational, no plain-language explanation |
| **CaseMine (AMICUS AI)** | AI-powered case-law research + strategic guidance assistant | Caps document handling at 100MB, litigation/precedent-focused, not citizen-facing |
| **VIDUR AI, BharatLaw.AI, NyayGuru, KanoonGPT (chat tier)** | Native Indian drafting, multilingual research, free-tier chat | Emerged only ~2024, still maturing; reliability/coverage varies widely on free tier |
| **Generic tools (ChatGPT, Gemini)** | Free, explains legal concepts simply, good for brainstorming | No understanding of BNS/BNSS transition, can't generate court-format documents, no Indian court DB integration, no vernacular legal drafting, hallucinates fake case law/citations |

**Your differentiation (state clearly in report):** Existing tools are either professional-grade but paywalled/complex, OR free but ungrounded/hallucination-prone. Almost none combine: citizen-facing simplicity + verified-source grounding + explainability + confidentiality-by-design + BNS/BNSS-era correctness in one open, India-focused platform. **This combination is Legal Assist+'s core novelty — not RAG itself, which by now is a fairly standard technique.**

---

## 9. RESEARCH PAPERS TO READ / CITE

1. **LawPal: A RAG-Based System for Enhanced Legal Accessibility in India** — closest existing comparable project; read to clearly differentiate your work. `arxiv.org/html/2502.16573v1`
2. **Domain-Partitioned Hybrid RAG for Legal Reasoning: Toward Modular and Explainable Legal AI for India** — directly aligned with "explainable AI + RAG + India" framing; source for agentic routing/modularity novelty. `arxiv.org/pdf/2602.23371`
3. **HyPA-RAG: A Hybrid Parameter-Adaptive RAG System for AI Legal and Policy Applications** — source for adaptive-retrieval novelty. `arxiv.org/pdf/2409.09046`
4. **LegalBench-RAG: A Benchmark for RAG in the Legal Domain** — for evaluating retrieval quality. `arxiv.org/abs/2408.10343`
5. **Bridging Legal Knowledge and AI: RAG with Vector Stores, Knowledge Graphs, and Hierarchical NMF** — source for knowledge-graph novelty. `arxiv.org/pdf/2502.20364`
6. **Where Does Legal AI Fail? Evaluating RAG Pipelines** (ACM CIKM '24) — for "limitations/future work" section on hallucination sources. `dl.acm.org/doi/10.1145/3746252.3761151`
7. **Retrieval Augmented Generation Framework for Nepali Legal QA** — methodology reference for low-resource-language legal RAG (relevant to multilingual goal). `arxiv.org/pdf/2606.07523`
8. **Blockchain cybersecurity implications in legal systems** — justification for hybrid encryption + hash-anchoring design. `arxiv.org/pdf/2410.06143`

---

## 10. TITLE EVOLUTION (for reference)

1. LegalMind AI (original)
2. NyayaSetu (proposed rename — Hindi/Sanskrit rooted: "Nyaya" = justice, "Setu" = bridge)
3. **Legal Assist+ (FINAL DECIDED NAME)**

---

## 11. SYNOPSIS (submission-ready, using final name)

**Title:** Legal Assist+ — An Explainable RAG-Based Legal Decision Support System for Indian Law

**Introduction:** Access to accurate legal information in India is difficult due to lengthy statutes, complex terminology, and the recent transition from IPC/CrPC/Evidence Act to BNS/BNSS/BSA. Generic AI chatbots often hallucinate legal facts, risking real-world harm. Legal Assist+ grounds every answer strictly in verified legal sources, with security and explainability built in from the start.

**Problem Statement:** Existing tools are either professional-grade but costly (Manupatra, SCC Online, CaseMine) or free but ungrounded and hallucination-prone (ChatGPT, Gemini). None combine citizen-friendly access, verified citations, confidential document handling, and real-time legal accuracy in one platform.

**Objectives:**
- Answer legal queries using RAG, grounded only in verified sources
- Provide section-wise citations with explainable reasoning (XAI)
- Securely process uploaded personal legal documents
- Keep the legal database updated via a scheduled pipeline from official sources
- Support state-wise jurisdiction differences
- Provide multilingual access for wider reach

**Proposed Methodology:**
1. **Data Ingestion:** Manually sourced + scraped statutes/amendments from India Code, e-Gazette, NCRB SANKALAN; judgments from eCourts/NJDG-derived open datasets; PIB feeds for notification dates
2. **Retrieval:** Hybrid semantic + keyword search over a vector database, enhanced with a legal knowledge graph
3. **Generation:** LLM produces answers strictly from retrieved content, with mandatory citations
4. **Explainability Layer:** Shows matched source text + confidence score behind each answer
5. **Cybersecurity Layer:** AES-256 encryption, JWT + RBAC, auto-deletion policy, DPDP Act compliance, SHA-256 hash anchored on lightweight blockchain for integrity verification (not storage)
6. **Jurisdiction Engine:** Tags content Central/State and filters by user's selected state

**APIs/Data Sources:** India Code Portal, e-Gazette of India, PIB press releases, eCourts/NJDG, Bhashini API

**Tools/Technologies:** Python, LangChain/LlamaIndex, FAISS/Pinecone, LLM API, AES encryption, Hyperledger/testnet blockchain (hash anchoring), React/Streamlit

**Expected Outcome:** A secure, explainable, citation-grounded, and periodically updated legal assistant that improves legal accessibility without replacing professional legal advice.

---

## 12. FEASIBILITY NOTE (IMPORTANT — do not lose this)

- **Do NOT train an LLM from scratch** — not feasible for a student project (needs massive compute/data).
- **Correct approach:** Use an existing pretrained LLM via API (Groq/Gemini/OpenAI/Claude) as the generator + build your OWN RAG pipeline + retrieval database around it (this IS your real technical contribution) + optionally fine-tune a small open-source model on Indian legal text for one specific sub-task only (stretch goal, not required).
- This mirrors how real Indian legal-AI research projects (LawPal, etc.) are actually built — none train foundation models from scratch either.

---

## 13. REQUIREMENTS LIST (full)

### 13.1 Datasets Required — Detailed List

**Category A — Core Statutory Documents (Priority 1, manual download, no API exists):**
- Constitution of India — indiacode.nic.in
- Bharatiya Nyaya Sanhita (BNS) 2023 — indiacode.nic.in / sankalan.ncrb.gov.in
- Bharatiya Nagarik Suraksha Sanhita (BNSS) 2023 — indiacode.nic.in / sankalan.ncrb.gov.in
- Bharatiya Sakshya Adhiniyam (BSA) 2023 — indiacode.nic.in / sankalan.ncrb.gov.in
- IPC 1860 (legacy, for mapping) — indiacode.nic.in
- CrPC 1973 (legacy, for mapping) — indiacode.nic.in
- Indian Evidence Act 1872 (legacy, for mapping) — indiacode.nic.in
- Official BNS↔IPC / BNSS↔CrPC / BSA↔Evidence Act section-mapping tables — NCRB SANKALAN portal

**Category A2 — Citizen-facing Central Acts (pick 8–10):**
Consumer Protection Act 2019, IT Act 2000 (+amendments), Motor Vehicles Act 1988, RTI Act 2005, Indian Contract Act 1872, Negotiable Instruments Act 1881, Protection of Women from Domestic Violence Act 2005, Rent Control Act (1–2 states), Hindu Marriage Act 1955 / Special Marriage Act 1954, Payment of Wages Act/Minimum Wages Act — all from indiacode.nic.in or respective state sites.

**Category A3 — State-Specific (pick 2–3 states):**
State amendment to a Central Act, state-specific Acts (land revenue code, excise act), state e-Gazette notifications — from respective state law department/gazette websites.

**Category B — Case Law/Judgment Datasets:**
- IL-TUR (umbrella — includes ILDC, HLDC, ILSI, IL-PCR, In-Abs, MiLPaC, RR): `huggingface.co/datasets/Exploration-Lab/IL-TUR`
- ILDC (~34,800 SC judgments 1947–2020): included in IL-TUR
- IL-PCSR (gated, precedent+statute retrieval — closest to RAG task): `huggingface.co/datasets/Exploration-Lab/IL-PCSR`
- HLDC (Hindi bail judgments, multilingual use): part of IL-TUR
- KanoonGPT Indian Case Laws (eCourts + metadata): `huggingface.co/datasets/KanoonGPT/indian-case-laws`
- KanoonGPT Open Initiative (raw PDFs): `kanoongpt.in/open-initiative`
- OpenNyAI InJudgements Dataset (categorized judgments): `huggingface.co/datasets/opennyaiorg/InJudgements_dataset`
- NyayaAnumana (largest dataset, 22L+ cases): search HF "NyayaAnumana"; paper `arxiv.org/pdf/2412.08385`
- Indian Kanoon website (manual reference): `indiankanoon.org`

**Category C — Pretrained Models:**
- InLegalBERT (legal embeddings, trained on 5.4M Indian legal docs): `huggingface.co/law-ai/InLegalBERT`
- LegalBERT (nlpaueb, baseline comparison): `huggingface.co/nlpaueb/legal-bert-base-uncased`
- sentence-transformers/all-MiniLM-L6-v2 (lightweight fallback)

**Category D — Contract Clause Datasets (for clause-risk feature):**
- CUAD (13,000+ annotated clauses, 13 categories): `atticusprojectai.org/cuad`
- LEDGAR (clause classification): search HF "LEDGAR"
- ContractNLI (entailment/contradiction detection): GitHub "ContractNLI Stanford"
- *(Note limitation in report: none are India-specific — no large India-specific contract dataset currently exists)*

**Category E — Multilingual Resources:**
- Bhashini API/models (register at bhashini.gov.in)
- MiLPaC (parallel corpus, English + 9 Indic languages) — part of IL-TUR
- AI4Bharat IndicTrans2 (open-source backup): `github.com/AI4Bharat/IndicTrans2`

**Category F — Aggregators/Reference (browse only):**
- `github.com/openlegaldata/awesome-legal-data`
- `github.com/OpenNyAI`
- `openjustice-in.github.io`

### 13.2 LLM (Generation) Options — pick ONE to start
| Option | Why | Cost |
|---|---|---|
| Groq API (Llama-3/Mistral) | Very fast, generous free tier — RECOMMENDED START | Free |
| Google Gemini API | Free tier, good multilingual pairing with Bhashini | Free |
| OpenAI API (GPT-4o-mini) | Reliable, well-documented | Small paid cost |
| Anthropic Claude API | Strong reasoning, good citation discipline | Small paid cost |

Design system to be **model-agnostic/swappable** — good architecture point for report.

### 13.3 APIs Required
- LLM API (Groq/Gemini/OpenAI/Claude)
- Bhashini API (Govt of India — register at bhashini.gov.in) — multilingual
- Google Translate API (backup/fallback for Bhashini)
- eCourts/NJDG (no clean API — scraping needed, optional/stretch feature)
- **Note:** India Code and e-Gazette have NO official public APIs — must scrape (Phase 6 of build plan)

### 13.4 Tools & Libraries (Software Stack)
| Category | Tool |
|---|---|
| Backend | Python, FastAPI |
| Vector DB | FAISS or ChromaDB |
| PDF/text processing | PyMuPDF, pdfplumber |
| Web scraping | BeautifulSoup, Selenium |
| Authentication | JWT (`pyjwt`), `passlib` |
| Encryption | `cryptography` (AES-256) |
| Frontend | Streamlit (fast) or React + Tailwind (polished) |
| Database (users/metadata) | PostgreSQL or MongoDB |
| Version control | Git + GitHub |

### 13.5 Accounts/Registrations Needed Before Coding
- [ ] Hugging Face account (datasets + InLegalBERT)
- [ ] Groq / Gemini / OpenAI API key
- [ ] Bhashini API access (bhashini.gov.in)
- [ ] GitHub repo created
- [ ] Cloud hosting decision (local for demo, or free-tier Render/Railway/Vercel for deployment)

### 13.6 Hardware/Infra
- Laptop with 8GB+ RAM is sufficient (FAISS runs locally; LLM calls via API — no local GPU needed)
- No paid cloud infra strictly required for demo scale

---

## 14. FULL STEP-BY-STEP BUILD PLAN (8 Phases, ~13 weeks)

### Phase 1: Setup & Data Collection (Week 1–2)
1. Set up environment — Python, FastAPI, virtualenv, GitHub repo
2. Collect legal documents — BNS/BNSS/BSA/Constitution from India Code; 2–3 Central Acts; judgment subset from ILDC/KanoonGPT; 1–2 states for regional demo
3. Clean data — PDF→text, remove headers/footers, split by section with metadata (Act name, section number, jurisdiction)

### Phase 2: Build the Retrieval System (Week 3–4)
4. Chunk documents (section-wise, ~300–500 words) with metadata
5. Generate embeddings using InLegalBERT or sentence-transformers
6. Store in vector DB (FAISS/ChromaDB) with metadata index
7. Add keyword search (BM25) alongside vector search → hybrid retrieval

### Phase 3: Connect the LLM (Week 5)
8. Choose LLM (Groq/Gemini/OpenAI/Claude)
9. Write RAG prompt template — answer ONLY from retrieved chunks, always cite section numbers, say "I don't have this information" if nothing relevant retrieved
10. Test basic Q&A — verify accuracy and correct citations

### Phase 4: Add Core Features (Week 6–8)
11. Explainability layer — show exact retrieved snippet alongside answer
12. Groundedness check — verify generated claims appear in retrieved chunk; flag if not
13. Jurisdiction filter — state dropdown; filter retrieval by Central vs selected state
14. Document upload + analysis — extract text from uploaded PDF/DOCX, summarize, flag risky clauses
15. Multilingual support (basic) — integrate Bhashini/Google Translate API

### Phase 5: Add Security (Week 9)
16. Encrypt uploaded files — AES-256 (Python `cryptography`)
17. Add authentication — JWT-based login/signup
18. Add access control — per-user document isolation
19. Add auto-deletion — scheduled job to delete files after X days
20. Add hash-based integrity check — SHA-256 hash on upload, stored in DB (full blockchain optional/stretch goal)

### Phase 6: Real-Time Update Pipeline (Week 10)
21. Build scraper — periodic check of India Code/e-Gazette for new notifications
22. Build change detection — compare scraped content vs stored version, flag differences
23. Add admin review panel — approve/reject updates before re-embedding
24. Show "last updated" timestamp on every answer in UI

### Phase 7: Frontend & Integration (Week 11)
25. Build UI — Streamlit or React: chat interface, document upload page, state selector, source citation display
26. Connect frontend to backend APIs — query, upload, auth endpoints
27. End-to-end testing — login → query → cited answer → upload → analysis

### Phase 8: Evaluation & Documentation (Week 12–13)
28. Evaluate system — 30–50 test legal questions with known correct answers; measure accuracy, citation correctness, relevance
29. Compare against baseline — same questions to plain ChatGPT (no RAG) to demonstrate hallucination reduction — strong evidence for report
30. Write report/synopsis — architecture diagram, dataset sources, security design, evaluation results, limitations, future scope
31. Prepare demo — video/live demo: query → citation → document upload → security features

### Suggested Team Role Division (if group project)
- Member 1: Data collection + preprocessing + vector DB
- Member 2: RAG pipeline + LLM integration + explainability
- Member 3: Security (encryption, auth, hashing) + backend APIs
- Member 4: Frontend + real-time update scraper + testing/evaluation

---

## 15. DELIVERABLES ALREADY PREPARED

1. ✅ Full submission-ready synopsis (Section 11 above)
2. ✅ Python dataset/model setup script (`setup_datasets.py`) — downloads IL-TUR, IL-PCSR, KanoonGPT, OpenNyAI, CUAD datasets + InLegalBERT/MiniLM models automatically into a structured `/data` folder; prints manual-download reminders for India Code/e-Gazette documents (no public API exists)

## 16. NOT YET DONE (pick up from here in next chat)
- [x] Actual dataset downloading/collection execution — DONE (BNS, BNSS, BSA, Constitution, 9 Central Acts, 2 Maharashtra state Acts, all structured to JSON; IL-PCSR, OpenNyAI, KanoonGPT, partial IL-TUR judgment datasets; InLegalBERT + MiniLM models)
- [x] Chunking + embeddings + vector DB (Phase 2) — DONE: FAISS index built with 3,723 chunks from full statute corpus (`build_vector_db.py`)
- [x] RAG prompt template + LLM integration code (Phase 3) — DONE (first working version): `query_legal_assist.py` using Groq (llama-3.3-70b-versatile) for retrieval + grounded, cited Q&A
- [ ] **PENDING DECISION: Switch LLM from Groq to Gemini (or offer both as a toggle) when building the multilingual/Bhashini feature in Phase 4** — reasoning: Gemini has stronger multilingual handling for Indic languages, relevant once Bhashini integration begins. Groq was chosen initially for speed/simplicity while getting the RAG pipeline working. The LLM call is isolated in one function (`ask_llm()` in `query_legal_assist.py`), so swapping providers does not require touching retrieval logic — should be a quick change when the time comes.
- [ ] Word (.docx) formatted version of synopsis for official submission
- [ ] System architecture diagram
- [ ] Week-wise Gantt chart/timeline
- [ ] Remaining Phase 4 features: explainability polish, groundedness/hallucination check, jurisdiction filter (state selector), document upload + clause analysis, multilingual (Bhashini) — see pending Gemini decision above
- [ ] Security implementation code (encryption, JWT auth, hashing) (Phase 5)
- [ ] Scraper + change detection + admin panel (Phase 6)
- [ ] Frontend build (Phase 7)
- [ ] Evaluation test set + baseline comparison + final report (Phase 8)
- [ ] Fix remaining data issues: retry IL-TUR gated access approval if not yet granted; confirm no leftover duplicate Maharashtra Rent Control JSON file

---
*End of master document. Paste/upload this file in a new chat to resume exactly where you left off, with zero loss of detail or novelty.*
