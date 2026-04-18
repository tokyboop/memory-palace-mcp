"""
MemoryPalace v2 — Remote MCP Server 骨架

用途：作为 221B 项目的起点，copy 到本地后按需改。
依赖：pip install mcp
本地测试：python server.py  （默认 stdio transport，Claude Desktop 可直接连）
生产部署：把 __main__ 改成 transport="streamable-http"，systemd + nginx 反代

文件结构约定（见 focus/MemoryPalace.md）：
  knowledge/                          干货笔记（已有）
  journal/YYYY/MM/YYYY-MM-DD-HHMM_<slug>.md   日记/零碎

工具清单：
  search_knowledge(query)   — 只搜 knowledge/
  search_journal(query)     — 只搜 journal/
  search_all(query)         — 两个都搜
  read_file(path)           — 读单个文件（相对 BASE_DIR）
  write_note(folder, title, content, tags=[])   — 写新笔记
  list_recent(folder, n=10) — 最近 n 条（按文件名里的时间戳排）
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8")

_allowed_hosts = [h.strip() for h in os.environ.get("MP_ALLOWED_HOSTS", "").split(",") if h.strip()]
_allowed_origins = [o.strip() for o in os.environ.get("MP_ALLOWED_ORIGINS", "").split(",") if o.strip()]


# ─── 配置 ──────────────────────────────────────────────────────────────

# 生产部署时通过环境变量覆盖：export MP_BASE_DIR=/var/lib/memory-palace
BASE_DIR = Path(os.environ.get("MP_BASE_DIR", "./data")).resolve()
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
JOURNAL_DIR = BASE_DIR / "journal"

MAX_SEARCH_HITS = 30  # 单次搜索返回上限
RIPGREP = os.environ.get("RIPGREP_BIN", "rg")


# ─── 工具函数 ───────────────────────────────────────────────────────────


def _slugify(title: str) -> str:
    """中英混合 title → 文件名安全的 slug（kebab-case）。"""
    # 去掉文件名非法字符，保留中英数字和空格/短横
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", title).strip()
    # 空格和连续 _ 换成单个 -
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    # 折叠多个连续 -
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    # 限长（文件名别太长）
    return cleaned[:50] or "untitled"


def _ripgrep_search(query: str, folder: Path) -> list[dict]:
    """用 ripgrep 搜 folder 下所有 .md；返回 {file, line, context} 列表。"""
    if not folder.exists():
        return []
    try:
        proc = subprocess.run(
            [
                RIPGREP,
                "--json",
                "-i",                    # 大小写不敏感
                "-C", "2",               # 上下各 2 行上下文
                "--type", "md",
                "-m", "5",               # 每文件最多 5 个命中
                query,
                str(folder),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    hits = []
    for line in proc.stdout.splitlines():
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") != "match":
            continue
        data = evt["data"]
        hits.append({
            "file": str(Path(data["path"]["text"]).relative_to(BASE_DIR)),
            "line": data["line_number"],
            "text": data["lines"]["text"].rstrip(),
        })
        if len(hits) >= MAX_SEARCH_HITS:
            break
    return hits


def _safe_resolve(path: str, base: Path = BASE_DIR) -> Optional[Path]:
    """防穿越：拒绝 ../ 跳出 base 的路径。"""
    try:
        resolved = (base / path).resolve()
        resolved.relative_to(base)
        return resolved
    except (ValueError, OSError):
        return None


# ─── MCP Server ────────────────────────────────────────────────────────

app = FastMCP(
    "memory-palace",
    host=os.environ.get("MP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MP_PORT", "8000")),
    transport_security=TransportSecuritySettings(
        allowed_hosts=_allowed_hosts,
        allowed_origins=_allowed_origins,
    ),
)


@app.tool()
def search_knowledge(query: str) -> str:
    """在 knowledge/ 里关键词搜索。返回 JSON：{hits: [{file, line, text}]}。"""
    return json.dumps({"hits": _ripgrep_search(query, KNOWLEDGE_DIR)}, ensure_ascii=False)


@app.tool()
def search_journal(query: str) -> str:
    """在 journal/ 里关键词搜索。返回 JSON：{hits: [{file, line, text}]}。"""
    return json.dumps({"hits": _ripgrep_search(query, JOURNAL_DIR)}, ensure_ascii=False)


@app.tool()
def search_all(query: str) -> str:
    """同时搜 knowledge/ 和 journal/。返回 JSON：{knowledge: [...], journal: [...]}。"""
    return json.dumps(
        {
            "knowledge": _ripgrep_search(query, KNOWLEDGE_DIR),
            "journal": _ripgrep_search(query, JOURNAL_DIR),
        },
        ensure_ascii=False,
    )


@app.tool()
def read_file(path: str) -> str:
    """读单个 .md 文件的全文。path 相对 BASE_DIR，例如 'journal/2026/04/2026-04-18-0930_xxx.md'。"""
    target = _safe_resolve(path)
    if target is None or not target.is_file():
        return json.dumps({"error": f"file not found or not allowed: {path}"})
    return target.read_text(encoding="utf-8")


@app.tool()
def write_note(folder: str, title: str, content: str, tags: Optional[list[str]] = None) -> str:
    """
    写一条新笔记。
      folder: "journal" 或 "knowledge"
      title: 短标题（用作 slug）
      content: 正文 markdown
      tags: 可选 tag 列表
    journal 文件路径：journal/YYYY/MM/YYYY-MM-DD-HHMM_<slug>.md
    knowledge 文件路径：knowledge/<slug>.md（不分子目录，沿用现有习惯）
    """
    if folder not in {"journal", "knowledge"}:
        return json.dumps({"error": "folder must be 'journal' or 'knowledge'"})

    now = datetime.now()
    slug = _slugify(title)
    tags = tags or []

    if folder == "journal":
        subdir = JOURNAL_DIR / f"{now.year:04d}" / f"{now.month:02d}"
        filename = f"{now.strftime('%Y-%m-%d-%H%M')}_{slug}.md"
    else:
        subdir = KNOWLEDGE_DIR
        filename = f"{slug}.md"

    subdir.mkdir(parents=True, exist_ok=True)
    target = subdir / filename

    frontmatter = [
        "---",
        f"created: {now.isoformat(timespec='seconds')}",
        f"title: {title}",
    ]
    if tags:
        frontmatter.append(f"tags: [{', '.join(tags)}]")
    frontmatter.append("---\n")

    target.write_text("\n".join(frontmatter) + content.rstrip() + "\n", encoding="utf-8")
    return json.dumps({"written": str(target.relative_to(BASE_DIR))}, ensure_ascii=False)


@app.tool()
def list_recent(folder: str, n: int = 10) -> str:
    """列最近 n 条。folder: 'journal' / 'knowledge' / 'all'。返回 JSON：{files: [{path, mtime}]}。"""
    dirs = {
        "journal": [JOURNAL_DIR],
        "knowledge": [KNOWLEDGE_DIR],
        "all": [JOURNAL_DIR, KNOWLEDGE_DIR],
    }.get(folder)
    if dirs is None:
        return json.dumps({"error": "folder must be 'journal' / 'knowledge' / 'all'"})

    files = []
    for d in dirs:
        if d.exists():
            files.extend(d.rglob("*.md"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    top = [
        {
            "path": str(f.relative_to(BASE_DIR)),
            "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
        }
        for f in files[:n]
    ]
    return json.dumps({"files": top}, ensure_ascii=False)


# ─── 启动 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.environ.get("MP_TRANSPORT", "stdio")
    if transport == "http":
        app.run(transport="streamable-http")
    else:
        app.run()
