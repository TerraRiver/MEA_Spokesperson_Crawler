"""浏览器自动化指纹隐匿与生物力学人类行为模拟（同步 Playwright 版）。

整合自 X_Crawler 的反爬与拟真策略：
1. STEALTH_INIT_SCRIPT：抹除 navigator.webdriver、伪造 languages 与 window.chrome.runtime、修复 Notification 权限查询。
2. 跨操作连续鼠标坐标记忆（_MOUSE_POS），杜绝从 (0, 0) 瞬移。
3. 双控制点三阶贝塞尔曲线 + Ease-Out 非线性减速 + 衰减生理微颤抖 + 偶发过冲（Overshoot）。
4. 分拨次变速滚轮浏览（page.mouse.wheel）+ 手握鼠标联动微漂移 + 过滚回拨微调。
"""

from __future__ import annotations

import math
import random
import weakref
from playwright.sync_api import Locator, Page

# 记录每个页面当前鼠标所在的坐标，使用 WeakKeyDictionary 避免已关闭页面残留引用
_MOUSE_POS: weakref.WeakKeyDictionary[Page, tuple[float, float]] = weakref.WeakKeyDictionary()

# 隐藏浏览器自动化指纹的初始化 JS 补丁
STEALTH_INIT_SCRIPT = """
(() => {
    // 1. 彻底抹除 navigator.webdriver 标记
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // 2. 伪造正常的英文语言列表特征（与印度外交部英文站点及 locale="en-US" 匹配）
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

    // 3. 确保 window.chrome 对象完整（模拟正常安装的 Chrome 扩展运行环境）
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
            PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' }
        };
    }

    // 4. 修复自动化环境下 Notification 权限查询异常（绑定 this，并将 Notification.permission 的 'default' 映射为 W3C 标准的 'prompt'）
    if (window.navigator.permissions && window.navigator.permissions.query) {
        const originalQuery = window.navigator.permissions.query.bind(window.navigator.permissions);
        window.navigator.permissions.query = (parameters) => (
            parameters && parameters.name === 'notifications'
                ? Promise.resolve({
                    state: Notification.permission === 'default' ? 'prompt' : Notification.permission
                })
                : originalQuery(parameters)
        );
    }
})();
"""


def human_move_mouse(
    page: Page,
    target_x: float,
    target_y: float,
    min_steps: int = 14,
    max_steps: int = 38,
) -> tuple[float, float]:
    """沿双控制点三阶贝塞尔曲线将鼠标从上次停留位置平滑移至目标坐标。

    融合生物力学特征：
    - 连续起点（_MOUSE_POS）
    - 双控制点三阶贝塞尔弧线
    - Ease-Out 减速瞄准：t = 1 - (1 - raw_t)^2.2
    - 随进度衰减的高斯生理微颤抖（Jitter）
    - 长距离（>120px）30% 概率触发滑过头再微调拉回（Overshoot）
    """
    viewport = page.viewport_size or {"width": 1400, "height": 1000}
    vw, vh = viewport["width"], viewport["height"]
    start_x, start_y = _MOUSE_POS.get(
        page, (random.uniform(vw * 0.30, vw * 0.65), random.uniform(vh * 0.25, vh * 0.55))
    )

    dist = math.hypot(target_x - start_x, target_y - start_y)
    steps = max(min_steps, min(max_steps, int(dist / 14) + random.randint(-3, 5)))

    offset_scale = max(18.0, dist * 0.24)
    ctrl1_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.4) + random.uniform(-offset_scale, offset_scale)
    ctrl1_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.4) + random.uniform(-offset_scale, offset_scale)
    ctrl2_x = start_x + (target_x - start_x) * random.uniform(0.6, 0.8) + random.uniform(-offset_scale, offset_scale)
    ctrl2_y = start_y + (target_y - start_y) * random.uniform(0.6, 0.8) + random.uniform(-offset_scale, offset_scale)

    for i in range(1, steps + 1):
        raw_t = i / steps
        t = 1.0 - math.pow(1.0 - raw_t, 2.2)
        u = 1.0 - t

        cur_x = (u**3) * start_x + 3 * (u**2) * t * ctrl1_x + 3 * u * (t**2) * ctrl2_x + (t**3) * target_x
        cur_y = (u**3) * start_y + 3 * (u**2) * t * ctrl1_y + 3 * u * (t**2) * ctrl2_y + (t**3) * target_y

        if i < steps:
            jitter = (1.0 - raw_t) * 1.6
            cur_x += random.gauss(0, jitter)
            cur_y += random.gauss(0, jitter)

        page.mouse.move(cur_x, cur_y)
        page.wait_for_timeout(random.uniform(3.5, 9.5) + raw_t * 4.0)

    if dist > 120 and random.random() < 0.30:
        over_x = target_x + random.uniform(-5.5, 5.5)
        over_y = target_y + random.uniform(-4.5, 4.5)
        page.mouse.move(over_x, over_y, steps=random.randint(2, 4))
        page.wait_for_timeout(random.randint(25, 65))
        page.mouse.move(target_x, target_y, steps=random.randint(2, 4))

    _MOUSE_POS[page] = (target_x, target_y)
    return target_x, target_y


