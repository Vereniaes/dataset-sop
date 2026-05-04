"""
Synthetic Data Generator untuk SOP-ify
Menggunakan Google Gemini via Vertex AI Agent Platform.

Metode: Reverse Generation
  1. Ambil SOP formal dari dataset/scraping/cleaned_sop.jsonl
  2. Minta Gemini Pro "ceritakan ulang dengan gaya UMKM"
  3. Simpan pasangan (casual, formal) sebagai training data

Jalankan: python3 generate_synthetic.py
"""

import json
import os
import time
import random
from google import genai
from google.genai import types
from tqdm import tqdm

# ============================================================
# CONFIG — ganti API key di sini jika expired
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE  = os.path.join(SCRIPT_DIR, "..", "scraping", "cleaned_sop.jsonl")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "paired_data.jsonl")

API_KEY   = os.environ.get("VERTEX_API_KEY", "")
MODEL     = "gemini-3.1-pro-preview"

VARIATIONS_PER_SOP   = 3   # variasi per SOP
DELAY_BETWEEN_CALLS  = 2   # detik antar request

# ============================================================
# PROMPT TEMPLATES (5 persona berbeda)
# ============================================================
PERSONA_VARIATIONS = [
    {
        "name": "pemilik_kelelahan",
        "prompt": """Berperanlah sebagai pemilik UMKM yang sedang kelelahan dan terburu-buru.
Ceritakan langkah-langkah dalam SOP berikut menggunakan bahasa lisan yang santai,
tidak beraturan, dan sedikit melompat-lompat topiknya.

Aturan:
- Jangan pakai format bullet point atau numbering
- Ceritakan seolah sedang bicara ke karyawan baru
- Pakai filler words (kayak, pokoknya, nah, terus, ya kan, dll)
- Sebutkan nama orang secara acak (si Andi, Mbak Yuni, dll)
- Panjang cerita sekitar 100-300 kata"""
    },
    {
        "name": "pemilik_santai",
        "prompt": """Berperanlah sebagai pemilik UMKM yang lagi santai ngobrol di warung kopi.
Ceritakan langkah-langkah dalam SOP berikut dengan gaya ngobrol biasa.

Aturan:
- Pakai bahasa Indonesia sehari-hari yang sangat kasual
- Campur slang (yaudah, emang gitu, biar ga ribet)
- Ceritakan kayak lagi curhat ke temen
- Jangan pakai format dokumen formal
- Panjang cerita sekitar 100-300 kata"""
    },
    {
        "name": "karyawan_senior",
        "prompt": """Berperanlah sebagai karyawan senior yang sedang mengajari karyawan baru secara lisan.
Jelaskan langkah-langkah dalam SOP berikut dengan cara bicara sehari-hari.

Aturan:
- Pakai bahasa "gue-lo" atau "aku-kamu" yang santai
- Sering pakai "jadi gini", "nah ini penting", "awas jangan sampe"
- Boleh ada tips pribadi yang tidak ada di SOP
- Urutan boleh sedikit berantakan
- Panjang cerita sekitar 100-300 kata"""
    },
    {
        "name": "voice_note_style",
        "prompt": """Berperanlah sebagai pemilik usaha yang sedang kirim voice note WhatsApp ke manajer.
Ceritakan langkah-langkah dalam SOP berikut persis seperti orang yang ngomong di voice note.

Aturan:
- Ada jeda pikir ("ehh", "gimana ya", "bentar")
- Ada pengulangan karena mikir sambil ngomong
- Sering bilang "oh iya" karena baru ingat
- Urutannya tidak beraturan, loncat-loncat
- Panjang cerita sekitar 150-350 kata"""
    },
    {
        "name": "chat_style",
        "prompt": """Berperanlah sebagai pemilik UMKM yang mengetik di grup WhatsApp.
Tulis langkah-langkah dalam SOP berikut dengan gaya chat.

Aturan:
- Kalimat pendek-pendek seperti chat
- Banyak singkatan (yg, gak, udh, hrs, dll)
- Kadang typo kecil boleh
- Pakai emoji sesekali 😅
- Urutannya campur aduk
- Panjang sekitar 100-250 kata"""
    },
]

