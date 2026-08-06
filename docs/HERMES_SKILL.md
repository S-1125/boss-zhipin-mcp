---
name: boss-zhipin-mcp
description: "Use when collecting BOSS直聘 job/company data via local MCP."
version: 1.0.0
author: Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [boss-zhipin, mcp, scraper, jobs, data-collection, jianfa]
---

# BOSS 直聘数据采集（MCP）

通过本机 MCP server 采集 BOSS 直聘职位/公司数据，供 JianFa 产品数据管线使用。

**触发场景**：用户要求搜集/采集 BOSS 直聘岗位、JD、公司信息；或 JianFa 需要岗位种子数据。

## 位置与工具

- 代码：`<boss-zhipin-mcp 仓库目录>/`（server.py / collector.py）
- Hermes 注册名：`boss_zhipin` → 工具前缀 `mcp_boss_zhipin_*`
- 数据输出：`<boss-zhipin-mcp 仓库目录>/storage/jobs.jsonl`（JSONL）

## 标准流程

1. **检查登录态**：调用 `mcp_boss_zhipin_boss_login_status`
   - `logged_in: false` → 调用 `mcp_boss_zhipin_boss_login`，**提示用户在弹出的 Chrome 窗口完成手机号/扫码登录**（最多等 300s，登录态自动保存到 storage/state.json）
2. **搜索职位**：`mcp_boss_zhipin_boss_search_jobs(keyword, city, page)`
   - 城市传中文名（"北京"/"上海"…），内置映射表
   - 返回：标题/公司/薪资/标签/详情链接
3. **抓详情**：`mcp_boss_zhipin_boss_get_job_detail(url)` → JD 全文/要求/福利
4. **批量落盘**：`mcp_boss_zhipin_boss_collect_batch(keyword, city, pages)` → 追加写 JSONL

## 关键约束（务必遵守）

- **合规**：仅限个人学习/研究/原型验证；低频采集（间隔 ≥5s，批量 ≤3 页/次）；数据仅本地存储，不对外分发。采集前提醒用户这一点。
- **登录是采集前提**：未登录时列表页只显示"加载中，请稍候"，解析会返回 error + page_snippet。
- **频率控制**：连续调用间必须间隔；触发滑块验证码时停止并等待一段时间（通常 10-30 分钟）。

## 踩坑记录（重要）

1. **mcp 包版本**：必须 `mcp>=1.9,<2`。mcp 2.x 是全新 API（MCPServer/Extension），没有 `mcp.server.fastmcp`。
2. **PYTHONPATH 污染**：Hermes 会话注入 `PYTHONPATH=<宿主 Hermes venv 路径>`，导致任何 python 加载 Hermes 的 python3.11 包（pydantic_core 二进制不兼容直接 ModuleNotFoundError）。**运行命令必须加 `PYTHONPATH=` 前缀**。Hermes 启动 MCP 子进程时会过滤环境（不继承 PYTHONPATH），但 config 里仍显式设了 `env: PYTHONPATH: ''` 双保险。
3. **asyncio 冲突**：MCP server 跑在 asyncio 事件循环，Playwright Sync API 会报 "Sync API inside the asyncio loop"。server.py 已用 `asyncio.to_thread` 包裹所有采集调用，每个调用创建独立 `BossCollector` 实例（禁止跨线程共享 browser/page）。
4. **venv python 必须用绝对路径**：`tools/boss-mcp/.venv/bin/python`（Hermes 环境里 `source activate` 不可靠）。
5. **页面选择器改版频繁**：collector.py 用多级 fallback 选择器；解析失败时返回 `page_snippet` 辅助排查，需按新页面结构更新 selector。
6. **`hermes mcp add` 的 args 陷阱**：`--args` 必须是最后一个选项，否则后面的 `--env`/`--connect-timeout` 会被吞进 args。
7. **登录态失效**：`boss_login_status` 返回 false 时重新 `boss_login`，不要直接采集（会全是"加载中"）。

## 验证命令

```bash
cd <boss-zhipin-mcp 仓库目录>
PYTHONPATH= ./.venv/bin/python test_server.py     # 工具发现测试
PYTHONPATH= ./.venv/bin/python test_call.py boss_login_status   # 连接+登录态测试
```
