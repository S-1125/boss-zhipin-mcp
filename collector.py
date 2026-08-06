"""
BOSS 直聘 (zhipin.com) 数据采集器
=================================
基于 Playwright + 系统 Chrome 的本地采集工具，供个人学习/研究使用。

设计要点:
- 复用系统 Chrome (channel="chrome")，无需下载浏览器二进制
- storage_state 持久化登录态：首次手动登录一次，后续免登录
- 内置随机节流(1-3s)与重试，降低风控触发概率
- 所有采集均为低频、个人使用；请遵守平台条款与法律法规

合规声明:
- 仅限个人学习/研究/产品原型验证，禁止用于商业分发、二次转售
- 请控制采集频率，尊重 robots.txt 与平台服务条款
- 采集数据仅保存在本地 (storage/ 目录)，不对外传输

依赖: pip install playwright  (并使用系统 Chrome)
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PWTimeout

logger = logging.getLogger("boss")

BASE_URL = "https://www.zhipin.com"


# ─────────────────────────── 数据结构 ───────────────────────────

@dataclass
class JobItem:
    title: str = ""
    company: str = ""
    salary: str = ""
    city: str = ""
    experience: str = ""       # 经验要求
    education: str = ""        # 学历要求
    tags: list = field(default_factory=list)   # 技能标签
    job_id: str = ""           # 职位 ID
    url: str = ""
    update_time: str = ""      # 发布时间/更新时间

    def to_dict(self):
        return asdict(self)


@dataclass
class JobDetail:
    job_id: str = ""
    title: str = ""
    salary: str = ""
    company: str = ""
    company_url: str = ""
    address: str = ""          # 工作地点
    experience: str = ""
    education: str = ""
    job_type: str = ""         # 全职/实习/兼职
    description: str = ""      # 职位描述全文
    requirements: str = ""     # 任职要求全文
    welfare: list = field(default_factory=list)   # 福利标签
    skills: list = field(default_factory=list)
    url: str = ""

    def to_dict(self):
        return asdict(self)


# ─────────────────────────── 采集器 ───────────────────────────

class BossCollector:
    """BOSS 直聘采集器。所有公开方法均为同步调用。"""

    def __init__(self, storage_state: Optional[str] = None, headless: bool = False):
        self.storage_state = storage_state
        self.headless = headless
        self._pw = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    # ---- 生命周期 ----
    def _ensure_browser(self) -> Page:
        if self._page and not self._page.is_closed():
            return self._page
        self._pw = sync_playwright().start()
        launch_kwargs = {"channel": "chrome", "headless": self.headless}
        if self.storage_state and Path(self.storage_state).exists():
            launch_kwargs["storage_state"] = self.storage_state
        self._browser = self._pw.chromium.launch(**launch_kwargs)
        ctx = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        )
        self._page = ctx.new_page()
        return self._page

    def close(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._page = None

    # ---- 工具方法 ----
    @staticmethod
    def _delay(min_s=1.0, max_s=3.0):
        time.sleep(random.uniform(min_s, max_s))

    def _get_texts(self, page: Page, selector: str) -> list[str]:
        try:
            els = page.query_selector_all(selector)
            return [e.inner_text().strip() for e in els if e.inner_text().strip()]
        except Exception:
            return []

    # ---- 登录 ----
    def login(self, timeout_sec: int = 300) -> dict:
        """打开浏览器窗口，用户手动扫码/验证码登录，成功后保存 storage_state。"""
        if self.storage_state and Path(self.storage_state).exists():
            # 复用已有登录态，验证是否仍有效
            self._page = self._ensure_browser()
            self._page.goto(f"{BASE_URL}/web/geek/job", timeout=30000)
            self._delay(2, 4)
            if self._is_logged_in(self._page):
                return {"status": "ok", "message": "已有有效登录态，无需重新登录"}
            logger.info("登录态已失效，需要重新登录")
            self.close()

        page = self._ensure_browser()
        page.goto(f"{BASE_URL}/web/geek/job", timeout=60000)
        logger.info("请在打开的浏览器窗口中完成登录（扫码或验证码）...")
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            self._delay(3, 5)
            try:
                if self._is_logged_in(page):
                    if self.storage_state:
                        ctx = page.context
                        ctx.storage_state(path=self.storage_state)
                    return {"status": "ok", "message": f"登录成功，登录态已保存至 {self.storage_state}"}
            except Exception:
                continue
        return {"status": "timeout", "message": f"等待登录超时（{timeout_sec}s），请重试"}

    @staticmethod
    def _is_logged_in(page: Page) -> bool:
        """通过页面特征判断登录态。BOSS 未登录时会跳转登录引导。"""
        url = page.url
        if "login" in url or "passport" in url:
            return False
        # 已登录特征：页面出现"职位"列表或右上角头像/用户名
        try:
            for sel in [
                ".job-list-box",            # 职位列表容器
                ".job-card-wrapper",        # 职位卡片
                ".user-nav",                # 用户导航
                ".job-search",              # 搜索区
            ]:
                if page.query_selector(sel):
                    return True
        except Exception:
            pass
        return False

    # ---- 职位搜索 ----
    def search_jobs(self, keyword: str, city: str = "北京", page: int = 1,
                    max_results: int = 30) -> list[dict]:
        """搜索职位，返回结构化列表。city 传城市名（如 '北京'、'上海'）。"""
        page = self._ensure_browser()
        from urllib.parse import quote
        city_code = CITY_MAP.get(city, "")
        url = (f"{BASE_URL}/web/geek/job?query={quote(keyword)}"
               f"&city={city_code}&page={page}")
        page.goto(url, timeout=45000)
        self._delay(2, 4)

        # 风控检测：出现验证码页
        if page.query_selector("#captcha") or "验证" in (page.title() or ""):
            return [{"error": "触发风控验证，请稍后重试或先手动登录", "url": page.url}]

        results: list[dict] = []
        # BOSS 职位卡片选择器（随改版可能变化，多级 fallback）
        card_sels = [
            ".job-card-wrapper",
            ".job-list-box li",
            ".job-card",
        ]
        cards = []
        for sel in card_sels:
            cards = page.query_selector_all(sel)
            if cards:
                break

        for card in cards[:max_results]:
            try:
                item = JobItem()
                # 标题
                a = card.query_selector("a.job-card-left, .job-title, a[href*='job_detail']")
                if a:
                    item.title = (a.inner_text() or "").strip()
                    href = a.get_attribute("href") or ""
                    if "job_detail" in href:
                        item.job_id = href.split("job_detail/")[-1].split(".html")[0]
                        item.url = BASE_URL + href if href.startswith("/") else href
                # 公司
                c = card.query_selector(".company-name, .company-info a, .job-card-right .company-name")
                if c:
                    item.company = (c.inner_text() or "").strip()
                # 薪资
                s = card.query_selector(".salary, .job-card-left .salary")
                if s:
                    item.salary = (s.inner_text() or "").strip()
                # 标签（经验/学历/城市）
                tags = []
                for t in card.query_selector_all(".tag-list li, .job-info .tag, .job-card-footer .tag"):
                    txt = (t.inner_text() or "").strip()
                    if txt:
                        tags.append(txt)
                item.tags = tags[:8]
                for t in tags:
                    if "经验" in t or any(k in t for k in ("应届", "在校", "经验")):
                        item.experience = t
                    if any(k in t for k in ("本科", "硕士", "博士", "大专", "学历")):
                        item.education = t
                item.city = city
                if item.title:
                    results.append(item.to_dict())
            except Exception as e:
                logger.warning("解析卡片失败: %s", e)
                continue

        if not results:
            # 兜底：抓取页面文本片段，便于排查选择器变化
            body_txt = page.inner_text("body")[:500] if page.query_selector("body") else ""
            results = [{"error": "未解析到职位卡片，页面结构可能已改版", "page_snippet": body_txt[:300]}]
        return results

    # ---- 职位详情 ----
    def get_job_detail(self, url: str) -> dict:
        """抓取职位详情页：JD 全文、要求、福利。url 可以是完整链接或 job_detail/xxx.html。"""
        if url.startswith("/"):
            url = BASE_URL + url
        page = self._ensure_browser()
        page.goto(url, timeout=45000)
        self._delay(2, 4)

        detail = JobDetail(url=url)
        m = url.split("job_detail/")
        if len(m) > 1:
            detail.job_id = m[1].split(".html")[0]

        # 标题 + 薪资
        t = page.query_selector("h1.name, .job-title h1, .name")
        if t:
            detail.title = (t.inner_text() or "").strip()
        s = page.query_selector(".salary, .job-banner .salary, .salary-text")
        if s:
            detail.salary = (s.inner_text() or "").strip()

        # 信息标签（经验/学历/类型/地点）
        info_sels = [".job-banner .info-primary .text", ".job-detail .info-primary .text",
                     ".job-sec .job-sec-text .text"]
        info_texts = []
        for sel in info_sels:
            info_texts = self._get_texts(page, sel)
            if info_texts:
                break
        # 另一种结构: 每个 <p> 包含 经验/学历/地点
        for p in page.query_selector_all(".job-banner .info-primary p, .job-primary-info p"):
            txt = (p.inner_text() or "").strip()
            if txt:
                info_texts.append(txt)
        for txt in info_texts:
            if any(k in txt for k in ("经验", "应届", "在校")):
                detail.experience = txt
            elif any(k in txt for k in ("本科", "硕士", "博士", "大专", "学历")):
                detail.education = txt
            elif any(k in txt for k in ("全职", "实习", "兼职", "校招")):
                detail.job_type = txt
            else:
                detail.address = txt

        # 职位描述 + 任职要求
        secs = page.query_selector_all(".job-sec")
        for sec in secs:
            h3 = sec.query_selector("h3, .section-title")
            if not h3:
                continue
            head = (h3.inner_text() or "").strip()
            body = sec.query_selector(".job-sec-text, .text")
            body_txt = (body.inner_text() or "").strip() if body else ""
            if "描述" in head or "职责" in head:
                detail.description = body_txt
            elif "要求" in head or "任职" in head:
                detail.requirements = body_txt
            elif not detail.description:
                detail.description = body_txt

        # 福利标签
        detail.welfare = [w.strip() for w in self._get_texts(page, ".job-banner .tag-list li, .welfare-tag, .job-sec .tag-list li") if w.strip()][:20]

        # 公司信息
        c = page.query_selector(".company-info .name, .job-banner .company-name, a.company-name")
        if c:
            detail.company = (c.inner_text() or "").strip()
            href = c.get_attribute("href") or ""
            if href:
                detail.company_url = BASE_URL + href if href.startswith("/") else href

        return detail.to_dict()

    # ---- 公司搜索 ----
    def search_companies(self, keyword: str, page: int = 1, max_results: int = 20) -> list[dict]:
        """搜索公司，返回公司列表（名称、行业、规模、在招数、主页链接）。"""
        page_obj = self._ensure_browser()
        from urllib.parse import quote
        url = f"{BASE_URL}/web/geek/company?query={quote(keyword)}&page={page}"
        page_obj.goto(url, timeout=45000)
        self._delay(2, 4)

        results = []
        sels = ["li.company-item", ".company-list li", ".company-card"]
        cards = []
        for sel in sels:
            cards = page_obj.query_selector_all(sel)
            if cards:
                break
        for card in cards[:max_results]:
            try:
                name_el = card.query_selector(".company-name, .name")
                if not name_el:
                    continue
                name = (name_el.inner_text() or "").strip()
                href = name_el.get_attribute("href") or ""
                info = card.query_selector(".company-info, .info")
                info_txt = (info.inner_text() or "").strip().replace("\n", " | ") if info else ""
                jobs_el = card.query_selector(".job-num, .position-num, a[href*='job']")
                jobs_txt = (jobs_el.inner_text() or "").strip() if jobs_el else ""
                results.append({
                    "name": name,
                    "info": info_txt,
                    "jobs_text": jobs_txt,
                    "company_url": BASE_URL + href if href.startswith("/") else href,
                })
            except Exception as e:
                logger.warning("解析公司卡片失败: %s", e)
        return results

    # ---- 公司主页在招职位 ----
    def get_company_jobs(self, company_url: str, max_results: int = 30) -> list[dict]:
        """抓取公司主页的在招职位列表。"""
        page = self._ensure_browser()
        if company_url.startswith("/"):
            company_url = BASE_URL + company_url
        page.goto(company_url, timeout=45000)
        self._delay(2, 4)
        results = []
        sels = [".job-list-box li", ".position-list li", "li.job-item"]
        cards = []
        for sel in sels:
            cards = page.query_selector_all(sel)
            if cards:
                break
        for card in cards[:max_results]:
            try:
                a = card.query_selector("a.job-title, .job-name a, a[href*='job_detail']")
                if not a:
                    continue
                title = (a.inner_text() or "").strip()
                href = a.get_attribute("href") or ""
                salary = ""
                s = card.query_selector(".salary, .job-salary")
                if s:
                    salary = (s.inner_text() or "").strip()
                tags = [t.strip() for t in self._get_texts(card, ".tag, .job-tags li")][:6]
                results.append({
                    "title": title,
                    "salary": salary,
                    "tags": tags,
                    "url": BASE_URL + href if href.startswith("/") else href,
                })
            except Exception:
                continue
        return results


# 常用城市代码（BOSS 直聘 web 端 city 参数）
CITY_MAP = {
    "北京": "101010100", "上海": "101020100", "广州": "101280100", "深圳": "101280600",
    "杭州": "101210100", "南京": "101190100", "苏州": "101190400", "成都": "101270100",
    "武汉": "101200100", "西安": "101110100", "重庆": "101040100", "天津": "101030100",
    "长沙": "101250100", "郑州": "101180100", "青岛": "101120200", "厦门": "101230200",
    "合肥": "101220100", "济南": "101120100", "福州": "101230100", "东莞": "101281600",
    "佛山": "101280800", "珠海": "101280700", "宁波": "101210400", "无锡": "101190200",
    "南昌": "101240100", "昆明": "101290100", "贵阳": "101260100", "哈尔滨": "101050100",
    "沈阳": "101070100", "大连": "101070200", "长春": "101060100", "石家庄": "101090100",
    "太原": "101100100", "兰州": "101160100", "南宁": "101300100", "海口": "101310100",
}


def collect_batch(keyword: str, city: str, pages: int = 1, storage_state: str = "storage/state.json",
                  out_path: str = "storage/jobs.jsonl") -> dict:
    """批量采集示例：抓取 N 页职位并落盘 JSONL。"""
    c = BossCollector(storage_state=storage_state)
    all_jobs = []
    try:
        for p in range(1, pages + 1):
            jobs = c.search_jobs(keyword, city, page=p)
            all_jobs.extend(jobs)
            c._delay(2, 4)
    finally:
        c.close()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as f:
        for j in all_jobs:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")
    return {"total": len(all_jobs), "file": out_path, "sample": all_jobs[:3]}
