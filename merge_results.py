#!/usr/bin/env python3
"""Merge batch_new_results.json into papers.json."""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TOPIC = "world_model"


def main():
    results_path = DATA_DIR / TOPIC / "batch_new_results.json"
    if not results_path.exists():
        print("No batch_new_results.json found, skipping merge.")
        return

    with open(results_path, encoding="utf-8") as f:
        results = json.load(f)

    results_map = {r["arxiv_id"]: r for r in results}

    json_path = DATA_DIR / TOPIC / "papers.json"
    with open(json_path, encoding="utf-8") as f:
        papers = json.load(f)

    updated = 0
    for p in papers:
        r = results_map.get(p["arxiv_id"])
        if not r:
            continue
        if (r.get("tldr") or "").strip():
            p["tldr"] = r["tldr"].strip()
        rating = r.get("rating")
        if rating is not None and rating > 0:
            p["rating"] = rating
        if "relevance" in r and r["relevance"] is not None:
            p["relevance"] = r["relevance"]
        updated += 1

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    results_path.unlink()
    print(f"Merged {updated} results into papers.json")


if __name__ == "__main__":
    main()
