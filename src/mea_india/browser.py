"""Playwright 浏览器封装：单个浏览器会话、指纹隐匿、生物力学拟真交互、限速与接口响应捕获。"""

import os
import random
import sys
import time
from pathlib import Path

from playwright.sync_api import (
    Error as BrowserError,
    Response,
    TimeoutError as BrowserTimeoutError,
    sync_playwright,
)

from .config import BASE_URL, DELAY_RANGE
from .stealth import STEALTH_INIT_SCRIPT, human_browse_page, human_micro_drift, human_reset_gaze


def _default_user_agent() -> str:
    """生成与当前操作系统平台一致的桌面 Chrome User-Agent，避免 navigator.platform 与 UA 冲突。"""
    if sys.platform.startswith("win"):
        platform_part = "Windows NT 10.0; Win64; x64"
    elif sys.platform.startswith("linux"):
        platform_part = "X11; Linux x86_64"
    else:
        platform_part = "Macintosh; Intel Mac OS X 10_15_7"
    return (
        f"Mozilla/5.0 ({platform_part}) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
    )


def _browser_args() -> list[str]:
    """构建浏览器启动参数：仅在 Linux 环境下附加 --no-sandbox / --disable-dev-shm-usage。"""
    args = ["--disable-blink-features=AutomationControlled"]
    if sys.platform.startswith("linux"):
        args.extend(["--no-sandbox", "--disable-dev-shm-usage"])
    return args


USER_AGENT = _default_user_agent()
BROWSER_ARGS = _browser_args()

_FETCH_JS = """
async (url) => {
    try {
        const r = await fetch(url, {credentials: 'same-origin'});
        const text = await r.text();
        return {status: r.status, text: text};
    } catch (e) {
        return {status: -1, text: String(e)};
    }
}
"""


def _default_chrome_path() -> str | None:
    """探测本机安装的 Google Chrome 可执行文件路径。"""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


class SelectorTimeoutError(BrowserTimeoutError):
    """页面导航已完成，但等待目标 CSS 选择器超时。"""


class Browser:
    def __init__(self, headless: bool = True, timeout: int = 40, simulate_human: bool = True):
        self.timeout_ms = timeout * 1000
        self.simulate_human = simulate_human
        self._last_request = 0.0
        self._responses: list[Response] = []
        self._in_fetch = False
        self._pw = None
        self._browser = None
        self._context = None

        try:
            self._pw = sync_playwright().start()
            self._browser = self._launch_browser(headless=headless)
            self._context = self._browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1400, "height": 1000},
                locale="en-US",
            )
            self._context.add_init_script(STEALTH_INIT_SCRIPT)
            self.page = self._context.new_page()
            self.page.set_default_timeout(self.timeout_ms)
            self.page.set_default_navigation_timeout(self.timeout_ms)
            self.page.on("response", self._on_response)
        except Exception:
            self.close()
            raise

    def _launch_browser(self, headless: bool):
        """优先启动本机真实 Google Chrome 以获得完整浏览器指纹，不可用时回退至 Playwright Chromium。"""
        chrome_path = _default_chrome_path()
        if chrome_path:
            try:
                return self._pw.chromium.launch(
                    executable_path=chrome_path,
                    headless=headless,
                    args=BROWSER_ARGS,
                )
            except Exception:
                pass
        return self._pw.chromium.launch(headless=headless, args=BROWSER_ARGS)

    def _on_response(self, response: Response):
        if (
            not self._in_fetch
            and response.status == 200
            and response.request.resource_type in ("xhr", "fetch")
        ):
            self._responses.append(response)

    def close(self):
        try:
            if self._context is not None:
                self._context.close()
        finally:
            try:
                if self._browser is not None:
                    self._browser.close()
            finally:
                if self._pw is not None:
                    self._pw.stop()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def page_source(self) -> str:
        return self.page.content()

    def polite_wait(self):
        """保证与上一次请求间隔 2—5 秒（随机）。"""
        gap = random.uniform(*DELAY_RANGE)
        elapsed = time.monotonic() - self._last_request
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_request = time.monotonic()

    def open(self, path_or_url: str, wait_css: str | None = None) -> str:
        """打开页面；wait_css 给定时等待该元素挂载到 DOM，并执行生物力学拟真浏览动作。"""
        url = path_or_url if path_or_url.startswith("http") else BASE_URL + path_or_url
        self.polite_wait()
        self._responses.clear()
        wait_until = "domcontentloaded" if wait_css else "load"
        self.page.goto(url, wait_until=wait_until)
        if wait_css:
            try:
                self.page.wait_for_selector(wait_css, state="attached", timeout=self.timeout_ms)
            except BrowserTimeoutError as e:
                raise SelectorTimeoutError(str(e)) from e
        content = self.page.content()
        if self.simulate_human:
            human_browse_page(self.page, content_selector=wait_css)
        return content

    def fetch(self, url: str) -> tuple[int, str]:
        """在当前页面内发起同源请求（沿用浏览器 cookie），遇 429/503 自动退避重试一次。"""
        for attempt in range(2):
            self.polite_wait()
            if self.simulate_human and random.random() < 0.35:
                human_micro_drift(self.page)
            self._in_fetch = True
            try:
                res = self.page.evaluate(_FETCH_JS, url)
            finally:
                self._in_fetch = False
            status, text = res["status"], res["text"]
            if status in (429, 503) and attempt == 0:
                cooldown = random.uniform(15.0, 25.0)
                print(f"  [!] 触发频率限制或服务繁忙 (HTTP {status})，暂停 {cooldown:.1f}s 后重试...", flush=True)
                time.sleep(cooldown)
                if self.simulate_human:
                    human_reset_gaze(self.page)
                continue
            return status, text
        return status, text

    def captured_response(self, url_part: str) -> str | None:
        """从当前页面导航期间捕获的响应中取接口响应原文，不额外发请求。"""
        matched = None
        for resp in self._responses:
            if url_part in resp.url and resp.status == 200:
                matched = resp
        if matched is None:
            return None
        try:
            return matched.text()
        except Exception:
            return None
