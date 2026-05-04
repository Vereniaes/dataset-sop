"""
generate_instruksi.py
=====================
Generate dataset pasangan (input_kasual → output_instruksi_lisan) untuk fine-tuning LLM.

Alur:
  1. Load SOP formal dari cleaned_sop.jsonl
  2. Untuk tiap SOP, generate 2 hal:
     - Versi kasual INPUT (deskripsi santai pemilik UMKM)
     - Versi Instruksi Lisan OUTPUT (seperti supervisor ke karyawan baru)
  3. Simpan ke paired_instruksi.jsonl

Format output JSONL:
  {
    "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Instruksi Lisan...",
    "input": "[deskripsi kasual pemilik UMKM]",
    "output": "[instruksi lisan terstruktur seperti supervisor berbicara]",
    "metadata": { ... }
  }

Jalankan:
  python3 generate_instruksi.py
  python3 generate_instruksi.py --limit 50     # test dengan 50 SOP dulu
  python3 generate_instruksi.py --resume       # lanjut dari yang sudah ada
"""

import json
import os
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
OUTPUT_FILE = SCRIPT_DIR / "paired_instruksi.jsonl"

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get(
    "VERTEX_API_KEY", ""
)
MODEL   = "gemini-3.1-pro-preview"

VARIATIONS_PER_SOP  = 2
DELAY_BETWEEN_CALLS = 2

# ─── Persona INPUT (sama seperti Chat WA — gaya user mendeskripsikan prosesnya) ──

INPUT_PERSONAS = [
    {
        "name": "pemilik_santai",
        "prompt": """Berperanlah sebagai pemilik UMKM yang cerita ke teman soal cara kerja di usahanya.
Ceritakan isi SOP berikut dalam bahasa santai seperti ngobrol biasa.

Aturan KETAT:
- JANGAN pakai format list/bullet/numbering formal
- Pakai bahasa Indonesia kasual (yaudah, emang, biar ga ribet, sih, deh)
- Ceritakan seolah lagi ngobrol spontan, boleh loncat-loncat
- Sebutkan nama orang sembarang (si Budi, Mbak Rina, dll)
- Panjang: 80-200 kata""",
    },
    {
        "name": "pemilik_buru",
        "prompt": """Berperanlah sebagai pemilik UMKM yang sedang terburu-buru menjelaskan prosedur ke karyawan baru.
Ceritakan isi SOP berikut dengan gaya bicara yang cepat dan tidak beraturan.

Aturan KETAT:
- Kalimat pendek, sering tidak selesai
- Pakai filler: pokoknya, yang penting, intinya, dll
- Urutan sedikit melompat karena buru-buru
- Sesekali kasih warning: "eh jangan lupa", "awas jangan sampe kelupaan"
- Panjang: 80-200 kata""",
    },
    {
        "name": "karyawan_senior",
        "prompt": """Berperanlah sebagai karyawan senior yang lagi ngajarin karyawan baru.
Jelaskan isi SOP berikut dengan gaya bicara santai sehari-hari.

Aturan KETAT:
- Pakai gaya "nah gini", "jadi gini", "lo tau ga", "nah ini penting"
- Boleh kasih tips personal yang ga ada di SOP
- Pakai "gue-lo" atau "aku-kamu" yang santai
- Urutan boleh sedikit berantakan karena teringat-ingat
- Panjang: 80-200 kata""",
    },
    {
        "name": "chat_singkat",
        "prompt": """Berperanlah sebagai pemilik UMKM yang ngetik cepat di grup WhatsApp.
Tulis isi SOP berikut dengan gaya chat informal yang singkat-singkat.

Aturan KETAT:
- Kalimat sangat pendek (1-2 kalimat per poin)
- Banyak singkatan (yg, gak, udh, hrs, trs, jgn, lgsg, sblm)
- Pakai emoji sesekali (maksimal 3)
- Urutan campur aduk, tidak perlu sempurna
- Panjang: 60-150 kata""",
    },
]

# ─── Prompt untuk generate OUTPUT Instruksi Lisan ─────────────────────────────

