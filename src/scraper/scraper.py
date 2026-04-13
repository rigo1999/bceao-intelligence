"""
BCEAO Scraper — Version 2 (robuste)
Approche en 2 phases :
  Phase 1 → Crawler les listings + télécharger les fichiers directs (PDFs)
  Phase 2 → Résoudre les pages de détail par petits lots avec backoff
"""

import os
import re
import json
import time
import random
import hashlib
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from settings import BCEAO_BASE_URL, RAW_DIR, REQUEST_DELAY

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

SECTIONS = {
    "rapports": {
        "url": f"{BCEAO_BASE_URL}/fr/publications/rapports",
        "label": "Rapports",
    },
    "bulletins": {
        "url": f"{BCEAO_BASE_URL}/fr/publications/bulletins",
        "label": "Bulletins",
    },
    "notes": {
        "url": f"{BCEAO_BASE_URL}/fr/publications/notes",
        "label": "Notes",
    },
    "documents-de-travail": {
        "url": f"{BCEAO_BASE_URL}/fr/publications/documents-de-travail",
        "label": "Documents de travail",
    },
    "revue-economique": {
        "url": f"{BCEAO_BASE_URL}/fr/publications/revue-economique-et-monetaire",
        "label": "Revue Économique et Monétaire",
    },
    "communiques": {
        "url": f"{BCEAO_BASE_URL}/fr/communique-presse",
        "label": "Communiqués de Presse",
    },
}

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".csv"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

INDEX_FILE    = Path(RAW_DIR) / "index.json"
LINKS_CACHE   = Path(RAW_DIR) / "_links_cache.json"
VISITED_CACHE = Path(RAW_DIR) / "_visited_urls.json"
LOG_FILE = Path("logs") / f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

def setup_logging():
    Path("logs").mkdir(exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
        colorize=True,
    )
    logger.add(
        str(LOG_FILE),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG",
        encoding="utf-8",
    )


