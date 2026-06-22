# 林知新

> 一位帮你读 Paper 的 Agent。

林知新是一个自动化的 arXiv 论文追踪与阅读助手。它每天从 arXiv 抓取与你研究方向相关的论文，下载 PDF、提取机构信息，调用 Codex 生成中文笔记与评分，并发布为可浏览的静态页面。发现 4 星及以上高价值论文时，还会通过钉钉机器人推送摘要。

当前追踪方向：**World Model**（视频世界模型、3D 世界模型、隐式世界模型等）。

- 在线演示：[https://frankjiang.github.io/linzhixin/](https://frankjiang.github.io/linzhixin/)
- 项目地址：[https://github.com/frankjiang/linzhixin](https://github.com/frankjiang/linzhixin)

## 功能

- **每日自动抓取**：从 arXiv 检索近期论文，去重合并
- **PDF 增量下载**：支持版本回退（v2 不可用时尝试 v1）
- **机构提取**：从 PDF 首屏提取作者单位
- **Agent 读论文**：Codex 阅读 PDF，生成结构化中文笔记（Insight / Method / Experiment / TL;DR 等）
- **评分与筛选**：创新度 1–5 星、相关度 0–3 级，支持搜索与多维排序
- **查漏补缺**：缺笔记、缺评分、缺 TL;DR 的论文会自动重新进入处理队列
- **钉钉推送**：本次批次中 ≥4 星的论文，推送 Markdown 摘要（含「快速阅读」深链接）
- **深链接**：`?paper=2606.12403v1` 可直达某篇论文并展开详情
- **LaTeX 渲染**：标题与摘要中的 `$\\texttt{...}$`、希腊字母等由 KaTeX 渲染
- **清退机制**：按评分与论文日期从网页下架旧论文（1 星 >1 月、2 星 >2 月、3 星 >6 月、4–5 星 >1 年）；`notes/` 中的笔记保留不删

## 安装

### 环境要求

| 依赖 | 版本 / 说明 |
|------|-------------|
| Python | 3.10+ |
| Git | 用于日报自动提交与 GitHub Pages |
| [poppler-utils](https://poppler.freedesktop.org/) | 提供 `pdftotext`，供 `extract_affiliations.py` 使用 |
| [Codex CLI](https://github.com/openai/codex) | 日报 Phase 4 读 PDF、写笔记（需已登录） |
| 网络代理（可选） | 访问 arXiv 受限时，在 `config.json` 的 `proxy` 段配置 |

### 克隆与初始化

```bash
git clone https://github.com/frankjiang/linzhixin.git paper-survey
cd paper-survey

# 可选：创建虚拟环境（项目本身无第三方 pip 依赖）
python3 -m venv .venv
source .venv/bin/activate

# 确认 Python 版本并记录环境（requirements.txt 无额外包）
pip install -r requirements.txt

# 生成本地配置（必做）
cp config.example.json config.json
```

编辑 `config.json`，填入本机路径、代理、钉钉 webhook 等（见下节）。

**系统工具示例（Ubuntu/Debian）：**

```bash
sudo apt-get install -y poppler-utils
# Codex CLI 请按官方文档安装，并确保 `codex` 在 PATH 中
```

### 首次验证

```bash
# 重建静态页面（需已有 data/world_model/papers.json，或先跑一遍日报）
python3 build_page.py

# 本地预览
python3 server.py
# 浏览器打开 http://127.0.0.1:7777
```

## 配置

`config.json` 存放本地敏感信息与路径，**已加入 `.gitignore`，不会被 git 提交或删除**。日报脚本只会 `git add docs/ notes/`，不会动 `config.json`。

若文件丢失，程序会回退到 `config.py` 中的默认值（钉钉默认关闭），并在日志中输出 WARNING。可从 `config.example.json` 重新复制一份。

### 配置项说明

| 配置项 | 说明 |
|--------|------|
| `proxy.http` / `https` / `all` | 访问 arXiv 的 HTTP/SOCKS 代理；不需要时可设为空字符串 |
| `proxy.no_proxy` | 不走代理的地址列表 |
| `paths.home` | 运行 Codex 时使用的 HOME |
| `paths.project_root` | 项目根目录绝对路径 |
| `paths.codex_bin_dirs` | 追加到 PATH 的目录（含 `codex` 可执行文件） |
| `dingtalk.enabled` | 是否启用钉钉推送 |
| `dingtalk.webhook` | 自定义机器人 Webhook URL |
| `dingtalk.secret` | 加签密钥（SEC 开头） |
| `dingtalk.min_rating` | 推送最低创新度星级（默认 4） |
| `dingtalk.survey_url` | 推送消息中「查看完整列表 / 快速阅读」的基础 URL |
| `site.public_url` | 对外站点地址（GitHub Pages）；钉钉链接的备选 |
| `site.github_url` | 页面右上角仓库链接 |
| `server.host` / `port` | 本地 `server.py` 监听地址 |
| `server.address` | 内网访问 IP（写入默认 survey URL 时的备选） |
| `topic.name` | 数据目录名，如 `world_model` → `data/world_model/` |
| `retirement.*` | 论文清退策略 |
| `git.auto_commit` / `auto_push` | 日报结束后是否自动提交、推送 `docs/` 与 `notes/` |

也可通过环境变量覆盖部分配置：`HTTP_PROXY`、`DINGTALK_WEBHOOK`、`DINGTALK_SECRET`、`DINGTALK_ENABLED`、`PAPER_SURVEY_PORT` 等。

## 使用

### 完整日报（推荐）

```bash
bash run_daily.sh
```

日志写入 `logs/YYYYMMDD.log`。流程如下：

| 阶段 | 脚本 | 作用 |
|------|------|------|
| 1 | `fetch_papers.py` | 从 arXiv 抓取新论文，写入 `data/<topic>/` |
| 2 | `download_pdfs.py` | 增量下载 PDF |
| 3 | `extract_affiliations.py` | 从 PDF 首屏提取机构 |
| 4 | `generate_notes.py` + `codex exec` | 待处理论文生成笔记与评分 |
| 5 | `merge_results.py` / `sync_from_notes.py` | 合并评分、从笔记回填元数据 |
| 5c | `retire_papers.py` | 下架过期低分论文（保留笔记） |
| 6 | `build_page.py` | 生成 `docs/index.html` |
| 7 | `notify_dingtalk.py` | 推送本批次 ≥ `min_rating` 星论文到钉钉 |
| 8 | git commit & push | 提交 `docs/`、`notes/` 并推送 GitHub Pages |

若 Phase 4 没有待处理论文，会跳过 Codex，其余阶段照常执行。

### 常用单步命令

```bash
# 仅重建静态页面
python3 build_page.py

# 本地 HTTP 服务（默认读 config.json 中的 host/port）
python3 server.py
python3 server.py -p 8080 -b 127.0.0.1

# 手动钉钉推送（推送 run_batch.json 中的本批次高星论文）
python3 notify_dingtalk.py

# 补发遗漏推送：指定日期以来所有符合条件论文，合并为今日日报格式
python3 notify_dingtalk.py --resend-since 2026-06-13

# 从笔记同步 TL;DR / 评分到 papers.json
python3 sync_from_notes.py
```

### 定时任务

```cron
# 每天 00:00 执行日报
0 0 * * * /path/to/paper-survey/run_daily.sh
```

建议使用绝对路径，并确保 cron 环境中的 `codex`、代理与交互式 shell 一致（`run_daily.sh` 会通过 `config.json` 注入 PATH 与代理）。

### 本地预览 vs 线上站点

| 场景 | 命令 / 地址 |
|------|-------------|
| 本地开发 | `python3 server.py` → `http://127.0.0.1:7777` |
| GitHub Pages | push 后访问 `site.public_url` |
| 钉钉深链接 | `{survey_url}?paper=<arxiv_id>`，如 `https://frankjiang.github.io/linzhixin/?paper=2606.12403v1` |

修改 `build_page.py` 等构建脚本后，需重新运行 `python3 build_page.py`；日报 Phase 6 会自动重建页面。

## GitHub Pages 部署

`build_page.py` 输出到 `docs/`（同时生成 `.nojekyll` 以跳过 Jekyll 处理），本地预览与 GitHub Pages 共用同一目录。

1. 运行 `python3 build_page.py` 生成最新页面
2. 将 `docs/` 提交并 push 到仓库（日报 Phase 8 可自动完成）
3. 在 GitHub 仓库 **Settings → Pages** 中：
   - Source: **Deploy from a branch**
   - Branch: `master`（或你的默认分支）
   - Folder: **`/docs`**
4. 在 `config.json` 中设置 `site.public_url` 与 `dingtalk.survey_url` 为 Pages 地址，例如：
   ```json
   "public_url": "https://frankjiang.github.io/linzhixin/",
   "survey_url": "https://frankjiang.github.io/linzhixin/"
   ```

页面采用 GitHub 风格设计：浅色/深色主题、固定宽度评分徽章、KaTeX 公式、issue 列表式论文卡片。

## 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 钉钉无推送 | `config.json` 缺失或未启用 | `cp config.example.json config.json` 并填写 `dingtalk.*` |
| 日志出现 `DingTalk notifications disabled` | 无配置文件，使用默认关闭 | 恢复 `config.json`，`enabled: true` |
| 网页更新但钉钉长期静默 | 同上，或本批次无 ≥4 星论文 | 查 `logs/YYYYMMDD.log`；可用 `--resend-since` 补发 |
| GitHub Pages 未更新 | push 失败或无新 commit | 查日志 Phase 8；手动 `git push` |
| 机构为空 | 未安装 `pdftotext` 或 PDF 未下载 | `apt install poppler-utils`；检查 `data/.../pdfs/` |
| Codex 未运行 | 无待处理论文，或 `codex` 不在 PATH | 查 `generate_notes.py` 输出；配置 `paths.codex_bin_dirs` |

**备份建议：** 定期备份 `config.json`（含 webhook/secret），该文件不在 git 中，误删后推送会静默失败。

## 项目结构

```
├── run_daily.sh           # 日报入口
├── requirements.txt       # Python 环境说明（无第三方包）
├── config.json            # 本地配置（不入库，需自行创建）
├── config.example.json    # 配置模板
├── config.py              # 配置加载与默认值
├── fetch_papers.py
├── download_pdfs.py
├── extract_affiliations.py
├── generate_notes.py
├── merge_results.py
├── sync_from_notes.py
├── retire_papers.py
├── build_page.py
├── notify_dingtalk.py
├── server.py              # 本地 HTTP 服务
├── data/world_model/      # 论文数据、PDF、批次文件（不入库）
├── notes/world_model/     # Agent 生成的 Markdown 笔记
├── docs/index.html        # 静态站点（本地预览 + GitHub Pages）
└── logs/                  # 日报运行日志（不入库）
```

## 笔记格式

每篇论文的笔记保存在 `notes/world_model/<arxiv_id>.md`（`.` 替换为 `_`），包含：

- Insight / Motivation / Method / Experiment / Value
- 创新度评分（1–5）与相关度（0–3）
- 一句话 TL;DR 与阅读建议

## License

本项目采用 [Apache License 2.0](LICENSE) 开源协议。
