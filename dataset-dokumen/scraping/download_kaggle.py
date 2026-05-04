"""
Download & Filter WikiHow Multilingual Dataset dari Kaggle.
Memfilter hanya data Bahasa Indonesia dan mengkonversi ke format SOP.

Dataset: https://www.kaggle.com/datasets/paolop/human-instructions-multilingual-wikihow
Deskripsi: 800K formalised step-by-step instructions in 16 languages

Setup:
  1. pip install kaggle
  2. Download API key dari https://www.kaggle.com/settings → Create New Token
  3. Taruh kaggle.json di ~/.kaggle/kaggle.json
  4. chmod 600 ~/.kaggle/kaggle.json
  5. Jalankan: python3 download_kaggle.py

Atau download manual:
  1. Buka https://www.kaggle.com/datasets/paolop/human-instructions-multilingual-wikihow
  2. Klik Download
  3. Extract ZIP ke folder ini
  4. Jalankan script ini
"""

import csv
import json
import os
import re
import subprocess
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_SLUG = "paolop/human-instructions-multilingual-wikihow"
ZIP_FILE = os.path.join(SCRIPT_DIR, "human-instructions-multilingual-wikihow.zip")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "raw_kaggle_id.jsonl")

# Bahasa yang kita mau
TARGET_LANG = "id"  # Bahasa Indonesia


