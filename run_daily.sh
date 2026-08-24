#!/bin/bash
# Daily paper survey update — called by crontab
set -u

cd "$(dirname "$0")"

# Prevent overlapping cron runs (every 6h) from racing on Codex token refresh.
LOCK_FILE="${TMPDIR:-/tmp}/paper-survey-run_daily.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  echo "Another run_daily.sh is already running, exiting."
  exit 0
fi

# Load proxy, PATH, HOME from config.json (falls back to defaults in config.py)
eval "$(python3 -c "from config import shell_exports; print(shell_exports())")"

LOG="logs/$(date +%Y%m%d).log"
mkdir -p logs

PROJECT_ROOT="$(python3 -c "from config import load_config; print(load_config()['paths']['project_root'])")"

ERRORS_FILE="$(mktemp)"
trap 'rm -f "$ERRORS_FILE"' EXIT

log_error() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$ERRORS_FILE"
}

run_phase() {
  local name="$1"
  shift
  echo "--- Phase: ${name} ---"
  "$@"
  local code=$?
  if [ "$code" -eq 0 ]; then
    echo "Phase completed: ${name}"
    return 0
  fi
  log_error "Phase failed: ${name} (exit ${code})"
  echo "WARNING: Phase failed: ${name} (exit ${code})"
  return "$code"
}

check_storage() {
  local required_kb="${PAPER_SURVEY_MIN_FREE_KB:-5242880}"
  local available_kb
  available_kb="$(df -Pk "$PROJECT_ROOT" | awk 'NR == 2 {print $4}')"
  if [[ ! "$available_kb" =~ ^[0-9]+$ ]]; then
    echo "Unable to determine free disk space for $PROJECT_ROOT"
    return 1
  fi
  echo "Storage preflight: $((available_kb / 1024)) MiB free; $((required_kb / 1024)) MiB required"
  if [ "$available_kb" -lt "$required_kb" ]; then
    echo "Insufficient free disk space; data phases will not run."
    return 1
  fi
}

