"""
Legal Assist+ : Embedding + Vector Database Builder
------------------------------------------------------
Purpose: Take all cleaned statute JSON files (data/statutes/cleaned/*.json)
and convert them into a searchable FAISS vector database.

BEFORE RUNNING:
    pip install sentence-transformers faiss-cpu

Run with:
    python build_vector_db.py
"""

import json
import pickle
from pathlib import Path

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------
CLEANED_DIR = Path("data/statutes/cleaned")
JUDGMENTS_DIR = Path("data/judgments")
VECTOR_DB_DIR = Path("data/vector_db")
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

# Judgment datasets (IL-PCSR, OpenNyAI, etc.) contain thousands of cases, many
# with very long full-text. For this project's scale, we sample a bounded
# number per source and truncate each judgment's text -- this keeps build
# time and index size reasonable while still giving genuine case-law coverage.
# This is a deliberate scoping decision, not a hidden limitation.
MAX_JUDGMENTS_PER_SOURCE = 800  # increased from 500 for better topic coverage
JUDGMENT_TEXT_MAX_CHARS = 3000
JUDGMENT_SAMPLE_SEED = 42  # fixed seed -- reproducible, but not just "the first N rows"

# Model choice: starting with a lightweight general-purpose model.
# You can swap this later for InLegalBERT for better legal-domain accuracy.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"  # reverted from InLegalBERT: empirically, MiniLM retrieved far more relevant chunks
                                             # (InLegalBERT wasn't fine-tuned for sentence-similarity/retrieval, just legal-domain language modeling)


# ---------------------------------------------------------
# STEP 1: Load all cleaned JSON files into one flat list of chunks
# ---------------------------------------------------------
# Known Indian states/UTs -- used to auto-detect jurisdiction from the Act name.
# Add to this list as more state-specific Acts are added to the corpus.
STATE_KEYWORDS = [
    "Maharashtra", "Gujarat", "Karnataka", "Tamil Nadu", "Kerala", "Delhi",
    "Uttar Pradesh", "West Bengal", "Rajasthan", "Punjab", "Haryana",
    "Madhya Pradesh", "Bihar", "Telangana", "Andhra Pradesh",
]


def detect_jurisdiction(act_name):
    """
    Tags a chunk as 'Central' (applies nationwide) or a specific state name,
    based on whether a state name appears in the Act's title. This is a
    simple, explicit heuristic -- correct for the current corpus, where
    state-specific Acts always name their state in the title.
    """
    for state in STATE_KEYWORDS:
        if state.lower() in act_name.lower():
            return state
    return "Central"