def download_from_kaggle():
    """Download dataset dari Kaggle menggunakan Kaggle CLI."""
    print("[1] Downloading dari Kaggle...")

    # Cek apakah sudah ada file yang terextract
    csv_files = [f for f in os.listdir(SCRIPT_DIR) if f.endswith('.csv')]
    if csv_files:
        print(f"  File CSV sudah ada: {csv_files}")
        return True

    # Cek apakah ZIP sudah ada
    zip_files = [f for f in os.listdir(SCRIPT_DIR) if f.endswith('.zip')]
    if zip_files:
        print(f"  ZIP sudah ada: {zip_files[0]}, extracting...")
        with zipfile.ZipFile(os.path.join(SCRIPT_DIR, zip_files[0]), 'r') as z:
            z.extractall(SCRIPT_DIR)
        return True

    # Download via Kaggle CLI
    try:
        result = subprocess.run(
            ["kaggle", "datasets", "download", "-d", DATASET_SLUG, "-p", SCRIPT_DIR],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            print(f"  Download berhasil!")
            # Extract ZIP
            zip_files = [f for f in os.listdir(SCRIPT_DIR) if f.endswith('.zip')]
            if zip_files:
                with zipfile.ZipFile(os.path.join(SCRIPT_DIR, zip_files[0]), 'r') as z:
                    z.extractall(SCRIPT_DIR)
            return True
        else:
            print(f"  [ERROR] Kaggle CLI gagal: {result.stderr}")
            return False
    except FileNotFoundError:
        print("  [ERROR] Kaggle CLI belum terinstall!")
        print("  Jalankan: pip install kaggle")
        print("  Atau download manual dari:")
        print(f"  https://www.kaggle.com/datasets/{DATASET_SLUG}")
        return False
    except subprocess.TimeoutExpired:
        print("  [ERROR] Download timeout (> 5 menit)")
        return False


def find_csv_files():
    """Cari semua CSV file di directory."""
    csv_files = []
    for root, dirs, files in os.walk(SCRIPT_DIR):
        for f in files:
            if f.endswith('.csv'):
                csv_files.append(os.path.join(root, f))
    return csv_files


def format_as_sop(title, steps):
    """Format langkah-langkah menjadi SOP formal."""
    sop_parts = []

    # Clean title
    clean_title = title
    for prefix in ["Cara ", "cara ", "Bagaimana ", "bagaimana "]:
        if clean_title.startswith(prefix):
            clean_title = clean_title[len(prefix):]
            break

    sop_parts.append(f"## SOP: {clean_title.strip()}")
    sop_parts.append("")

    # Tujuan
    sop_parts.append("### Tujuan")
    sop_parts.append(f"Menetapkan prosedur standar untuk {clean_title.lower().strip()}.")
    sop_parts.append("")

    # Ruang Lingkup
    sop_parts.append("### Ruang Lingkup")
    sop_parts.append(f"SOP ini berlaku untuk seluruh proses {clean_title.lower().strip()}.")
    sop_parts.append("")

    # Prosedur Kerja
    sop_parts.append("### Prosedur Kerja")
    for i, step in enumerate(steps, 1):
        step_clean = step.strip()
        if step_clean:
            sop_parts.append(f"{i}. {step_clean}")
    sop_parts.append("")

    return "\n".join(sop_parts)


def process_csv(filepath):
    """Process satu file CSV dan filter bahasa Indonesia."""
    results = []
    print(f"\n  Processing: {os.path.basename(filepath)}")

    try:
        # Coba baca dengan berbagai encoding
        for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1']:
            try:
                with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                    # Baca dulu beberapa baris untuk lihat struktur
                    sample = f.read(2000)
                    f.seek(0)

                    reader = csv.DictReader(f)
                    columns = reader.fieldnames
                    print(f"    Kolom: {columns}")

                    count = 0
                    id_count = 0

                    for row in reader:
                        count += 1

                        # Cek apakah ada kolom language
                        lang = None
                        for col in ['language', 'lang', 'Language', 'Lang']:
                            if col in row:
                                lang = row[col].strip().lower()
                                break

                        # Filter hanya bahasa Indonesia
                        if lang and lang not in ['id', 'indonesian', 'ind', 'bahasa indonesia']:
                            continue

                        # Jika tidak ada kolom language, cek dari title/content
                        title = ""
                        for col in ['title', 'Title', 'TITLE', 'article_title', 'headline']:
                            if col in row and row[col]:
                                title = row[col].strip()
                                break

                        # Extract steps/content
                        steps = []
                        content = ""

                        for col in ['steps', 'Steps', 'content', 'Content',
                                   'article_content', 'Article Content',
                                   'text', 'Text', 'instructions']:
                            if col in row and row[col]:
                                content = row[col].strip()
                                break

                        # Jika ada content, parse steps
                        if content:
                            # Coba split by newline atau numbering
                            if '\n' in content:
                                steps = [s.strip() for s in content.split('\n') if s.strip()]
                            else:
                                # Coba split by numbering pattern
                                step_pattern = re.split(r'\d+[\.\)]\s+', content)
                                steps = [s.strip() for s in step_pattern if s.strip()]

                        # Juga cek kolom individual step
                        for col in columns or []:
                            if col and ('step' in col.lower() or 'instruction' in col.lower()):
                                if col in row and row[col] and row[col].strip():
                                    steps.append(row[col].strip())

                        if not title and not steps:
                            continue

                        # Hanya simpan jika ada minimal 3 langkah
                        if len(steps) < 2:
                            # Jika ada content tapi gak bisa di-split, simpan as-is
                            if content and len(content) > 50:
                                steps = [content]
                            else:
                                continue

                        sop_text = format_as_sop(title, steps)

                        results.append({
                            "id": f"kaggle_{id_count:05d}",
                            "source": "kaggle_wikihow",
                            "title": title,
                            "num_steps": len(steps),
                            "steps_raw": steps,
                            "sop_text": sop_text,
                            "language": lang or "unknown",
                        })
                        id_count += 1

                    print(f"    Total rows: {count}")
                    print(f"    Indonesian entries: {id_count}")
                    break  # Berhasil baca, keluar dari loop encoding

            except UnicodeDecodeError:
                continue

    except Exception as e:
        print(f"    [ERROR] {e}")

    return results


def main():
    print("=" * 60)
    print("Kaggle WikiHow Dataset Downloader & Filter")
    print("=" * 60)

    # Step 1: Download
    download_from_kaggle()

    # Step 2: Find CSV files
    csv_files = find_csv_files()
    if not csv_files:
        print("\n[ERROR] Tidak ada CSV file ditemukan!")
        print("Download manual dari:")
        print(f"  https://www.kaggle.com/datasets/{DATASET_SLUG}")
        print(f"  Extract ke: {SCRIPT_DIR}")
        return

    print(f"\nDitemukan {len(csv_files)} CSV file(s)")

    # Step 3: Process & filter
    print("\n[2] Filtering data Bahasa Indonesia...")
    all_results = []
    for csv_file in csv_files:
        results = process_csv(csv_file)
        all_results.extend(results)

    if not all_results:
        print("\n[WARNING] Tidak ada data Indonesia ditemukan dari Kaggle.")
        print("Kemungkinan format dataset berbeda. Coba cek manual CSV filenya.")
        print("Dataset mungkin perlu difilter dengan cara lain.")
        print("\nSebagai alternatif, jalankan scrape_wikihow.py untuk scraping langsung.")
        return

    # Step 4: Save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for entry in all_results:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"\n{'=' * 60}")
    print(f"SELESAI!")
    print(f"  Data Indonesia: {len(all_results)} entries")
    print(f"  Disimpan di: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