def load_index() -> dict:
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_index(index: dict):
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def load_links_cache() -> list:
    if LINKS_CACHE.exists():
        with open(LINKS_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_links_cache(links: list):
    LINKS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(LINKS_CACHE, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)


def load_visited_urls() -> set:
    if VISITED_CACHE.exists():
        with open(VISITED_CACHE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_visited_urls(visited: set):
    VISITED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(VISITED_CACHE, "w", encoding="utf-8") as f:
        json.dump(list(visited), f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# HTTP avec retry + backoff
# ─────────────────────────────────────────────

def smart_delay():
    """Délai aléatoire pour paraître plus humain."""
    time.sleep(REQUEST_DELAY + random.uniform(0.5, 2.0))


def fetch_with_retry(url: str, session: requests.Session, max_retries: int = 3) -> BeautifulSoup | None:
    """GET avec retries et backoff exponentiel."""
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.exceptions.RequestException as e:
            wait = (2 ** attempt) * 5 + random.uniform(2, 6)
            if attempt < max_retries - 1:
                logger.warning(f"  ⚠ Tentative {attempt+1}/{max_retries} échouée pour {url}, retry dans {wait:.0f}s...")
                time.sleep(wait)
            else:
                logger.error(f"  ✗ Échec définitif pour {url}: {e}")
                return None


# ─────────────────────────────────────────────
# ÉTAPE 2 — Crawler les pages de listing
# ─────────────────────────────────────────────

def extract_links_from_listing(soup: BeautifulSoup, base_url: str) -> tuple[list, list]:
    """
    Extrait les liens depuis une page de listing.
    Retourne (direct_files, detail_pages) séparément.
    """
    direct_files = []
    detail_pages = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        
        if full_url in seen:
            continue
        seen.add(full_url)

        ext = Path(urlparse(full_url).path).suffix.lower()
        title = a.get_text(strip=True) or Path(urlparse(full_url).path).stem

        # Fichier direct (PDF, Excel, etc.)
        if ext in ALLOWED_EXTENSIONS:
            direct_files.append({
                "type": "direct_file",
                "url": full_url,
                "title": title,
                "ext": ext,
            })
        # Page de détail (nœud Drupal ou slug)
        elif "/node/" in href:
            detail_pages.append({
                "type": "detail_page",
                "url": full_url,
                "title": title,
                "ext": None,
            })
        elif any(pattern in href for pattern in [
            "/fr/publications/rapport",
            "/fr/publications/bulletin",
            "/fr/publications/note",
            "/fr/publications/document",
            "/fr/publications/revue",
            "/fr/communique-presse/",
        ]):
            # Vérifier que ce n'est pas un lien de section
            is_section = href.rstrip("/") in [
                "/fr/publications/rapports", "/fr/publications/bulletins",
                "/fr/publications/notes", "/fr/publications/documents-de-travail",
                "/fr/publications/revue-economique-et-monetaire",
                "/fr/communique-presse",
            ]
            if not is_section and "?" not in href:
                detail_pages.append({
                    "type": "detail_page",
                    "url": full_url,
                    "title": title,
                    "ext": None,
                })

    return direct_files, detail_pages


def crawl_section(section_key: str, section_info: dict, session: requests.Session) -> tuple[list, list]:
    """Parcourt une section avec pagination. Retourne (direct_files, detail_pages)."""
    base_url = section_info["url"]
    label = section_info["label"]
    all_direct = []
    all_detail = []
    page = 0

    logger.info(f"📂 Section : {label}")

    while True:
        url = f"{base_url}?page={page}" if page > 0 else base_url
        logger.debug(f"  → GET {url}")

        soup = fetch_with_retry(url, session, max_retries=2)
        if soup is None:
            break

        direct, detail = extract_links_from_listing(soup, BCEAO_BASE_URL)

        if not direct and not detail and page > 0:
            break

        for link in direct:
            link["category"] = label
            link["section_key"] = section_key
        for link in detail:
            link["category"] = label
            link["section_key"] = section_key

        all_direct.extend(direct)
        all_detail.extend(detail)

        logger.info(f"  Page {page}: {len(direct)} fichiers directs, {len(detail)} pages détail")

        # Pagination — chercher le lien "suivant" (tag <a rel="next"> ou <a> dans le <li> pager)
        next_a = soup.find("a", {"rel": "next"})
        if not next_a:
            next_li = soup.find("li", class_="pager__item--next")
            next_a = next_li.find("a") if next_li else None
        if not next_a:
            break

        page += 1
        smart_delay()

    return all_direct, all_detail


# ─────────────────────────────────────────────
# ÉTAPE 2b — Résolution des pages de détail (par lots)
# ─────────────────────────────────────────────

def resolve_detail_page(url: str, session: requests.Session) -> list[dict]:
    """Visite une page de détail, extrait fichiers ou contenu HTML."""
    soup = fetch_with_retry(url, session, max_retries=3)
    if soup is None:
        return []

    results = []

    # Chercher fichiers téléchargeables
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(BCEAO_BASE_URL, href)
        ext = Path(urlparse(full_url).path).suffix.lower()
        if ext in ALLOWED_EXTENSIONS:
            title = a.get_text(strip=True) or Path(urlparse(full_url).path).stem
            results.append({
                "type": "direct_file",
                "url": full_url,
                "title": title,
                "ext": ext,
            })

    # Si pas de fichier → sauvegarder le HTML
    if not results:
        title_tag = soup.find("h1") or soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else url
        content_div = (
            soup.find("div", class_="field--type-text-with-summary") or
            soup.find("div", class_="field--name-body") or
            soup.find("article") or
            soup.find("main")
        )
        if content_div:
            results.append({
                "type": "html_content",
                "url": url,
                "title": page_title,
                "ext": ".html",
                "html_content": str(content_div),
            })

    return results


# ─────────────────────────────────────────────
# Nommage des fichiers + téléchargement
# ─────────────────────────────────────────────

def build_filename(title: str, url: str, ext: str) -> str:
    clean = re.sub(r"[^\w\s\-éèêàâùûîïôœç]", "", title, flags=re.UNICODE)
    clean = re.sub(r"\s+", "_", clean.strip())[:80]
    short_hash = hashlib.md5(url.encode()).hexdigest()[:6]
    if not ext:
        ext = Path(urlparse(url).path).suffix.lower() or ".bin"
    return f"{clean}_{short_hash}{ext}"


def deduplicate(links: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for link in links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique.append(link)
    return unique


def download_file(url: str, dest: Path, session: requests.Session) -> bool:
    try:
        with session.get(url, headers=HEADERS, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        logger.error(f"  ✗ Download échoué {url}: {e}")
        return False


def save_html(content: str, dest: Path) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"  ✗ Sauvegarde HTML échouée: {e}")
        return False


# ─────────────────────────────────────────────
# ORCHESTRATEUR PRINCIPAL
# ─────────────────────────────────────────────

def run_scraper():
    """Scraping en 2 phases : fichiers directs d'abord, puis pages de détail."""
    setup_logging()
    logger.info("=" * 60)
    logger.info("BCEAO RAG — Scraping v2 (robuste)")
    logger.info("=" * 60)

    raw_dir = Path(RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    index = load_index()
    existing_files = set(index.keys())
    stats = {"found": 0, "downloaded": 0, "skipped": 0, "errors": 0}

    session = requests.Session()
    session.headers.update(HEADERS)

    # ── PHASE 1 : Crawler les listings ─────────────────────────
    cached_links = load_links_cache()
    
    if cached_links:
        logger.info(f"♻️  Cache trouvé avec {len(cached_links)} liens, skip du crawling")
        all_direct = [l for l in cached_links if l["type"] == "direct_file"]
        all_detail = [l for l in cached_links if l["type"] == "detail_page"]
    else:
        all_direct = []
        all_detail = []
        
        for section_key, section_info in SECTIONS.items():
            direct, detail = crawl_section(section_key, section_info, session)
            all_direct.extend(direct)
            all_detail.extend(detail)
            smart_delay()

        # Sauvegarder le cache
        save_links_cache(all_direct + all_detail)
        logger.info(f"\n🔍 Liens trouvés : {len(all_direct)} fichiers directs + {len(all_detail)} pages de détail")

    # ── PHASE 1b : Télécharger les fichiers directs ────────────
    all_direct = deduplicate(all_direct)
    logger.info(f"\n⬇️  Phase 1 — Téléchargement de {len(all_direct)} fichiers directs")

    for item in tqdm(all_direct, desc="📥 Fichiers directs", unit="doc"):
        url = item["url"]
        title = item.get("title", "")
        ext = item.get("ext", ".pdf")
        category = item.get("category", "divers")
        section_key = item.get("section_key", "divers")

        filename = build_filename(title, url, ext)
        dest = raw_dir / section_key / filename

        if filename in existing_files and dest.exists():
            stats["skipped"] += 1
            continue

        success = download_file(url, dest, session)
        if success:
            logger.info(f"  ✓ {filename}")
            stats["downloaded"] += 1
            index[filename] = {
                "filename": filename,
                "url": url,
                "title": title,
                "category": category,
                "section_key": section_key,
                "type": "direct_file",
                "extension": ext,
                "downloaded_at": datetime.now().isoformat(),
            }
            save_index(index)
        else:
            stats["errors"] += 1

        smart_delay()

    # ── PHASE 2 : Résoudre les pages de détail par lots ────────
    all_detail = deduplicate(all_detail)
    visited_urls = load_visited_urls()

    # Filtrer les URLs déjà visitées
    pending_detail = [item for item in all_detail if item["url"] not in visited_urls]
    skipped_count = len(all_detail) - len(pending_detail)
    logger.info(f"\n📄 Phase 2 — {len(pending_detail)} pages à traiter ({skipped_count} déjà visitées, ignorées)")

    BATCH_SIZE  = 10
    BATCH_PAUSE = 30   # Pause entre lots

    consecutive_errors = 0

    for i in range(0, len(pending_detail), BATCH_SIZE):
        batch = pending_detail[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(pending_detail) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info(f"\n  📦 Lot {batch_num}/{total_batches} ({len(batch)} pages)")

        batch_errors = 0

        for item in batch:
            url = item["url"]
            category = item.get("category", "divers")
            section_key = item.get("section_key", "divers")

            resolved = resolve_detail_page(url, session)

            # Marquer l'URL comme visitée même si 0 fichiers trouvés
            visited_urls.add(url)
            save_visited_urls(visited_urls)

            if not resolved:
                batch_errors += 1
                consecutive_errors += 1
                stats["errors"] += 1
                # Pause supplémentaire si on accumule les erreurs
                if consecutive_errors >= 3:
                    extra = 30 * consecutive_errors
                    logger.warning(f"  ⚠ {consecutive_errors} erreurs consécutives — pause de {extra}s")
                    time.sleep(extra)
                continue

            consecutive_errors = 0  # reset si succès

            for r in resolved:
                r_title = r.get("title", item.get("title", ""))
                r_ext = r.get("ext", ".pdf")

                filename = build_filename(r_title, r["url"], r_ext)
                dest = raw_dir / section_key / filename

                if filename in existing_files and dest.exists():
                    stats["skipped"] += 1
                    continue

                if r["type"] == "html_content":
                    success = save_html(r.get("html_content", ""), dest)
                else:
                    success = download_file(r["url"], dest, session)

                if success:
                    logger.info(f"  ✓ {filename}")
                    stats["downloaded"] += 1
                    existing_files.add(filename)
                    index[filename] = {
                        "filename": filename,
                        "url": r["url"],
                        "title": r_title,
                        "category": category,
                        "section_key": section_key,
                        "type": r["type"],
                        "extension": r_ext,
                        "downloaded_at": datetime.now().isoformat(),
                    }
                    save_index(index)
                else:
                    batch_errors += 1
                    stats["errors"] += 1

                smart_delay()

        # Pause adaptative : plus longue si le lot a eu beaucoup d'erreurs
        if i + BATCH_SIZE < len(pending_detail):
            pause = BATCH_PAUSE + (batch_errors * 10)
            logger.info(f"  ⏸  Pause de {pause}s pour éviter le rate-limit...")
            time.sleep(pause)

    # ── RAPPORT FINAL ──────────────────────────────────────────
    stats["found"] = len(all_direct) + len(all_detail)
    logger.info("\n" + "=" * 60)
    logger.info("📊 RAPPORT FINAL")
    logger.info("=" * 60)
    logger.info(f"  Documents trouvés   : {stats['found']}")
    logger.info(f"  Téléchargés         : {stats['downloaded']}")
    logger.info(f"  Déjà existants (↷)  : {stats['skipped']}")
    logger.info(f"  Erreurs             : {stats['errors']}")
    logger.info(f"  Index sauvegardé    : {INDEX_FILE}")
    logger.info("=" * 60)

    return stats