def load_all_chunks():
    """
    Reads every *.json file in data/statutes/cleaned/ and combines
    them into one big list of chunk dictionaries.
    """
    all_chunks = []
    json_files = list(CLEANED_DIR.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in {CLEANED_DIR}/")
        print("Make sure your cleaned Act JSON files (e.g. BSA_2023.json) are there.")
        return []

    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as f:
            sections = json.load(f)

        for section in sections:
            # Normalize fields (different Acts might use slightly different keys,
            # e.g. Constitution chunks might use "article" instead of "section")
            act_name = section.get("act_name") or section.get("document_name", "Unknown")
            chunk = {
                "source_file": json_file.name,
                "act_name": act_name,
                "number": section.get("section_number") or section.get("number", "N/A"),
                "title": section.get("section_title") or section.get("title", ""),
                "text": section.get("text", ""),
                "jurisdiction": detect_jurisdiction(act_name),
                "chunk_type": "statute",
            }
            if chunk["text"].strip():  # skip empty entries
                all_chunks.append(chunk)

    jurisdictions_found = sorted(set(c["jurisdiction"] for c in all_chunks))
    print(f"Loaded {len(all_chunks)} total chunks from {len(json_files)} file(s).")
    print(f"Jurisdictions detected: {jurisdictions_found}")
    return all_chunks


# ---------------------------------------------------------
# STEP 1b: Load judgment/case-law datasets and convert to the same
# chunk schema as statutes, tagged chunk_type="judgment" so they stay
# distinguishable in citations and prompts.
# ---------------------------------------------------------
def truncate_text(text, max_chars=JUDGMENT_TEXT_MAX_CHARS):
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def load_il_pcsr_chunks():
    """IL-PCSR: Supreme Court cases with links to relevant statutes and precedents."""
    chunks = []
    path = JUDGMENTS_DIR / "il-pcsr"
    if not path.exists():
        print(f"  [skip] IL-PCSR not found at {path}")
        return chunks
    try:
        from datasets import load_from_disk
        ds = load_from_disk(str(path))
        split = ds["train_queries"] if "train_queries" in ds else list(ds.values())[0]
        sample = split.shuffle(seed=JUDGMENT_SAMPLE_SEED).select(range(min(MAX_JUDGMENTS_PER_SOURCE, len(split))))  # random sample, not just the first N rows

        for row in sample:
            case_title = (row.get("case_title") or "").strip()
            text = truncate_text(row.get("text", ""))
            if not text.strip() or not case_title:  # skip blank titles too
                continue
            chunks.append({
                "source_file": "il-pcsr",
                "act_name": case_title,
                "number": row.get("id", "N/A"),
                "title": f"Case ({row.get('date', 'date unknown')})",
                "text": text,
                "jurisdiction": row.get("jurisdiction") or "Central",
                "chunk_type": "judgment",
            })
        print(f"  [ok] IL-PCSR: loaded {len(chunks)} case chunks")
    except Exception as e:
        print(f"  [FAIL] Could not load IL-PCSR: {e}")
    return chunks


def load_opennyai_chunks():
    """OpenNyAI: categorized Indian court judgments with court/case-type metadata."""
    chunks = []
    path = JUDGMENTS_DIR / "opennyai"
    if not path.exists():
        print(f"  [skip] OpenNyAI not found at {path}")
        return chunks
    try:
        from datasets import load_from_disk
        ds = load_from_disk(str(path))
        split = ds["train"] if "train" in ds else list(ds.values())[0]
        sample = split.shuffle(seed=JUDGMENT_SAMPLE_SEED).select(range(min(MAX_JUDGMENTS_PER_SOURCE, len(split))))  # random sample, not just the first N rows

        for row in sample:
            title = (row.get("Titles") or "").strip()
            text = truncate_text(row.get("Text", ""))
            if not text.strip() or not title:  # skip blank titles too
                continue
            court = row.get("Court_Name_Normalized") or row.get("Court_Name") or "Court unknown"
            case_type = row.get("Case_Type", "")
            chunks.append({
                "source_file": "opennyai",
                "act_name": title,
                "number": "N/A",
                "title": f"{court}{' - ' + case_type if case_type else ''}",
                "text": text,
                "jurisdiction": "Central",  # OpenNyAI doesn't provide a clean state field
                "chunk_type": "judgment",
            })
        print(f"  [ok] OpenNyAI: loaded {len(chunks)} case chunks")
    except Exception as e:
        print(f"  [FAIL] Could not load OpenNyAI: {e}")
    return chunks


def load_judgment_chunks():
    print("\nLoading judgment/case-law datasets...")
    print(f"(Sampling up to {MAX_JUDGMENTS_PER_SOURCE} cases per source, "
          f"truncating each to {JUDGMENT_TEXT_MAX_CHARS} characters -- see "
          f"settings at the top of this file to adjust.)")
    all_judgment_chunks = []
    all_judgment_chunks.extend(load_il_pcsr_chunks())
    all_judgment_chunks.extend(load_opennyai_chunks())
    print(f"Total judgment chunks loaded: {len(all_judgment_chunks)}\n")
    return all_judgment_chunks


# ---------------------------------------------------------
# STEP 2: Generate embeddings for every chunk
# ---------------------------------------------------------
def generate_embeddings(chunks, model):
    """
    Converts each chunk's text into a vector using the embedding model.
    Combines title + text for slightly better context in the embedding.
    """
    texts_to_embed = [
        f"{c['act_name']} Section {c['number']}: {c['title']}. {c['text']}"
        for c in chunks
    ]

    print(f"Generating embeddings for {len(texts_to_embed)} chunks...")
    embeddings = model.encode(
        texts_to_embed,
        show_progress_bar=True,
        convert_to_numpy=True,
        batch_size=32,
    )
    return embeddings


# ---------------------------------------------------------
# STEP 3: Build and save the FAISS index
# ---------------------------------------------------------
def build_faiss_index(embeddings):
    """
    Creates a FAISS index from the embeddings for fast similarity search.
    Uses a simple flat L2 index -- good enough for a few thousand chunks.
    """
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings.astype(np.float32))
    print(f"Built FAISS index with {index.ntotal} vectors of dimension {dimension}.")
    return index


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    # 1. Load all chunks from your cleaned statute JSON files
    statute_chunks = load_all_chunks()

    # 1b. Load judgment/case-law chunks (IL-PCSR, OpenNyAI) and merge them in
    judgment_chunks = load_judgment_chunks()

    chunks = statute_chunks + judgment_chunks
    print(f"Combined total: {len(statute_chunks)} statute chunks + "
          f"{len(judgment_chunks)} judgment chunks = {len(chunks)} chunks\n")

    if not chunks:
        print("Nothing to embed. Exiting.")
        exit()

    # 2. Load the embedding model (downloads once, then cached locally)
    print(f"Loading embedding model: {EMBEDDING_MODEL_NAME} ...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    # 3. Generate embeddings
    embeddings = generate_embeddings(chunks, model)

    # 4. Build FAISS index
    index = build_faiss_index(embeddings)

    # 5. Save everything to disk
    faiss.write_index(index, str(VECTOR_DB_DIR / "legal_index.faiss"))

    with open(VECTOR_DB_DIR / "chunk_metadata.pkl", "wb") as f:
        pickle.dump(chunks, f)

    print("\nDone!")
    print(f"  - FAISS index saved to: {VECTOR_DB_DIR / 'legal_index.faiss'}")
    print(f"  - Chunk metadata saved to: {VECTOR_DB_DIR / 'chunk_metadata.pkl'}")
    print(f"\nYour vector database is ready with {len(chunks)} searchable legal chunks.")
