# 📋 PLANNING: Dataset — Gaya SOP Dokumen Terstruktur

## Target Output Format
```
📋 DOKUMEN STANDAR OPERASIONAL PROSEDUR (SOP)
1. Nama Modul       → judul proses
2. Tujuan           → tujuan SOP
3. Ruang Lingkup    → siapa/area yang terlibat
4. Referensi/Pedoman
5. Sarana           → alat/bahan yang dibutuhkan
6. Prosedur Kerja   → langkah-langkah kronologis
7. Flowchart        → bagan alir (ASCII atau Mermaid)
```

## Status
- [x] Raw data: `scraping/raw_wikihow.jsonl` (~300 artikel)
- [x] Synthetic pairs: `synthetic-generation/paired_data.jsonl` (1.186 pairs)
- [ ] Format output belum sesuai (saat ini hanya Tujuan + Ruang Lingkup + Prosedur Kerja, belum 7 seksi)
- [ ] Dataset final (train/val/test) belum dibuild

## Yang Harus Dilakukan

### Step 1A — Scraping Web (sudah ada, tapi perlu validasi)
- Jalankan `scraping/scrape_wikihow.py` jika data kurang
- Jalankan `scraping/scrape_sop_templates.py` untuk SOP asli dari web
- Jalankan `scraping/merge_scraped.py` → output: `scraping/cleaned_sop.jsonl`

### Step 1B — Scraping Dokumen SOP (PDF/DOCX/PPT) ✨ Baru
Scrape **5-10 dokumen SOP nyata per kategori UMKM** dari internet.
Ini adalah sumber berkualitas tinggi karena sudah ditulis oleh praktisi bisnis.

**Target 10 Kategori UMKM:**
| # | Kategori | Contoh Bisnis | Keyword Cari |
|---|----------|--------------|-------------|
| 1 | F&B | Restoran, warung, katering, bakery | `SOP restoran filetype:pdf` |
| 2 | Retail & Toko | Minimarket, toko fashion, toko online | `SOP toko retail filetype:pdf` |
| 3 | Jasa Perawatan | Salon, barbershop, spa, laundry | `SOP salon kecantikan filetype:pdf` |
| 4 | Otomotif | Bengkel motor/mobil, cuci kendaraan | `SOP bengkel filetype:pdf` |
| 5 | Kerajinan & Konveksi | Handicraft, jahit, percetakan | `SOP konveksi produksi filetype:pdf` |
| 6 | Agribisnis | Budidaya, pertanian, peternakan | `SOP budidaya filetype:pdf` |
| 7 | Kesehatan Kecil | Apotek, klinik kecantikan | `SOP apotek filetype:pdf` |
| 8 | Pendidikan | Bimbel, kursus, les privat | `SOP bimbingan belajar filetype:pdf` |
| 9 | Properti & Jasa Teknik | Kontraktor kecil, service AC | `SOP jasa teknik filetype:pdf` |
| 10 | Jasa Digital & Kreatif | Fotografi, desain grafis, video | `SOP studio foto filetype:pdf` |

**Sumber Dokumen:**
- Google: `site:.go.id SOP UMKM filetype:pdf` (situs pemerintah)
- `site:.ac.id SOP bisnis filetype:pdf` (universitas — sering ada studi kasus UMKM)
- SlideShare: SOP UMKM presentation
- Scribd: dokumen SOP operasional
- Dinas Koperasi daerah (banyak yang upload PDF panduan)
- LPDB-KUMKM, Kemenkop portal

**Cara Ekstraksi Teks:**
```python
# PDF → teks
import pdfplumber
with pdfplumber.open("sop.pdf") as pdf:
    text = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])

# DOCX → teks
from docx import Document
doc = Document("sop.docx")
text = "\n".join([p.text for p in doc.paragraphs])

# PPT → teks
from pptx import Presentation
prs = Presentation("sop.pptx")
text = "\n".join([shape.text for slide in prs.slides for shape in slide.shapes if shape.has_text_frame])
```

**Script yang perlu dibuat:** `scraping/scrape_sop_documents.py`
- Download PDF/DOCX dari URL yang dikumpulkan manual
- Ekstrak teks
- Normalisasi ke format 7 seksi menggunakan Gemini API
- Output: `scraping/sop_documents_raw.jsonl`

**Estimasi yield:** 10 kategori × 7 dokumen rata-rata = **~70 SOP berkualitas tinggi**

### Step 2 — Regenerate Synthetic Pairs dengan format baru
> ⚠️ `paired_data.jsonl` yang ada format output-nya belum 7 seksi.
> Perlu update `generate_synthetic.py` agar output menggunakan format lengkap.

Format `instruction` yang benar:
```json
{
  "instruction": "Ubah catatan UMKM berikut menjadi SOP dengan GAYA: Dokumen Terstruktur (7 seksi: Nama Modul, Tujuan, Ruang Lingkup, Referensi, Sarana, Prosedur Kerja, Flowchart).",
  "input": "[teks kasual dari pemilik UMKM]",
  "output": "[SOP lengkap 7 seksi]"
}
```

### Step 3 — Target Jumlah Data
| Split | Jumlah |
|-------|--------|
| Train | 800 pairs |
| Val   | 100 pairs |
| Test  | 100 pairs |
| **Total** | **1.000 pairs** |

### Step 4 — Build Final Dataset
- Jalankan `final/build_dataset.py`
- Output: `final/train.jsonl`, `final/val.jsonl`, `final/test.jsonl`

## Sumber Data
| Sumber | Estimasi Jumlah | Kualitas | Cara Dapat |
|--------|----------------|----------|----------|
| WikiHow ID (scraping) | ~300 artikel | ⭐⭐⭐ | `scrape_wikihow.py` |
| SOP template web ID | ~50-100 halaman | ⭐⭐⭐ | `scrape_sop_templates.py` |
| **Dokumen SOP nyata (PDF/DOCX/PPT)** | **~70 dokumen** | **⭐⭐⭐⭐⭐** | `scrape_sop_documents.py` (baru) |
| Kaggle WikiHow multilingual | Ribuan (filter ID) | ⭐⭐⭐ | `download_kaggle.py` |
| STIF-Indonesia | ~6.000 pasangan | ⭐⭐ (input ref) | HuggingFace |
| Synthetic (Gemini API) | 3 variasi/SOP | ⭐⭐⭐⭐ | `generate_synthetic.py` |

> 💡 Dokumen SOP nyata (PDF/DOCX) adalah sumber **terbaik** karena ditulis praktisi asli.
> Gunakan ini sebagai **gold standard output** dan benchmark kualitas.

## Catatan
- Tiap SOP butuh minimal 3 langkah
- Cek duplikat berdasarkan judul sebelum training
- Output harus include flowchart di seksi 7 (Mermaid format)
