# 🗣️ PLANNING: Dataset — Gaya Instruksi Lisan

## Target Output Format
Kalimat instruksi langsung seperti supervisor yang ngomong ke karyawan baru,
pakai kata kerja imperatif, urutan jelas, tapi tetap informal dan mudah diikuti.

```
Dengerin ya, ini prosedur buka toko:

Pertama, kamu cek dulu rolling door-nya, buka jam 8 pas, jangan telat.
Kedua, langsung nyalain mesin kopi, tunggu 15 menit biar ready.
Ketiga, sambil nunggu mesin, lap meja sama kursi semua dulu.
Keempat — ini penting — cek stok susu sama cup, kalo abis langsung hubungi supplier.
Terakhir, baru boleh buka pintu buat pelanggan jam 9.
Ngerti? Ada pertanyaan?
```

## Status
- [ ] Belum ada data (belum dijalankan)
- [x] Script generate sudah dibuat: `generate_instruksi.py`

## Sumber Data
| Sumber | Platform | Isi | Fungsi |
|--------|----------|-----|--------|
| `cleaned_sop.jsonl` | Lokal | SOP formal Indonesia | **Output target** untuk generate |
| **STIF-Indonesia** | HuggingFace `SEACrowd/stif_indonesia` | ~6.000 pasangan informal↔formal | Referensi gaya bahasa semi-formal lisan |
| **IndoCollex** | `github.com/haryoa/indo-collex` | Kamus frasa formal-informal | Inspirasi variasi kalimat imperatif |

> STIF-Indonesia berguna untuk memvalidasi **tone** output — apakah sudah cukup alami seperti orang bicara, bukan seperti dokumen.

## Strategi Pengumpulan Data

### Opsi A — Synthetic via Script (Direkomendasikan)
Gunakan SOP formal dari `dataset-dokumen/scraping/cleaned_sop.jsonl` sebagai sumber output target.
Gunakan 5-10 contoh instruksi lisan dari STIF-Indonesia sebagai **few-shot examples** dalam prompt.

Alur:
1. Load SOP formal dari `cleaned_sop.jsonl`
2. Ambil sampel kalimat semi-formal dari STIF-Indonesia sebagai referensi tone
3. Prompt Gemini: "Ubah SOP ini menjadi instruksi lisan seperti supervisor berbicara ke karyawan baru"
4. Simpan sebagai `(input_kasual_umkm, output_instruksi_lisan)`

Format `instruction`:
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Instruksi Lisan (seperti supervisor mengajari karyawan baru secara langsung, pakai kalimat perintah yang jelas dan urutan bernomor).",
  "input": "[deskripsi proses UMKM dari pemilik]",
  "output": "[SOP gaya instruksi lisan]"
}
```

### Cara Load STIF-Indonesia
```python
from datasets import load_dataset
dset = load_dataset("SEACrowd/stif_indonesia", trust_remote_code=True)
# Ambil kalimat semi-formal sebagai referensi tone lisan
formal_samples = [d['formal'] for d in dset['train']][:30]
```
> Install dulu: `pip install seacrowd datasets`

### Karakteristik Output yang Harus Ada
- [ ] Dimulai dengan kalimat pengantar ("Dengerin ya", "Oke, jadi gini", "Perhatiin ya")
- [ ] Kata kerja imperatif: Pertama kamu X, Kedua langsung Y, Ketiga pastikan Z
- [ ] Nomor urut eksplisit (Pertama, Kedua, Ketiga, atau 1. 2. 3.)
- [ ] Boleh ada emphasis lisan: "ini penting", "jangan sampai skip", "awas lupa"
- [ ] Diakhiri kalimat penutup opsional ("Ngerti?" / "Ada pertanyaan?" / "Oke lanjut.")
- [ ] Tidak terlalu panjang per poin — 1-2 kalimat
- [ ] Bahasa semi-formal, bukan terlalu baku, bukan terlalu slang

## Target Jumlah Data
| Split | Jumlah |
|-------|--------|
| Train | 500 pairs |
| Val   | 60 pairs |
| Test  | 60 pairs |
| **Total** | **620 pairs** |

## Script yang Perlu Dibuat
- `generate_instruksi.py`
  - Input: `../dataset-dokumen/scraping/cleaned_sop.jsonl`
  - Output: `paired_instruksi.jsonl`

## Contoh Pair
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Instruksi Lisan.",
  "input": "Kalo pagi Andi buka rolling door jam 8, terus panasin mesin kopi 15 menit, lap meja, cek stok susu cup, buka jam 9.",
  "output": "Oke dengerin baik-baik, ini prosedur opening:\n\nPertama, kamu buka rolling door tepat jam 8, jangan telat.\nKedua, langsung nyalain mesin kopi dan tunggu sekitar 15 menit biar siap.\nKetiga, sambil nunggu mesin, lap semua meja dan kursi dulu — jangan dilewatin.\nKeempat — ini penting — cek stok susu sama cup. Kalo mau abis, langsung hubungi supplier sekarang juga.\nKelima, baru buka pintu buat pelanggan pas jam 9 tepat.\n\nUdah ngerti? Kalo ada yang kurang jelas tanya sekarang ya."
}
```

## Catatan
- Berbeda dari Voice Note (yang dihapus) — Instruksi Lisan lebih terstruktur dan terarah
- Tone: supervisor/senior mengajari, bukan ngobrol santai
- Perlu validasi: apakah urutannya logis dan lengkap?