def human_reset_gaze(page: Page) -> tuple[float, float] | None:
    """将鼠标沿自然弧线移回页面中上方阅读准备区并更新 _MOUSE_POS。"""
    try:
        viewport = page.viewport_size or {"width": 1400, "height": 1000}
        vw, vh = viewport["width"], viewport["height"]
        reset_x = random.uniform(vw * 0.35, vw * 0.60)
        reset_y = random.uniform(vh * 0.25, vh * 0.45)
        return human_move_mouse(page, reset_x, reset_y, min_steps=10, max_steps=20)
    except Exception:
        return None


def human_micro_drift(page: Page) -> None:
    """模拟手握鼠标静置或等待期间 1~3px 的生理微漂移。"""
    try:
        viewport = page.viewport_size or {"width": 1400, "height": 1000}
        vw, vh = viewport["width"], viewport["height"]
        cur_x, cur_y = _MOUSE_POS.get(page, (vw * 0.45, vh * 0.35))
        new_x = max(80.0, min(vw - 80.0, cur_x + random.gauss(0, 1.6)))
        new_y = max(80.0, min(vh - 80.0, cur_y + random.gauss(0, 1.2)))
        page.mouse.move(new_x, new_y)
        _MOUSE_POS[page] = (new_x, new_y)
    except Exception:
        pass


def human_browse_page(page: Page, content_selector: str | None = None) -> None:
    """模拟真人在打开列表页或文章详情页后的视线落点、指读微移与滚轮扫视动作。

    1. 若存在正文区域（content_selector），75% 概率将鼠标滑向正文偏左阅读区，否则复位至中上方阅读区；
    2. 使用真实 page.mouse.wheel() 分 2~4 拨次变速向下滚动浏览，60% 概率伴随 1~3px 手部微漂移；
    3. 25% 概率模拟“滚过头一点再轻轻往回拨一点”的视觉微调。
    所有动作均做异常隔离，确保不会影响已完成的页面抓取结果。
    """
    try:
        viewport = page.viewport_size or {"width": 1400, "height": 1000}
        vw, vh = viewport["width"], viewport["height"]

        moved = False
        if content_selector and random.random() < 0.75:
            try:
                loc = page.locator(content_selector).first
                box = loc.bounding_box(timeout=1000)
                if box and box["width"] > 40 and box["height"] > 20:
                    read_x = max(80.0, min(vw - 80.0, box["x"] + box["width"] * random.uniform(0.18, 0.58)))
                    read_y = max(80.0, min(vh - 80.0, box["y"] + min(box["height"], 420.0) * random.uniform(0.22, 0.68)))
                    human_move_mouse(page, read_x, read_y, min_steps=10, max_steps=22)
                    moved = True
            except Exception:
                pass

        if not moved:
            human_reset_gaze(page)

        cur_x, cur_y = _MOUSE_POS.get(page, (vw * 0.45, vh * 0.35))
        flicks = random.randint(2, 4)
        for idx in range(flicks):
            # 模拟加速-巡航-减速的分拨次滚轮距离
            if idx == 0:
                step_scroll = random.uniform(90, 160)
            elif idx == flicks - 1:
                step_scroll = random.uniform(45, 95)
            else:
                step_scroll = random.uniform(110, 210)

            if random.random() < 0.60:
                cur_x = max(100.0, min(vw - 100.0, cur_x + random.gauss(0, 1.5)))
                cur_y = max(100.0, min(vh - 100.0, cur_y + random.gauss(0, 1.1)))
                page.mouse.move(cur_x, cur_y)
                _MOUSE_POS[page] = (cur_x, cur_y)

            page.mouse.wheel(0, step_scroll)
            page.wait_for_timeout(random.randint(35, 85))

        if random.random() < 0.25:
            tiny_over = random.uniform(20, 45)
            page.mouse.wheel(0, tiny_over)
            page.wait_for_timeout(random.randint(50, 110))
            page.mouse.wheel(0, -tiny_over * random.uniform(0.75, 1.10))
            page.wait_for_timeout(random.randint(40, 90))
    except Exception:
        pass


def human_move_and_click(page: Page, locator: Locator) -> None:
    """高拟真度模拟真人鼠标轨迹并点击目标元素（贝塞尔弧线 + 悬停瞄准 + 真实按压时长）。"""
    try:
        box = locator.bounding_box(timeout=1000)
    except Exception:
        box = None

    if not box:
        locator.click()
        return

    target_x = box["x"] + box["width"] * random.uniform(0.30, 0.70)
    target_y = box["y"] + box["height"] * random.uniform(0.30, 0.70)
    human_move_mouse(page, target_x, target_y)

    # 悬停瞄准（80~220ms）+ 真实手指按压保持（50~130ms）
    page.wait_for_timeout(random.randint(80, 220))
    page.mouse.down()
    page.wait_for_timeout(random.randint(50, 130))
    page.mouse.up()
