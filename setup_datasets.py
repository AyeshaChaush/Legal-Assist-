"""
Legal Assist+ : Dataset & Model Setup Script
----------------------------------------------
This script downloads/sets up the open-source datasets and models
needed for the project's RAG knowledge base and embeddings.

Run once at the start of the project:
    python setup_datasets.py

Requirements (install first):
    pip install datasets huggingface_hub transformers sentence-transformers requests beautifulsoup4 tqdm
"""

import os
from pathlib import Path

# ---------------------------------------------------------
# 1. FOLDER STRUCTURE SETUP
# ---------------------------------------------------------
BASE_DIR = Path("data")
FOLDERS = [
    "statutes",          # Constitution, BNS, BNSS, BSA, Central Acts (manual PDFs)
    "statutes/legacy",   # IPC, CrPC, Evidence Act (for old-law mapping)
    "statutes/state",    # State-specific acts/amendments
    "judgments",         # Case law datasets (ILDC, IL-TUR, etc.)
    "contracts",         # CUAD, LEDGAR clause datasets
    "models",            # Downloaded embedding models
    "raw_pdfs",          # Dumping ground for manually downloaded PDFs
]

def setup_folders():
    print("Creating folder structure...")
    for folder in FOLDERS:
        path = BASE_DIR / folder
        path.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] {path}")
    print("Folder structure ready.\n")


# ---------------------------------------------------------
# 2. HUGGING FACE DATASETS (case law / judgments)
# ---------------------------------------------------------
def download_hf_datasets():
    """
    Downloads open Indian legal datasets from Hugging Face.
    Some datasets are 'gated' (e.g., IL-PCSR) and require you to:
      1. Visit the dataset page on huggingface.co while logged in
      2. Click 'Request Access' and accept the terms
      3. Run `huggingface-cli login` locally with your access token
    before this script can pull them.
    """
    from datasets import load_dataset

    hf_datasets = {
        # name : (hf_repo_id, config_name_or_None)
        "IL-TUR": ("Exploration-Lab/IL-TUR", None),        # includes ILDC, HLDC, ILSI, IL-PCR, In-Abs, MiLPaC
        "IL-PCSR": ("Exploration-Lab/IL-PCSR", "queries"), # gated - needs access approval
    }

    for name, (repo_id, config) in hf_datasets.items():
        print(f"Downloading {name} ({repo_id}) ...")
        try:
            if config:
                ds = load_dataset(repo_id, name=config)
            else:
                ds = load_dataset(repo_id)
            save_path = BASE_DIR / "judgments" / name.lower()
            ds.save_to_disk(str(save_path))
            print(f"  [OK] Saved to {save_path}\n")
        except Exception as e:
            print(f"  [FAIL] Could not download {name}: {e}")
            print(f"    -> If this is a gated dataset, request access on huggingface.co first.\n")


def download_kanoongpt_dataset():
    """KanoonGPT open Indian case-law dataset (metadata-rich judgments)."""
    from datasets import load_dataset
    print("Downloading KanoonGPT/indian-case-laws ...")
    try:
        ds = load_dataset("KanoonGPT/indian-case-laws")
        save_path = BASE_DIR / "judgments" / "kanoongpt"
        ds.save_to_disk(str(save_path))
        print(f"  [OK] Saved to {save_path}\n")
    except Exception as e:
        print(f"  [FAIL] Could not download KanoonGPT dataset: {e}\n")


def download_opennyai_dataset():
    """OpenNyAI categorized Indian judgments dataset."""
    from datasets import load_dataset
    print("Downloading opennyaiorg/InJudgements_dataset ...")
    try:
        ds = load_dataset("opennyaiorg/InJudgements_dataset")
        save_path = BASE_DIR / "judgments" / "opennyai"
        ds.save_to_disk(str(save_path))
        print(f"  [OK] Saved to {save_path}\n")
    except Exception as e:
        print(f"  [FAIL] Could not download OpenNyAI dataset: {e}\n")


