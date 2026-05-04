# 💬 PLANNING: Dataset — Gaya Chat WA

## Target Output Format
Teks singkat-singkat mirip chat WhatsApp group, banyak singkatan, informal, boleh emoji.

```
Gaes dengerin ya soal buka toko pagi 👇

- pertama itu cek stok dlu seblm buka, klo ada yg abis lgsg catat
- trs nyalain mesin/sistem kasir, pastiin jalan
- lap2 meja kursi dlu seblm pelanggan masuk
- klo udh jam 8 baru buka pintu, jgn sblm itu ya
- ingetin juga cek hp buat notif order online
```

## Status
- [ ] Belum ada data (belum dijalankan)
- [x] Script generate sudah dibuat: `generate_chat_wa.py`

## Sumber Data
| Sumber | Platform | Isi | Fungsi |
|--------|----------|-----|--------|
| `cleaned_sop.jsonl` (WikiHow ID + SOP web) | Lokal | SOP formal Indonesia | **Output target** untuk generate |
| **STIF-Indonesia** | HuggingFace `SEACrowd/stif_indonesia` | ~6.000 pasangan informal↔formal dari Twitter | **Referensi gaya input kasual** yang natural |
| **IndoCollex** | `github.com/haryoa/indo-collex` | Kamus frasa formal-informal | Augmentasi variasi slang di input |
| **Kamus Alay** | `github.com/okkyibrohim` → `new_kamusalay.csv` | ~5.000 kata slang | Token informal untuk augmentasi prompt |

> ⚠️ **STIF-Indonesia tidak bisa dipakai langsung** sebagai training pair karena domain-nya bukan UMKM SOP.
> Fungsinya: ambil teks informal-nya → jadikan **referensi gaya bahasa** saat prompt Gemini generate versi Chat WA.

## Strategi Pengumpulan Data

### Opsi A — Synthetic via Script (Direkomendasikan)
Gunakan SOP formal dari `dataset-dokumen/scraping/cleaned_sop.jsonl` sebagai sumber output target.
Untuk variasi INPUT yang lebih natural, gunakan teks informal dari STIF-Indonesia sebagai contoh gaya bahasa di dalam prompt.

Alur:
1. Load SOP formal dari `cleaned_sop.jsonl`
2. Load sampel teks informal dari STIF-Indonesia sebagai **few-shot style example**
3. Prompt Gemini: "Tuliskan ulang SOP ini dalam gaya Chat WA, seperti contoh berikut: [contoh STIF]"
4. Simpan sebagai `(input_kasual_umkm, output_chat_wa)`

Format `instruction`:
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Chat WA (singkat, informal, boleh emoji, seperti pesan grup WhatsApp).",
  "input": "[deskripsi proses UMKM dari pemilik]",
  "output": "[SOP format chat WA]"
}
```

### Opsi B — Manual Gold Standard
- Ambil 20-30 SOP formal dari `cleaned_sop.jsonl`
- Tulis manual versi chat WA-nya
- Jadikan gold standard untuk evaluasi kualitas synthetic data

### Cara Load STIF-Indonesia
```python
from datasets import load_dataset
dset = load_dataset("SEACrowd/stif_indonesia", trust_remote_code=True)
# Ambil kolom teks informal sebagai style reference
informal_samples = [d['informal'] for d in dset['train']][:50]
```
> Install dulu: `pip install seacrowd datasets`

### Karakteristik Output yang Harus Ada
- [ ] Kalimat pendek (1-2 baris per poin)
- [ ] Singkatan umum: yg, gak, udh, hrs, blm, trs, jgn, lgsg, sblm
- [ ] Boleh pakai emoji (👇 ✅ ⚠️ 📌)
- [ ] Urutan pakai bullet `-` atau nomor sederhana
- [ ] Tidak pakai heading formal (## atau ###)
- [ ] Bahasa santai/gaul tapi isinya tetap informatif

## Target Jumlah Data
| Split | Jumlah |
|-------|--------|
| Train | 500 pairs |
| Val   | 60 pairs |
| Test  | 60 pairs |
| **Total** | **620 pairs** |

## Script yang Perlu Dibuat
- `generate_chat_wa.py` — generate pairs dengan prompt persona Chat WA
  - Input: `../dataset-dokumen/scraping/cleaned_sop.jsonl`
  - Output: `paired_chat_wa.jsonl`

## Contoh Pair
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Chat WA.",
  "input": "Pokoknya kalo pagi si Andi buka rolling door dulu jam 8, terus panasin mesin kopi sekitar 15 menit, sambil itu lap-lap meja. Jangan lupa cek stok susu sama cup.",
  "output": "Aturan opening pagi guys 📌\n- jam 8 buka rolling door (si Andi yg pegang kunci)\n- langsung panasin mesin kopi, tunggu ±15 menit\n- sambil nunggu lap meja + kursi dulu\n- cek stok susu & cup, klo abis lgsg WA ke supplier\n- baru buka jam 9 tepat ✅"
}
```

## Catatan
- Output Chat WA berbeda dari input Chat WA (persona chat_style di dataset-dokumen)
- Jangan campur dengan input style — ini adalah OUTPUT style
- Validasi: output harus bisa dibaca di WhatsApp tanpa format rusak
