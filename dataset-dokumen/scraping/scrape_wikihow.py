"""
Scraper untuk WikiHow Indonesia
Mengumpulkan artikel how-to dan mengubahnya ke format SOP.

Output: raw_wikihow.jsonl
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
import re
from urllib.parse import urljoin

# ============================================================
# CONFIG
# ============================================================
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "raw_wikihow.jsonl")
BASE_URL = "https://id.wikihow.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
DELAY_SECONDS = 2  # jeda antar request biar gak di-block
MAX_ARTICLES = 300  # target jumlah artikel

# Kategori WikiHow yang relevan untuk UMKM / proses bisnis
SEED_CATEGORIES = [
    "/Kategori:Bisnis",
    "/Kategori:Keuangan-dan-Bisnis",
    "/Kategori:Pekerjaan",
    "/Kategori:Karier",
    "/Kategori:Makanan-dan-Hiburan",
    "/Kategori:Memasak",
    "/Kategori:Kebersihan",
    "/Kategori:Komputer-dan-Elektronik",
]

# Kata kunci pencarian tambahan (search di WikiHow)
SEARCH_QUERIES = [
    "cara membuka usaha",
    "cara melayani pelanggan",
    "cara mengelola keuangan",
    "cara membuat laporan",
    "cara memasak",
    "cara membersihkan",
    "cara menyimpan makanan",
    "cara mengoperasikan mesin",
    "cara mengemas produk",
    "cara menangani komplain",
    "cara merekrut karyawan",
    "cara membuat rencana bisnis",
    "cara mengelola stok",
    "cara promosi",
    "cara membuat website toko",
    "cara membuat kopi",
    "cara membuat roti",
    "cara mencuci",
    "cara memperbaiki",
    "cara mengatur jadwal",
]


def get_soup(url):
    """Fetch URL dan return BeautifulSoup object."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        print(f"  [ERROR] Gagal fetch {url}: {e}")
        return None


def get_article_links_from_category(category_path, max_per_category=50):
    """Ambil link artikel dari halaman kategori WikiHow."""
    url = BASE_URL + category_path
    print(f"[KATEGORI] Fetching: {url}")
    soup = get_soup(url)
    if not soup:
        return []

    links = []
    # WikiHow category pages list articles in divs
    for a_tag in soup.select("a[href]"):
        href = a_tag.get("href", "")
        # WikiHow article URLs biasanya format /Cara-Melakukan-Sesuatu
        if href.startswith("/") and not href.startswith("/Kategori:") and "Cara" in href:
            full_url = BASE_URL + href
            if full_url not in links:
                links.append(full_url)
        if len(links) >= max_per_category:
            break

    print(f"  Ditemukan {len(links)} artikel dari kategori")
    return links


def search_wikihow(query, max_results=15):
    """Cari artikel di WikiHow Indonesia via search."""
    search_url = f"{BASE_URL}/wikiHowTo?search={requests.utils.quote(query)}"
    print(f"[SEARCH] Query: '{query}'")
    soup = get_soup(search_url)
    if not soup:
        return []

    links = []
    for a_tag in soup.select("a.result_link"):
        href = a_tag.get("href", "")
        if href and href not in links:
            links.append(href)
        if len(links) >= max_results:
            break

    # Fallback: cari semua link yang mengandung "Cara"
    if not links:
        for a_tag in soup.select("a[href]"):
            href = a_tag.get("href", "")
            if "wikihow" in href and "Cara" in href and href not in links:
                links.append(href)
            if len(links) >= max_results:
                break

    print(f"  Ditemukan {len(links)} hasil")
    return links