# ---------------------------------------------------------
# 3. CONTRACT CLAUSE DATASETS
# ---------------------------------------------------------
def download_contract_datasets():
    """CUAD-style contract clause dataset for the clause-risk-analysis feature."""
    from datasets import load_dataset
    print("Downloading contract clause datasets ...")
    try:
        # Community mirror of CUAD on Hugging Face
        ds = load_dataset("theatticusproject/cuad-qa")
        save_path = BASE_DIR / "contracts" / "cuad"
        ds.save_to_disk(str(save_path))
        print(f"  [OK] Saved CUAD to {save_path}\n")
    except Exception as e:
        print(f"  [FAIL] Could not download CUAD: {e}")
        print("    -> Alternative: manually download from atticusprojectai.org/cuad\n")


# ---------------------------------------------------------
# 4. PRETRAINED MODELS (embeddings)
# ---------------------------------------------------------
def download_models():
    """
    Downloads InLegalBERT (legal-domain embeddings) and a lightweight
    general-purpose fallback embedding model.
    """
    from transformers import AutoModel, AutoTokenizer

    models_to_get = {
        "InLegalBERT": "law-ai/InLegalBERT",
    }

    for name, repo_id in models_to_get.items():
        print(f"Downloading model: {name} ({repo_id}) ...")
        try:
            save_path = BASE_DIR / "models" / name
            tokenizer = AutoTokenizer.from_pretrained(repo_id)
            model = AutoModel.from_pretrained(repo_id)
            tokenizer.save_pretrained(str(save_path))
            model.save_pretrained(str(save_path))
            print(f"  [OK] Saved to {save_path}\n")
        except Exception as e:
            print(f"  [FAIL] Could not download {name}: {e}\n")

    # Lightweight fallback embedding model via sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer
        print("Downloading fallback model: sentence-transformers/all-MiniLM-L6-v2 ...")
        st_model = SentenceTransformer("all-MiniLM-L6-v2")
        save_path = BASE_DIR / "models" / "MiniLM-L6-v2"
        st_model.save(str(save_path))
        print(f"  [OK] Saved to {save_path}\n")
    except Exception as e:
        print(f"  [FAIL] Could not download fallback model: {e}\n")


# ---------------------------------------------------------
# 5. MANUAL DOWNLOAD REMINDERS (no public API available)
# ---------------------------------------------------------
def print_manual_download_reminders():
    """
    India Code, e-Gazette, and NCRB SANKALAN do NOT provide public APIs.
    These must be downloaded manually (or scraped separately later in
    Phase 6 of the project) and placed in data/raw_pdfs/.
    """
    reminders = [
        ("Constitution of India", "https://www.indiacode.nic.in"),
        ("Bharatiya Nyaya Sanhita (BNS) 2023", "https://sankalan.ncrb.gov.in"),
        ("Bharatiya Nagarik Suraksha Sanhita (BNSS) 2023", "https://sankalan.ncrb.gov.in"),
        ("Bharatiya Sakshya Adhiniyam (BSA) 2023", "https://sankalan.ncrb.gov.in"),
        ("IPC / CrPC / Evidence Act (legacy, for mapping)", "https://www.indiacode.nic.in"),
        ("Selected Central Acts (Consumer Protection, IT Act, etc.)", "https://www.indiacode.nic.in"),
        ("State-specific Acts/Amendments (pick 2-3 states)", "respective state law department website"),
        ("e-Gazette notifications", "https://egazette.gov.in"),
    ]

    print("=" * 70)
    print("MANUAL DOWNLOAD REQUIRED (no public API available for these):")
    print("=" * 70)
    for name, url in reminders:
        print(f"  - {name}\n      -> {url}")
    print("\nDownload these as PDFs and place them in: data/raw_pdfs/")
    print("They will be cleaned and chunked in the next pipeline step.\n")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    setup_folders()

    print("Starting downloads. This may take a few minutes...\n")

    download_hf_datasets()
    download_kanoongpt_dataset()
    download_opennyai_dataset()
    download_contract_datasets()
    download_models()

    print_manual_download_reminders()

    print("Setup complete. Check the 'data/' folder for downloaded content.")
