"""
Merge & Clean semua hasil scraping menjadi satu file SOP terstandarisasi.

Input:  raw_wikihow.jsonl, raw_sop_templates.jsonl
Output: cleaned_sop.jsonl
"""

import json
import os
import re

SCRIPT_DIR = os.path.dirname(__file__)
WIKIHOW_FILE = os.path.join(SCRIPT_DIR, "raw_wikihow.jsonl")
SOP_TEMPLATES_FILE = os.path.join(SCRIPT_DIR, "raw_sop_templates.jsonl")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "cleaned_sop.jsonl")


def clean_text(text):
    """Bersihkan teks dari karakter aneh dan whitespace berlebih."""
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()
    return text


def standardize_wikihow(entry):
    """Standardize format dari WikiHow entry."""
    return {
        "id": f"wikihow_{hash(entry['url']) % 100000:05d}",
        "source": "wikihow",
        "title": entry.get("title", ""),
        "sop_text": clean_text(entry.get("sop_text", "")),
        "num_steps": entry.get("num_steps", 0),
        "url": entry.get("url", ""),
    }


def standardize_sop_template(entry):
    """Standardize format dari SOP template scrape."""
    # Coba buat SOP text dari sections jika ada
    sections = entry.get("sections", {})
    if sections:
        sop_parts = []
        title = entry.get("title", "Prosedur Operasional")
        sop_parts.append(f"## SOP: {title}")
        sop_parts.append("")

        if "tujuan" in sections:
            sop_parts.append("### Tujuan")
            sop_parts.append(sections["tujuan"])
            sop_parts.append("")

        if "ruang_lingkup" in sections:
            sop_parts.append("### Ruang Lingkup")
            sop_parts.append(sections["ruang_lingkup"])
            sop_parts.append("")

        if "penanggung_jawab" in sections:
            sop_parts.append("### Penanggung Jawab")
            sop_parts.append(sections["penanggung_jawab"])
            sop_parts.append("")

        if "prosedur" in sections:
            sop_parts.append("### Prosedur Kerja")
            sop_parts.append(sections["prosedur"])
            sop_parts.append("")

        sop_text = "\n".join(sop_parts)
    else:
        sop_text = entry.get("full_text", "")

    return {
        "id": f"web_{hash(entry['url']) % 100000:05d}",
        "source": "web_scrape",
        "title": entry.get("title", ""),
        "sop_text": clean_text(sop_text),
        "num_steps": sop_text.count("\n") // 3,  # rough estimate
        "url": entry.get("url", ""),
    }


def load_jsonl(filepath):
    """Load file JSONL."""
    entries = []
    if not os.path.exists(filepath):
        print(f"  File tidak ditemukan: {filepath}")
        return entries
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def main():
    print("=" * 60)
    print("Merge & Clean Scraped SOP Data")
    print("=" * 60)

    all_sops = []

    # Load WikiHow
    print("\n[1] Loading WikiHow data...")
    wikihow_data = load_jsonl(WIKIHOW_FILE)
    print(f"  Loaded {len(wikihow_data)} entries")
    for entry in wikihow_data:
        standardized = standardize_wikihow(entry)
        if len(standardized["sop_text"]) >= 100:
            all_sops.append(standardized)

    # Load SOP Templates
    print("\n[2] Loading SOP template data...")
    sop_data = load_jsonl(SOP_TEMPLATES_FILE)
    print(f"  Loaded {len(sop_data)} entries")
    for entry in sop_data:
        standardized = standardize_sop_template(entry)
        if len(standardized["sop_text"]) >= 100:
            all_sops.append(standardized)

    # Deduplicate by title (fuzzy)
    seen_titles = set()
    deduped = []
    for sop in all_sops:
        title_key = re.sub(r'\W+', '', sop["title"].lower())
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            deduped.append(sop)

    print(f"\n[3] Deduplicated: {len(all_sops)} → {len(deduped)}")

    # Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for sop in deduped:
            f.write(json.dumps(sop, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 60}")
    print(f"SELESAI! Total SOP bersih: {len(deduped)}")
    print(f"Disimpan di: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
