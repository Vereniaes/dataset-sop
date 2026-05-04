"""
generate_tabel.py
=================
Generate dataset pasangan (input_kasual → output_markdown_tabel) untuk fine-tuning LLM.

Alur:
  1. Load SOP formal dari cleaned_sop.jsonl
  2. Untuk tiap SOP, generate 2 hal:
     - Versi kasual INPUT (deskripsi santai pemilik UMKM)
     - Versi Markdown Table OUTPUT (SOP dalam format tabel No/Langkah/PIC/Waktu)
  3. Validasi syntax tabel (kolom konsisten, ada header + separator + data)
  4. Simpan ke paired_tabel.jsonl

Format output JSONL:
  {
    "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Tabel...",
    "input": "[deskripsi kasual pemilik UMKM]",
    "output": "**SOP: [Judul]**\\n\\n| No | Langkah | ... |",
    "metadata": { ... }
  }

Jalankan:
  python3 generate_tabel.py
  python3 generate_tabel.py --limit 50     # test dengan 50 SOP dulu
  python3 generate_tabel.py --resume       # lanjut dari yang sudah ada
"""

import json
import os
import re
import time
import random
import argparse
from pathlib import Path
from google import genai
from google.genai import types
from tqdm import tqdm

# ─── Konfigurasi ──────────────────────────────────────────────────────────────

SCRIPT_DIR  = Path(__file__).parent
INPUT_FILE  = SCRIPT_DIR / ".." / "dataset-dokumen" / "scraping" / "cleaned_sop.jsonl"
OUTPUT_FILE = SCRIPT_DIR / "paired_tabel.jsonl"

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get(
    "VERTEX_API_KEY", ""
)
MODEL   = "gemini-3.1-pro-preview"

VARIATIONS_PER_SOP  = 2
DELAY_BETWEEN_CALLS = 2

# ─── Variasi format kolom tabel yang diperbolehkan ────────────────────────────
# Model harus belajar memilih variasi yang sesuai konteks SOP
TABLE_VARIANTS = [
    {
        "name":    "standar",
        "header":  "| No | Langkah | Penanggung Jawab | Waktu |",
        "sep":     "|----|---------|-----------------|-------|",
        "desc":    "Format standar 4 kolom: No, Langkah, PIC, Waktu",
    },
    {
        "name":    "simplified",
        "header":  "| No | Langkah | Keterangan |",
        "sep":     "|----|---------|------------|",
        "desc":    "Format 3 kolom sederhana: No, Langkah, Keterangan",
    },
    {
        "name":    "checklist",
        "header":  "| No | Langkah | PIC | Waktu | Status |",
        "sep":     "|----|---------|-----|-------|--------|",
        "desc":    "Format 5 kolom dengan kolom Status checklist (☐)",
    },
]

# ─── Persona INPUT ────────────────────────────────────────────────────────────

INPUT_PERSONAS = [
    {
        "name": "pemilik_santai",
        "prompt": """Berperanlah sebagai pemilik UMKM yang cerita ke teman soal cara kerja di usahanya.
Ceritakan isi SOP berikut dalam bahasa santai seperti ngobrol biasa.

Aturan KETAT:
- JANGAN pakai format list/bullet/numbering formal
- Pakai bahasa Indonesia kasual (yaudah, emang, biar ga ribet, sih, deh)
- Seolah lagi ngobrol spontan, boleh loncat-loncat
- Sebutkan nama orang sembarang (si Budi, Mbak Rina, dll)
- Panjang: 80-200 kata""",
    },
    {
        "name": "pemilik_buru",
        "prompt": """Berperanlah sebagai pemilik UMKM yang terburu-buru menjelaskan prosedur ke karyawan baru.

Aturan KETAT:
- Kalimat pendek, sering tidak selesai
- Pakai filler: pokoknya, yang penting, intinya
- Urutan sedikit melompat
- Sesekali kasih warning: "eh jangan lupa", "awas kelupaan"
- Panjang: 80-200 kata""",
    },
    {
        "name": "karyawan_senior",
        "prompt": """Berperanlah sebagai karyawan senior yang ngajarin karyawan baru secara santai.

Aturan KETAT:
- Pakai gaya "nah gini", "jadi gini", "nah ini penting"
- Boleh kasih tips personal
- Pakai "gue-lo" atau "aku-kamu" santai
- Boleh urutan sedikit berantakan
- Panjang: 80-200 kata""",
    },
    {
        "name": "chat_singkat",
        "prompt": """Berperanlah sebagai pemilik UMKM yang ngetik cepat di WA group.

Aturan KETAT:
- Kalimat sangat pendek
- Banyak singkatan (yg, gak, udh, hrs, trs, jgn, lgsg, sblm)
- Emoji sesekali (max 3)
- Urutan campur aduk
- Panjang: 60-150 kata""",
    },
]

