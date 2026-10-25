"""
Legal Assist+ : Phase 3 - RAG Query Engine
----------------------------------------------
Connects your FAISS vector database to Groq's LLM to answer
legal questions with citations, grounded only in retrieved text.

BEFORE RUNNING:
    pip install groq python-dotenv faiss-cpu sentence-transformers

Also make sure you have a .env file in this same folder with:
    GROQ_API_KEY=gsk_your_key_here

Run with:
    python query_legal_assist.py
"""

import pickle
import re
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv
import os

# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------
VECTOR_DB_DIR = Path("data/vector_db")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"  # must match build_vector_db.py -- reverted from InLegalBERT (see notes there)
GROQ_MODEL = "openai/gpt-oss-20b"     # confirmed available on this account; swap to "openai/gpt-oss-120b" for higher quality (slower)
TOP_K = 5  # how many chunks to retrieve per question
DISTANCE_THRESHOLD = 1.0  # FINAL VALUE -- calibrated from real test data: genuine matches scored 0.35-0.72,
                            # weak/no-match cases scored 0.86-1.03. This threshold reliably separates them.

# --- Act-overview mode: for questions like "explain the IT Act" -----------------
OVERVIEW_TOP_K = 8          # sections gathered for an overview
OVERVIEW_CHUNK_CHARS = 1200  # trim each section so the prompt stays within rate limits

# alias phrase (lowercase) -> text that must appear in the Act's name in the index
ACT_ALIASES = {
    "information technology act": "information technology",
    "it act": "information technology",
    "cyber law": "information technology",
    "cyber crime act": "information technology",
    "women rights act": "domestic violence",
    "women protection act": "domestic violence",
    "domestic violence act": "domestic violence",
    "dv act": "domestic violence",
    "pwdva": "domestic violence",
    "consumer protection act": "consumer protection",
    "consumer act": "consumer protection",
    "motor vehicles act": "motor vehicles",
    "mv act": "motor vehicles",
    "indian contract act": "contract act",
    "contract act": "contract act",
    "negotiable instruments act": "negotiable instruments",
    "ni act": "negotiable instruments",
    "cheque bounce act": "negotiable instruments",
    "pocso act": "protection of children",
    "pocso": "protection of children",
    "hindu marriage act": "hindu marriage",
    "right to information act": "right to information",
    "rti act": "right to information",
    "rti": "right to information",
    "rent control act": "rent control",
    "land revenue code": "land revenue",
    "payment and settlement systems act": "payment and settlement",
    "bharatiya nyaya sanhita": "bharatiya nyaya",
    "bns": "bharatiya nyaya",
    "bharatiya nagarik suraksha sanhita": "bharatiya nagarik",
    "bnss": "bharatiya nagarik",
    "bharatiya sakshya adhiniyam": "bharatiya sakshya",
    "bsa": "bharatiya sakshya",
    "indian penal code": "penal code",
    "ipc": "penal code",
    "code of criminal procedure": "criminal procedure",
    "crpc": "criminal procedure",
    "indian evidence act": "evidence act",
    "evidence act": "evidence act",
    "constitution of india": "constitution of india",
    "constitution": "constitution of india",
}

OVERVIEW_INTENT = re.compile(
    r"^(please\s+)?(give me an? (overview|summary) of|explain|summari[sz]e|overview of|overview|"
    r"describe|tell me about|what is|what are|about)\b"
)
OVERVIEW_FILLER = {
    "the", "a", "an", "of", "in", "india", "indian", "act", "law", "laws", "please", "me",
    "briefly", "simply", "simple", "short", "to", "and", "is", "are", "it", "this",
}

load_dotenv()  # reads GROQ_API_KEY from .env


# ---------------------------------------------------------
# STEP 1: Load the vector database + embedding model + LLM client
# ---------------------------------------------------------
def load_everything():
    print("Loading FAISS index...")
    index = faiss.read_index(str(VECTOR_DB_DIR / "legal_index.faiss"))

    print("Loading chunk metadata...")
    with open(VECTOR_DB_DIR / "chunk_metadata.pkl", "rb") as f:
        chunks = pickle.load(f)

    print(f"Loading embedding model: {EMBEDDING_MODEL_NAME} ...")
    embed_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not found. Make sure you created a .env file "
            "with GROQ_API_KEY=your_key_here in the project root."
        )
    groq_client = Groq(api_key=api_key)

    print(f"Ready. {index.ntotal} chunks loaded.\n")
    return index, chunks, embed_model, groq_client


# ---------------------------------------------------------
# STEP 2: Retrieve the most relevant chunks for a question
# ---------------------------------------------------------
import re


