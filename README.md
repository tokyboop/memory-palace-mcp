# Memory Palace — a minimal Remote MCP server

**English** | [中文](#中文)

A personal knowledge server spoken to by any Claude client (Desktop / CLI / Web)
via the Model Context Protocol. Serves markdown notes over **Streamable HTTP**,
backed by **ripgrep** keyword search — no embeddings, no vector database, zero
maintenance cost.

Built as a minimal reference for anyone putting a Remote MCP server into
production. Designed to be forked and adapted.

## Why this exists

The "hello world" for Remote MCP is scattered across spec updates, SDK changes,
and transport migrations (SSE → Streamable HTTP in 2026-04). This repo is a
single file that compiles, runs, and passes the real gauntlet: public HTTPS,
`mcp >= 1.13` DNS-rebinding checks, systemd, nginx, TLS renewal.

A walk-through of the concrete pitfalls is in
[`knowledge/mcp-server-deployment-pitfalls.md`](knowledge/mcp-server-deployment-pitfalls.md).

## Quick start (local stdio)

```bash
pip install -r requirements.txt
python server.py                       # stdio transport, for Claude Desktop
```

Point Claude Desktop at `server.py`; `knowledge/` and `journal/` are created
under `./data/` on first write.

## Quick start (public HTTPS)

```bash
# On a host behind nginx + Let's Encrypt:
export MP_TRANSPORT=http
export MP_BASE_DIR=/var/lib/memory-palace
export MP_ALLOWED_HOSTS=your.domain.com,127.0.0.1:8000,localhost:8000
export MP_ALLOWED_ORIGINS=https://your.domain.com,https://claude.ai,https://claude.com
python server.py
```

See `knowledge/mcp-server-deployment-pitfalls.md` for a full systemd unit and
nginx reverse-proxy config.

## Architecture

```
Claude Desktop ─┐
Claude CLI    ─┼──► https://your.domain.com/mcp  (Streamable HTTP)
Claude.ai Web ─┘                │
                                ▼
                  nginx (TLS, Let's Encrypt)
                                │
                                ▼
                  systemd: FastMCP on 127.0.0.1:8000
                                │
                  ┌─────────────┴─────────────┐
                  ▼                           ▼
            knowledge/*.md              journal/YYYY/MM/*.md
                  └───────── ripgrep ─────────┘
```

## Tools

| Tool | Purpose |
|---|---|
| `search_knowledge(query)` | ripgrep over `knowledge/` |
| `search_journal(query)` | ripgrep over `journal/` |
| `search_all(query)` | both at once |
| `read_file(path)` | read a single note (path traversal guarded) |
| `write_note(folder, title, content, tags?)` | create a note with auto-slugged filename + frontmatter |
| `list_recent(folder, n)` | most-recently-modified notes |

## Design choices (and why)

- **Streamable HTTP, not SSE.** SSE is deprecated as of 2026-04-01.
- **Local stdio fallback is read-only.** Writes always go to the remote to
  prevent local/remote divergence when both are configured on the same client.
- **ripgrep, not embeddings.** At personal scale (< 100 notes) embeddings add
  cost and maintenance burden without better recall than keyword search.
- **No auth in v1.** Obscurity via a non-published URL; `Bearer` / OAuth is a
  planned backlog item and is a straightforward addition on top of FastMCP.

## Layout

```
server.py              # the whole server, ~250 lines
requirements.txt
knowledge/             # long-form notes (shipped in this repo as examples)
data/                  # created at runtime: knowledge/ + journal/ live here
```

## License

MIT.

---

<a id="中文"></a>

# Memory Palace — 最小 Remote MCP 服务器

[English](#memory-palace--a-minimal-remote-mcp-server) | **中文**

一个个人知识服务器，任何 Claude 客户端（Desktop / CLI / Web）都能通过 Model Context Protocol 连上。基于 **Streamable HTTP** 提供 markdown 笔记服务，用 **ripgrep** 做关键词搜索——不跑 embedding、不依赖向量数据库，零维护成本。

作为给想把 Remote MCP Server 真正部署到生产环境的人用的最小参考，鼓励 fork 和改造。

## 为什么做这个

Remote MCP 的 "hello world" 散落在 spec 更新、SDK 变化、transport 迁移（2026-04 SSE → Streamable HTTP）之间。这个仓库用单文件解决全部真实门槛：公网 HTTPS、`mcp >= 1.13` 的 DNS rebinding 白名单、systemd、nginx、TLS 自动续期。

踩坑详情见 [`knowledge/mcp-server-deployment-pitfalls.md`](knowledge/mcp-server-deployment-pitfalls.md)。

## 快速上手（本地 stdio）

```bash
pip install -r requirements.txt
python server.py                       # stdio 模式，Claude Desktop 直接连
```

让 Claude Desktop 指向 `server.py`；首次写入时会在 `./data/` 下创建 `knowledge/` 和 `journal/`。

## 快速上手（公网 HTTPS）

```bash
# 一台配好 nginx + Let's Encrypt 的主机：
export MP_TRANSPORT=http
export MP_BASE_DIR=/var/lib/memory-palace
export MP_ALLOWED_HOSTS=your.domain.com,127.0.0.1:8000,localhost:8000
export MP_ALLOWED_ORIGINS=https://your.domain.com,https://claude.ai,https://claude.com
python server.py
```

完整 systemd unit + nginx 反代配置见 `knowledge/mcp-server-deployment-pitfalls.md`。

## 架构

```
Claude Desktop ─┐
Claude CLI    ─┼──► https://your.domain.com/mcp  (Streamable HTTP)
Claude.ai Web ─┘                │
                                ▼
                  nginx（TLS，Let's Encrypt）
                                │
                                ▼
              systemd：FastMCP 跑在 127.0.0.1:8000
                                │
                  ┌─────────────┴─────────────┐
                  ▼                           ▼
            knowledge/*.md              journal/YYYY/MM/*.md
                  └───────── ripgrep ─────────┘
```

## 工具清单

| 工具 | 用途 |
|---|---|
| `search_knowledge(query)` | 对 `knowledge/` 跑 ripgrep |
| `search_journal(query)` | 对 `journal/` 跑 ripgrep |
| `search_all(query)` | 两个一起搜 |
| `read_file(path)` | 读单篇（有路径穿越防护） |
| `write_note(folder, title, content, tags?)` | 新建一篇，自动 slug + frontmatter |
| `list_recent(folder, n)` | 按修改时间列最近条目 |

## 关键设计选择

- **用 Streamable HTTP，不用 SSE**：SSE 在 2026-04-01 起已弃用
- **本地 stdio fallback 只读**：写操作强制走远程，避免本地/远程双向漂移
- **用 ripgrep 而不是 embedding**：个人规模（< 100 篇）下 embedding 的成本和维护负担都不划算，召回也不明显更好
- **v1 不做 auth**：靠"域名未公开"兜底；`Bearer` / OAuth 在 backlog，FastMCP 上加一层很轻

## 目录结构

```
server.py              # 服务器全部代码，约 250 行
requirements.txt
knowledge/             # 长文笔记（仓库里带了几篇作示例）
data/                  # 运行时创建：knowledge/ 和 journal/ 放这里
```

## 许可证

MIT。