# ─── Prompt untuk generate OUTPUT Markdown Table ──────────────────────────────

TABLE_SYSTEM = """Kamu adalah asisten yang mengubah dokumen SOP formal menjadi tabel Markdown yang terstruktur.
HANYA hasilkan tabel Markdown-nya saja, tanpa penjelasan, tanpa komentar tambahan.
Langsung mulai dengan judul tabel bold (**SOP: ...**) diikuti baris kosong, lalu tabelnya."""

TABLE_PROMPT_TEMPLATE = """Ubah dokumen SOP formal berikut menjadi tabel Markdown.

SOP yang harus diubah:
---
{sop_text}
---

Format tabel yang harus digunakan:
{variant_desc}

Header tabel: {header}
Separator   : {sep}

Aturan KETAT:
1. Baris pertama: judul bold → `**SOP: [nama proses singkat]**`
2. Baris kedua: kosong
3. Baris ketiga: header tabel sesuai format di atas
4. Baris keempat: separator sesuai format di atas
5. Baris berikutnya: satu baris per langkah, minimal 4 baris, maksimal 15 baris
6. Kolom "Penanggung Jawab" / "PIC": gunakan role generik jika tidak ada nama (Staf, Manajer, Kasir, Barista, Teknisi, dll)
7. Kolom "Waktu": gunakan jam spesifik jika ada, atau "Sesuai kebutuhan" / "-" jika tidak ada
8. Kolom "Status" (jika ada): isi dengan "☐" (belum) untuk semua baris
9. TIDAK BOLEH ada heading markdown lain (##, ###) — hanya judul bold + tabel
10. Jumlah pipe `|` di setiap baris data HARUS SAMA dengan di header
11. Isi tiap sel: singkat dan jelas, maks 7 kata per sel

Langsung tulis output-nya:"""

INSTRUCTION = (
    "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Tabel "
    "(format Markdown table dengan kolom No, Langkah, Penanggung Jawab, dan Waktu/Keterangan). "
    "Sertakan judul tabel di atas."
)

# ─── Validasi Markdown Table ───────────────────────────────────────────────────

def validate_table(text: str) -> tuple[bool, str]:
    """
    Validasi struktur Markdown table.
    Return (is_valid, reason).
    """
    text = text.strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if len(lines) < 4:
        return False, f"Terlalu sedikit baris: {len(lines)}"

    # Harus ada judul bold
    has_title = any(l.startswith("**") for l in lines)
    if not has_title:
        return False, "Tidak ada judul **SOP: ...**"

    # Temukan HANYA baris tabel (dimulai dengan | dan mengandung lebih dari 1 pipe)
    table_lines = [l for l in lines if l.startswith("|") and l.count("|") >= 2]
    if len(table_lines) < 3:
        return False, f"Tabel tidak lengkap: hanya {len(table_lines)} baris tabel"

    # Harus ada separator (baris dengan |---|)
    separator_pattern = re.compile(r'^\|[-| :]+\|$')
    has_separator = any(separator_pattern.match(l) for l in table_lines)
    if not has_separator:
        return False, "Tidak ada baris separator |---|"

    # Hitung kolom dari baris header (baris pertama tabel)
    header_line = table_lines[0]
    col_count = header_line.count("|")

    # Cek konsistensi kolom HANYA pada baris tabel yang valid
    # (skip baris separator karena formatnya berbeda dari data)
    data_and_header = [l for l in table_lines if not separator_pattern.match(l)]
    inconsistent = [
        l for l in data_and_header
        if l.count("|") != col_count
    ]
    if inconsistent:
        return False, f"Jumlah kolom tidak konsisten: {inconsistent[0][:60]}"

    # Hitung baris data (exclude header + separator)
    data_rows = [
        l for l in table_lines
        if not separator_pattern.match(l) and l != header_line
    ]
    if len(data_rows) < 2:
        return False, f"Terlalu sedikit baris data: {len(data_rows)} (min 2)"
    if len(data_rows) > 20:
        return False, f"Terlalu banyak baris data: {len(data_rows)} (max 20)"

    # Tidak boleh ada heading markdown
    has_heading = any(l.startswith("##") or l.startswith("###") for l in lines)
    if has_heading:
        return False, "Ada heading markdown (## atau ###) yang tidak diperbolehkan"

    return True, "OK"


