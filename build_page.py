#!/usr/bin/env python3
"""Build a self-contained index.html from paper data."""

import json
from datetime import datetime
from pathlib import Path

from config import load_config, topic_name

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
NOTES_DIR = BASE_DIR / "notes"


def load_papers(topic: str) -> list[dict]:
    json_path = DATA_DIR / topic / "papers.json"
    if not json_path.exists():
        return []
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def load_notes(topic: str) -> dict[str, str]:
    notes = {}
    notes_path = NOTES_DIR / topic
    if not notes_path.exists():
        return notes
    for md_file in notes_path.glob("*.md"):
        arxiv_id = md_file.stem.replace("_", ".")
        notes[arxiv_id] = md_file.read_text(encoding="utf-8")
    return notes


def build_html(
    papers: list[dict],
    notes: dict[str, str],
    *,
    site_name: str,
    site_tagline: str,
    topic_display: str,
    github_url: str,
) -> str:
    papers_json = json.dumps(papers, ensure_ascii=False)
    notes_json = json.dumps(notes, ensure_ascii=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    github_link = (
        f'<a class="gh-link" href="{github_url}" target="_blank" rel="noopener" '
        f'title="GitHub">'
        f'<svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true">'
        f'<path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 '
        f'0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 '
        f'1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 '
        f'1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>'
        f"</svg></a>"
        if github_url
        else ""
    )

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{site_name} — {site_tagline}">
<title>{site_name} · {topic_display}</title>
<style>
:root {{
  --bg: #ffffff;
  --bg-muted: #f6f8fa;
  --card-bg: #ffffff;
  --text: #1f2328;
  --text2: #656d76;
  --border: #d0d7de;
  --border-muted: #d8dee4;
  --accent: #0969da;
  --accent-hover: #0550ae;
  --accent-subtle: #ddf4ff;
  --tag-bg: #f6f8fa;
  --star: #bf8700;
  --shadow: none;
  --header-bg: #ffffff;
  --focus-ring: rgba(9, 105, 218, 0.3);
  --highlight-border: #0969da;
}}
[data-theme="dark"] {{
  --bg: #0d1117;
  --bg-muted: #010409;
  --card-bg: #0d1117;
  --text: #e6edf3;
  --text2: #8b949e;
  --border: #30363d;
  --border-muted: #21262d;
  --accent: #4493f8;
  --accent-hover: #79c0ff;
  --accent-subtle: #13253c;
  --tag-bg: #161b22;
  --star: #d29922;
  --header-bg: #0d1117;
  --focus-ring: rgba(68, 147, 248, 0.35);
  --highlight-border: #4493f8;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
  background: var(--bg-muted);
  color: var(--text);
  line-height: 1.5;
  min-height: 100vh;
}}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; color: var(--accent-hover); }}

.site-header {{
  background: var(--header-bg);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
}}
.site-header-inner {{
  max-width: 1012px;
  margin: 0 auto;
  padding: 16px 16px 0;
}}
.brand-row {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}}
.brand {{
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}}
.brand-mark {{
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: var(--accent-subtle);
  color: var(--accent);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  font-weight: 700;
  flex-shrink: 0;
}}
.brand-text h1 {{
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.25;
  color: var(--text);
}}
.brand-text .tagline {{
  font-size: 0.875rem;
  color: var(--text2);
  margin-top: 2px;
}}
.brand-text .meta {{
  font-size: 0.75rem;
  color: var(--text2);
  margin-top: 6px;
}}
.brand-text .meta strong {{
  color: var(--text);
  font-weight: 600;
}}
.header-actions {{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}}
.gh-link, .theme-toggle {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--text2);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}}
.gh-link:hover, .theme-toggle:hover {{
  background: var(--bg-muted);
  border-color: var(--border-muted);
  color: var(--text);
  text-decoration: none;
}}
.toolbar {{
  max-width: 1012px;
  margin: 0 auto;
  padding: 12px 16px 16px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  border-top: 1px solid var(--border);
  background: var(--bg-muted);
}}
.search-box {{
  flex: 1;
  min-width: 220px;
  position: relative;
}}
.search-box input {{
  width: 100%;
  padding: 5px 12px 5px 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--text);
  font-size: 0.875rem;
  outline: none;
  box-shadow: inset 0 1px 0 rgba(31,35,40,0.04);
}}
.search-box input:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}}
.search-icon {{
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text2);
  font-size: 0.8rem;
  pointer-events: none;
}}
.filter-label {{
  font-size: 0.75rem;
  color: var(--text2);
  white-space: nowrap;
}}
.btn-group {{
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--card-bg);
}}
.btn-group button {{
  padding: 5px 10px;
  border: none;
  border-right: 1px solid var(--border);
  background: transparent;
  color: var(--text2);
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}}
.btn-group button:last-child {{ border-right: none; }}
.btn-group button.active {{
  background: var(--accent-subtle);
  color: var(--accent);
}}
.btn-group button:hover:not(.active) {{
  background: var(--bg-muted);
  color: var(--text);
}}
.stats {{
  font-size: 0.75rem;
  color: var(--text2);
  white-space: nowrap;
  margin-left: auto;
}}

