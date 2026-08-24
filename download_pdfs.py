#!/usr/bin/env python3
"""Download PDFs for papers, skipping already downloaded ones."""

import re
import time
import urllib.request
from pathlib import Path

from paper_store import load_papers
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TOPIC = "world_model"


def pdf_url_candidates(paper: dict) -> list[str]:
    urls = [paper["pdf_url"]]
    aid = paper["arxiv_id"]
    m = re.match(r"^(.+v)(\d+)$", aid)
    if m:
        base, version = m.group(1), int(m.group(2))
        for v in range(version - 1, 0, -1):
            urls.append(f"https://arxiv.org/pdf/{base}{v}")
    return urls


def download(paper: dict, pdf_dir: Path) -> tuple[str, str]:
    aid = paper["arxiv_id"]
    fname = aid.replace("/", "_").replace(".", "_") + ".pdf"
    fpath = pdf_dir / fname

    if fpath.exists() and fpath.stat().st_size > 1024:
        return aid, "skip"

    last_error = None
    for pdf_url in pdf_url_candidates(paper):
        try:
            req = urllib.request.Request(
                pdf_url,
                headers={"User-Agent": "PaperSurveyBot/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                fpath.write_bytes(resp.read())
            if fpath.stat().st_size < 1024:
                fpath.unlink()
                last_error = "too_small"
                continue
            return aid, "ok"
        except Exception as e:
            last_error = f"error: {e}"

    return aid, last_error or "error: unknown"


def main():
    from config import apply_proxy_env

    apply_proxy_env()
    json_path = DATA_DIR / TOPIC / "papers.json"
    if not json_path.exists():
        print("No papers.json found, run fetch_papers.py first")
        return

    papers = load_papers(json_path)

    pdf_dir = DATA_DIR / TOPIC / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    ok = skip = fail = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(download, p, pdf_dir): p for p in papers}
        for fut in as_completed(futures):
            aid, status = fut.result()
            if status == "ok":
                ok += 1
            elif status == "skip":
                skip += 1
            else:
                fail += 1
                print(f"  Failed: {aid} - {status}")
            time.sleep(0.3)

    print(f"PDFs: {ok} downloaded, {skip} skipped, {fail} failed (total {len(papers)})")


if __name__ == "__main__":
    main()
