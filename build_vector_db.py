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
VECTOR_DB_DIR = Path("data/vector_db")
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

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
            }
            if chunk["text"].strip():  # skip empty entries
                all_chunks.append(chunk)

    jurisdictions_found = sorted(set(c["jurisdiction"] for c in all_chunks))
    print(f"Loaded {len(all_chunks)} total chunks from {len(json_files)} file(s).")
    print(f"Jurisdictions detected: {jurisdictions_found}")
    return all_chunks


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
    # 1. Load all chunks from your cleaned JSON files
    chunks = load_all_chunks()

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