SYSTEM_PROMPT = """Kamu adalah generator data untuk proyek NLP.
Tugasmu adalah mengubah dokumen SOP formal menjadi teks kasual sesuai instruksi persona.
HANYA hasilkan teks kasual saja, tanpa penjelasan tambahan, tanpa label, tanpa metadata.
Langsung mulai dengan teks kasualnya."""


def make_client():
    return genai.Client(vertexai=True, api_key=API_KEY)


def load_sop_data(filepath):
    data = []
    if not os.path.exists(filepath):
        print(f"[ERROR] File tidak ditemukan: {filepath}")
        print("Jalankan dulu:")
        print("  python3 dataset/scraping/scrape_wikihow.py")
        print("  python3 dataset/scraping/merge_scraped.py")
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


def generate_casual_text(client, sop_text, persona):
    """Generate versi kasual dari SOP menggunakan Gemini Pro."""
    prompt = f"""{persona['prompt']}

SOP yang harus diceritakan ulang:
---
{sop_text}
---

Ingat: Langsung tulis teks kasualnya saja, tanpa pengantar atau label."""

    try:
        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=prompt)]
            )
        ]
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.9,
            top_p=0.95,
            max_output_tokens=1024,
        )
        result = ""
        for chunk in client.models.generate_content_stream(
            model=MODEL, contents=contents, config=config
        ):
            if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                continue
            result += chunk.text
        return result.strip()
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None


def main():
    print("=" * 60)
    print("Synthetic Data Generator — SOP-ify (Vertex AI)")
    print(f"Model: {MODEL}")
    print("=" * 60)

    client = make_client()

    # Load SOP data
    print(f"\n[1] Loading SOP dari: {INPUT_FILE}")
    sop_data = load_sop_data(INPUT_FILE)
    if not sop_data:
        return
    print(f"  Loaded {len(sop_data)} SOP entries")

    # Load existing pairs (resume support)
    existing_ids = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    key = f"{entry['metadata']['source_id']}_{entry['metadata']['persona']}"
                    existing_ids.add(key)
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"  Sudah ada {len(existing_ids)} pairs, skip yang sudah ada")

    print(f"\n[2] Generating {VARIATIONS_PER_SOP} variasi per SOP...")
    print(f"  Estimasi total: {len(sop_data) * VARIATIONS_PER_SOP} pairs\n")

    success_count = 0
    fail_count = 0

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for i, sop in enumerate(tqdm(sop_data, desc="SOPs")):
            selected = random.sample(
                PERSONA_VARIATIONS,
                min(VARIATIONS_PER_SOP, len(PERSONA_VARIATIONS))
            )

            for persona in selected:
                pair_key = f"{sop.get('id', '')}_{persona['name']}"
                if pair_key in existing_ids:
                    continue

                casual = generate_casual_text(client, sop["sop_text"], persona)

                if casual and len(casual) > 50:
                    pair = {
                        "instruction": "Ubah catatan berantakan berikut menjadi dokumen SOP yang rapi dan terstruktur dengan format: Judul, Tujuan, Ruang Lingkup, Penanggung Jawab (jika ada), dan Prosedur Kerja.",
                        "input": casual,
                        "output": sop["sop_text"],
                        "metadata": {
                            "source_id": sop.get("id", ""),
                            "source_type": sop.get("source", ""),
                            "persona": persona["name"],
                            "original_title": sop.get("title", ""),
                        }
                    }
                    f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                    f.flush()
                    success_count += 1
                else:
                    fail_count += 1

                time.sleep(DELAY_BETWEEN_CALLS)

            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(sop_data)}] Success: {success_count} | Failed: {fail_count}")

    print(f"\n{'=' * 60}")
    print(f"SELESAI! Berhasil: {success_count} pairs | Gagal: {fail_count}")
    print(f"Disimpan: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
