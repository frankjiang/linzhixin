#!/usr/bin/env python3
"""Fetch recent papers from arxiv API for a given research topic."""

import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import hashlib
import csv
import math
import os
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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
FETCH_STAGE_TIMEOUT_SECONDS = 3600
ARXIV_REQUEST_TIMEOUT_SECONDS = 30
ARXIV_MAX_ATTEMPTS = 32
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

_last_arxiv_request_at: Optional[float] = None


class FetchDeadlineExceeded(TimeoutError):
    """The complete fetch phase exhausted its one-hour budget."""


def _remaining_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchDeadlineExceeded("fetch_papers exceeded the 1 hour deadline without complete fresh data")
    return remaining


def _sleep_with_deadline(seconds: float, deadline: float) -> None:
    time.sleep(min(seconds, _remaining_time(deadline)))
    _remaining_time(deadline)

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


def _wait_for_arxiv_slot(deadline: float | None = None) -> None:
    """Enforce arXiv's one-request-per-three-seconds legacy API limit."""
    global _last_arxiv_request_at

    now = time.monotonic()
    if _last_arxiv_request_at is not None:
        wait = ARXIV_MIN_INTERVAL - (now - _last_arxiv_request_at)
        if wait > 0:
            if deadline is None:
                time.sleep(wait)
            else:
                _sleep_with_deadline(wait, deadline)
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
            seconds = float(value)
            if math.isfinite(seconds):
                return max(seconds, fallback)
        except ValueError:
            pass
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max((when - datetime.now(timezone.utc)).total_seconds(), fallback)
        except (TypeError, ValueError, OverflowError):
            pass
    return fallback


def _retry_delay(attempt: int) -> float:
    # Persistent 406/429 responses should not hammer the arXiv endpoint.
    return min(30 * (2 ** min(attempt, 2)), 120)


def _is_retryable_http_status(status: int) -> bool:
    return status in (406, 408, 425, 429) or 500 <= status <= 599


def _stale_cache_info(cache_path: Path) -> str:
    if not cache_path.is_file():
        return ""
    day_path = cache_path.with_suffix(".day")
    cache_day = day_path.read_text(encoding="utf-8").strip() if day_path.is_file() else "unknown"
    return f"; stale cache dated {cache_day} was not used"


def fetch_arxiv(keyword: str, max_results: int = 200, start: int = 0, *, deadline: float | None = None) -> str:
    if deadline is None:
        deadline = time.monotonic() + FETCH_STAGE_TIMEOUT_SECONDS
    _remaining_time(deadline)
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

    last_error: Exception | None = None
    try:
        for attempt in range(ARXIV_MAX_ATTEMPTS):
            _remaining_time(deadline)
            _wait_for_arxiv_slot(deadline)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "PaperSurveyBot/1.0"})
                with _open_arxiv(req, timeout=min(ARXIV_REQUEST_TIMEOUT_SECONDS, _remaining_time(deadline))) as resp:
                    xml_text = resp.read().decode("utf-8")
                if ET.fromstring(xml_text).tag != "{http://www.w3.org/2005/Atom}feed":
                    raise ValueError("arXiv did not return an Atom feed")
                _remaining_time(deadline)
            except FetchDeadlineExceeded:
                raise
            except urllib.error.HTTPError as e:
                last_error = e
                if not _is_retryable_http_status(e.code):
                    raise RuntimeError(f"Non-retryable arXiv HTTP {e.code}: {e.reason}{_stale_cache_info(cache_path)}") from e
                retry_delay = _retry_after_seconds(e, _retry_delay(attempt)) if e.code == 429 else _retry_delay(attempt)
                print(f"  arXiv HTTP {e.code} (attempt {attempt + 1}/{ARXIV_MAX_ATTEMPTS}); retry in {retry_delay:g}s")
            except (urllib.error.URLError, OSError, UnicodeError, ET.ParseError, ValueError) as e:
                last_error = e
                retry_delay = _retry_delay(attempt)
                print(f"  arXiv request failed (attempt {attempt + 1}/{ARXIV_MAX_ATTEMPTS}): {type(e).__name__}: {e}; retry in {retry_delay:g}s")
            else:
                _write_arxiv_cache(cache_path, xml_text)
                return xml_text

            if attempt < ARXIV_MAX_ATTEMPTS - 1:
                _sleep_with_deadline(retry_delay, deadline)
    except FetchDeadlineExceeded as e:
        if last_error is not None:
            raise FetchDeadlineExceeded(
                f"{e}; last arXiv error: {type(last_error).__name__}: {last_error}"
                f"{_stale_cache_info(cache_path)}"
            ) from last_error
        raise

    # A successful exit suppresses run_daily.sh's manager alert. Leave existing
    # data intact and report failure when a fresh response cannot be obtained.
    raise RuntimeError(
        f"Failed to fetch arxiv after {ARXIV_MAX_ATTEMPTS} attempts: "
        f"{type(last_error).__name__}: {last_error}{_stale_cache_info(cache_path)}"
    ) from last_error


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


def fetch_topic(topic_name: str, config: dict, *, deadline: float | None = None):
    if deadline is None:
        deadline = time.monotonic() + FETCH_STAGE_TIMEOUT_SECONDS
    _remaining_time(deadline)
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
            _remaining_time(deadline)
            xml = fetch_arxiv(kw, max_results=100, start=start, deadline=deadline)
            papers = parse_entries(xml, cutoff)
            all_papers.extend(papers)
            print(f"    Page {start//100 + 1}: {len(papers)} papers in date range")
            # Category filtering can remove entries from an otherwise full page.
            entries = ET.fromstring(xml).findall("atom:entry", NS)
            if len(entries) < 100:
                break
            oldest = min(
                datetime.fromisoformat(entry.find("atom:published", NS).text.strip().replace("Z", "+00:00")).replace(tzinfo=None)
                for entry in entries
            )
            if oldest < cutoff:
                break
            _sleep_with_deadline(3, deadline)

    _remaining_time(deadline)
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
    deadline = time.monotonic() + FETCH_STAGE_TIMEOUT_SECONDS
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for topic_name, config in TOPICS.items():
        _remaining_time(deadline)
        fetch_topic(topic_name, config, deadline=deadline)
    _remaining_time(deadline)
    print("\nDone.")


if __name__ == "__main__":
    main()