.page-body {{
  max-width: 1012px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}}
.section-title {{
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.section-title .count {{
  display: inline-flex;
  align-items: center;
  padding: 0 7px;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text2);
  background: var(--tag-bg);
  border: 1px solid var(--border);
  border-radius: 2em;
}}
.paper-list {{
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--card-bg);
}}
.paper-card {{
  padding: 16px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
}}
.paper-card:last-child {{ border-bottom: none; }}
.paper-card:hover {{ background: var(--bg-muted); }}
.paper-card.expanded {{ background: var(--bg-muted); }}
.paper-card.highlighted {{
  box-shadow: inset 3px 0 0 var(--highlight-border);
  background: var(--accent-subtle);
}}
.paper-header {{
  display: flex;
  gap: 12px;
  align-items: flex-start;
}}
.rating-badge {{
  flex-shrink: 0;
  min-width: 28px;
  height: 22px;
  padding: 0 6px;
  border-radius: 2em;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 600;
  border: 1px solid transparent;
}}
.rating-0 {{ background: var(--tag-bg); color: var(--text2); border-color: var(--border); }}
.rating-1 {{ background: #f6f8fa; color: #656d76; border-color: #d0d7de; }}
.rating-2 {{ background: #dafbe1; color: #1a7f37; border-color: #aceebb; }}
.rating-3 {{ background: #fff8c5; color: #9a6700; border-color: #fae17d; }}
.rating-4 {{ background: #ffebe9; color: #cf222e; border-color: #ffcecb; }}
.rating-5 {{ background: #fbefff; color: #8250df; border-color: #e6d5f8; }}
[data-theme="dark"] .rating-1 {{ background: #161b22; color: #8b949e; border-color: #30363d; }}
[data-theme="dark"] .rating-2 {{ background: #12261e; color: #3fb950; border-color: #1f3d2f; }}
[data-theme="dark"] .rating-3 {{ background: #2a1f00; color: #d29922; border-color: #4a3800; }}
[data-theme="dark"] .rating-4 {{ background: #2d1114; color: #ff7b72; border-color: #5c1f24; }}
[data-theme="dark"] .rating-5 {{ background: #271052; color: #d2a8ff; border-color: #4a2f7a; }}
.paper-info {{ flex: 1; min-width: 0; }}
.paper-title {{
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--accent);
  line-height: 1.4;
  margin-bottom: 6px;
}}
.paper-card:hover .paper-title {{ text-decoration: underline; }}
.paper-meta {{
  font-size: 0.75rem;
  color: var(--text2);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}}
.paper-date, .cat-tag {{
  display: inline-flex;
  align-items: center;
  padding: 0 7px;
  border-radius: 2em;
  font-size: 0.7rem;
  font-weight: 500;
  border: 1px solid var(--border);
  background: var(--tag-bg);
  color: var(--text2);
}}
.cat-tag {{ color: var(--accent); background: var(--accent-subtle); border-color: transparent; }}
.paper-authors {{
  font-size: 0.8rem;
  color: var(--text2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.paper-affil {{
  font-size: 0.75rem;
  color: var(--text2);
  margin-top: 4px;
}}
.paper-tldr {{
  font-size: 0.8125rem;
  color: var(--text);
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--bg-muted);
  border: 1px solid var(--border);
  border-radius: 6px;
}}
.paper-abstract-preview {{
  font-size: 0.8125rem;
  color: var(--text2);
  margin-top: 8px;
  line-height: 1.5;
}}
.paper-expand {{
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
}}
.paper-card.expanded .paper-expand {{
  max-height: 5000px;
}}
.paper-abstract {{
  margin-top: 12px;
  padding: 12px;
  background: var(--bg-muted);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.8125rem;
  line-height: 1.6;
}}
.paper-abstract-label {{
  font-weight: 600;
  font-size: 0.75rem;
  color: var(--text2);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}
.paper-links {{
  margin-top: 10px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}}
.paper-links a {{
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text);
  text-decoration: none;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card-bg);
}}
.paper-links a:hover {{
  background: var(--bg-muted);
  border-color: var(--border-muted);
  text-decoration: none;
}}
.paper-note {{
  margin-top: 12px;
  padding: 12px 14px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.8125rem;
  line-height: 1.7;
}}
.paper-note h1, .paper-note h2, .paper-note h3 {{
  margin-top: 12px;
  margin-bottom: 6px;
  font-size: 0.9rem;
  color: var(--text);
}}
.paper-note p {{ margin-bottom: 6px; }}
.paper-note ul, .paper-note ol {{ padding-left: 1.25rem; margin-bottom: 6px; }}
.rel-tag {{
  display: inline-flex;
  align-items: center;
  padding: 0 7px;
  border-radius: 2em;
  font-size: 0.7rem;
  font-weight: 600;
  border: 1px solid transparent;
}}
.rel-3 {{ background: var(--accent-subtle); color: var(--accent); }}
.rel-2 {{ background: #dafbe1; color: #1a7f37; }}
.rel-1 {{ background: #fff8c5; color: #9a6700; }}
.rel-0 {{ background: var(--tag-bg); color: var(--text2); border-color: var(--border); }}
[data-theme="dark"] .rel-2 {{ background: #12261e; color: #3fb950; }}
[data-theme="dark"] .rel-1 {{ background: #2a1f00; color: #d29922; }}
.empty-state {{
  text-align: center;
  padding: 48px 16px;
  color: var(--text2);
  border: 1px dashed var(--border);
  border-radius: 6px;
  background: var(--card-bg);
}}
.empty-state h2 {{ font-size: 1rem; margin-bottom: 6px; color: var(--text); }}
.site-footer {{
  max-width: 1012px;
  margin: 0 auto;
  padding: 24px 16px 32px;
  border-top: 1px solid var(--border);
  color: var(--text2);
  font-size: 0.75rem;
  text-align: center;
}}
.site-footer strong {{ color: var(--text); }}
@media (max-width: 768px) {{
  .brand-row {{ flex-direction: column; }}
  .header-actions {{ align-self: flex-end; }}
  .toolbar {{ padding: 12px; }}
  .stats {{ margin-left: 0; width: 100%; }}
  .paper-header {{ flex-direction: column; }}
}}
</style>
</head>
<body>
<header class="site-header">
  <div class="site-header-inner">
    <div class="brand-row">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">知</div>
        <div class="brand-text">
          <h1>{site_name}</h1>
          <div class="tagline">{site_tagline}</div>
          <div class="meta">
            追踪方向 <strong>{topic_display}</strong>
            &middot; 更新于 {now}
            &middot; <span id="paperCount">0</span> 篇论文
          </div>
        </div>
      </div>
      <div class="header-actions">
        {github_link}
        <button class="theme-toggle" onclick="toggleTheme()" title="切换主题" aria-label="切换主题">&#9789;</button>
      </div>
    </div>
  </div>
  <div class="toolbar">
    <div class="search-box">
      <span class="search-icon" aria-hidden="true">&#128269;</span>
      <input type="text" id="searchInput" placeholder="搜索标题、作者、机构、摘要…" oninput="filterPapers()">
    </div>
    <span class="filter-label">排序</span>
    <div class="btn-group" id="sortGroup">
      <button class="active" data-sort="date" onclick="setSort('date')">最新</button>
      <button data-sort="relevance" onclick="setSort('relevance')">相关度</button>
      <button data-sort="rating" onclick="setSort('rating')">评分</button>
    </div>
    <span class="filter-label">相关度</span>
    <div class="btn-group" id="relGroup">
      <button class="active" data-rel="0" onclick="setRelFilter(0)">全部</button>
      <button data-rel="1" onclick="setRelFilter(1)">1+</button>
      <button data-rel="2" onclick="setRelFilter(2)">2+</button>
      <button data-rel="3" onclick="setRelFilter(3)">核心</button>
    </div>
    <span class="filter-label">评分</span>
    <div class="btn-group" id="filterGroup">
      <button class="active" data-filter="0" onclick="setFilter(0)">全部</button>
      <button data-filter="2" onclick="setFilter(2)">2+</button>
      <button data-filter="3" onclick="setFilter(3)">3+</button>
      <button data-filter="4" onclick="setFilter(4)">4+</button>
    </div>
    <div class="stats" id="statsInfo"></div>
  </div>
</header>

<main class="page-body">
  <div class="section-title">
    论文列表 <span class="count" id="visibleCount">0</span>
  </div>
  <div class="paper-list" id="paperList"></div>
  <div class="empty-state" id="emptyState" style="display:none">
    <h2>没有找到匹配的论文</h2>
    <p>试试调整搜索词或筛选条件</p>
  </div>
</main>

<footer class="site-footer">
  <strong>{site_name}</strong> &middot; 数据来自 arXiv &middot; 由 Agent 每日自动更新
</footer>

<script>
const PAPERS = {papers_json};
const NOTES = {notes_json};

let currentSort = 'date';
let currentFilter = 0;
let currentRelFilter = 0;
let currentSearch = '';

const REL_LABELS = ['Noise', 'Tangential', 'Related', 'Core'];

function toggleTheme() {{
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  document.querySelector('.theme-toggle').textContent = next === 'dark' ? '\\u2600' : '\\u263D';
}}

(function() {{
  const saved = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', saved);
  document.querySelector('.theme-toggle').textContent = saved === 'dark' ? '\\u2600' : '\\u263D';
}})();

function setSort(sort) {{
  currentSort = sort;
  document.querySelectorAll('#sortGroup button').forEach(b => b.classList.toggle('active', b.dataset.sort === sort));
  renderPapers();
}}

function setFilter(min) {{
  currentFilter = min;
  document.querySelectorAll('#filterGroup button').forEach(b => b.classList.toggle('active', parseInt(b.dataset.filter) === min));
  renderPapers();
}}

function setRelFilter(min) {{
  currentRelFilter = min;
  document.querySelectorAll('#relGroup button').forEach(b => b.classList.toggle('active', parseInt(b.dataset.rel) === min));
  renderPapers();
}}

function filterPapers() {{
  currentSearch = document.getElementById('searchInput').value.toLowerCase();
  renderPapers();
}}

function getPaperFromUrl() {{
  const params = new URLSearchParams(location.search);
  const fromQuery = params.get('paper');
  if (fromQuery) return fromQuery;
  const hash = location.hash.replace(/^#/, '');
  if (hash.startsWith('paper=')) return decodeURIComponent(hash.slice(6));
  if (hash) return decodeURIComponent(hash);
  return null;
}}

function focusPaper(arxivId) {{
  document.querySelectorAll('.paper-card.highlighted').forEach(el => el.classList.remove('highlighted'));
  const el = document.querySelector(`.paper-card[data-arxiv-id="${{arxivId}}"]`);
  if (!el) return false;
  el.classList.add('expanded', 'highlighted');
  requestAnimationFrame(() => {{
    el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }});
  return true;
}}

function resetFiltersForDeepLink() {{
  currentFilter = 0;
  currentRelFilter = 0;
  currentSearch = '';
  document.getElementById('searchInput').value = '';
  document.querySelectorAll('#filterGroup button').forEach(b => {{
    b.classList.toggle('active', parseInt(b.dataset.filter) === 0);
  }});
  document.querySelectorAll('#relGroup button').forEach(b => {{
    b.classList.toggle('active', parseInt(b.dataset.rel) === 0);
  }});
}}

function openPaperFromUrl() {{
  const arxivId = getPaperFromUrl();
  if (!arxivId) return;
  if (focusPaper(arxivId)) return;
  resetFiltersForDeepLink();
  renderPapers();
  focusPaper(arxivId);
}}

function getStars(rating) {{
  if (!rating) return '-';
  return '\\u2B50'.repeat(rating);
}}

function mdToHtml(md) {{
  if (!md) return '';
  let h = md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
    .replace(/\\*(.+?)\\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\\/li>)/s, '<ul>$1</ul>')
    .replace(/\\n\\n/g, '</p><p>')
    .replace(/\\n/g, '<br>');
  return '<p>' + h + '</p>';
}}

function renderPapers() {{
  let papers = [...PAPERS];

  if (currentFilter > 0) {{
    papers = papers.filter(p => (p.rating || 0) >= currentFilter);
  }}

  if (currentRelFilter > 0) {{
    papers = papers.filter(p => (p.relevance || 0) >= currentRelFilter);
  }}

  if (currentSearch) {{
    const q = currentSearch;
    papers = papers.filter(p => {{
      const searchable = [
        p.title, p.abstract,
        (p.authors || []).join(' '),
        (p.affiliations || []).join(' '),
        p.tldr || ''
      ].join(' ').toLowerCase();
      return searchable.includes(q);
    }});
  }}

  if (currentSort === 'date') {{
    papers.sort((a, b) => b.date.localeCompare(a.date));
  }} else if (currentSort === 'relevance') {{
    papers.sort((a, b) => (b.relevance || 0) - (a.relevance || 0) || b.date.localeCompare(a.date));
  }} else {{
    papers.sort((a, b) => (b.rating || 0) - (a.rating || 0) || b.date.localeCompare(a.date));
  }}

  document.getElementById('paperCount').textContent = PAPERS.length;
  document.getElementById('visibleCount').textContent = papers.length;
  document.getElementById('statsInfo').textContent = papers.length === PAPERS.length
    ? '' : `显示 ${{papers.length}} / ${{PAPERS.length}}`;

  const list = document.getElementById('paperList');
  const empty = document.getElementById('emptyState');

  if (papers.length === 0) {{
    list.innerHTML = '';
    list.style.display = 'none';
    empty.style.display = 'block';
    return;
  }}
  list.style.display = 'flex';
  empty.style.display = 'none';

  const deepLinkId = getPaperFromUrl();
  list.innerHTML = papers.map((p) => {{
    const cats = (p.categories || []).slice(0, 4).map(c => `<span class="cat-tag">${{esc(c)}}</span>`).join('');
    const authors = esc((p.authors || []).slice(0, 5).join(', ') + (p.authors && p.authors.length > 5 ? ' et al.' : ''));
    const ratingClass = 'rating-' + (p.rating || 0);
    const ratingText = getStars(p.rating);
    const rel = p.relevance || 0;
    const relTag = `<span class="rel-tag rel-${{rel}}">${{REL_LABELS[rel]}}</span>`;
    const affil = (p.affiliations || []).length > 0
      ? `<div class="paper-affil">${{esc(p.affiliations.join(' · '))}}</div>` : '';
    const summary = p.tldr
      ? `<div class="paper-tldr">${{esc(p.tldr)}}</div>`
      : `<div class="paper-abstract-preview">${{esc(p.abstract.substring(0, 200) + (p.abstract.length > 200 ? '...' : ''))}}</div>`;
    const note = NOTES[p.arxiv_id] ? `<div class="paper-note">${{mdToHtml(NOTES[p.arxiv_id])}}</div>` : '';
    const highlighted = deepLinkId === p.arxiv_id ? ' highlighted expanded' : '';

    return `<div class="paper-card${{highlighted}}" data-arxiv-id="${{esc(p.arxiv_id)}}" onclick="this.classList.toggle('expanded')">
      <div class="paper-header">
        <div class="rating-badge ${{ratingClass}}">${{ratingText}}</div>
        <div class="paper-info">
          <div class="paper-title">${{esc(p.title)}}</div>
          <div class="paper-meta">
            <span class="paper-date">${{p.date}}</span>
            ${{relTag}}
            <div class="paper-cats">${{cats}}</div>
          </div>
          <div class="paper-authors">${{authors}}</div>
          ${{affil}}
          ${{summary}}
        </div>
      </div>
      <div class="paper-expand">
        <div class="paper-abstract">
          <div class="paper-abstract-label">Abstract</div>
          ${{esc(p.abstract)}}
        </div>
        ${{note}}
        <div class="paper-links">
          <a href="${{esc(p.url)}}" target="_blank" rel="noopener" onclick="event.stopPropagation()">arXiv</a>
          <a href="${{esc(p.pdf_url)}}" target="_blank" rel="noopener" onclick="event.stopPropagation()">PDF</a>
        </div>
      </div>
    </div>`;
  }}).join('');
}}

function esc(s) {{
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}}

document.addEventListener('keydown', e => {{
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {{
    e.preventDefault();
    document.getElementById('searchInput').focus();
  }}
  if (e.key === 'Escape') {{
    document.getElementById('searchInput').blur();
    document.getElementById('searchInput').value = '';
    currentSearch = '';
    renderPapers();
  }}
}});

renderPapers();
openPaperFromUrl();
</script>
</body>
</html>'''


def write_output(html: str, output_dir: str) -> Path:
    out_dir = BASE_DIR / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").touch()
    return out_path


def main():
    cfg = load_config()
    site = cfg.get("site", {})
    topic_cfg = cfg.get("topic", {})
    gh_pages = cfg.get("github_pages", {})

    topic = topic_name(cfg)
    papers = load_papers(topic)
    notes = load_notes(topic)
    print(f"Loaded {len(papers)} papers, {len(notes)} notes")

    html = build_html(
        papers,
        notes,
        site_name=site.get("name", "林知新"),
        site_tagline=site.get("tagline", "一位帮你读 Paper 的 Agent."),
        topic_display=topic_cfg.get("display_name", "World Model"),
        github_url=site.get("github_url", ""),
    )

    output_dir = gh_pages.get("output_dir", "docs")
    out_path = write_output(html, output_dir)
    print(f"Built: {out_path}")


if __name__ == "__main__":
    main()
