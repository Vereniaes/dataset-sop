"""
generate_chat_wa.py
===================
Generate dataset pasangan (input_kasual → output_chat_wa) untuk fine-tuning LLM.

Alur:
  1. Load SOP formal dari cleaned_sop.jsonl
  2. Untuk tiap SOP, generate 2 hal secara SERENTAK dalam 1 prompt:
     - Versi kasual INPUT (deskripsi santai pemilik UMKM)
     - Versi Chat WA OUTPUT (SOP diformat seperti pesan grup WA)
  3. Simpan ke paired_chat_wa.jsonl

Format output JSONL:
  {
    "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Chat WA...",
    "input": "[deskripsi kasual pemilik UMKM]",
    "output": "[SOP format chat WA dengan emoji dan singkatan]",
    "metadata": { ... }
  }

Jalankan:
  python3 generate_chat_wa.py
  python3 generate_chat_wa.py --limit 50     # test dengan 50 SOP dulu
  python3 generate_chat_wa.py --resume       # lanjut dari yang sudah ada
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
OUTPUT_FILE = SCRIPT_DIR / "paired_chat_wa.jsonl"

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get(
    "VERTEX_API_KEY", ""
)
MODEL   = "gemini-3.1-pro-preview"

VARIATIONS_PER_SOP  = 2   # berapa variasi input per SOP
DELAY_BETWEEN_CALLS = 2   # detik jeda antar API call

# ─── Persona INPUT (gaya user mendeskripsikan proses UMKM mereka) ─────────────

INPUT_PERSONAS = [
    {
        "name": "pemilik_santai",
        "desc": "pemilik UMKM yang santai ngobrol ke teman",
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
        "desc": "pemilik UMKM yang terburu-buru menjelaskan ke karyawan baru",
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
        "desc": "karyawan senior mengajari karyawan baru secara lisan",
        "prompt": """Berperanlah sebagai karyawan senior yang lagi ngajarin karyawan baru.
Jelaskan isi SOP berikut dengan gaya bicara santai sehari-hari.

Aturan KETAT:
- Pakai gaya "nah gini", "jadi gini", "lo tau ga", "nah ini penting"
- Boleh kasih tips personal yang ga ada di SOP ("biasanya sih aku...")
- Pakai "gue-lo" atau "aku-kamu" yang santai
- Urutan boleh sedikit berantakan karena teringat-ingat
- Panjang: 80-200 kata""",
    },
    {
        "name": "chat_singkat",
        "desc": "pemilik yang ngetik cepat di WA group",
        "prompt": """Berperanlah sebagai pemilik UMKM yang ngetik cepat di grup WhatsApp.
Tulis isi SOP berikut dengan gaya chat informal yang singkat-singkat.

Aturan KETAT:
- Kalimat sangat pendek (1-2 kalimat per poin)
- Banyak singkatan (yg, gak, udh, hrs, trs, jgn, lgsg, sblm, dll)
- Pakai emoji sesekali (maksimal 3)
- Urutan campur aduk, tidak perlu sempurna
- Panjang: 60-150 kata""",
    },
]

# ─── Prompt untuk generate OUTPUT Chat WA ─────────────────────────────────────

CHAT_WA_SYSTEM = """Kamu adalah asisten yang mengubah dokumen SOP formal menjadi pesan Chat WA yang natural dan mudah dipahami karyawan UMKM.
HANYA hasilkan teks chat WA-nya saja, tanpa penjelasan, tanpa label, tanpa markdown heading.
Langsung mulai dengan pesannya."""

CHAT_WA_PROMPT_TEMPLATE = """Ubah dokumen SOP formal berikut menjadi pesan Chat WA untuk grup karyawan.

SOP yang harus diubah:
---
{sop_text}
---

