"""
Retry: IL-TUR with specific configs relevant to Legal Assist+
Run with:
    python retry_iltur_configs.py
"""

from pathlib import Path
from datasets import load_dataset

BASE_DIR = Path("data/judgments/il-tur")
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Only the configs relevant to our project
CONFIGS_TO_DOWNLOAD = ["lsi", "pcr", "summ"]

for config in CONFIGS_TO_DOWNLOAD:
    print(f"\nAttempting IL-TUR config: {config} ...")
    try:
        ds = load_dataset("Exploration-Lab/IL-TUR", config)
        save_path = BASE_DIR / config
        ds.save_to_disk(str(save_path))
        print(f"[OK] Saved '{config}' to {save_path}")
        print(ds)
    except Exception as e:
        print(f"[FAIL] Could not download config '{config}': {e}")

print("\nDone. Check data/judgments/il-tur/ for results.")
