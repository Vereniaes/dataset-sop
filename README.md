# SOP-ify: Dataset Generation Pipeline

Proyek ini berisi *pipeline* lengkap untuk mengumpulkan dan membuat dataset instruksional multi-gaya (multi-style) guna melakukan *fine-tuning* pada model LLM agar dapat mengotomatisasi pembuatan SOP untuk UMKM.

## ⚠️ Wajib Dibaca Pertama Kali
Sebelum menjalankan atau mengubah skrip di proyek ini, pastikan Anda membaca dua file utama berikut untuk memahami tujuan (goals) dan struktur data yang diharapkan:
1. **[`konteks.txt`](./konteks.txt)**: Berisi latar belakang proyek, persona, *prompt* sistem, dan batasan dalam mengumpulkan serta memproses data.
2. **[`expected_output.txt`](./expected_output.txt)**: Berisi contoh bentuk akhir JSONL yang diharapkan untuk *training* dan penjelasan metadatanya.

---

## 📂 Struktur Direktori

Setiap folder di bawah ini mewakili satu gaya (style) generasi dataset beserta script untuk men-generate variasi datanya. Masing-masing folder memiliki file `paired_*.jsonl` sebagai hasil keluarannya.

### 1. `dataset-dokumen/`
Berisi skrip untuk mengumpulkan dokumen SOP mentah dan mengubahnya menjadi format dokumen formal.
- **`scraping/`**: Skrip untuk mendownload PDF/DOCX referensi dari internet (`scrape_sop_documents.py`), atau dari WikiHow (`scrape_wikihow.py`).
- **`synthetic-generation/`**: Skrip untuk mengubah SOP mentah menjadi dataset dokumen formal.

### 2. `dataset-chat-wa/`
Skrip (`generate_chat_wa.py`) untuk men-generate dataset **Chat WhatsApp**. 
Model LLM mengubah instruksi kasual menjadi SOP formal yang disajikan dengan gaya balas-balasan chat yang ramah.

### 3. `dataset-instruksi/`
Skrip (`generate_instruksi.py`) untuk men-generate dataset **Instruksi Lisan**. 
Berfokus pada bagaimana mengonversi perintah kasual atau pesan suara (transkrip lisan) menjadi urutan SOP operasional.

### 4. `dataset-diagram/`
Skrip (`generate_diagram.py`) untuk men-generate dataset **Diagram Mermaid**.
Berfokus pada output berupa *flowchart* (`flowchart TD`) menggunakan sintaks `mermaid.js` untuk memvisualisasikan alur SOP.

### 5. `dataset-kolomtabel/`
Skrip (`generate_tabel.py`) untuk men-generate dataset **Kolom Tabel**.
Output dari skrip ini berupa tabel Markdown terstruktur yang berisi langkah-langkah, pelaksana, dan keterangan.

---

## 🚀 Cara Menjalankan Generator

Setiap folder memiliki skrip Python mandiri. Pastikan environment variables (`GEMINI_API_KEY` atau `VERTEX_API_KEY`) sudah diset, atau secara hardcode sudah ada di dalam script.

Contoh untuk menjalankan salah satu generator:
```bash
# Menjalankan generator Chat WA dengan limit 50 SOP pertama
cd dataset-chat-wa
python3 generate_chat_wa.py --limit 50
```

Semua skrip mendukung parameter:
- `--limit N`: Membatasi jumlah SOP yang akan diproses.
- `--resume`: Melanjutkan proses (skip data yang sudah ada di file output).
- `--dry-run`: Hanya mencetak estimasi *API calls* tanpa menjalankan proses sebenarnya (khusus beberapa skrip).

## 🛠 Instalasi dan Dependensi
Pastikan dependensi di dalam `requirements.txt` sudah terinstal:
```bash
pip install -r requirements.txt
```
(Termasuk `google-genai`, `tqdm`, `requests`, dan pustaka lainnya yang relevan).
