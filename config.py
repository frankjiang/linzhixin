#!/usr/bin/env python3
"""Load project configuration from config.json with environment overrides."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
EXAMPLE_PATH = BASE_DIR / "config.example.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "proxy": {
        "http": "http://127.0.0.1:7892",
        "https": "http://127.0.0.1:7892",
        "all": "socks5://127.0.0.1:7892",
        "no_proxy": "localhost,127.0.0.1,::1",
    },
    "paths": {
        "home": "/home/frank.jf",
        "project_root": str(BASE_DIR),
        "codex_bin_dirs": [
            "/home/frank.jf/.local/bin",
            "/home/frank.jf/anaconda3/bin",
            "/home/frank.jf/.nvm/versions/node/v18.20.8/bin",
        ],
    },
    "dingtalk": {
        "enabled": False,
        "webhook": "",
        "secret": "",
        "min_rating": 4,
        "survey_url": "http://127.0.0.1:7777",
    },
    "server": {
        "host": "0.0.0.0",
        "port": 7777,
        "static_dir": "docs",
    },
    "topic": {
        "name": "world_model",
        "display_name": "World Model",
    },
    "site": {
        "name": "林知新",
        "tagline": "一位帮你读 Paper 的 Agent.",
        "github_url": "",
        "public_url": "",
    },
    "github_pages": {
        "output_dir": "docs",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            file_cfg = json.load(f)
        if isinstance(file_cfg, dict):
            cfg = _deep_merge(cfg, file_cfg)

    proxy = cfg.setdefault("proxy", {})
    proxy["http"] = os.getenv("HTTP_PROXY", proxy.get("http", ""))
    proxy["https"] = os.getenv("HTTPS_PROXY", proxy.get("https", ""))
    proxy["all"] = os.getenv("ALL_PROXY", proxy.get("all", ""))
    proxy["no_proxy"] = os.getenv("NO_PROXY", proxy.get("no_proxy", ""))

    dingtalk = cfg.setdefault("dingtalk", {})
    dingtalk["webhook"] = os.getenv("DINGTALK_WEBHOOK", dingtalk.get("webhook", ""))
    dingtalk["secret"] = os.getenv("DINGTALK_SECRET", dingtalk.get("secret", ""))
    if os.getenv("DINGTALK_ENABLED") is not None:
        dingtalk["enabled"] = os.getenv("DINGTALK_ENABLED", "").lower() in {"1", "true", "yes"}

    server = cfg.setdefault("server", {})
    if os.getenv("PAPER_SURVEY_PORT"):
        server["port"] = int(os.getenv("PAPER_SURVEY_PORT", "7777"))
    if os.getenv("PAPER_SURVEY_HOST"):
        server["host"] = os.getenv("PAPER_SURVEY_HOST")

    return cfg


def apply_proxy_env(cfg: dict[str, Any] | None = None) -> None:
    cfg = cfg or load_config()
    proxy = cfg.get("proxy", {})
    for key in ("http", "https", "all", "no_proxy"):
        value = proxy.get(key, "")
        if not value:
            continue
        env_key = "NO_PROXY" if key == "no_proxy" else key.upper()
        os.environ[env_key] = value
        if key != "no_proxy":
            os.environ[env_key.lower()] = value
        else:
            os.environ["no_proxy"] = value


def shell_exports(cfg: dict[str, Any] | None = None) -> str:
    """Emit shell export statements for bash eval."""
    cfg = cfg or load_config()
    lines: list[str] = []

    paths = cfg.get("paths", {})
    home = paths.get("home")
    if home:
        lines.append(f'export HOME="{home}"')

    codex_dirs = paths.get("codex_bin_dirs", [])
    if codex_dirs:
        joined = ":".join(codex_dirs)
        lines.append(f'export PATH="{joined}:$PATH"')

    proxy = cfg.get("proxy", {})
    mapping = {
        "HTTP_PROXY": proxy.get("http", ""),
        "HTTPS_PROXY": proxy.get("https", ""),
        "ALL_PROXY": proxy.get("all", ""),
        "NO_PROXY": proxy.get("no_proxy", ""),
    }
    for env_key, value in mapping.items():
        if value:
            lines.append(f'export {env_key}="{value}"')
            lower = env_key.lower()
            if lower != env_key:
                lines.append(f'export {lower}="{value}"')

    return "\n".join(lines)


def topic_name(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    topic = cfg.get("topic", {})
    if isinstance(topic, dict):
        return topic.get("name", "world_model")
    return str(topic or "world_model")