def clean_table_output(text: str) -> str:
    """Bersihkan output dari markdown code block dan teks pengantar jika ada."""
    text = text.strip()
    # Hapus ```markdown atau ``` code fence jika ada
    if "```" in text:
        lines = text.split("\n")
        start_idx = next((i for i, l in enumerate(lines) if l.strip().startswith("```")), None)
        end_idx   = next((i for i in range(len(lines)-1, -1, -1) if lines[i].strip() == "```"), None)
        if start_idx is not None:
            lines = lines[start_idx+1:]
        if end_idx is not None and end_idx < len(lines):
            lines = lines[:end_idx]
        text = "\n".join(lines).strip()
    # Strip teks pengantar sebelum judul **SOP atau baris tabel |
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("**") or l.strip().startswith("|")), 0)
    text = "\n".join(lines[start:]).strip()
    return text


# ─── Helper ───────────────────────────────────────────────────────────────────

def make_client():
    return genai.Client(vertexai=True, api_key=API_KEY)


def load_sop_data(filepath: Path) -> list[dict]:
    data = []
    if not filepath.exists():
        print(f"[ERROR] File tidak ditemukan: {filepath}")
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


def call_gemini(client, prompt: str, system: str, temperature: float = 0.65) -> str | None:
    try:
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            top_p=0.9,
            max_output_tokens=2048,  # dinaikkan dari 1024 agar tabel tidak terpotong
        )
        result = ""
        for chunk in client.models.generate_content_stream(
            model=MODEL, contents=contents, config=config
        ):
            if (
                chunk.candidates
                and chunk.candidates[0].content
                and chunk.candidates[0].content.parts
            ):
                result += chunk.text
        return result.strip() or None
    except Exception as e:
        print(f"  [API ERROR] {e}")
        return None


def generate_pair(client, sop: dict, persona: dict) -> dict | None:
    """
    Generate satu pasangan (input_kasual, output_tabel).
    Step 1: Generate INPUT kasual dari SOP formal pakai persona.
    Step 2: Generate Markdown Table dari SOP formal (dengan random variant).
    """
    sop_text = sop.get("sop_text", "").strip()
    if not sop_text or len(sop_text) < 100:
        return None

    # ── Step 1: Generate INPUT kasual ─────────────────────────────────────────
    input_prompt = f"""{persona['prompt']}

SOP yang harus diceritakan ulang:
---
{sop_text}
---

Langsung tulis teks kasualnya saja, tanpa pengantar atau label."""

    casual_input = call_gemini(
        client, input_prompt,
        system="Kamu adalah generator data NLP. Hasilkan HANYA teks kasual sesuai instruksi persona.",
        temperature=0.9
    )

    if not casual_input or len(casual_input) < 50:
        return None

    time.sleep(DELAY_BETWEEN_CALLS)

    # ── Step 2: Generate OUTPUT Tabel (pilih variant secara acak) ─────────────
    variant = random.choice(TABLE_VARIANTS)
    table_prompt = TABLE_PROMPT_TEMPLATE.format(
        sop_text=sop_text,
        variant_desc=variant["desc"],
        header=variant["header"],
        sep=variant["sep"],
    )

    table_output = None
    for attempt in range(2):  # max 2 attempt
        raw = call_gemini(
            client, table_prompt,
            system=TABLE_SYSTEM,
            temperature=0.55 if attempt == 0 else 0.35
        )
        if not raw:
            continue

        cleaned = clean_table_output(raw)
        is_valid, reason = validate_table(cleaned)

        if is_valid:
            table_output = cleaned
            break
        else:
            tqdm.write(f"  ⚠ Attempt {attempt+1} invalid: {reason}")
            if attempt == 0:
                time.sleep(DELAY_BETWEEN_CALLS)

    if not table_output:
        return None

    return {
        "instruction": INSTRUCTION,
        "input":       casual_input,
        "output":      table_output,
        "metadata": {
            "source_id":      sop.get("id", ""),
            "source_type":    sop.get("source", ""),
            "persona":        persona["name"],
            "original_title": sop.get("title", ""),
            "table_variant":  variant["name"],
            "style":          "kolom_tabel",
        }
    }


