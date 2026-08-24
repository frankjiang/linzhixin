#!/usr/bin/env python3
"""Fetch recent papers from arxiv API for a given research topic."""

import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import hashlib
import csv
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from paper_store import load_papers, save_papers

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_CACHE_DIR = DATA_DIR / ".cache" / "arxiv"
ARXIV_TIMEZONE = ZoneInfo("America/New_York")
ARXIV_MIN_INTERVAL = 3.1
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

_last_arxiv_request_at: Optional[float] = None

ALLOWED_CAT_PREFIXES = ("cs.", "stat.ML", "eess.IV", "eess.SP")
EXCLUDED_CATS = {"cs.CL", "cs.IR", "cs.DB", "cs.CR", "cs.SE", "cs.PL", "cs.DC"}

RELEVANCE_KEYWORDS = {
    "high": [
        "video world model", "video generation", "video prediction",
        "video diffusion", "video synthesis",
        "world modeling", "world modelling",
        "interactive world", "interactive simulation",
        "3d world", "3d generation", "3d scene", "neural radiance",
        "gaussian splatting", "3d reconstruction", "3d-aware",
        "jepa", "dreamer", "dreamerv2", "dreamerv3",
        "latent world model", "latent dynamics", "latent action",
        "imagination", "imagined trajectories",
        "action-conditioned", "action conditioned", "action-conditional",
        "model-based reinforcement learning", "model based reinforcement learning",
        "world simulator", "world simulation",
        "embodied world model", "embodied simulation",
        "physical world model", "physics simulation",
        "autoregressive video", "autoregressive world",
        "diffusion world model", "diffusion transformer",
        "long-horizon video", "minute-scale",
        "occupancy prediction", "4d generation",
        "sora", "genie", "unisim", "pandora", "cosmos",
    ],
    "medium": [
        "world model", "predictive model",
        "visual dynamics", "visual prediction",
        "model-based planning", "model based planning",
        "environment model", "dynamics model",
        "forward model", "transition model",
        "diffusion model", "autoregressive",
        "embodied", "robot", "manipulation",
        "simulator", "simulation",
        "self-supervised", "representation learning",
        "video understanding", "video generation",
    ],
    "low": [
        "language model", "large language",
        "knowledge graph", "reasoning",
        "natural language", "text generation",
    ],
}

TOPICS = {
    "world_model": {
        "keywords": [
            "world model",
            "world simulator",
        ],
        "days": 30,
    }
}


def _arxiv_day() -> str:
    """Return the arXiv publication day used for the daily query cache."""
    return datetime.now(ARXIV_TIMEZONE).date().isoformat()


def _arxiv_cache_path(url: str) -> Path:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return ARXIV_CACHE_DIR / f"{key}.xml"


def _cache_is_current(cache_path: Path) -> bool:
    day_path = cache_path.with_suffix(".day")
    try:
        return cache_path.is_file() and day_path.read_text(encoding="utf-8").strip() == _arxiv_day()
    except OSError:
        return False