def exact_section_lookup(question, chunks):
    """
    Detects a specific section/article number mentioned in the question
    (e.g., 'Section 420', 'Article 21') and returns any chunk that matches
    it exactly. This catches cases where semantic search misses an exact
    numeric identifier that doesn't carry strong semantic meaning.
    """
    match = re.search(r'\b(?:section|article)\s+(\d+[A-Za-z]?)\b', question, re.IGNORECASE)
    if not match:
        return []

    target_number = match.group(1)
    exact_matches = [c for c in chunks if c.get("number") == target_number]
    return [{**c, "distance": 0.0, "match_type": "exact_number"} for c in exact_matches]


def detect_act_overview(question, chunks):
    """
    Returns a set of Act names if the question is a plain request to explain/summarise
    a whole Act (e.g. "explain IT act", "what is the women rights act"), else None.
    Specific questions ("what does the IT Act say about hacking?") are NOT treated as
    overviews and use normal retrieval.
    """
    q = re.sub(r"[^a-z0-9 ]", " ", question.lower())
    q = " ".join(q.split())

    statute_names = {c["act_name"] for c in chunks if c.get("chunk_type") != "judgment"}

    # candidate (phrase, matcher) pairs: manual aliases first, then real Act names
    candidates = []
    for alias in sorted(ACT_ALIASES, key=len, reverse=True):
        key = ACT_ALIASES[alias]
        names = {n for n in statute_names if key in n.lower()}
        if names:
            candidates.append((alias, names))
    for name in sorted(statute_names, key=len, reverse=True):
        short = re.sub(r",?\s*\d{4}$", "", name.lower())
        short = " ".join(re.sub(r"[^a-z0-9 ]", " ", short).split())
        candidates.append((short, {name}))

    for phrase, names in candidates:
        m = re.search(rf"\b{re.escape(phrase)}\b", q)
        if not m:
            continue
        rest = (q[:m.start()] + " " + q[m.end():]).split()
        intent = OVERVIEW_INTENT.match(q)
        leftover = [w for w in rest if w not in OVERVIEW_FILLER and not (intent and w in intent.group(0).split())]
        if not leftover:
            return names
    return None


def act_overview_retrieve(question, act_names, index, chunks, embed_model, jurisdiction_filter=None):
    allowed = set()
    for i, c in enumerate(chunks):
        if c["act_name"] not in act_names or c.get("chunk_type") == "judgment":
            continue
        if jurisdiction_filter and c.get("jurisdiction", "Central") not in ("Central", jurisdiction_filter):
            continue
        allowed.add(i)
    if not allowed:
        return []

    picked = []  # (chunk index, distance)

    # Anchor sections: short title and definitions orient the reader.
    for i in sorted(allowed):
        title = (chunks[i].get("title") or "").lower()
        if "short title" in title or "definition" in title:
            picked.append((i, 0.0))
        if len(picked) >= 3:
            break

    # Then the sections most related to the Act's core provisions, within this Act only.
    probe = embed_model.encode(
        [f"{question}: main provisions, purpose, rights, duties, offences, penalties and remedies"],
        convert_to_numpy=True,
    )
    distances, indices = index.search(probe.astype("float32"), index.ntotal)
    already = {i for i, _ in picked}
    for idx, dist in zip(indices[0], distances[0]):
        if idx in allowed and idx not in already:
            picked.append((int(idx), float(dist)))
            already.add(int(idx))
        if len(picked) >= OVERVIEW_TOP_K:
            break

    results = []
    for i, dist in picked:
        c = dict(chunks[i])
        c["text"] = c["text"][:OVERVIEW_CHUNK_CHARS]
        c["distance"] = dist
        c["match_type"] = "act_overview"
        results.append(c)
    return results


def retrieve(question, index, chunks, embed_model, top_k=TOP_K, jurisdiction_filter=None):
    """
    jurisdiction_filter: None (no filtering, default) or a state name (e.g. "Maharashtra").
    When set, results are restricted to chunks tagged "Central" (applies nationwide)
    or matching the selected state -- never excludes Central law, since Central and
    State law both apply simultaneously in India.
    """
    # First, check for an exact section/article number match (always honored,
    # regardless of jurisdiction filter -- if the user named a specific section,
    # give it to them).
    exact = exact_section_lookup(question, chunks)

    # "Explain the X Act": gather that Act's key sections instead of relying on one
    # similarity search, which scores poorly for broad questions with no specific topic.
    if not exact:
        act_names = detect_act_overview(question, chunks)
        if act_names:
            overview = act_overview_retrieve(question, act_names, index, chunks, embed_model, jurisdiction_filter)
            if overview:
                return overview

    query_vector = embed_model.encode([question], convert_to_numpy=True)
    # Over-fetch candidates when a jurisdiction filter is active, since some
    # will be filtered out after the search.
    search_k = top_k * 4 if jurisdiction_filter else top_k
    distances, indices = index.search(query_vector.astype("float32"), search_k)

    semantic_results = []
    for idx, dist in zip(indices[0], distances[0]):
        if idx == -1:
            continue
        if dist > DISTANCE_THRESHOLD:
            continue
        chunk = chunks[idx]
        if jurisdiction_filter and chunk.get("jurisdiction", "Central") not in ("Central", jurisdiction_filter):
            continue  # skip chunks from a different state
        semantic_results.append({**chunk, "distance": float(dist), "match_type": "semantic"})
        if len(semantic_results) >= top_k:
            break

    # Combine: exact matches first, then semantic results, deduplicated by (act_name, number)
    seen = set()
    combined = []
    for c in exact + semantic_results:
        key = (c["act_name"], c["number"])
        if key not in seen:
            seen.add(key)
            combined.append(c)

    return combined[:top_k]


