#!/usr/bin/env python3
"""Crash-safe storage for the canonical papers.json dataset."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def backup_path(path: Path) -> Path:
    return Path(f"{path}.bak")


def _read_valid(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        papers = json.load(stream)
    if not isinstance(papers, list):
        raise ValueError(f"expected a JSON list in {path}")
    if any(not isinstance(paper, dict) or not paper.get("arxiv_id") for paper in papers):
        raise ValueError(f"invalid paper record in {path}")
    return papers


def load_papers(path: Path) -> list[dict]:
    """Load the primary dataset, falling back to its last valid backup."""
    path = Path(path)
    primary_error: Exception | None = None
    try:
        return _read_valid(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        primary_error = error

    backup = backup_path(path)
    try:
        papers = _read_valid(backup)
    except (OSError, ValueError, json.JSONDecodeError) as backup_error:
        raise RuntimeError(
            f"{path} is invalid and no valid backup is available "
            f"(primary: {primary_error}; backup: {backup_error})"
        ) from primary_error

    print(f"WARNING: {path} is invalid; using backup {backup}")
    return papers


def _prepare_json(path: Path, papers: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(papers, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        _read_valid(temp_path)
        return temp_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _replace_prepared(temp_path: Path, destination: Path) -> None:
    os.replace(temp_path, destination)
    directory_fd = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def save_papers(path: Path, papers: list[dict]) -> None:
    """Atomically replace papers.json and retain its last valid version."""
    path = Path(path)
    old_papers: list[dict] | None = None
    if path.exists():
        try:
            old_papers = _read_valid(path)
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    new_temp = _prepare_json(path, papers)
    try:
        if old_papers is not None:
            backup = backup_path(path)
            backup_temp = _prepare_json(backup, old_papers)
            try:
                _replace_prepared(backup_temp, backup)
            finally:
                backup_temp.unlink(missing_ok=True)
        _replace_prepared(new_temp, path)
    finally:
        new_temp.unlink(missing_ok=True)