def load_existing_keys(filepath: Path) -> set[str]:
    keys = set()
    if not filepath.exists():
        return keys
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                meta = entry.get("metadata", {})
                key = f"{meta.get('source_id','')}_{meta.get('persona','')}"
                keys.add(key)
            except (json.JSONDecodeError, KeyError):
                continue
    return keys


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate dataset Kolom Tabel untuk SOP-ify")
    parser.add_argument("--limit",   type=int, default=None, help="Batasi jumlah SOP diproses")
    parser.add_argument("--resume",  action="store_true",    help="Lanjut dari data yang sudah ada")
    parser.add_argument("--dry-run", action="store_true",    help="Test tanpa API call")
    parser.add_argument("--variant", type=str, default=None,
                        choices=["standar", "simplified", "checklist"],
                        help="Paksa pakai satu variant tabel (default: acak)")
    args = parser.parse_args()

    # Override variant jika diminta
    if args.variant:
        forced = [v for v in TABLE_VARIANTS if v["name"] == args.variant]
        TABLE_VARIANTS.clear()
        TABLE_VARIANTS.extend(forced)
        print(f"  Variant dipaksa: {args.variant}")

    print("=" * 60)
    print("Kolom Tabel Dataset Generator — SOP-ify")
    print(f"Model    : {MODEL}")
    print(f"Input    : {INPUT_FILE}")
    print(f"Output   : {OUTPUT_FILE}")
    print(f"Variants : {[v['name'] for v in TABLE_VARIANTS]}")
    print("=" * 60)

    print(f"\n[1] Loading SOP dari: {INPUT_FILE.resolve()}")
    sop_data = load_sop_data(INPUT_FILE)
    if not sop_data:
        return
    if args.limit:
        sop_data = sop_data[:args.limit]
        print(f"  Dibatasi ke {args.limit} SOP")
    print(f"  Loaded: {len(sop_data)} SOP entries")

    existing_keys: set[str] = set()
    if args.resume and OUTPUT_FILE.exists():
        existing_keys = load_existing_keys(OUTPUT_FILE)
        print(f"  Resume: {len(existing_keys)} pairs sudah ada, akan di-skip")

    if args.dry_run:
        estimasi_calls = len(sop_data) * VARIATIONS_PER_SOP * 2
        print("\n[DRY RUN] Tidak ada API call. Validasi selesai.")
        print(f"  Akan generate: {len(sop_data)} SOP × {VARIATIONS_PER_SOP} persona × 2 steps")
        print(f"  = ~{estimasi_calls} API calls (+ retry jika tabel invalid)")
        print(f"  Estimasi waktu: ~{estimasi_calls * DELAY_BETWEEN_CALLS // 60} menit")
        return

    client = make_client()

    estimasi = len(sop_data) * VARIATIONS_PER_SOP
    print(f"\n[2] Generating ~{estimasi} pairs ({VARIATIONS_PER_SOP} variasi/SOP)...")
    print(f"    Note: Setiap SOP bisa hingga 2 API calls untuk tabel (ada 1x retry)\n")

    success = 0
    failed  = 0
    skipped = 0

    # Hitung distribusi variant untuk monitoring
    variant_count: dict[str, int] = {v["name"]: 0 for v in TABLE_VARIANTS}

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
        for i, sop in enumerate(tqdm(sop_data, desc="Processing SOPs")):
            personas = random.sample(INPUT_PERSONAS, min(VARIATIONS_PER_SOP, len(INPUT_PERSONAS)))

            for persona in personas:
                pair_key = f"{sop.get('id','')}_{persona['name']}"

                if pair_key in existing_keys:
                    skipped += 1
                    continue

                pair = generate_pair(client, sop, persona)
                time.sleep(DELAY_BETWEEN_CALLS)

                if pair is None:
                    failed += 1
                    continue

                variant_count[pair["metadata"]["table_variant"]] += 1
                out_f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                out_f.flush()
                success += 1

            if (i + 1) % 20 == 0:
                tqdm.write(
                    f"  [{i+1}/{len(sop_data)}] "
                    f"✓ {success} | ✗ {failed} | ↷ {skipped} skip"
                )

    print(f"\n{'='*60}")
    print(f"✅ SELESAI!")
    print(f"  Berhasil : {success} pairs")
    print(f"  Gagal    : {failed} (API error atau tabel tidak valid setelah 2 retry)")
    print(f"  Di-skip  : {skipped} (sudah ada)")
    print(f"  Output   : {OUTPUT_FILE}")
    print(f"\n📊 Distribusi Variant Tabel:")
    for variant_name, count in variant_count.items():
        print(f"  {variant_name:12s}: {count} pairs")
    print(f"\n💡 Tip: Render hasil di VS Code dengan extension Markdown Preview")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