# ---------------------------------------------------------
# STEP 3: Build the RAG prompt and call the LLM
# ---------------------------------------------------------
def build_prompt(question, retrieved_chunks):
    context_blocks = []
    for i, c in enumerate(retrieved_chunks, start=1):
        if c.get("chunk_type") == "judgment":
            # Case law: cite as a case, not a statute section
            context_blocks.append(
                f"[Source {i} - Court Judgment] {c['act_name']} ({c['title']}):\n{c['text']}"
            )
        else:
            context_blocks.append(
                f"[Source {i} - Statute] {c['act_name']}, Section {c['number']} "
                f"({c['title']}):\n{c['text']}"
            )
    context_text = "\n\n".join(context_blocks)

    overview_note = ""
    if any(c.get("match_type") == "act_overview" for c in retrieved_chunks):
        overview_note = (
            "- The user asked for an overview of an Act. The sources are a SELECTION of its key "
            "sections, not the whole Act. Explain what the Act is for, who it protects or applies "
            "to, and the main rights, duties, offences or remedies shown in the sources. Do not "
            "claim anything about provisions not shown. End with one sentence saying this "
            "overview is based on selected sections.\n"
        )

    prompt = f"""You are a legal information assistant for Indian law. Answer the user's
question using ONLY the information in the sources below. Do not use any
outside knowledge or assumptions.

ANSWER STRUCTURE:
- Start with a short, direct answer to their actual question in plain conversational
  language (2-4 sentences), before going into supporting detail.
- Then add supporting detail/citations if useful.

RULES:
- For statute sources, always cite the Act name and section number, like: (BSA 2023, Section 118)
- For court judgment sources, cite the case name, like: (Case: [case name])
- Be clear about the difference between what a statute says and how a court has
  interpreted or applied it in a specific case -- don't blend the two together
  as if they were the same kind of authority
- If the sources do not contain enough information to answer, say so clearly in the
  first sentence.
- Explain the answer in simple, plain language a non-lawyer can understand.
- Do not give personal legal advice; frame answers as general legal information.
- Do NOT use markdown tables unless comparing 3+ distinct items side by side. For a
  normal explanation, use plain paragraphs and/or short bullet points instead.
- NEVER use raw HTML tags like <br>, <b>, <div>. Use plain markdown only.
- Keep the tone conversational and direct, not like a formal memo with a header for
  every sub-point.
{overview_note}
SOURCES:
{context_text}

QUESTION: {question}

ANSWER:"""
    return prompt


def ask_llm(prompt, groq_client):
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,  # low temperature = more factual, less creative
    )
    return response.choices[0].message.content


# ---------------------------------------------------------
# STEP 4: Full pipeline for one question
# ---------------------------------------------------------
def answer_question(question, index, chunks, embed_model, groq_client):
    retrieved = retrieve(question, index, chunks, embed_model)

    if not retrieved:
        print("\n[No sufficiently relevant sections found in the corpus.]")
        answer = ("I don't have enough relevant information in my current legal corpus "
                   "to answer this question confidently. Please rephrase, or note that "
                   "this topic may not yet be covered in the available documents.")
        print("\n[ANSWER]")
        print(answer)
        print("\n" + "=" * 70)
        return answer, retrieved

    print(f"\n[Retrieved {len(retrieved)} relevant sections:]")
    for c in retrieved:
        print(f"  - {c['act_name']}, Section {c['number']}: {c['title']}  (distance: {c['distance']:.3f})")

    prompt = build_prompt(question, retrieved)
    answer = ask_llm(prompt, groq_client)

    print("\n[ANSWER]")
    print(answer)
    print("\n" + "=" * 70)
    return answer, retrieved


# ---------------------------------------------------------
# MAIN: interactive test loop
# ---------------------------------------------------------
if __name__ == "__main__":
    index, chunks, embed_model, groq_client = load_everything()

    print("Legal Assist+ is ready. Type a legal question, or 'exit' to quit.\n")

    while True:
        question = input("Your question: ").strip()
        if question.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        if not question:
            continue

        answer_question(question, index, chunks, embed_model, groq_client)
