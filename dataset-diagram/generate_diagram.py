"""
generate_diagram.py
===================
Generate dataset pasangan (input_kasual → output_mermaid_flowchart) untuk fine-tuning LLM.

Alur:
  1. Load SOP formal dari cleaned_sop.jsonl
  2. Untuk tiap SOP, generate 2 hal:
     - Versi kasual INPUT (deskripsi santai pemilik UMKM)
     - Versi Mermaid Flowchart OUTPUT (diagram alur kerja)
  3. Validasi syntax Mermaid dasar sebelum simpan
  4. Simpan ke paired_diagram.jsonl

Format output JSONL:
  {
    "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Diagram Flowchart...",
    "input": "[deskripsi kasual pemilik UMKM]",
    "output": "flowchart TD\\n    A([MULAI]) --> B[...] ...",
    "metadata": { ... }
  }

Jalankan:
  python3 generate_diagram.py
  python3 generate_diagram.py --limit 50     # test dengan 50 SOP dulu
  python3 generate_diagram.py --resume       # lanjut dari yang sudah ada
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
OUTPUT_FILE = SCRIPT_DIR / "paired_diagram.jsonl"

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get(
    "VERTEX_API_KEY", ""
)
MODEL   = "gemini-3.1-pro-preview"

VARIATIONS_PER_SOP  = 1   # 1 saja karena validasi Mermaid lebih ketat
DELAY_BETWEEN_CALLS = 2

# ─── Persona INPUT (sama seperti generator lain) ──────────────────────────────

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

# ─── Prompt untuk generate OUTPUT Mermaid Flowchart ───────────────────────────

MERMAID_SYSTEM = """Kamu adalah ahli dalam membuat diagram Mermaid.js dari prosedur operasional bisnis.
HANYA hasilkan kode Mermaid yang valid saja, tanpa penjelasan, tanpa markdown code block (jangan pakai ```).
Langsung mulai dengan 'flowchart TD'."""

MERMAID_PROMPT_TEMPLATE = """Ubah dokumen SOP formal berikut menjadi diagram flowchart Mermaid.js.

SOP yang harus diubah:
---
{sop_text}
---

Aturan KETAT untuk output Mermaid:
1. Selalu mulai dengan baris pertama: `flowchart TD`
2. Node MULAI: `A([MULAI])`
3. Node SELESAI: `Z([SELESAI])` (atau huruf terakhir yang dipakai)
4. Step proses biasa: `B[Label langkah]`
5. Kondisi/keputusan: `F{{Pertanyaan kondisi?}}` dengan edge berlabel `-->|Ya|` dan `-->|Tidak|`
6. Format edge: `A --> B` atau `A -->|label| B`
7. Label node: SINGKAT, maksimal 5 kata, tanpa tanda kutip di dalam label
8. LARANGAN KETAT — jangan pakai karakter ini di dalam label node: `"`, `(`, `)`, `{{}}`
9. Jumlah node: antara 5 sampai 12 node
10. Setiap langkah penting dari SOP harus jadi node
11. Jika ada kondisi (cek, kalau, jika), wajib buat decision node `{{}}`
12. JANGAN tambahkan styling, subgraph, atau class definition

Contoh output yang BENAR:
flowchart TD
    A([MULAI]) --> B[Buka Toko Jam 08.00]
    B --> C[Nyalakan Mesin Kopi]
    C --> D[Tunggu 15 Menit]
    D --> E[Bersihkan Meja dan Kursi]
    E --> F{{Cek Stok Susu}}
    F -->|Cukup| G[Buka Pintu Jam 09.00]
    F -->|Habis| H[Hubungi Supplier]
    H --> G
    G --> I([SELESAI])

Sekarang buat flowchart untuk SOP di atas. Langsung tulis kode Mermaid-nya:"""

INSTRUCTION = (
    "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Diagram Flowchart "
    "(format Mermaid.js flowchart TD, tampilkan alur kerja dari MULAI hingga SELESAI "
    "dengan decision node jika ada kondisi)."
)

# ─── Validasi Mermaid ──────────────────────────────────────────────────────────

# Karakter yang merusak syntax Mermaid jika ada di dalam label node
FORBIDDEN_IN_LABEL = re.compile(r'\[.*?["\(\){}].*?\]')

# Kata-kata yang diterima sebagai node akhir flowchart
END_NODE_KEYWORDS = ["SELESAI", "AKHIR", "END", "FINISH", "DONE", "KELUAR", "STOP", "BERAKHIR"]

def validate_mermaid(text: str) -> tuple[bool, str]:
    """
    Validasi basic syntax Mermaid.
    Return (is_valid, reason).
    """
    text = text.strip()

    if not text.startswith("flowchart TD"):
        return False, "Tidak dimulai dengan 'flowchart TD'"

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if len(lines) < 4:
        return False, f"Terlalu sedikit baris: {len(lines)}"

    # Harus ada node MULAI
    has_mulai = any("MULAI" in l.upper() for l in lines)
    if not has_mulai:
        return False, "Tidak ada node MULAI"

    # Cukup ada salah satu end node keyword
    full_text_upper = text.upper()
    has_end = any(kw in full_text_upper for kw in END_NODE_KEYWORDS)
    if not has_end:
        return False, f"Tidak ada node akhir (SELESAI/AKHIR/END/FINISH)"

    # Harus ada minimal 1 edge
    has_edge = any("-->" in l for l in lines)
    if not has_edge:
        return False, "Tidak ada edge (-->)"

    # Cek karakter terlarang di label node
    for line in lines:
        if FORBIDDEN_IN_LABEL.search(line):
            return False, f"Karakter terlarang di label: {line[:60]}"

    # Hitung node unik
    node_pattern = re.compile(r'\b([A-Z][A-Z0-9]*)\b(?:\s*[\[\({])')
    nodes_defined = set()
    for line in lines[1:]:  # skip baris 'flowchart TD'
        matches = node_pattern.findall(line)
        nodes_defined.update(matches)

    if len(nodes_defined) < 3:
        return False, f"Terlalu sedikit node unik: {len(nodes_defined)}"

    # Tidak boleh ada markdown code block
    if "```" in text:
        return False, "Ada markdown code fence (```) yang tidak boleh ada"

    return True, "OK"


def clean_mermaid_output(text: str) -> str:
    """Bersihkan output Gemini: strip pengantar, markdown fences, dan trailing teks."""
    text = text.strip()

    # Hapus ```mermaid ... ``` jika model lupa instruksi
    if "```" in text:
        lines = text.split("\n")
        # Cari baris yang berisi ``` (bisa ```mermaid atau ```)
        start_idx = next((i for i, l in enumerate(lines) if l.strip().startswith("```")), None)
        end_idx   = next((i for i in range(len(lines)-1, -1, -1) if lines[i].strip() == "```"), None)
        if start_idx is not None:
            lines = lines[start_idx+1:]
        if end_idx is not None and end_idx < len(lines):
            lines = lines[:end_idx]
        text = "\n".join(lines).strip()

    # Strip teks pengantar sebelum 'flowchart TD'
    # Model kadang menulis penjelasan dulu baru kodenya
    if "flowchart TD" in text and not text.startswith("flowchart"):
        idx = text.index("flowchart TD")
        text = text[idx:].strip()

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
                    entry = json.loads(line)
                    # Filter: hanya SOP yang punya langkah-langkah cukup jelas
                    sop_text = entry.get("sop_text", "")
                    step_indicators = sum(1 for kw in ["langkah", "tahap", "step", "prosedur", "pertama", "kedua"]
                                         if kw in sop_text.lower())
                    if len(sop_text) >= 200 and step_indicators >= 1:
                        data.append(entry)
                except json.JSONDecodeError:
                    continue
    return data


def call_gemini(client, prompt: str, system: str, temperature: float = 0.6) -> str | None:
    """Temperature rendah (0.6) untuk diagram — konsistensi syntax lebih penting dari kreativitas."""
    try:
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            top_p=0.9,
            max_output_tokens=2048,  # dinaikkan dari 1024 agar output tidak terpotong
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
    Generate satu pasangan (input_kasual, output_mermaid).
    Step 1: Generate INPUT kasual dari SOP formal pakai persona.
    Step 2: Generate Mermaid Flowchart dari SOP formal.
    """
    sop_text = sop.get("sop_text", "").strip()
    if not sop_text or len(sop_text) < 200:
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

    # ── Step 2: Generate OUTPUT Mermaid (dengan retry 1x jika invalid) ─────────
    mermaid_prompt = MERMAID_PROMPT_TEMPLATE.format(sop_text=sop_text)
    mermaid_output = None

    for attempt in range(2):  # max 2 attempt
        raw = call_gemini(
            client, mermaid_prompt,
            system=MERMAID_SYSTEM,
            temperature=0.5 if attempt == 0 else 0.3  # lebih konservatif di retry
        )
        if not raw:
            continue

        cleaned = clean_mermaid_output(raw)
        is_valid, reason = validate_mermaid(cleaned)

        if is_valid:
            mermaid_output = cleaned
            break
        else:
            tqdm.write(f"  ⚠ Attempt {attempt+1} invalid: {reason}")
            if attempt == 0:
                time.sleep(DELAY_BETWEEN_CALLS)

    if not mermaid_output:
        return None

    return {
        "instruction": INSTRUCTION,
        "input": casual_input,
        "output": mermaid_output,
        "metadata": {
            "source_id":      sop.get("id", ""),
            "source_type":    sop.get("source", ""),
            "persona":        persona["name"],
            "original_title": sop.get("title", ""),
            "style":          "diagram_mermaid",
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
    parser = argparse.ArgumentParser(description="Generate dataset Diagram Mermaid untuk SOP-ify")
    parser.add_argument("--limit",   type=int, default=None, help="Batasi jumlah SOP diproses")
    parser.add_argument("--resume",  action="store_true",    help="Lanjut dari data yang sudah ada")
    parser.add_argument("--dry-run", action="store_true",    help="Test tanpa API call")
    args = parser.parse_args()

    print("=" * 60)
    print("Diagram Mermaid Dataset Generator — SOP-ify")
    print(f"Model  : {MODEL}")
    print(f"Input  : {INPUT_FILE}")
    print(f"Output : {OUTPUT_FILE}")
    print("=" * 60)

    print(f"\n[1] Loading SOP dari: {INPUT_FILE.resolve()}")
    sop_data = load_sop_data(INPUT_FILE)
    if not sop_data:
        return
    if args.limit:
        sop_data = sop_data[:args.limit]
        print(f"  Dibatasi ke {args.limit} SOP")
    print(f"  Loaded: {len(sop_data)} SOP entries (sudah difilter: punya langkah jelas)")

    existing_keys: set[str] = set()
    if args.resume and OUTPUT_FILE.exists():
        existing_keys = load_existing_keys(OUTPUT_FILE)
        print(f"  Resume: {len(existing_keys)} pairs sudah ada, akan di-skip")

    if args.dry_run:
        estimasi_calls = len(sop_data) * VARIATIONS_PER_SOP * 2
        print("\n[DRY RUN] Tidak ada API call. Validasi selesai.")
        print(f"  Akan generate: {len(sop_data)} SOP × {VARIATIONS_PER_SOP} persona × 2 steps")
        print(f"  = ~{estimasi_calls} API calls (+ retry jika Mermaid invalid)")
        print(f"  Estimasi waktu: ~{estimasi_calls * DELAY_BETWEEN_CALLS // 60} menit")
        return

    client = make_client()

    estimasi = len(sop_data) * VARIATIONS_PER_SOP
    print(f"\n[2] Generating ~{estimasi} pairs ({VARIATIONS_PER_SOP} variasi/SOP)...")
    print(f"    Note: Setiap SOP bisa hingga 2 API calls untuk Mermaid (ada 1x retry)\n")

    success = 0
    failed  = 0
    skipped = 0
    invalid = 0

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
                    invalid += 1
                    continue

                out_f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                out_f.flush()
                success += 1

            if (i + 1) % 20 == 0:
                tqdm.write(
                    f"  [{i+1}/{len(sop_data)}] "
                    f"✓ {success} | ✗ {failed+invalid} gagal/invalid | ↷ {skipped} skip"
                )

    print(f"\n{'='*60}")
    print(f"✅ SELESAI!")
    print(f"  Berhasil : {success} pairs")
    print(f"  Gagal    : {failed + invalid} (API error atau Mermaid tidak valid setelah 2 retry)")
    print(f"  Di-skip  : {skipped} (sudah ada)")
    print(f"  Output   : {OUTPUT_FILE}")
    print(f"\n💡 Tips: Cek kualitas dengan membuka beberapa entry dan validasi di https://mermaid.live")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
