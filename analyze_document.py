"""
Legal Assist+ : Phase 4 - Document Upload & Clause Analysis
------------------------------------------------------------
This is the CORE feature of the project: a user uploads their own
document (contract, agreement, etc.), and the system answers questions
about specific clauses by combining:
  1. The uploaded document's own text (what does THIS clause say)
  2. Your existing legal knowledge base (what does the LAW say about this)

BEFORE RUNNING:
    pip install pdfplumber numpy

Run with:
    python analyze_document.py
"""

import re
import time
import pickle
from pathlib import Path

import numpy as np
import pdfplumber
import faiss
from sentence_transformers import SentenceTransformer
from groq import Groq
import groq as groq_module
from dotenv import load_dotenv
import os

# ---------------------------------------------------------
# SETTINGS (matching query_legal_assist.py for consistency)
# ---------------------------------------------------------
VECTOR_DB_DIR = Path("data/vector_db")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
GROQ_MODEL = "openai/gpt-oss-20b"
LAW_TOP_K = 3        # how many law chunks to retrieve per question
CLAUSE_TOP_K = 3      # how many document clauses to retrieve per question
LAW_DISTANCE_THRESHOLD = 0.85  # tightened for document analysis specifically -- stricter than the
                                 # general Q&A tool (1.0), since pulling wrong-domain law into a
                                 # contract review is worse than citing no law at all

load_dotenv()


# ---------------------------------------------------------
# STEP 1: Extract text from the uploaded document
# ---------------------------------------------------------
def extract_text_from_pdf(pdf_path):
    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
    return "\n".join(full_text)


# ---------------------------------------------------------
# STEP 2: Split the uploaded document into clauses
# ---------------------------------------------------------
def split_into_clauses(raw_text):
    """
    Splits a contract/agreement into individual clauses.
    Handles common numbering styles: '1.', '1)', 'Clause 1', etc.
    Falls back to paragraph-based splitting if no numbering is detected.
    """
    lines = raw_text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip() and len(l.strip()) > 2]
    cleaned_text = "\n".join(cleaned_lines)

    clause_pattern = re.compile(
        r'\n(?:Clause\s+)?(\d{1,3})[\.\)]\s+', re.MULTILINE
    )
    matches = list(clause_pattern.finditer(cleaned_text))

    clauses = []
    if matches:
        for i, match in enumerate(matches):
            clause_num = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned_text)
            text = cleaned_text[start:end].strip()
            if text:
                clauses.append({"clause_number": clause_num, "text": text})
    else:
        # fallback: split by double newlines / paragraphs
        paragraphs = [p.strip() for p in cleaned_text.split("\n\n") if p.strip()]
        for i, p in enumerate(paragraphs, start=1):
            clauses.append({"clause_number": str(i), "text": p})

    return clauses


# ---------------------------------------------------------
# STEP 3: Build an in-memory index for the uploaded document
# ---------------------------------------------------------
def embed_clauses(clauses, embed_model):
    texts = [f"Clause {c['clause_number']}: {c['text']}" for c in clauses]
    embeddings = embed_model.encode(texts, convert_to_numpy=True)
    return embeddings


