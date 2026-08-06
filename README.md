# BOSS直聘 MCP Server

> 通过 [Model Context Protocol](https://modelcontextprotocol.io) 暴露 BOSS 直聘（zhipin.com）数据采集能力的本地 MCP 服务器。提供职位搜索、JD 详情、公司查询等 7 个工具，配合 Hermes Agent、Claude Desktop 等 MCP 客户端使用。

> [!WARNING]
> **合规与免责声明（务必阅读）**
> 本项目**仅供个人学习、研究、产品原型验证**使用。
> - 采集 BOSS 直聘数据可能违反其服务条款，使用风险由使用者自行承担
> - 请严格控制采集频率（间隔 ≥5 秒、单次批量 ≤3 页），尊重平台风控
> - 采集数据仅保存在本地，**禁止商业分发、二次转售、公开传播**
> - 本项目与 BOSS 直聘（看准科技）无任何关联，未获其官方授权

## ✨ 功能

| 工具 | 说明 |
|---|---|
| `boss_login` | 打开浏览器完成登录（首次必做，登录态持久化复用） |
| `boss_login_status` | 检查登录态是否有效 |
| `boss_search_jobs(keyword, city, page)` | 搜索职位列表（标题/公司/薪资/标签/链接） |
| `boss_get_job_detail(url)` | 抓取职位详情（JD 全文/任职要求/福利/公司） |
| `boss_search_companies(keyword)` | 搜索公司 |
| `boss_get_company_jobs(company_url)` | 公司主页在招职位 |
| `boss_collect_batch(keyword, city, pages)` | 批量采集多页职位，落盘 JSONL |

## 🚀 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/S-1125/boss-zhipin-mcp.git
cd boss-zhipin-mcp

uv venv .venv --python 3.13
uv pip install "mcp>=1.9,<2" playwright
# 需要本机已安装 Google Chrome（复用系统浏览器，无需下载浏览器二进制）
```

> ⚠️ 务必使用 `mcp>=1.9,<2`：mcp 2.x 是全新 API（无 `mcp.server.fastmcp`）。

### 2. 登录（一次即可，登录态自动保存到 `storage/state.json`）

```bash
PYTHONPATH= ./.venv/bin/python -c "
from collector import BossCollector
BossCollector(storage_state='storage/state.json').login(timeout_sec=420)"
```

会弹出**独立的 Chrome 窗口**（Playwright 隔离实例，与你日常浏览器不互通），请**在该窗口内**完成手机号/扫码登录。

### 3. 注册到 MCP 客户端

**Hermes Agent**（`~/.hermes/config.yaml`）：

```yaml
mcp_servers:
  boss_zhipin:
    command: /绝对路径/boss-zhipin-mcp/.venv/bin/python
    args:
      - /绝对路径/boss-zhipin-mcp/server.py
    env:
      PYTHONPATH: ''          # 防止宿主环境 PYTHONPATH 污染
    enabled: true
```

工具将以 `mcp_boss_zhipin_*` 前缀自动注入。**修改配置后需重启会话生效。**

**Claude Desktop / 其他客户端**：按各自 MCP 配置格式，stdio command 指向 `server.py` 即可。

### 4. 使用

```python
# 任意 MCP 客户端中调用
boss_search_jobs(keyword="AI 产品经理", city="北京", page=1)
boss_get_job_detail(url="https://www.zhipin.com/job_detail/xxxx.html")
boss_collect_batch(keyword="产品经理", city="北京", pages=2)  # -> storage/jobs.jsonl
```

## 📁 目录结构

```
boss-zhipin-mcp/
├── server.py          # MCP server（FastMCP）
├── collector.py       # 采集核心（Playwright + 系统 Chrome + 登录态持久化）
├── test_server.py     # 工具发现测试
├── test_call.py       # 工具调用测试
├── docs/
│   └── HERMES_SKILL.md  # Hermes Agent skill（含踩坑记录）
└── storage/           # 登录态 + 采集数据（gitignore，不会提交）
```

## 🏗️ 架构要点

- **浏览器**：Playwright `channel="chrome"` 复用系统 Chrome，无需下载浏览器二进制
- **登录态**：`storage_state` 持久化 → 一次登录长期复用；失效自动检测
- **反爬友好**：随机 1-3s 节流、低频调用、风控检测（验证码页面识别）
- **asyncio 适配**：MCP server 运行于 asyncio 事件循环，Playwright Sync API 不能直接运行其中 → 所有采集经 `asyncio.to_thread` 放入独立线程，每个调用独立采集器实例
- **选择器容错**：BOSS 前端改版频繁，所有选择器均为多级 fallback；解析失败返回页面片段辅助排查

## 🐛 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| `No module named 'mcp.server.fastmcp'` | 装了 mcp 2.x | `uv pip install "mcp>=1.9,<2"` |
| `Sync API inside the asyncio loop` | 直接调用 Playwright Sync API | server.py 已用 `asyncio.to_thread` 处理 |
| `加载中，请稍候` / 未解析到卡片 | 未登录 or 页面改版 | 先 `boss_login`；改版则更新选择器 |
| 触发滑块/验证码 | 采集频率过高 | 降低频率、增大间隔、暂停 10-30 分钟 |
| 登录窗口与日常 Chrome 不同 | Playwright 使用隔离浏览器实例 | 在**弹出的新窗口**内登录 |

## 📄 许可证

[MIT License](LICENSE)

---

**免责声明**：本项目按"现状"提供，不提供任何担保。使用者应自行评估合规风险，并对使用后果负责。