def parse_wikihow_article(url):
    """Parse satu artikel WikiHow dan extract steps."""
    soup = get_soup(url)
    if not soup:
        return None

    # Extract judul
    title_tag = soup.find("h1", class_="firstHeading") or soup.find("h1")
    if not title_tag:
        return None
    title = title_tag.get_text(strip=True)

    # Extract steps
    steps = []
    # WikiHow steps biasanya dalam div.step > b.whb (bold step text)
    step_elements = soup.select("div.step")
    for i, step_div in enumerate(step_elements, 1):
        # Ambil bold header step
        bold = step_div.find("b", class_="whb")
        step_title = bold.get_text(strip=True) if bold else ""

        # Ambil full text step
        step_text = step_div.get_text(strip=True)
        # Clean up
        step_text = re.sub(r'\s+', ' ', step_text)

        if step_text:
            steps.append({
                "step_number": i,
                "step_title": step_title,
                "step_detail": step_text
            })

    # Fallback: cari via ordered list
    if not steps:
        for i, li in enumerate(soup.select("ol li"), 1):
            text = li.get_text(strip=True)
            if len(text) > 10:
                steps.append({
                    "step_number": i,
                    "step_title": "",
                    "step_detail": re.sub(r'\s+', ' ', text)
                })

    if not steps:
        return None

    # Extract intro/summary jika ada
    intro = ""
    intro_div = soup.select_one("div.mf-section-0") or soup.select_one("p")
    if intro_div:
        intro = intro_div.get_text(strip=True)[:500]

    # Konversi ke format SOP
    sop_text = format_as_sop(title, intro, steps)

    return {
        "source": "wikihow_id",
        "url": url,
        "title": title,
        "num_steps": len(steps),
        "steps_raw": steps,
        "sop_text": sop_text
    }


def format_as_sop(title, intro, steps):
    """Konversi artikel WikiHow ke format SOP formal."""
    sop_parts = []

    # Header
    clean_title = title.replace("Cara ", "").replace("cara ", "")
    sop_parts.append(f"## SOP: {clean_title}")
    sop_parts.append("")

    # Tujuan
    sop_parts.append("### Tujuan")
    if intro:
        # Ambil kalimat pertama sebagai tujuan
        first_sentence = intro.split('.')[0] + '.'
        sop_parts.append(f"Memastikan proses {clean_title.lower()} berjalan dengan baik dan sesuai standar.")
    else:
        sop_parts.append(f"Menetapkan prosedur standar untuk {clean_title.lower()}.")
    sop_parts.append("")

    # Ruang Lingkup
    sop_parts.append("### Ruang Lingkup")
    sop_parts.append(f"SOP ini berlaku untuk seluruh proses {clean_title.lower()}.")
    sop_parts.append("")

    # Prosedur
    sop_parts.append("### Prosedur Kerja")
    for step in steps:
        title_part = f" — {step['step_title']}" if step['step_title'] else ""
        sop_parts.append(f"{step['step_number']}. {step['step_detail'][:300]}")
    sop_parts.append("")

    return "\n".join(sop_parts)


def main():
    """Main scraping pipeline."""
    print("=" * 60)
    print("WikiHow Indonesia Scraper untuk SOP-ify Dataset")
    print("=" * 60)

    all_urls = set()

    # 1. Kumpulkan URL dari kategori
    print("\n--- Fase 1: Scraping dari Kategori ---")
    for cat in SEED_CATEGORIES:
        urls = get_article_links_from_category(cat)
        all_urls.update(urls)
        time.sleep(DELAY_SECONDS)

    # 2. Kumpulkan URL dari search
    print("\n--- Fase 2: Scraping dari Search ---")
    for query in SEARCH_QUERIES:
        urls = search_wikihow(query)
        all_urls.update(urls)
        time.sleep(DELAY_SECONDS)

    print(f"\nTotal URL unik yang ditemukan: {len(all_urls)}")

    # Limit
    url_list = list(all_urls)[:MAX_ARTICLES]
    print(f"Akan memproses: {len(url_list)} artikel\n")

    # 3. Parse setiap artikel
    results = []
    existing_urls = set()

    # Load existing data jika ada (untuk resume)
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                existing_urls.add(data["url"])
        print(f"Sudah ada {len(existing_urls)} artikel dari sebelumnya, skip...")

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for i, url in enumerate(url_list, 1):
            if url in existing_urls:
                continue

            print(f"[{i}/{len(url_list)}] Parsing: {url}")
            article = parse_wikihow_article(url)

            if article and article["num_steps"] >= 3:
                f.write(json.dumps(article, ensure_ascii=False) + "\n")
                results.append(article)
                print(f"  ✓ {article['title']} ({article['num_steps']} langkah)")
            else:
                print(f"  ✗ Skip (terlalu sedikit langkah atau gagal parse)")

            time.sleep(DELAY_SECONDS)

    print(f"\n{'=' * 60}")
    print(f"SELESAI! Total artikel berhasil: {len(results)}")
    print(f"Disimpan di: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
