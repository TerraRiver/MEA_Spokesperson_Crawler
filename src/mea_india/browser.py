"""Selenium 浏览器封装：单个 Chrome 会话、限速、页面内请求、从网络日志取接口原始响应。"""

import json
import random
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config import BASE_URL, DELAY_RANGE

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)

_FETCH_JS = """
const [url, done] = arguments;
fetch(url, {credentials: 'same-origin'})
  .then(r => r.text().then(t => done({status: r.status, text: t})))
  .catch(e => done({status: -1, text: String(e)}));
"""


class Browser:
    def __init__(self, headless: bool = True, timeout: int = 40):
        opts = webdriver.ChromeOptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument(f"--user-agent={USER_AGENT}")
        opts.add_argument("--window-size=1400,1000")
        opts.add_argument("--lang=en-US")
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        self.driver = webdriver.Chrome(options=opts)
        self.driver.set_page_load_timeout(timeout)
        self.driver.set_script_timeout(timeout)
        self.timeout = timeout
        self._last_request = 0.0

    def close(self):
        self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def polite_wait(self):
        """保证与上一次请求间隔 2—5 秒（随机）。"""
        gap = random.uniform(*DELAY_RANGE)
        elapsed = time.monotonic() - self._last_request
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_request = time.monotonic()

    def open(self, path_or_url: str, wait_css: str | None = None):
        """打开页面；wait_css 给定时等待该元素出现且有内容。"""
        url = path_or_url if path_or_url.startswith("http") else BASE_URL + path_or_url
        self.polite_wait()
        self.drain_logs()
        self.driver.get(url)
        if wait_css:
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_css))
            )
        return self.driver.page_source

    def fetch(self, url: str) -> tuple[int, str]:
        """在当前页面内发起同源请求（沿用浏览器 cookie），返回 (状态码, 文本)。"""
        self.polite_wait()
        res = self.driver.execute_async_script(_FETCH_JS, url)
        return res["status"], res["text"]

    def drain_logs(self):
        try:
            return self.driver.get_log("performance")
        except Exception:
            return []

    def captured_response(self, url_part: str) -> str | None:
        """从 Chrome 网络日志里取页面自身请求过的接口响应原文，不额外发请求。"""
        request_id = None
        for entry in self.drain_logs():
            msg = json.loads(entry["message"])["message"]
            if msg.get("method") == "Network.responseReceived":
                resp = msg["params"]["response"]
                if url_part in resp.get("url", "") and resp.get("status") == 200:
                    request_id = msg["params"]["requestId"]
        if request_id is None:
            return None
        try:
            body = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
        except Exception:
            return None
        if body.get("base64Encoded"):
            import base64

            return base64.b64decode(body["body"]).decode("utf-8")
        return body["body"]
