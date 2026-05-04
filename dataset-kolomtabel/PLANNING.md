# 📊 PLANNING: Dataset — Gaya Kolom Tabel (Markdown Table)

## Target Output Format
Tabel Markdown dengan kolom: No, Langkah/Aktivitas, Penanggung Jawab, Waktu/Keterangan.
Mudah dibaca sekilas, cocok untuk print atau ditempel di dinding.

```
**SOP: Pembukaan Toko Harian**

| No | Langkah | Penanggung Jawab | Waktu |
|----|---------|-----------------|-------|
| 1  | Buka rolling door | Andi (Key Holder) | 08.00 |
| 2  | Nyalakan dan periksa mesin kopi | Barista | 08.00 - 08.15 |
| 3  | Bersihkan meja dan kursi area makan | Semua Staf | 08.15 - 08.30 |
| 4  | Cek ketersediaan stok susu dan cup | Barista | 08.30 |
| 5  | Hubungi supplier jika stok habis | Manajer / Barista | 08.30 |
| 6  | Buka pintu untuk pelanggan | Semua Staf | 09.00 |
```

## Status
- [ ] Belum ada data (belum dijalankan)
- [x] Script generate sudah dibuat: `generate_tabel.py`

## Sumber Data
| Sumber | Platform | Isi | Fungsi |
|--------|----------|-----|--------|
| `cleaned_sop.jsonl` | Lokal | SOP formal Indonesia | **Sumber utama** langkah-langkah untuk baris tabel |
| **STIF-Indonesia** | HuggingFace `SEACrowd/stif_indonesia` | ~6.000 pasangan informal↔formal | Referensi variasi input kasual yang natural |
| **Kamus Alay** | `github.com/okkyibrohim` → `new_kamusalay.csv` | ~5.000 kata slang | Augmentasi token informal di input |
| **WikiHow ID** | Lokal `raw_wikihow.jsonl` | Artikel HOW-TO berstruktur | SOP berurutan mudah dikonversi ke tabel |

> Tabel butuh SOP dengan info **siapa** yang bertanggung jawab tiap langkah.
> WikiHow ID kadang tidak ada info PIC — perlu generate role secara generic (Staf, Manajer, dll).

## Strategi Pengumpulan Data

### Opsi A — Synthetic via Script (Direkomendasikan)
Gunakan SOP formal dari `dataset-dokumen/scraping/cleaned_sop.jsonl`.
Konversi langkah-langkah SOP menjadi baris tabel.

Format `instruction`:
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Tabel (format Markdown table dengan kolom: No, Langkah, Penanggung Jawab, Waktu/Keterangan). Sertakan judul tabel di atas.",
  "input": "[deskripsi proses UMKM dari pemilik]",
  "output": "**SOP: [Judul]**\n\n| No | Langkah | Penanggung Jawab | Waktu |\n|...|\n| 1 | ... |"
}
```

### Karakteristik Output yang Harus Ada
- [ ] Judul tabel di atas (`**SOP: [nama proses]**`)
- [ ] Header: `| No | Langkah | Penanggung Jawab | Waktu |`
- [ ] Separator: `|----|---------|-----------------|-------|`
- [ ] Tiap langkah = 1 baris tabel
- [ ] Kolom Penanggung Jawab: bisa nama role (Barista, Kasir, Manajer) atau "Semua Staf"
- [ ] Kolom Waktu: bisa jam spesifik, durasi, atau "Sesuai kebutuhan"
- [ ] Minimal 4 baris, maksimal 15 baris
- [ ] Tidak ada heading markdown lain (### dll) — hanya tabel

## Variasi Kolom yang Boleh Digunakan
Tergantung konteks SOP, kolom bisa divariasikan:

| Variasi | Kolom |
|---------|-------|
| Standar | No, Langkah, Penanggung Jawab, Waktu |
| Simplified | No, Langkah, Keterangan |
| Dengan Status | No, Langkah, PIC, Waktu, Checklist |

> Model harus belajar memilih variasi yang sesuai konteks.
> Tapi untuk dataset awal, gunakan format Standar dulu untuk konsistensi.

## Target Jumlah Data
| Split | Jumlah |
|-------|--------|
| Train | 500 pairs |
| Val   | 60 pairs |
| Test  | 60 pairs |
| **Total** | **620 pairs** |

## Script yang Perlu Dibuat
- `generate_tabel.py`
  - Input: `../dataset-dokumen/scraping/cleaned_sop.jsonl`
  - Output: `paired_tabel.jsonl`
  - Validasi: cek syntax tabel valid (jumlah kolom konsisten tiap baris)

## Contoh Pair
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Tabel Markdown.",
  "input": "Pagi jam 8 buka toko, Andi yang pegang kunci. Terus panasin mesin kopi 15 menit. Lap meja sama kursi. Cek stok susu cup, kalo abis hubungi supplier. Buka jam 9.",
  "output": "**SOP: Pembukaan Toko Harian**\n\n| No | Langkah | Penanggung Jawab | Waktu |\n|----|---------|-----------------|-------|\n| 1 | Buka rolling door | Andi (Key Holder) | 08.00 |\n| 2 | Nyalakan mesin kopi | Barista | 08.00 |\n| 3 | Tunggu pemanasan mesin | Barista | 08.00 - 08.15 |\n| 4 | Bersihkan meja dan kursi | Semua Staf | 08.15 - 08.30 |\n| 5 | Cek stok susu dan cup | Barista | 08.30 |\n| 6 | Hubungi supplier jika stok habis | Barista/Manajer | 08.30 |\n| 7 | Buka pintu untuk pelanggan | Semua Staf | 09.00 |"
}
```

## Validasi Output
Sebelum masuk dataset, cek:
```python
# Pseudocode validasi tabel markdown
def is_valid_table(text):
    lines = text.strip().split('\n')
    # Ada header, separator, dan minimal 1 baris data
    table_lines = [l for l in lines if l.startswith('|')]
    if len(table_lines) < 3:
        return False
    # Jumlah kolom konsisten
    col_count = lines[0].count('|')
    return all(l.count('|') == col_count for l in table_lines)
```

## Catatan
- Render di Streamlit pakai `st.markdown(output)` langsung
- Kolom "Waktu" boleh dikosongkan (`-`) jika tidak ada info waktu dari input
- Jangan halusinasi nama orang — kalau tidak ada nama di input, pakai role saja