def _write_arxiv_cache(cache_path: Path, xml_text: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    day_path = cache_path.with_suffix(".day")
    xml_tmp = cache_path.with_name(f".{cache_path.name}.{os.getpid()}.tmp")
    day_tmp = day_path.with_name(f".{day_path.name}.{os.getpid()}.tmp")
    try:
        xml_tmp.write_text(xml_text, encoding="utf-8")
        day_tmp.write_text(f"{_arxiv_day()}\n", encoding="utf-8")
        os.replace(xml_tmp, cache_path)
        os.replace(day_tmp, day_path)
    finally:
        xml_tmp.unlink(missing_ok=True)
        day_tmp.unlink(missing_ok=True)


def _wait_for_arxiv_slot() -> None:
    """Enforce arXiv's one-request-per-three-seconds legacy API limit."""
    global _last_arxiv_request_at

    now = time.monotonic()
    if _last_arxiv_request_at is not None:
        wait = ARXIV_MIN_INTERVAL - (now - _last_arxiv_request_at)
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
    _last_arxiv_request_at = now


def _open_arxiv(req: urllib.request.Request, timeout: int = 30):
    """Open arXiv directly so a shared model-proxy IP cannot consume our quota."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(req, timeout=timeout)


def _retry_after_seconds(error: urllib.error.HTTPError, fallback: float) -> float:
    value = error.headers.get("Retry-After") if error.headers else None
    if value is not None:
        try:
            return max(float(value), fallback)
        except ValueError:
            pass
    return fallback


def fetch_arxiv(keyword: str, max_results: int = 200, start: int = 0) -> str:
    query = f'all:"{keyword}"'
    params = urllib.parse.urlencode({
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "start": start,
        "max_results": max_results,
    })
    url = f"{ARXIV_API}?{params}"
    cache_path = _arxiv_cache_path(url)
    if _cache_is_current(cache_path):
        print(f"  Using today's cached arXiv response: \"{keyword}\" page {start // max_results + 1}")
        return cache_path.read_text(encoding="utf-8")

    delays = (5, 15, 45)
    last_error: Exception | None = None
    for attempt, delay in enumerate(delays):
        _wait_for_arxiv_slot()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PaperSurveyBot/1.0"})
            with _open_arxiv(req, timeout=30) as resp:
                xml_text = resp.read().decode("utf-8")
            _write_arxiv_cache(cache_path, xml_text)
            return xml_text
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 and attempt < len(delays) - 1:
                retry_delay = _retry_after_seconds(e, delay)
                print(f"  arXiv rate limited (429), retry in {retry_delay:g}s...")
                time.sleep(retry_delay)
                continue
            if attempt < len(delays) - 1:
                time.sleep(delay)
                continue
        except Exception as e:
            last_error = e
            if attempt < len(delays) - 1:
                time.sleep(delay)
                continue

    if cache_path.is_file():
        print(f"  WARNING: arXiv unavailable after {len(delays)} attempts; using last successful cache")
        return cache_path.read_text(encoding="utf-8")
    raise RuntimeError(f"Failed to fetch arxiv after {len(delays)} attempts: {last_error}") from last_error


def parse_entries(xml_text: str, cutoff_date: datetime) -> list[dict]:
    root = ET.fromstring(xml_text)
    papers = []
    for entry in root.findall("atom:entry", NS):
        paper_id_url = entry.find("atom:id", NS).text.strip()
        arxiv_id = paper_id_url.split("/abs/")[-1]
        if arxiv_id.startswith("http"):
            continue

        published = entry.find("atom:published", NS).text.strip()
        pub_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if pub_date.replace(tzinfo=None) < cutoff_date:
            continue

        title = " ".join(entry.find("atom:title", NS).text.strip().split())
        abstract = " ".join(entry.find("atom:summary", NS).text.strip().split())

        authors = []
        for author in entry.findall("atom:author", NS):
            name = author.find("atom:name", NS).text.strip()
            authors.append(name)

        categories = []
        for cat in entry.findall("atom:category", NS):
            categories.append(cat.get("term"))

        if not is_relevant_category(categories):
            continue

        pdf_url = ""
        for link in entry.findall("atom:link", NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")

        relevance = compute_relevance(title, abstract)

        papers.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "date": pub_date.strftime("%Y-%m-%d"),
            "categories": categories,
            "abstract": abstract,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
            "affiliations": [],
            "tldr": "",
            "rating": 0,
            "relevance": relevance,
        })

    return papers


import re


def is_relevant_category(categories: list[str]) -> bool:
    for cat in categories:
        if cat in EXCLUDED_CATS:
            continue
        for prefix in ALLOWED_CAT_PREFIXES:
            if cat.startswith(prefix):
                return True
    return False


def compute_relevance(title: str, abstract: str) -> int:
    """Score 0-3: 0=unrelated, 1=tangential, 2=related, 3=core."""
    title_lower = title.lower()
    text = (title + " " + abstract).lower()

    high_hits = sum(1 for kw in RELEVANCE_KEYWORDS["high"] if kw in text)
    med_hits = sum(1 for kw in RELEVANCE_KEYWORDS["medium"] if kw in text)
    low_hits = sum(1 for kw in RELEVANCE_KEYWORDS["low"] if kw in text)

    title_has_wm = any(kw in title_lower for kw in [
        "world model", "world simulator", "world simulation",
        "world modeling", "world modelling",
    ])

    if title_has_wm:
        return 3 if high_hits >= 1 or med_hits >= 2 else 2

    if high_hits >= 2:
        return 3
    if high_hits >= 1:
        return 3 if med_hits >= 2 else 2
    if med_hits >= 3:
        return 2
    if med_hits >= 1:
        return 1 if low_hits < 2 else 0
    return 0


def deduplicate(papers: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for p in papers:
        if p["arxiv_id"] not in seen:
            seen.add(p["arxiv_id"])
            result.append(p)
    return result


def merge_with_existing(new_papers: list[dict], json_path: Path) -> list[dict]:
    existing = []
    if json_path.exists():
        existing = load_papers(json_path)

    existing_ids = {p["arxiv_id"] for p in existing}
    added = 0
    for p in new_papers:
        if p["arxiv_id"] not in existing_ids:
            existing.append(p)
            existing_ids.add(p["arxiv_id"])
            added += 1

    existing.sort(key=lambda x: x["date"], reverse=True)
    print(f"  Merged: {added} new papers, {len(existing)} total")
    return existing


def save_csv(papers: list[dict], csv_path: Path):
    fields = ["arxiv_id", "title", "date", "authors", "categories",
              "affiliations", "tldr", "rating", "relevance", "url", "pdf_url"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for p in papers:
            row = dict(p)
            row["authors"] = "; ".join(p["authors"])
            row["categories"] = "; ".join(p["categories"])
            row["affiliations"] = "; ".join(p.get("affiliations", []))
            writer.writerow(row)


def fetch_topic(topic_name: str, config: dict):
    print(f"\n{'='*60}")
    print(f"Fetching: {topic_name}")
    print(f"{'='*60}")

    topic_dir = DATA_DIR / topic_name
    topic_dir.mkdir(parents=True, exist_ok=True)
    json_path = topic_dir / "papers.json"
    csv_path = topic_dir / "papers.csv"

    cutoff = datetime.now() - timedelta(days=config["days"])
    all_papers = []

    for kw in config["keywords"]:
        print(f"  Searching: \"{kw}\"")
        for start in range(0, 500, 100):
            xml = fetch_arxiv(kw, max_results=100, start=start)
            papers = parse_entries(xml, cutoff)
            all_papers.extend(papers)
            print(f"    Page {start//100 + 1}: {len(papers)} papers in date range")
            if len(papers) < 100:
                break
            time.sleep(3)

    all_papers = deduplicate(all_papers)
    print(f"  Found {len(all_papers)} unique papers after dedup")

    merged = merge_with_existing(all_papers, json_path)

    save_papers(json_path, merged)

    save_csv(merged, csv_path)
    print(f"  Saved: {json_path}")
    print(f"  Saved: {csv_path}")

    from collections import Counter
    rel_counts = Counter(p.get("relevance", 0) for p in merged)
    print(f"  Relevance: core={rel_counts[3]} related={rel_counts[2]} tangential={rel_counts[1]} noise={rel_counts[0]}")

    return merged


def main():
    from config import apply_proxy_env

    apply_proxy_env()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for topic_name, config in TOPICS.items():
        fetch_topic(topic_name, config)
    print("\nDone.")


if __name__ == "__main__":
    main()