{
  echo "=== Paper Survey Daily Run: $(date) ==="

  if [ ! -f config.json ]; then
    log_error "config.json missing — DingTalk disabled, using config.py defaults"
    echo "WARNING: config.json missing — DingTalk disabled, using config.py defaults."
    echo "         Copy config.example.json to config.json and fill in secrets."
  fi

  if run_phase "storage_preflight" check_storage; then
    # Phase 1: Fetch new papers from arxiv
    run_phase "fetch_papers" python3 fetch_papers.py || true

  # Phase 2: Download PDFs (incremental)
  run_phase "download_pdfs" python3 download_pdfs.py || true

  # Phase 3: Extract affiliations from new PDFs
  run_phase "extract_affiliations" python3 extract_affiliations.py || true

  # Phase 4: Generate notes for papers missing notes/ratings via Codex
  EXIT_CODE=0
  python3 generate_notes.py || EXIT_CODE=$?
  if [ "${EXIT_CODE:-0}" -eq 42 ]; then
    cp data/world_model/batch_new.json data/world_model/run_batch.json
    echo "Papers need notes or ratings, invoking Codex..."
    if bash scripts/check_codex_auth.sh; then
      if codex exec \
        --cd "$PROJECT_ROOT" \
        --skip-git-repo-check \
        --sandbox danger-full-access \
        -c 'approval_policy="never"' \
        --color never \
        - <<PROMPT
角色设定：你是一名理性、严谨的计算机科学家。

## 任务
1. 读取 ${PROJECT_ROOT}/data/world_model/batch_new.json 获取待处理论文列表
2. 对每篇论文：读取 pdf_path 指定的 PDF 文件（至少前 10 页，必要时续读；可使用 pdftotext、python PDF 库或其他本地命令行工具），然后生成笔记和评分

## 研究方向
用户关注：视频世界模型、3D世界模型、隐式世界模型（JEPA/Dreamer）。大气/气候等非CS领域不相关。

## 笔记要求
论文笔记是帮助提炼核心要点、辅助速读的工具，不要做成"全文翻译"，要提炼，用最精炼的语言表达核心思想。笔记主要语言为中文。

保存到 ${PROJECT_ROOT}/notes/world_model/{arxiv_id点替换为下划线}.md，格式：

# {论文标题}

## Insight
论文有无什么 insight，可以为无。若有的话，简要聊聊在什么样的 Observation 下，有什么样的推论，并做了怎么样的证明。

## Motivation
总结该论文解决什么问题？同行是怎么做的？是否是关键问题？为什么。

## Method
整体流程/管线是什么样的？关键技术细节有哪些？创新程度如何？

## Experiment
实验方法（消融/对比）、实验指标（用了哪些）、实验效果（指标/可视化）

## Value
整体工作价值如何评估。对我们有什么启发？还有什么待解决的问题？

## Strengths
工作有什么亮点？

## Weaknesses
工作有什么不足？

## Future Work
作者有无提出什么针对该工作的未来改进方向？

## Rating
创新度评分：{1-5}/5 - 简短说明评分理由
相关度评分：{0-3}/3 ({Core/Related/Tangential/Noise}) - 简短说明与研究方向的关系

## TL;DR
一句话中文总结（30-60字），包含核心贡献+阅读建议（值得精读/可选读/可跳过）。

评分参考（仅用于判断，不要作为笔记标题输出）：
创新度评分标准（1-5分）
- 5⭐：开创性工作，定义新范式
- 4⭐：显著创新，新方法+效果优异
- 3⭐：有一定创新，组合/新场景应用
- 2⭐：增量改进，贡献有限
- 1⭐：跟风/应用，几乎无新技术贡献
评分要严格，大部分论文应在 2-3 分。基于视频/3D/隐式世界模型方向评价。

相关度评分（0-3分）
基于对论文全文的理解，判断与用户研究方向（视频世界模型、3D世界模型、隐式世界模型如JEPA/Dreamer）的相关程度：
- 3 (Core)：直接研究上述方向，核心相关
- 2 (Related)：方法或场景与上述方向密切相关，有直接借鉴价值
- 1 (Tangential)：仅有间接关联，参考价值有限
- 0 (Noise)：与上述方向无实质关联（如大气模型、经济模型、纯NLP等）

## 输出
处理完后将每篇的 TL;DR、rating 和 relevance 写入：
${PROJECT_ROOT}/data/world_model/batch_new_results.json
格式：[{"arxiv_id": "...", "tldr": "...", "rating": 3, "relevance": 3}, ...]

每篇论文都要认真读 PDF 全文，不要只看 abstract。
PROMPT
      then
        run_phase "merge_results" python3 merge_results.py || true
      else
        log_error "Codex exec failed; skipping merge_results (run: codex logout && codex login)"
        echo "WARNING: Codex exec failed; skipping merge_results."
        echo "         Fix auth with: codex logout && codex login"
      fi
    else
      log_error "Codex auth check failed; skipping note generation (run: codex logout && codex login)"
      echo "WARNING: Codex auth check failed; skipping note generation."
      echo "         Fix auth with: codex logout && codex login"
    fi
  else
    echo "All papers have notes and ratings."
  fi

  # Phase 5b: Sync metadata from notes (fallback if merge skipped or partial)
  run_phase "sync_from_notes" python3 sync_from_notes.py || true

  # Phase 5c: Retire old low-rated papers
  run_phase "retire_papers" python3 retire_papers.py || true

  # Phase 6: Rebuild page
  run_phase "build_page" python3 build_page.py || true

  # Phase 7: DingTalk notification for high-rated papers in this batch
  run_phase "notify_dingtalk" python3 notify_dingtalk.py || true

  # Phase 8: Commit and push updates (notes + docs for GitHub Pages)
  if git rev-parse --git-dir >/dev/null 2>&1; then
    GIT_CFG="$(python3 -c "from config import load_config; g=load_config().get('git',{}); print(int(bool(g.get('auto_commit', True))), int(bool(g.get('auto_push', True))), g.get('push_remote','origin'))")"
    AUTO_COMMIT="${GIT_CFG%% *}"
    REST="${GIT_CFG#* }"
    AUTO_PUSH="${REST%% *}"
    PUSH_REMOTE="${REST#* }"

    if [ "$AUTO_COMMIT" = 1 ]; then
      git add -A docs/ notes/
      if git diff --staged --quiet; then
        echo "No changes to commit."
      else
        git commit -m "$(cat <<EOF
daily update: $(date +%Y-%m-%d)

Auto-generated by run_daily.sh
EOF
)" || {
          log_error "git commit failed"
          echo "WARNING: git commit failed"
        }
      fi
    fi

    if [ "$AUTO_PUSH" = 1 ]; then
      BRANCH="$(git rev-parse --abbrev-ref HEAD)"
      if git push "$PUSH_REMOTE" "HEAD:${BRANCH}"; then
        echo "Pushed to ${PUSH_REMOTE}/${BRANCH} for GitHub Pages."
      else
        log_error "git push failed — GitHub Pages will not update until push succeeds"
        echo "WARNING: git push failed (GitHub Pages will not update until push succeeds)"
      fi
    fi
    else
      echo "Not a git repository, skipping commit."
    fi
  else
    echo "Skipping paper processing because storage preflight failed."
  fi

  if [ -s "$ERRORS_FILE" ]; then
    echo "--- Phase: notify_manager ---"
    if python3 notify_manager.py --file "$ERRORS_FILE" --log "$LOG"; then
      echo "Phase completed: notify_manager"
    else
      echo "WARNING: notify_manager failed"
    fi
  fi

  echo "=== Done: $(date) ==="
} >> "$LOG" 2>&1