INSTRUKSI_SYSTEM = """Kamu adalah asisten yang mengubah dokumen SOP formal menjadi instruksi lisan
yang disampaikan seorang supervisor kepada karyawan baru secara langsung.
HANYA hasilkan teks instruksi lisannya saja, tanpa penjelasan, tanpa label, tanpa markdown heading.
Langsung mulai dengan kalimat pembukanya."""

INSTRUKSI_PROMPT_TEMPLATE = """Ubah dokumen SOP formal berikut menjadi instruksi lisan dari seorang supervisor kepada karyawan baru.

SOP yang harus diubah:
---
{sop_text}
---

Aturan output Instruksi Lisan:
1. Awali dengan kalimat pembuka yang natural seperti berbicara langsung:
   - "Dengerin ya, ini prosedur yang harus kamu ikutin:"
   - "Oke, aku jelasin ya langkah-langkahnya:"
   - "Perhatiin baik-baik, ini yang harus lo kerjain:"
2. Gunakan kata perintah langsung (Pertama kamu..., Kedua langsung..., Ketiga pastikan...)
3. Urutan bernomor eksplisit: Pertama, Kedua, Ketiga — atau 1. 2. 3.
4. Boleh ada penekanan lisan: "ini penting ya", "jangan sampai skip", "awas lupa"
5. Bahasa semi-formal — tidak terlalu baku, tidak terlalu slang
6. Setiap langkah maksimal 2 kalimat agar mudah diingat
7. Akhiri dengan kalimat penutup opsional: "Ngerti?", "Ada pertanyaan?", "Oke lanjut."
8. TIDAK BOLEH pakai heading markdown (## atau ###)
9. Semua langkah penting dari SOP harus tercakup
10. Panjang total: 120-280 kata

Langsung tulis instruksi lisannya:"""

INSTRUCTION = (
    "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Instruksi Lisan "
    "(seperti supervisor mengajari karyawan baru secara langsung, "
    "pakai kalimat perintah berurutan yang jelas dan mudah diikuti)."
)

# ─── Helper ───────────────────────────────────────────────────────────────────

def make_client():
    return genai.Client(vertexai=True, api_key=API_KEY)


def load_sop_data(filepath: Path) -> list[dict]:
    data = []
    if not filepath.exists():
        print(f"[ERROR] File tidak ditemukan: {filepath}")
        print("Pastikan cleaned_sop.jsonl ada di dataset-dokumen/scraping/")
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


def call_gemini(client, prompt: str, system: str, temperature: float = 0.85) -> str | None:
    try:
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            top_p=0.95,
            max_output_tokens=1024,
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
    Generate satu pasangan (input_kasual, output_instruksi).
    Step 1: Generate INPUT kasual dari SOP formal pakai persona.
    Step 2: Generate OUTPUT Instruksi Lisan dari SOP formal.
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