Aturan output Chat WA:
1. Gunakan bahasa santai dan singkatan khas WA (yg, gak, udh, hrs, trs, jgn, lgsg, sblm, biar)
2. Kalimat pendek-pendek, maks 1-2 baris per poin
3. Pakai bullet list dengan tanda `-` atau nomor sederhana (1. 2. 3.)
4. Tambahkan emoji yang relevan (📌 ✅ ⚠️ 👇 📝) tapi jangan berlebihan
5. Awali dengan kalimat pembuka santai (misal: "gaes dengerin ya 👇", "info penting guys:", dll)
6. TIDAK BOLEH pakai heading markdown (## atau ###)
7. Isi harus tetap akurat dan mencakup semua langkah penting dari SOP
8. Panjang total: 100-250 kata

Langsung tulis pesan Chat WA-nya:"""

INSTRUCTION = (
    "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Chat WA "
    "(singkat, informal, pakai singkatan dan emoji, seperti pesan grup WhatsApp). "
    "Pastikan semua langkah penting tetap tercantum."
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
    """Panggil Gemini dan return teks. Return None jika gagal."""
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
    Generate satu pasangan (input_kasual, output_chat_wa) dari satu SOP.
    Step 1: Generate INPUT kasual dari SOP formal pakai persona.
    Step 2: Generate OUTPUT Chat WA dari SOP formal.
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

    # ── Step 2: Generate OUTPUT Chat WA ───────────────────────────────────────
    chat_wa_prompt = CHAT_WA_PROMPT_TEMPLATE.format(sop_text=sop_text)
    chat_wa_output = call_gemini(
        client, chat_wa_prompt,
        system=CHAT_WA_SYSTEM,
        temperature=0.75
    )

    if not chat_wa_output or len(chat_wa_output) < 50:
        return None

    return {
        "instruction": INSTRUCTION,
        "input": casual_input,
        "output": chat_wa_output,
        "metadata": {
            "source_id":     sop.get("id", ""),
            "source_type":   sop.get("source", ""),
            "persona":       persona["name"],
            "original_title": sop.get("title", ""),
            "style":         "chat_wa",
        }
    }


def load_existing_keys(filepath: Path) -> set[str]:
    """Load key pairs yang sudah ada untuk resume."""
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


def validate_chat_wa(text: str) -> bool:
    """Validasi apakah output Chat WA memenuhi karakteristik dasar."""
    if len(text) < 50:
        return False
    # Harus ada minimal salah satu ciri Chat WA
    slang_markers = ["yg", "gak", "udh", "hrs", "trs", "jgn", "lgsg", "sblm",
                     "biar", "nih", "deh", "sih", "ya", "aja"]
    emoji_markers  = ["📌", "✅", "⚠️", "👇", "📝", "😊", "🙏", "💡"]
    has_slang = any(m in text.lower() for m in slang_markers)
    has_emoji = any(e in text for e in emoji_markers)
    has_list  = "-" in text or any(f"{i}." in text for i in range(1, 10))
    return (has_slang or has_emoji) and has_list


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate dataset Chat WA untuk SOP-ify")
    parser.add_argument("--limit",  type=int, default=None, help="Batasi jumlah SOP diproses")
    parser.add_argument("--resume", action="store_true",    help="Lanjut dari data yang sudah ada")
    parser.add_argument("--dry-run",action="store_true",    help="Test tanpa API call")
    args = parser.parse_args()

    print("=" * 60)
    print("Chat WA Dataset Generator — SOP-ify")
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
        print("\n[DRY RUN] Tidak ada API call. Validasi selesai.")
        print(f"  Akan generate: {len(sop_data)} SOP × {VARIATIONS_PER_SOP} persona = "
              f"~{len(sop_data) * VARIATIONS_PER_SOP * 2} API calls")
        return

    client = make_client()

    # Generate
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

                # Validasi output Chat WA
                if not validate_chat_wa(pair["output"]):
                    invalid += 1
                    tqdm.write(f"  ⚠ Output tidak memenuhi validasi Chat WA, skip.")
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
    print(f"  Invalid   : {invalid} (output tidak memenuhi ciri Chat WA)")
    print(f"  Di-skip   : {skipped} (sudah ada)")
    print(f"  Output    : {OUTPUT_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
