#!/usr/bin/env python3
"""Extract author affiliations from PDF first pages."""

import re
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from paper_store import load_papers, save_papers

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TOPIC = "world_model"

INSTITUTION_PATTERNS = [
    r"University|Universidad|Universit[àäé]|Universiteit",
    r"Institute|Institut[eo]?",
    r"Laboratory|Lab(?:\b|oratory)",
    r"College",
    r"School of",
    r"Department of|Dept\.?\s+of",
    r"Microsoft|Google|Meta|NVIDIA|Apple|Amazon|Adobe|Baidu|Tencent|Alibaba|ByteDance|Huawei",
    r"DeepMind|OpenAI|Anthropic|FAIR|Brain",
    r"MIT\b|Stanford|Berkeley|CMU|ETH|Oxford|Cambridge|Princeton|Harvard|Caltech",
    r"Tsinghua|Peking|Zhejiang|Fudan|SJTU|NUS|KAIST|KAUST",
    r"INRIA|CNRS|Max Planck|Fraunhofer",
    r"Inc\.|Ltd\.|Corp\.|LLC",
    r"Research Center|Centre",
]

NOISE_PATTERNS = [
    r"^https?://",
    r"^arXiv:",
    r"^\d{4}\.\d{4,5}",
    r"^Abstract",
    r"^Keywords?:",
    r"^Figure\s+\d",
    r"^Table\s+\d",
    r"^\d+$",
]

INSTITUTION_RE = re.compile("|".join(INSTITUTION_PATTERNS), re.IGNORECASE)
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


def extract_first_page(pdf_path: Path) -> str:
    try:
        result = subprocess.run(
            ["pdftotext", "-l", "1", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout
    except Exception:
        return ""


def find_affiliations(text: str, title: str) -> list[str]:
    lines = text.split("\n")

    title_lower = title.lower()
    title_words = set(title_lower.split())

    abstract_idx = len(lines)
    for i, line in enumerate(lines):
        if re.match(r"^\s*(Abstract|ABSTRACT)\b", line):
            abstract_idx = i
            break

    title_end = 0
    for i, line in enumerate(lines[:min(20, abstract_idx)]):
        line_lower = line.strip().lower()
        overlap = sum(1 for w in line_lower.split() if w in title_words)
        if overlap >= 3 or (len(line_lower) > 10 and line_lower in title_lower):
            title_end = i + 1

    candidate_lines = lines[title_end:abstract_idx]

    affiliations = set()
    for line in candidate_lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
        if NOISE_RE.search(line):
            continue
        if INSTITUTION_RE.search(line):
            cleaned = re.sub(r"^[\d\*†‡§¶\s,;]+", "", line).strip()
            cleaned = re.sub(r"[\{\}\[\]†‡§¶\*]", "", cleaned).strip()
            cleaned = re.sub(r"^\d+\s*", "", cleaned).strip()
            if len(cleaned) > 3 and len(cleaned) < 200:
                affiliations.add(cleaned)

    return sorted(affiliations)


def process_paper(paper: dict) -> tuple[str, list[str]]:
    aid = paper["arxiv_id"]
    fname = aid.replace("/", "_").replace(".", "_") + ".pdf"
    pdf_path = DATA_DIR / TOPIC / "pdfs" / fname

    if not pdf_path.exists():
        return aid, []

    text = extract_first_page(pdf_path)
    if not text:
        return aid, []

    affils = find_affiliations(text, paper["title"])
    return aid, affils


def main():
    json_path = DATA_DIR / TOPIC / "papers.json"
    papers = load_papers(json_path)

    print(f"Extracting affiliations for {len(papers)} papers...")

    results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(process_paper, p): p for p in papers}
        for fut in futures:
            aid, affils = fut.result()
            results[aid] = affils

    updated = 0
    for p in papers:
        if not p.get("affiliations") and results.get(p["arxiv_id"]):
            p["affiliations"] = results[p["arxiv_id"]]
            updated += 1

    save_papers(json_path, papers)

    has_affil = sum(1 for p in papers if p.get("affiliations"))
    print(f"Updated {updated} papers, {has_affil}/{len(papers)} have affiliations")


if __name__ == "__main__":
    main()
