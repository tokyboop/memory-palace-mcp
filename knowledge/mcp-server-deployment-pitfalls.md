# MCP Server 部署踩坑合辑（Streamable HTTP）

> 蒸馏日期：2026-04-18
> 来源：自建 Remote MCP Server 部署实战（Python MCP SDK 1.27.0 + systemd + nginx + Let's Encrypt）
> 置信度：C5（实战验证，服务器已上线运行）

---

## 适用场景

用 Python MCP SDK（`mcp` 包）在 Linux 服务器上部署 Streamable HTTP transport 的 MCP Server，nginx 反代到 HTTPS 域名，供 Claude Desktop / Claude Code CLI / Claude App 的 custom connector 接入。

如果你在搭类似架构，下面 6 个坑基本都会撞到。

---

## 坑 1：FastMCP 1.9+ 的 `run()` 不再接受 `host/port`

### 症状

```
TypeError: FastMCP.run() got an unexpected keyword argument 'host'
```

### 原因

从 `mcp>=1.9` 起，`host/port/transport_security` 这类 transport 配置必须在 `FastMCP(...)` 构造时传入，`run()` 只接受 `transport` 和 `mount_path`。

### 修法

**错误写法**（旧教程常见）：

```python
app = FastMCP("my-server")
app.run(
    host="127.0.0.1",
    port=8000,
    transport="streamable-http",
)
```

**正确写法**：

```python
app = FastMCP(
    "my-server",
    host="127.0.0.1",
    port=8000,
)
app.run(transport="streamable-http")
```

---

## 坑 2：FastMCP 1.13+ 的 DNS rebinding 保护默认拦反代

### 症状

服务进程本地 `curl 127.0.0.1:8000/mcp` 能通，但 nginx 反代过去返：

```
HTTP/1.1 421 Misdirected Request
Invalid Host header
```

### 原因

`mcp>=1.13` 引入 `TransportSecuritySettings`，默认 `enable_dns_rebinding_protection=True`，且 `allowed_hosts=[]`（空列表 = 只接受 `127.0.0.1:8000` / `localhost:8000`）。

nginx 反代把外部请求的 `Host: your.domain.com` 透传给 upstream 时，MCP 看到不在白名单的 Host 就拒。

### 修法

```python
from mcp.server.fastmcp.server import TransportSecuritySettings

app = FastMCP(
    "my-server",
    host="127.0.0.1",
    port=8000,
    transport_security=TransportSecuritySettings(
        allowed_hosts=["your.domain.com", "127.0.0.1:8000", "localhost:8000"],
        allowed_origins=["https://your.domain.com", "https://claude.ai", "https://claude.com"],
    ),
)
```

**建议**通过环境变量注入，避免代码里写死域名：

```python
import os
_allowed_hosts = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
_allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
```

---

## 坑 3：`which <cmd>` 会被 shell function 误报成功

### 症状

`sudo -u mcp which rg` 返回路径，但 server 运行时 `subprocess.run(["rg", ...])` 返空/报 FileNotFoundError。

### 原因

很多 shell（尤其发行版带 alias 的）里 `which` 是 function 或 builtin，会走 alias/history 兜底，**即使二进制根本没装也可能返回看起来像路径的东西**。

### 修法

验证命令真装了，用这个组合：

```bash
command -v rg && rg --version | head -1
```

- `command -v` 是 POSIX 标准，不被 alias 污染
- `rg --version` 真正跑一次二进制，没装必报错

**不要**单独用 `which`。

---

## 坑 4：Windows 上 subprocess 读 UTF-8 输出会崩

### 症状

MCP Server 在 Windows 本机跑（stdio 模式或 HTTP 模式都一样）调 `ripgrep --json` 时：

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0xxx
```

或中文文件名出现在工具响应里时被乱码。

### 原因

Windows Python 默认 stdout/stderr 编码是 GBK（系统 locale），而 `rg --json` 输出 UTF-8。`subprocess.run(...)` 用 text 模式时按默认 locale 解码，中文直接崩。

### 修法（两处都要）

**subprocess 调用时显式 UTF-8**：

```python
subprocess.run(
    [rg_bin, "--json", "-i", query, str(folder)],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=10,
)
```

**server 启动时重配 stdout/stderr**：

```python
import sys
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8")
```

`reconfigure` 是 Python 3.7+ 的 TextIOWrapper 方法，安全调一次即可。

---

## 坑 5：nginx `proxy_buffering` 不关会 hang 流式响应

### 症状

客户端调一个稍长的工具（比如 ripgrep 搜大目录），nginx 卡着不吐数据，直到 upstream 全返完才一次放出，或者超时断连。

### 原因

nginx 默认 `proxy_buffering on`，要把 upstream 响应攒满 buffer 才往下游转。Streamable HTTP 是**逐块流式响应**，被 buffer 就 hang。

### 修法

location 块里加：

```nginx
location /mcp {
    proxy_pass http://mcp_upstream;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;              # 关键
    proxy_read_timeout 86400s;        # 坑 6 一起改
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Host $host;
}
```

---

## 坑 6：nginx 默认 `proxy_read_timeout=60s` 会切断长工具调用

### 症状

工具跑超过 60 秒（大搜索 / 大文件读 / LLM 调用代理）时客户端收到 `upstream timed out`。

### 原因

nginx 默认 60 秒没从 upstream 收到数据就断。

### 修法

同上 location 块：

```nginx
proxy_read_timeout 86400s;
```

设 1 天是经验值，够所有合理工具场景，又不会让挂掉的 upstream 永远占 worker。

---

## 自检 checklist

部署前按这个勾：

- [ ] `FastMCP(...)` 构造里传 `host/port`（不在 `run()` 里）
- [ ] `TransportSecuritySettings` 白名单含反代域名 + `127.0.0.1:<port>` + `localhost:<port>`
- [ ] `allowed_origins` 含 `https://claude.ai` + `https://claude.com`
- [ ] 服务器上 `command -v rg && rg --version` 能真输出版本号
- [ ] subprocess 调用显式 `encoding="utf-8"`（跨平台一致）
- [ ] nginx location `/mcp` 设了 `proxy_buffering off` + `proxy_read_timeout 86400s`
- [ ] systemd unit 带 `PYTHONIOENCODING=utf-8`（Windows/Linux 都加上，保险）

---

## 推断 vs 验证

**已验证**（C5）：6 个坑都在实际部署中撞过并修通。

**未验证**（C3）：
- 其他 MCP SDK 语言实现（TypeScript/Rust）是否有类似 DNS rebinding 默认开启——大概率有，但具体 API 名不一样
- `mcp` SDK 后续版本会不会改变默认行为——到 1.27.0 为止行为稳定

**不适用**：Windows 上跑生产 MCP Server 不推荐，上面坑 4 只是本地开发调试用。
