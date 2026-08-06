"""
BOSS 直聘 MCP Server
====================
通过 Model Context Protocol 暴露 BOSS 直聘数据采集能力，
供 Hermes Agent 等 MCP 客户端调用。

启动:  .venv/bin/python server.py
注册:  ~/.hermes/config.yaml -> mcp_servers.boss_zhipin
工具命名: mcp_boss_zhipin_<tool_name>

用法示例（在 Hermes 中）:
  "用 mcp_boss_zhipin_search_jobs 搜索北京的 AI 产品经理岗位"

实现说明:
- MCP server 运行在 asyncio 事件循环中，而 Playwright Sync API 不能在
  asyncio loop 内运行，因此所有采集调用通过 asyncio.to_thread 放到
  独立线程执行，每个调用使用独立的采集器实例（避免跨线程共享浏览器）。
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# 日志输出到 stderr（stdout 被 MCP 协议占用）
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("boss-mcp")

from collector import BossCollector, collect_batch  # noqa: E402

# 数据目录：默认与 server.py 同级 storage/
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_STATE = BASE_DIR / "storage" / "state.json"
# 持久化浏览器 profile（登录态最稳，优先使用）
CHROME_PROFILE = BASE_DIR / "storage" / "chrome-profile"

mcp = FastMCP("boss-zhipin")


def _new_collector() -> BossCollector:
    """创建独立采集器实例（每个调用一个，运行于独立线程）。

    优先使用持久化 Chrome profile（user_data_dir），登录态/验证状态
    天然保留；不存在时回退到 storage_state 登录态文件。
    """
    if CHROME_PROFILE.exists():
        return BossCollector(user_data_dir=str(CHROME_PROFILE), headless=False)
    return BossCollector(storage_state=str(STORAGE_STATE), headless=False)


def _ok(**kwargs) -> dict:
    return {"status": "ok", **kwargs}


def _err(message: str, **kwargs) -> dict:
    return {"status": "error", "message": str(message), **kwargs}


# ─────────────────────────── 工具定义 ───────────────────────────

@mcp.tool()
async def boss_login(timeout_sec: int = 300) -> dict:
    """打开浏览器窗口完成 BOSS 直聘登录（首次需手机号/扫码登录，登录态自动保存）。

    之后所有采集工具自动复用登录态。若登录态失效会返回提示，重新调用本工具即可。
    """
    try:
        return await asyncio.to_thread(_new_collector().login, timeout_sec=timeout_sec)
    except Exception as e:
        logger.exception("login failed")
        return _err(e)


@mcp.tool()
async def boss_login_status() -> dict:
    """检查当前 BOSS 直聘登录态是否有效。"""
    try:
        c = _new_collector()
        def _check():
            page = c._ensure_browser()
            page.goto("https://www.zhipin.com/web/geek/job", timeout=30000)
            import time as _t
            _t.sleep(2)
            logged_in = c._is_logged_in(page)
            c.close()
            return logged_in
        logged_in = await asyncio.to_thread(_check)
        return _ok(logged_in=logged_in,
                   message="已登录" if logged_in else "未登录（请调用 boss_login）")
    except Exception as e:
        return _err(e)


@mcp.tool()
async def boss_search_jobs(keyword: str, city: str = "北京", page: int = 1,
                           max_results: int = 30) -> dict:
    """搜索 BOSS 直聘职位。

    Args:
        keyword: 职位关键词，如 "产品经理"、"AI 前端"
        city: 城市名，如 "北京"、"上海"（常用城市已内置映射）
        page: 页码，从 1 开始
        max_results: 单页最多返回条数
    """
    try:
        def _search():
            c = _new_collector()
            try:
                return c.search_jobs(keyword, city, page=page, max_results=max_results)
            finally:
                c.close()
        jobs = await asyncio.to_thread(_search)
        if jobs and "error" in jobs[0]:
            return _err(jobs[0]["error"], detail=jobs[0])
        return _ok(keyword=keyword, city=city, page=page, count=len(jobs), jobs=jobs)
    except Exception as e:
        logger.exception("search_jobs failed")
        return _err(e)


@mcp.tool()
async def boss_get_job_detail(url: str) -> dict:
    """抓取职位详情（JD 全文、任职要求、福利、公司信息）。

    Args:
        url: 职位详情链接，如 https://www.zhipin.com/job_detail/xxxx.html
            或相对路径 job_detail/xxxx.html
    """
    try:
        def _detail():
            c = _new_collector()
            try:
                return c.get_job_detail(url)
            finally:
                c.close()
        detail = await asyncio.to_thread(_detail)
        return _ok(**detail)
    except Exception as e:
        logger.exception("get_job_detail failed")
        return _err(e)


@mcp.tool()
async def boss_search_companies(keyword: str, page: int = 1, max_results: int = 20) -> dict:
    """搜索公司（名称、行业、规模、在招职位数、主页链接）。"""
    try:
        def _companies():
            c = _new_collector()
            try:
                return c.search_companies(keyword, page=page, max_results=max_results)
            finally:
                c.close()
        companies = await asyncio.to_thread(_companies)
        return _ok(keyword=keyword, page=page, count=len(companies), companies=companies)
    except Exception as e:
        logger.exception("search_companies failed")
        return _err(e)


@mcp.tool()
async def boss_get_company_jobs(company_url: str, max_results: int = 30) -> dict:
    """抓取某公司主页的在招职位列表。

    Args:
        company_url: 公司主页链接，如 https://www.zhipin.com/gongsi/xxxx.html
    """
    try:
        def _jobs():
            c = _new_collector()
            try:
                return c.get_company_jobs(company_url, max_results=max_results)
            finally:
                c.close()
        jobs = await asyncio.to_thread(_jobs)
        return _ok(company_url=company_url, count=len(jobs), jobs=jobs)
    except Exception as e:
        logger.exception("get_company_jobs failed")
        return _err(e)


@mcp.tool()
async def boss_collect_batch(keyword: str, city: str = "北京", pages: int = 2,
                             out_path: str = "") -> dict:
    """批量采集：抓取多页职位并追加保存为 JSONL 文件。

    默认保存到 tools/boss-mcp/storage/jobs.jsonl，可指定自定义路径。

    Args:
        keyword: 职位关键词
        city: 城市名
        pages: 抓取页数（建议 1-3，避免高频触发风控）
        out_path: 输出文件路径（默认 storage/jobs.jsonl）
    """
    try:
        path = out_path or str(STORAGE_DIR / "jobs.jsonl")
        def _batch():
            return collect_batch(keyword, city, pages=pages,
                                 storage_state=str(STORAGE_STATE), out_path=path)
        result = await asyncio.to_thread(_batch)
        return _ok(**result)
    except Exception as e:
        logger.exception("collect_batch failed")
        return _err(e)


# ─────────────────────────── 入口 ───────────────────────────

def main():
    # 确保目录存在
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("boss-zhipin MCP server starting, storage=%s", STORAGE_DIR)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
