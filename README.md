# Memory Palace — a minimal Remote MCP server

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