Ingat: Langsung tulis teks kasualnya saja, tanpa pengantar atau label."""

    casual_input = call_gemini(
        client, input_prompt,
        system="Kamu adalah generator data NLP. Hasilkan HANYA teks kasual sesuai instruksi persona. Tanpa label, tanpa penjelasan.",
        temperature=0.9
    )

    if not casual_input or len(casual_input) < 50:
        return None

    time.sleep(DELAY_BETWEEN_CALLS)

    # ── Step 2: Generate OUTPUT Instruksi Lisan ────────────────────────────────
    instruksi_prompt = INSTRUKSI_PROMPT_TEMPLATE.format(sop_text=sop_text)
    instruksi_output = call_gemini(
        client, instruksi_prompt,
        system=INSTRUKSI_SYSTEM,
        temperature=0.75
    )

    if not instruksi_output or len(instruksi_output) < 80:
        return None

    return {
        "instruction": INSTRUCTION,
        "input": casual_input,
        "output": instruksi_output,
        "metadata": {
            "source_id":      sop.get("id", ""),
            "source_type":    sop.get("source", ""),
            "persona":        persona["name"],
            "original_title": sop.get("title", ""),
            "style":          "instruksi_lisan",
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


def validate_instruksi(text: str) -> bool:
    """Validasi apakah output Instruksi Lisan memenuhi karakteristik dasar."""
    if len(text) < 80:
        return False

    # Harus ada penanda urutan (Pertama/Kedua/angka)
    order_markers = [
        "pertama", "kedua", "ketiga", "keempat", "kelima",
        "1.", "2.", "3.", "langkah 1", "langkah 2",
    ]
    has_order = any(m in text.lower() for m in order_markers)

    # Harus ada kata perintah imperatif
    imperative_markers = [
        "kamu", "lo", "anda", "pastikan", "jangan", "lakukan",
        "cek", "siapkan", "buka", "tutup", "hubungi", "periksa",
    ]
    has_imperative = any(m in text.lower() for m in imperative_markers)

    # Tidak boleh ada heading markdown
    has_heading = "##" in text or "###" in text

    return has_order and has_imperative and not has_heading


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate dataset Instruksi Lisan untuk SOP-ify")
    parser.add_argument("--limit",   type=int, default=None, help="Batasi jumlah SOP diproses")
    parser.add_argument("--resume",  action="store_true",    help="Lanjut dari data yang sudah ada")
    parser.add_argument("--dry-run", action="store_true",    help="Test tanpa API call")
    args = parser.parse_args()

    print("=" * 60)
    print("Instruksi Lisan Dataset Generator — SOP-ify")
    print(f"Model  : {MODEL}")
    print(f"Input  : {INPUT_FILE}")
    print(f"Output : {OUTPUT_FILE}")
    print("=" * 60)

    # Load SOP data
    print(f"\n[1] Loading SOP dari: {INPUT_FILE.resolve()}")
    sop_data = load_sop_data(INPUT_FILE)
    if not sop_data:
        return
    if args.limit:
        sop_data = sop_data[:args.limit]
        print(f"  Dibatasi ke {args.limit} SOP")
    print(f"  Loaded: {len(sop_data)} SOP entries")

    # Resume support
    existing_keys: set[str] = set()
    if args.resume and OUTPUT_FILE.exists():
        existing_keys = load_existing_keys(OUTPUT_FILE)
        print(f"  Resume: {len(existing_keys)} pairs sudah ada, akan di-skip")

    if args.dry_run:
        estimasi_calls = len(sop_data) * VARIATIONS_PER_SOP * 2
        print("\n[DRY RUN] Tidak ada API call. Validasi selesai.")
        print(f"  Akan generate: {len(sop_data)} SOP × {VARIATIONS_PER_SOP} persona × 2 steps")
        print(f"  = ~{estimasi_calls} API calls")
        print(f"  Estimasi waktu: ~{estimasi_calls * DELAY_BETWEEN_CALLS // 60} menit")
        return

    client = make_client()

    estimasi = len(sop_data) * VARIATIONS_PER_SOP
    print(f"\n[2] Generating ~{estimasi} pairs ({VARIATIONS_PER_SOP} variasi/SOP)...")
    print(f"    Estimasi waktu: ~{estimasi * DELAY_BETWEEN_CALLS * 2 // 60} menit\n")

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
                    continue

                # Validasi output Instruksi Lisan
                if not validate_instruksi(pair["output"]):
                    invalid += 1
                    tqdm.write(f"  ⚠ Output tidak memenuhi validasi Instruksi Lisan, skip.")
                    continue

                out_f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                out_f.flush()
                success += 1

            if (i + 1) % 20 == 0:
                tqdm.write(
                    f"  [{i+1}/{len(sop_data)}] "
                    f"✓ {success} | ✗ {failed} | ⚠ {invalid} invalid | ↷ {skipped} skip"
                )

    print(f"\n{'='*60}")
    print(f"✅ SELESAI!")
    print(f"  Berhasil  : {success} pairs")
    print(f"  Gagal     : {failed}")
    print(f"  Invalid   : {invalid} (output tidak memenuhi ciri Instruksi Lisan)")
    print(f"  Di-skip   : {skipped} (sudah ada)")
    print(f"  Output    : {OUTPUT_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
