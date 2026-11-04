"""Raw-HTML archive: what the crawler saves and what seeding reads back.

Fetching (window-limited, 05:00-07:00 SGT) is kept separate from indexing
(unlimited): the full crawl only saves pages here, gzip-compressed, and appends
them to manifest.json. `python -m app.crawler seed --archive <dir>` then builds
the index from the archive at any time, and the same folder is the corpus that
goes into the submission's data zip.

Pure functions only (bs4 + stdlib), so they are testable without the network.
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

# /Act/EmA1968, /Act/PDPA2012, /SL/EmA1968-RG1 (optionally with a trailing slash)
DOC_PATH_RX = re.compile(r"^/(Act|SL|Acts-Supp)/[A-Za-z0-9][A-Za-z0-9-]*/?$")


def strip_query(url: str) -> str:
    s = urlsplit(url)
    return urlunsplit((s.scheme, s.netloc, s.path.rstrip("/"), "", ""))


def extract_listing_links(
    html: str, page_url: str, browse_prefix: str,
) -> tuple[list[str], list[str]]:
    """From one SSO browse page, return (document URLs, further listing pages).

    Document URLs are anchors whose path is /Act/<code> or /SL/<code>, with the
    query string removed. Listing pages are anchors whose path starts with the
    browse prefix (pagination, letter filters); the caller de-duplicates them
    and caps how many it follows.
    """
    soup = BeautifulSoup(html, "lxml")
    docs: list[str] = []
    pages: list[str] = []
    seen_docs: set[str] = set()
    seen_pages: set[str] = set()
    prefix_path = urlsplit(browse_prefix).path.rstrip("/")
    for a in soup.find_all("a", href=True):
        url = urljoin(page_url, a["href"])
        parts = urlsplit(url)
        if parts.netloc and parts.netloc != urlsplit(page_url).netloc:
            continue
        if DOC_PATH_RX.match(parts.path):
            clean = strip_query(url)
            if clean not in seen_docs:
                seen_docs.add(clean)
                docs.append(clean)
        elif prefix_path and parts.path.startswith(prefix_path):
            page = url.split("#")[0]
            if page not in seen_pages and page != page_url:
                seen_pages.add(page)
                pages.append(page)
    return docs, pages


def archive_relpath(url: str, kind: str) -> str:
    """acts/EmA1968.html.gz, sl/EmA1968-RG1.html.gz, judgments/2022-sgca-60.html.gz"""
    path = urlsplit(url).path.rstrip("/")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", path.rsplit("/", 1)[-1]) or "index"
    if kind == "judgment":
        folder = "judgments"
    elif "/SL/" in path or kind == "subsidiary_legislation":
        folder = "sl"
    else:
        folder = "acts"
    return f"{folder}/{name}.html.gz"


def _load_manifest(archive_dir: Path) -> dict:
    mpath = archive_dir / "manifest.json"
    if mpath.exists():
        return json.loads(mpath.read_text())
    return {"note": "SingLaw corpus archive: raw pages saved by the crawler "
                    "(gzip) plus bulk sources. Rebuild the index with "
                    "`python -m app.crawler seed --archive <this folder>`.",
            "documents": []}


def save_to_archive(archive_dir: Path, url: str, kind: str, html: str) -> str:
    """Write the page (gzip) and add or refresh its manifest entry. Returns relpath."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    rel = archive_relpath(url, kind)
    target = archive_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(target, "wt", encoding="utf-8") as fh:
        fh.write(html)

    manifest = _load_manifest(archive_dir)
    entry = {
        "path": rel,
        "kind": "judgment" if kind == "judgment" else "legislation",
        "source_url": strip_query(url),
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    if "/SL/" in url or kind == "subsidiary_legislation":
        entry["doc_type"] = "subsidiary_legislation"
    docs = [d for d in manifest["documents"] if d.get("path") != rel]
    docs.append(entry)
    manifest["documents"] = docs
    tmp = archive_dir / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=2))
    tmp.replace(archive_dir / "manifest.json")
    return rel


def read_archived(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return fh.read()
    return path.read_text(encoding="utf-8")
