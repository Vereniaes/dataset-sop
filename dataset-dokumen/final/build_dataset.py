"""
Final Dataset Builder — SOP-ify
Menggabungkan semua sumber data dan membuat train/val/test split.

Input:
  - dataset/scraping/cleaned_sop.jsonl
  - dataset/synthetic-generation/paired_data.jsonl
  - dataset/searching-umkm/gold_standard.jsonl (opsional)

Output:
  - dataset/final/train.jsonl (80%)
  - dataset/final/val.jsonl   (10%)
  - dataset/final/test.jsonl  (10% + gold standard)
  - dataset/final/stats.json  (statistik dataset)
"""

import json
import os
import random
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

# Input files
SYNTHETIC_FILE = os.path.join(BASE_DIR, "synthetic-generation", "paired_data.jsonl")
GOLD_FILE = os.path.join(BASE_DIR, "searching-umkm", "gold_standard.jsonl")

# Output directory
OUTPUT_DIR = os.path.join(BASE_DIR, "final")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TRAIN_FILE = os.path.join(OUTPUT_DIR, "train.jsonl")
VAL_FILE = os.path.join(OUTPUT_DIR, "val.jsonl")
TEST_FILE = os.path.join(OUTPUT_DIR, "test.jsonl")
STATS_FILE = os.path.join(OUTPUT_DIR, "stats.json")

# Config
RANDOM_SEED = 42
TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10


def load_jsonl(filepath, required=False):
    """Load JSONL file."""
    data = []
    if not os.path.exists(filepath):
        if required:
            print(f"[ERROR] File required tidak ditemukan: {filepath}")
        else:
            print(f"[INFO] File opsional tidak ditemukan: {filepath}")
        return data

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return data


def save_jsonl(data, filepath):
    """Save data ke JSONL file."""
    with open(filepath, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def standardize_entry(entry, source_type):
    """Standardize semua entry ke format yang sama."""
    if source_type == "synthetic":
        return {
            "instruction": entry.get("instruction", ""),
            "input": entry.get("input", ""),
            "output": entry.get("output", ""),
            "source": "synthetic",
            "persona": entry.get("metadata", {}).get("persona", "unknown"),
        }
    elif source_type == "gold":
        return {
            "instruction": "Ubah catatan berantakan berikut menjadi dokumen SOP yang rapi dan terstruktur.",
            "input": entry.get("raw_text", ""),
            "output": entry.get("manual_sop", ""),
            "source": "gold_standard",
            "persona": "real_umkm",
        }
    return entry


def main():
    print("=" * 60)
    print("Final Dataset Builder — SOP-ify")
    print("=" * 60)

    random.seed(RANDOM_SEED)

    # Load data
    print("\n[1] Loading data...")

    synthetic_data = load_jsonl(SYNTHETIC_FILE, required=True)
    print(f"  Synthetic pairs: {len(synthetic_data)}")

    gold_data = load_jsonl(GOLD_FILE, required=False)
    # Filter gold data yang sudah punya manual_sop
    gold_data = [g for g in gold_data if g.get("manual_sop")]
    print(f"  Gold standard (with SOP): {len(gold_data)}")

    # Standardize
    print("\n[2] Standardizing format...")
    all_synthetic = [standardize_entry(e, "synthetic") for e in synthetic_data]
    all_gold = [standardize_entry(e, "gold") for e in gold_data]

    # Filter entries yang valid (punya input dan output)
    all_synthetic = [e for e in all_synthetic if e["input"] and e["output"]]
    all_gold = [e for e in all_gold if e["input"] and e["output"]]

    print(f"  Valid synthetic: {len(all_synthetic)}")
    print(f"  Valid gold: {len(all_gold)}")

    # Split synthetic data
    print("\n[3] Splitting data...")
    random.shuffle(all_synthetic)

    n = len(all_synthetic)
    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)

    train_data = all_synthetic[:n_train]
    val_data = all_synthetic[n_train:n_train + n_val]
    test_data = all_synthetic[n_train + n_val:]

    # Gold standard selalu masuk ke test set
    test_data.extend(all_gold)

    print(f"  Train: {len(train_data)}")
    print(f"  Val:   {len(val_data)}")
    print(f"  Test:  {len(test_data)} (termasuk {len(all_gold)} gold standard)")

    # Save
    print("\n[4] Saving...")
    save_jsonl(train_data, TRAIN_FILE)
    save_jsonl(val_data, VAL_FILE)
    save_jsonl(test_data, TEST_FILE)

    # Stats
    stats = {
        "total": len(train_data) + len(val_data) + len(test_data),
        "train": len(train_data),
        "val": len(val_data),
        "test": len(test_data),
        "gold_standard_in_test": len(all_gold),
        "source_distribution": dict(Counter(
            e["source"] for e in train_data + val_data + test_data
        )),
        "persona_distribution": dict(Counter(
            e.get("persona", "unknown") for e in train_data + val_data + test_data
        )),
        "avg_input_length": sum(len(e["input"]) for e in train_data) / max(len(train_data), 1),
        "avg_output_length": sum(len(e["output"]) for e in train_data) / max(len(train_data), 1),
    }

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"DATASET FINAL SELESAI!")
    print(f"  Train:  {TRAIN_FILE} ({len(train_data)} entries)")
    print(f"  Val:    {VAL_FILE} ({len(val_data)} entries)")
    print(f"  Test:   {TEST_FILE} ({len(test_data)} entries)")
    print(f"  Stats:  {STATS_FILE}")
    print(f"  Total:  {stats['total']} entries")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
