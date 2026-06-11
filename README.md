# 林知新

> 一位帮你读 Paper 的 Agent。

林知新是一个自动化的 arXiv 论文追踪与阅读助手。它每天从 arXiv 抓取与你研究方向相关的论文，下载 PDF、提取机构信息，调用 Codex 生成中文笔记与评分，并发布为可浏览的静态页面。发现 4 星及以上高价值论文时，还会通过钉钉机器人推送摘要。

当前追踪方向：**World Model**（视频世界模型、3D 世界模型、隐式世界模型等）。

在线演示：[https://frankjiang.github.io/linzhixin/](https://frankjiang.github.io/linzhixin/)

项目地址：[https://github.com/frankjiang/linzhixin](https://github.com/frankjiang/linzhixin)

## 功能

- **每日自动抓取**：从 arXiv 检索近期论文，去重合并
- **PDF 增量下载**：支持版本回退（v2 不可用时尝试 v1）
- **机构提取**：从 PDF 首屏提取作者单位
- **Agent 读论文**：Codex 阅读 PDF，生成结构化中文笔记（Insight / Method / Experiment / TL;DR 等）
- **评分与筛选**：创新度 1–5 星、相关度 0–3 级，支持搜索与多维排序
- **查漏补缺**：缺笔记、缺评分、缺 TL;DR 的论文会自动重新进入处理队列
- **钉钉推送**：本次批次中 ≥4 星的论文，推送 Markdown 摘要（含「快速阅读」深链接）
- **深链接**：`?paper=2606.12403v1` 可直达某篇论文并展开详情

## 架构

```
run_daily.sh
  ├─ fetch_papers.py        # 抓取 arXiv
  ├─ download_pdfs.py       # 下载 PDF
  ├─ extract_affiliations.py
  ├─ generate_notes.py      # 生成待处理批次
  ├─ codex exec             # Agent 读论文、写笔记
  ├─ merge_results.py       # 合并评分到 papers.json
  ├─ sync_from_notes.py     # 从笔记回填元数据
  ├─ build_page.py          # 构建静态页面
  └─ notify_dingtalk.py     # 钉钉推送高星论文
```

## 快速开始

### 1. 配置

```bash
cp config.example.json config.json
```

编辑 `config.json`，至少配置：

| 配置项 | 说明 |
|--------|------|
| `proxy.*` | 访问 arXiv 所需的代理（如不需要可留空） |
| `paths.*` | 本机路径、Codex 可执行文件 PATH |
| `dingtalk.webhook` / `secret` | 钉钉自定义机器人（加签） |
| `dingtalk.enabled` | 是否启用推送 |
| `site.public_url` | 对外访问地址（GitHub Pages URL 或内网地址） |
| `site.github_url` | 仓库链接（显示在页面右上角） |

敏感信息仅保存在 `config.json`，该文件已加入 `.gitignore`。

### 2. 手动运行

```bash
# 完整日报流程
bash run_daily.sh

# 仅重建页面
python3 build_page.py

# 本地预览
python3 server.py
# 打开 http://127.0.0.1:7777
```

### 3. 定时任务

```cron
0 0 * * * /path/to/paper-survey/run_daily.sh
```

每次日报完成后，`run_daily.sh` 会自动将 `docs/`、`notes/` 的变更提交到 git（commit message 为 `daily update: YYYY-MM-DD`）。`config.json`、`data/`、`logs/` 不会入库。如需同步到 GitHub Pages，请另行配置 `git push`（例如在 cron 末尾追加推送，或由 CI 触发）。

## GitHub Pages 部署

`build_page.py` 输出到 `docs/`（同时生成 `.nojekyll` 以跳过 Jekyll 处理），本地预览与 GitHub Pages 共用同一目录。

**步骤：**

1. 运行 `python3 build_page.py` 生成最新页面
2. 将 `docs/` 目录提交到仓库
3. 在 GitHub 仓库 **Settings → Pages** 中：
   - Source: **Deploy from a branch**
   - Branch: `main`（或你的默认分支）
   - Folder: **`/docs`**
4. 在 `config.json` 中设置 `site.public_url` 为 Pages 地址，例如：
   ```json
   "public_url": "https://frankjiang.github.io/linzhixin/"
   ```
5. 钉钉「快速阅读」链接将指向 `?paper=<arxiv_id>` 深链接

页面采用 GitHub 风格设计：浅色/深色主题、issue 列表式论文卡片、圆角标签与分段工具栏，适合静态托管。

## 项目结构

```
├── run_daily.sh           # 日报入口
├── config.json            # 本地配置（不入库）
├── config.example.json    # 配置示例
├── fetch_papers.py
├── download_pdfs.py
├── extract_affiliations.py
├── generate_notes.py
├── merge_results.py
├── sync_from_notes.py
├── build_page.py
├── notify_dingtalk.py
├── server.py              # 本地 HTTP 服务
├── data/world_model/      # 论文数据（不入库）
├── notes/world_model/     # Agent 生成的 Markdown 笔记
└── docs/index.html        # 静态站点（本地预览 + GitHub Pages）
```

## 笔记格式

每篇论文的笔记保存在 `notes/world_model/<arxiv_id>.md`，包含：

- Insight / Motivation / Method / Experiment / Value
- 创新度评分（1–5）与相关度（0–3）
- 一句话 TL;DR 与阅读建议

## License

本项目采用 [Apache License 2.0](LICENSE) 开源协议。
