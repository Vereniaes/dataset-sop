# 🔀 PLANNING: Dataset — Gaya Diagram (Mermaid Flowchart)

## Target Output Format
Diagram alur proses dalam format **Mermaid.js** (`flowchart TD`).
Bisa di-render langsung di Streamlit menggunakan `streamlit-mermaid`.

```
flowchart TD
    A([MULAI]) --> B[Buka Rolling Door - Jam 08.00]
    B --> C[Nyalakan Mesin Kopi]
    C --> D[Tunggu 15 menit]
    D --> E[Lap Meja & Kursi]
    E --> F{Cek Stok Susu & Cup}
    F -->|Stok Cukup| G[Buka Pintu - Jam 09.00]
    F -->|Stok Habis| H[Hubungi Supplier]
    H --> G
    G --> I([SELESAI - Toko Siap Beroperasi])
```

## Status
- [ ] Belum ada data (belum dijalankan)
- [x] Script generate sudah dibuat: `generate_diagram.py`

## Sumber Data
| Sumber | Platform | Isi | Fungsi |
|--------|----------|-----|--------|
| `cleaned_sop.jsonl` | Lokal | SOP formal Indonesia | **Sumber utama** untuk konversi ke flowchart |
| **STIF-Indonesia** | HuggingFace `SEACrowd/stif_indonesia` | ~6.000 pasangan informal↔formal | Inspirasi variasi kalimat input kasual |
| **WikiHow ID** | Lokal `raw_wikihow.jsonl` | Artikel HOW-TO berstruktur | SOP berurutan yang mudah dikonversi ke diagram |

> Diagram tidak butuh referensi gaya bahasa dari STIF — yang penting input kasual bervariasi dan SOP formal-nya berurutan dengan jelas.
> WikiHow ID sangat cocok untuk diagram karena artikelnya sudah step-by-step.

## Strategi Pengumpulan Data

### Opsi A — Synthetic via Script (Direkomendasikan)
Gunakan SOP formal dari `dataset-dokumen/scraping/cleaned_sop.jsonl`.
Script generate Mermaid flowchart dari langkah-langkah SOP yang sudah terstruktur.

Format `instruction`:
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Diagram Flowchart (format Mermaid.js flowchart TD, tampilkan alur kerja dari MULAI hingga SELESAI dengan decision node jika ada kondisi).",
  "input": "[deskripsi proses UMKM dari pemilik]",
  "output": "flowchart TD\n    A([MULAI]) --> ..."
}
```

### Karakteristik Output yang Harus Ada
- [ ] Selalu diawali `flowchart TD`
- [ ] Node MULAI: `A([MULAI])`
- [ ] Node SELESAI: `Z([SELESAI])`
- [ ] Step biasa: `[Label langkah]`
- [ ] Decision/kondisi: `{Pertanyaan?}` dengan label edge `-->|Ya|` dan `-->|Tidak|`
- [ ] Label node singkat dan jelas (max ~5 kata)
- [ ] Syntax valid — tidak boleh ada karakter special yang merusak Mermaid
- [ ] Jumlah node: 5-15 node (tidak terlalu kompleks)

## Tantangan Teknis
> ⚠️ Mermaid syntax harus 100% valid agar bisa di-render.
> Model yang di-fine-tune bisa salah syntax (kurung tidak match, karakter aneh, dll).

**Mitigasi:**
- Validasi output dengan `mermaid-py` atau regex cek dasar sebelum masuk training data
- Buat template yang konsisten sehingga model belajar pola yang sama
- Batasi complexity (hindari subgraph, styling custom, dll)

## Target Jumlah Data
| Split | Jumlah |
|-------|--------|
| Train | 400 pairs |
| Val   | 50 pairs |
| Test  | 50 pairs |
| **Total** | **500 pairs** |

> Lebih sedikit dari gaya lain karena kesulitan validasi syntax

## Script yang Perlu Dibuat
- `generate_diagram.py`
  - Input: `../dataset-dokumen/scraping/cleaned_sop.jsonl`
  - Output: `paired_diagram.jsonl`
  - Wajib ada validasi syntax Mermaid sebelum simpan

## Contoh Pair
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Diagram Flowchart (Mermaid).",
  "input": "Pagi jam 8 buka toko, panasin mesin kopi 15 menit, lap meja, cek stok susu & cup, kalo abis hubungi supplier, buka jam 9.",
  "output": "flowchart TD\n    A([MULAI]) --> B[Buka Toko - Jam 08.00]\n    B --> C[Nyalakan Mesin Kopi]\n    C --> D[Tunggu Pemanasan 15 Menit]\n    D --> E[Bersihkan Meja dan Kursi]\n    E --> F{Cek Stok Susu dan Cup}\n    F -->|Stok Cukup| G[Buka Pintu - Jam 09.00]\n    F -->|Stok Habis| H[Hubungi Supplier]\n    H --> G\n    G --> I([SELESAI])"
}
```

## Dependensi
```
pip install mermaid-py  # untuk validasi syntax
```

## Catatan
- Gunakan `flowchart TD` (top-down), bukan LR (left-right)
- Hindari karakter: `"`, `(`, `)` di dalam label node — bisa rusak syntax
- Kalau ada kondisi (if/else), wajib pakai decision node `{}`
