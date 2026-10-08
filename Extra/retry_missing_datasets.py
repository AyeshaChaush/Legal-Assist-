"""
Retry script: just IL-TUR and OpenNyAI
----------------------------------------
Run with:
    python retry_missing_datasets.py
"""

from pathlib import Path
from datasets import load_dataset

BASE_DIR = Path("data/judgments")
BASE_DIR.mkdir(parents=True, exist_ok=True)


def try_download(name, repo_id, config=None):
    print(f"\nAttempting: {name} ({repo_id}) ...")
    try:
        if config:
            ds = load_dataset(repo_id, name=config)
        else:
            ds = load_dataset(repo_id)
        save_path = BASE_DIR / name.lower()
        ds.save_to_disk(str(save_path))
        print(f"[OK] Saved {name} to {save_path}")
        print(ds)
    except Exception as e:
        print(f"[FAIL] Could not download {name}")
        print(f"       Error: {e}")


if __name__ == "__main__":
    try_download("IL-TUR", "Exploration-Lab/IL-TUR")
    try_download("OpenNyAI", "opennyaiorg/InJudgements_dataset")

    print("\nDone. Check data/judgments/ for results.")
