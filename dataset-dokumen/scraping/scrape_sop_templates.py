"""
Scraper untuk template SOP dari berbagai sumber Indonesia.
Mengumpulkan contoh SOP formal dari blog bisnis, HR, dan portal UMKM.

Output: raw_sop_templates.jsonl
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
import re

# ============================================================
# CONFIG
# ============================================================
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "raw_sop_templates.jsonl")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
DELAY_SECONDS = 3

# Google search queries untuk mencari SOP template
SEARCH_QUERIES = [
    "contoh SOP UMKM lengkap",
    "template SOP kedai kopi",
    "contoh SOP restoran",
    "contoh SOP toko online",
    "SOP laundry kiloan",
    "contoh SOP bengkel motor",
    "SOP warung makan",
    "template SOP salon kecantikan",
    "contoh SOP klinik",
    "SOP minimarket",
    "contoh SOP bakery",
    "SOP catering rumahan",
    "contoh SOP barbershop",
    "SOP percetakan digital",
    "contoh SOP apotek",
    "SOP operasional toko",
    "contoh SOP pelayanan pelanggan",
    "SOP penerimaan barang gudang",
    "contoh SOP kebersihan restoran",
    "SOP pembukaan toko pagi",
    "contoh SOP kasir",
    "SOP penanganan komplain pelanggan",
    "contoh SOP pengiriman barang",
    "SOP perawatan mesin",
    "contoh SOP stock opname",
]


def google_search(query, num_results=10):
    """
    Cari di Google dan return list of URLs.
    Menggunakan Google Search via requests.
    """
    search_url = "https://www.google.com/search"
    params = {
        "q": query,
        "num": num_results,
        "hl": "id",
        "gl": "id",
    }

    try:
        resp = requests.get(search_url, params=params, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")

        urls = []
        for a_tag in soup.select("a[href]"):
            href = a_tag.get("href", "")
            # Google wraps URLs in /url?q=...
            if href.startswith("/url?q="):
                actual_url = href.split("/url?q=")[1].split("&")[0]
                # Filter out google, youtube, wikipedia
                skip_domains = ["google.", "youtube.", "wikipedia.", "facebook.", "instagram."]
                if not any(d in actual_url for d in skip_domains):
                    urls.append(actual_url)

        return urls[:num_results]
    except Exception as e:
        print(f"  [ERROR] Google search gagal: {e}")
        return []


def extract_sop_content(url):
    """
    Extract konten SOP dari sebuah halaman web.
    Mencoba mengidentifikasi bagian-bagian SOP.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        print(f"  [ERROR] Gagal fetch {url}: {e}")
        return None

    # Remove script, style, nav, footer
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Ambil judul
    title = ""
    title_tag = soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Ambil konten utama
    # Coba cari article atau main content area
    main_content = (
        soup.find("article") or
        soup.find("main") or
        soup.find("div", class_=re.compile(r"content|post|article|entry", re.I)) or
        soup.find("body")
    )

    if not main_content:
        return None

    # Extract text terstruktur
    full_text = main_content.get_text(separator="\n", strip=True)

    # Harus mengandung kata kunci SOP
    sop_keywords = ["sop", "prosedur", "langkah", "standar operasional", "tujuan", "ruang lingkup"]
    text_lower = full_text.lower()
    keyword_count = sum(1 for kw in sop_keywords if kw in text_lower)

    if keyword_count < 2:
        return None

    # Coba extract bagian-bagian SOP
    sections = extract_sop_sections(main_content)

    # Jangan simpan jika teksnya terlalu pendek
    if len(full_text) < 200:
        return None

    # Truncate jika terlalu panjang
    if len(full_text) > 5000:
        full_text = full_text[:5000]

    return {
        "source": "web_scrape",
        "url": url,
        "title": title,
        "full_text": full_text,
        "sections": sections,
        "keyword_score": keyword_count,
    }


def extract_sop_sections(content_elem):
    """Coba extract bagian Tujuan, Ruang Lingkup, Prosedur dari elemen HTML."""
    sections = {}

    # Cari heading-heading
    headings = content_elem.find_all(["h1", "h2", "h3", "h4", "strong", "b"])

    for heading in headings:
        heading_text = heading.get_text(strip=True).lower()

        # Identifikasi section
        section_name = None
        if any(kw in heading_text for kw in ["tujuan", "objective", "purpose"]):
            section_name = "tujuan"
        elif any(kw in heading_text for kw in ["ruang lingkup", "scope"]):
            section_name = "ruang_lingkup"
        elif any(kw in heading_text for kw in ["prosedur", "langkah", "procedure", "steps"]):
            section_name = "prosedur"
        elif any(kw in heading_text for kw in ["penanggung jawab", "responsibility", "pic"]):
            section_name = "penanggung_jawab"

        if section_name:
            # Ambil teks setelah heading sampai heading berikutnya
            next_texts = []
            sibling = heading.find_next_sibling()
            while sibling and sibling.name not in ["h1", "h2", "h3", "h4"]:
                text = sibling.get_text(strip=True)
                if text:
                    next_texts.append(text)
                sibling = sibling.find_next_sibling()

            sections[section_name] = "\n".join(next_texts)[:1000]

    return sections


def main():
    """Main scraping pipeline untuk SOP templates."""
    print("=" * 60)
    print("SOP Template Scraper - Sumber Web Indonesia")
    print("=" * 60)

    # Load existing URLs
    existing_urls = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                existing_urls.add(data["url"])
        print(f"Sudah ada {len(existing_urls)} entri, akan append...")

    all_urls = set()
    success_count = 0

    # Kumpulkan URLs dari Google Search
    print("\n--- Mengumpulkan URL dari Google Search ---")
    for query in SEARCH_QUERIES:
        print(f"\n[SEARCH] '{query}'")
        urls = google_search(query)
        print(f"  Ditemukan {len(urls)} URL")
        all_urls.update(urls)
        time.sleep(DELAY_SECONDS)

    # Filter URL yang sudah ada
    new_urls = [u for u in all_urls if u not in existing_urls]
    print(f"\nTotal URL baru: {len(new_urls)}")

    # Process setiap URL
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for i, url in enumerate(new_urls, 1):
            print(f"\n[{i}/{len(new_urls)}] Processing: {url[:80]}...")
            result = extract_sop_content(url)

            if result:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                success_count += 1
                print(f"  ✓ '{result['title'][:50]}' (keyword score: {result['keyword_score']})")
            else:
                print(f"  ✗ Tidak mengandung konten SOP")

            time.sleep(DELAY_SECONDS)

    print(f"\n{'=' * 60}")
    print(f"SELESAI! Berhasil extract: {success_count} halaman SOP")
    print(f"Disimpan di: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