def retrieve_clauses(question, clauses, clause_embeddings, embed_model, top_k=CLAUSE_TOP_K):
    """
    Retrieves relevant clauses. First checks for an EXACT clause number
    mentioned in the question (e.g. "Clause 7", "clause 7") and guarantees
    it's included -- semantic similarity alone can miss exact number
    references, the same issue we found and fixed for law section lookups.
    """
    exact_matches = []
    number_match = re.search(r'\bclause\s+(\d{1,3}[A-Za-z]?)\b', question, re.IGNORECASE)
    if number_match:
        target_number = number_match.group(1)
        exact_matches = [
            {**c, "score": 1.0, "match_type": "exact_number"}
            for c in clauses if c["clause_number"] == target_number
        ]

    query_vec = embed_model.encode([question], convert_to_numpy=True)[0]

    def cos_sim(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

    scored = [(cos_sim(query_vec, emb), clause) for emb, clause in zip(clause_embeddings, clauses)]
    scored.sort(key=lambda x: x[0], reverse=True)
    semantic_results = [
        {**c, "score": float(s), "match_type": "semantic"} for s, c in scored[:top_k]
    ]

    # Combine: exact match first, then semantic, deduplicated by clause_number
    seen = set()
    combined = []
    for c in exact_matches + semantic_results:
        if c["clause_number"] not in seen:
            seen.add(c["clause_number"])
            combined.append(c)

    return combined[:top_k]


# ---------------------------------------------------------
# STEP 4: Retrieve relevant LAW from your existing knowledge base
# ---------------------------------------------------------
def retrieve_law(question, law_index, law_chunks, embed_model, top_k=LAW_TOP_K, jurisdiction_filter=None):
    """
    jurisdiction_filter: None (default) or a state name, e.g. "Maharashtra".
    Restricts results to Central law + the selected state's law, never excluding
    Central law (Central and State law apply simultaneously in India).
    """
    query_vector = embed_model.encode([question], convert_to_numpy=True)
    search_k = top_k * 4 if jurisdiction_filter else top_k
    distances, indices = law_index.search(query_vector.astype("float32"), search_k)

    results = []
    for idx, dist in zip(indices[0], distances[0]):
        if idx == -1 or dist > LAW_DISTANCE_THRESHOLD:
            continue
        chunk = law_chunks[idx]
        if jurisdiction_filter and chunk.get("jurisdiction", "Central") not in ("Central", jurisdiction_filter):
            continue
        results.append({**chunk, "distance": float(dist)})
        if len(results) >= top_k:
            break
    return results


# ---------------------------------------------------------
# STEP 5: Build the combined prompt and ask the LLM
# ---------------------------------------------------------
def build_combined_prompt(question, retrieved_clauses, retrieved_law):
    clause_blocks = "\n\n".join(
        f"[Your Document - Clause {c['clause_number']}]:\n{c['text']}"
        for c in retrieved_clauses
    )
    law_blocks = "\n\n".join(
        (f"[Court Judgment - {l['act_name']} ({l['title']})]:\n{l['text']}"
         if l.get("chunk_type") == "judgment" else
         f"[Relevant Law - {l['act_name']}, Section {l['number']} ({l['title']})]:\n{l['text']}")
        for l in retrieved_law
    )

    prompt = f"""You are a legal document assistant. The user has uploaded their own document
(e.g. a contract or agreement) and is asking a PRACTICAL question about their situation.
You have access to:
1. Relevant clauses from THEIR uploaded document
2. Relevant sections of Indian law that may apply

ANSWER STRUCTURE (follow this order strictly):
1. Start with a short, direct answer to their actual question, in plain conversational
   language -- 2-4 sentences. Answer what THEY asked, don't just describe clauses.
   Example: if asked "what happens if I resign early", say plainly what happens to
   THEM (e.g. "You would owe liquidated damages of three months' fees, unless you give
   60 days' notice") before going into clause detail.
2. THEN, if useful, add supporting detail: which clause(s) say this, and any relevant
   law, in plain prose or short bullet points.
3. If a clause seems unusual, one-sided, or worth flagging, say so clearly.
4. If something has serious financial/legal consequences, add one line suggesting they
   consult a lawyer.

STRICT FORMATTING RULES:
- Do NOT use markdown tables unless you are comparing 3+ distinct items side by side on
  the same set of attributes. For a single clause explanation or a direct answer, use
  plain paragraphs and/or a short bullet list instead -- tables make simple answers
  harder to read, not easier.
- NEVER use raw HTML tags like <br>, <b>, <div>, etc. Use plain markdown only: line
  breaks, bullet points (-), numbered lists, and **bold** where needed.
- Keep the tone conversational and direct, like a knowledgeable friend explaining
  something -- not a formal legal memo with headers for every sub-point.
- Do not give personal legal advice or tell the user exactly what to do -- explain the
  situation factually so they can make an informed decision.
- If the retrieved clauses or law don't actually answer the question, say so honestly
  in the first sentence rather than padding with unrelated detail.

YOUR DOCUMENT'S RELEVANT CLAUSES:
{clause_blocks if clause_blocks else "(No closely matching clause found in your document.)"}

RELEVANT INDIAN LAW:
{law_blocks if law_blocks else "(No closely matching law found in the knowledge base.)"}

QUESTION: {question}

ANSWER:"""
    return prompt


def ask_llm(prompt, groq_client, max_tokens=900, max_retries=4):
    """
    Calls the LLM with automatic retry-with-backoff if we hit Groq's
    rate limit (free tier has a fairly low tokens-per-minute cap).
    Also retries if the model returns an empty response (rare, but happens).
    """
    for attempt in range(max_retries):
        try:
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content
            # Empty response -- retry once more before giving up
            print(f"  [Got an empty response -- retrying ({attempt + 1}/{max_retries})]")
            time.sleep(2)
        except groq_module.RateLimitError as e:
            wait_time = 8 * (attempt + 1)  # back off a bit more each retry
            print(f"  [Rate limit hit -- waiting {wait_time}s before retry {attempt + 1}/{max_retries}]")
            time.sleep(wait_time)
    return ("[No answer could be generated for this question -- this can happen with very "
            "short or ambiguous queries. Try rephrasing your question with more detail.]")


# ---------------------------------------------------------
# STEP 6: FULL DOCUMENT REVIEW -- proactive lawyer-style scan
# ---------------------------------------------------------

# A checklist of protections/clauses a lawyer would typically expect
# to see in a well-drafted agreement. Used to flag what's MISSING,
# not just what's present and risky.
STANDARD_CLAUSE_CHECKLIST = [
    "Termination clause (how either party can end the agreement, and notice period)",
    "Dispute resolution / arbitration clause",
    "Governing law / jurisdiction clause",
    "Liability cap or limitation of liability",
    "Confidentiality obligations",
    "Force majeure (unforeseeable events like natural disasters)",
    "Payment terms and late payment consequences",
    "Renewal or auto-renewal terms",
    "Indemnity clause",
]

CLAUSE_BATCH_SIZE = 2  # reduced from 4 -- smaller calls avoid rate-limit errors and truncated responses


def review_clause_batch(clause_batch, law_index, law_chunks, embed_model, groq_client):
    """
    Sends a small batch of clauses to the LLM for risk analysis,
    along with any relevant law found for each clause.
    Returns the raw LLM text (structured, but not strictly parsed JSON --
    kept readable for the report rather than over-engineering parsing).
    """
    blocks = []
    for c in clause_batch:
        relevant_law = retrieve_law(c["text"], law_index, law_chunks, embed_model, top_k=2)
        law_text = "\n".join(
            f"  - {l['act_name']}, Section {l['number']} ({l['title']})"
            for l in relevant_law
        ) or "  (no directly relevant law found)"
        blocks.append(
            f"Clause {c['clause_number']}:\n{c['text']}\n\nPotentially relevant law:\n{law_text}"
        )

    combined = "\n\n---\n\n".join(blocks)

    prompt = f"""You are reviewing clauses from a contract/agreement, the way a lawyer would
when checking a document for a client before they sign it.

For EACH clause below, assess:
- Risk level: None, Low, Medium, or High
- What the clause means in plain language
- Why it might be risky, unusual, one-sided, or unenforceable (if applicable) --
  reference the relevant law provided if it applies
- If the clause seems standard and fair, say so briefly -- don't manufacture risk where none exists

Format your response as a clear list, one entry per clause, like this:
Clause [number] -- Risk: [level]
[explanation]

Do NOT use markdown tables. Do NOT use raw HTML tags like <br>. Use plain paragraphs
and bullet points only.

CLAUSES TO REVIEW:
{combined}

REVIEW:"""

    return ask_llm(prompt, groq_client, max_tokens=1300)  # increased -- was truncating on Medium/High risk clauses needing longer explanations


def check_missing_clauses(clauses, groq_client):
    """
    Checks the checklist of standard protections against the document.
    Uses a short summary of each clause (not the full text) to keep this
    single call well within the token/rate limits.
    """
    checklist_text = "\n".join(f"- {item}" for item in STANDARD_CLAUSE_CHECKLIST)

    # Build a compact summary instead of sending the full document text --
    # just clause numbers + first ~120 characters is enough for the LLM
    # to judge whether a topic is covered.
    summary_lines = [
        f"Clause {c['clause_number']}: {c['text'][:120].strip()}..."
        for c in clauses
    ]
    compact_summary = "\n".join(summary_lines)

    prompt = f"""Below is a compact summary of each clause in a contract/agreement
(clause number + the start of its text). Compare it against this checklist of
protections that well-drafted agreements typically include:

{checklist_text}

For each checklist item, say whether it APPEARS PRESENT or APPEARS MISSING,
in one line each, based on the clause summaries. If missing, briefly note why
it might matter. Do not invent clauses that aren't suggested by the summaries.

CLAUSE SUMMARIES:
{compact_summary}

CHECKLIST REVIEW:"""

    return ask_llm(prompt, groq_client, max_tokens=1000)  # increased -- 700 was cutting off the checklist before all 9 items were covered


def run_full_review(clauses, law_index, law_chunks, embed_model, groq_client):
    print("\n" + "=" * 70)
    print("FULL DOCUMENT REVIEW -- scanning all clauses for risks...")
    print("=" * 70)

    all_findings = []
    for i in range(0, len(clauses), CLAUSE_BATCH_SIZE):
        batch = clauses[i:i + CLAUSE_BATCH_SIZE]
        print(f"\nReviewing clauses {batch[0]['clause_number']}-{batch[-1]['clause_number']}...")
        findings = review_clause_batch(batch, law_index, law_chunks, embed_model, groq_client)
        all_findings.append(findings)
        print(findings)
        time.sleep(2)  # small pause to stay comfortably under the rate limit

    print("\n" + "-" * 70)
    print("CHECKING FOR MISSING STANDARD PROTECTIONS...")
    print("-" * 70)
    time.sleep(2)
    missing_report = check_missing_clauses(clauses, groq_client)
    print(missing_report)

    print("\n" + "=" * 70)
    print("END OF FULL REVIEW")
    print("=" * 70)
    print("\nNote: This is an automated risk scan to help you understand your document.")
    print("It does not replace professional legal advice, especially for anything")
    print("with significant financial or legal consequences.\n")


# ---------------------------------------------------------
# REUSABLE LOADER (so Streamlit / other apps can import this
# module and call this function instead of duplicating setup)
# ---------------------------------------------------------
def load_everything():
    law_index = faiss.read_index(str(VECTOR_DB_DIR / "legal_index.faiss"))
    with open(VECTOR_DB_DIR / "chunk_metadata.pkl", "rb") as f:
        law_chunks = pickle.load(f)
    embed_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    api_key = os.getenv("GROQ_API_KEY")
    groq_client = Groq(api_key=api_key)
    return law_index, law_chunks, embed_model, groq_client


# ---------------------------------------------------------
# MAIN (only runs when executed directly as a script, e.g.
# `python analyze_document.py` -- NOT when imported by Streamlit)
# ---------------------------------------------------------
if __name__ == "__main__":
    # Load the existing legal knowledge base (statutes)
    print("Loading legal knowledge base...")
    law_index, law_chunks, embed_model, groq_client = load_everything()

    # Ask for the document to analyze
    pdf_path = input("Enter the path to your document (PDF): ").strip().strip('"')
    if not Path(pdf_path).exists():
        print(f"File not found: {pdf_path}")
        exit()

    print("\nExtracting and splitting your document into clauses...")
    raw_text = extract_text_from_pdf(pdf_path)
    clauses = split_into_clauses(raw_text)
    print(f"Found {len(clauses)} clauses in your document.")

    print("Embedding your document's clauses...")
    clause_embeddings = embed_clauses(clauses, embed_model)

    # Run the proactive full review automatically -- this is the core
    # "act like a lawyer reviewing your document" feature
    run_full_review(clauses, law_index, law_chunks, embed_model, groq_client)

    print(f"\nYou can now ask follow-up questions about your document, or 'exit' to quit.\n")

    while True:
        question = input("Your question: ").strip()
        if question.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        if not question:
            continue

        retrieved_clauses = retrieve_clauses(question, clauses, clause_embeddings, embed_model)
        retrieved_law = retrieve_law(question, law_index, law_chunks, embed_model)

        print(f"\n[Matched {len(retrieved_clauses)} clause(s) from your document]")
        for c in retrieved_clauses:
            tag = " (exact match)" if c.get("match_type") == "exact_number" else f" (score: {c.get('score', 0):.3f})"
            print(f"  - Clause {c['clause_number']}{tag}")
        print(f"[Matched {len(retrieved_law)} relevant law section(s)]")
        for l in retrieved_law:
            print(f"  - {l['act_name']}, Section {l['number']}: {l['title']}  (distance: {l['distance']:.3f})")

        prompt = build_combined_prompt(question, retrieved_clauses, retrieved_law)
        answer = ask_llm(prompt, groq_client, max_tokens=2048)  # increased further to stop mid-answer cutoffs

        print("\n[ANSWER]")
        print(answer)
        print("\n" + "=" * 70)
