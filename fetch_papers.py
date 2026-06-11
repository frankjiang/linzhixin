#!/usr/bin/env python3
"""Fetch recent papers from arxiv API for a given research topic."""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import csv
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ARXIV_API = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

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
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PaperSurveyBot/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
            else:
                raise RuntimeError(f"Failed to fetch arxiv after 3 attempts: {e}")


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
        with open(json_path) as f:
            existing = json.load(f)

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

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

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
