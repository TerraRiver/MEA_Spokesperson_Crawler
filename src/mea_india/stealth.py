"""浏览器属性修改与鼠标移动、滚轮滚动模拟。"""

from __future__ import annotations

import math
import random
import weakref
from playwright.sync_api import Locator, Page

# 记录每个页面当前鼠标所在的坐标，使用 WeakKeyDictionary 避免已关闭页面残留引用
_MOUSE_POS: weakref.WeakKeyDictionary[Page, tuple[float, float]] = weakref.WeakKeyDictionary()

# 页面初始化时注入的脚本：设置冻结的 languages 数组并处理 Notification 权限查询
# 注：navigator.webdriver 已由启动参数 --disable-blink-features=AutomationControlled 置为 false
STEALTH_INIT_SCRIPT = """
(() => {
    // 1. 在 Navigator 原型上返回同一个冻结数组，保证 navigator.languages === navigator.languages 为 true
    try {
        const langs = Object.freeze(['en-US', 'en']);
        Object.defineProperty(Object.getPrototypeOf(navigator), 'languages', {
            get: () => langs,
            configurable: true
        });
    } catch (e) {}

    // 2. 处理 Notification 权限查询（绑定 this，并将 'default' 映射为标准状态 'prompt'）
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


def _clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def human_move_mouse(
    page: Page,
    target_x: float,
    target_y: float,
    min_steps: int = 14,
    max_steps: int = 38,
) -> tuple[float, float] | None:
    """从上一次记录的鼠标坐标出发，按三阶贝塞尔曲线分步移动鼠标至目标位置（全程限制在视口内）。"""
    try:
        viewport = page.viewport_size or {"width": 1400, "height": 1000}
        vw, vh = float(viewport["width"]), float(viewport["height"])
        margin = 20.0

        target_x = _clamp(target_x, margin, vw - margin)
        target_y = _clamp(target_y, margin, vh - margin)

        start_x, start_y = _MOUSE_POS.get(
            page, (random.uniform(vw * 0.30, vw * 0.65), random.uniform(vh * 0.25, vh * 0.55))
        )
        start_x = _clamp(start_x, margin, vw - margin)
        start_y = _clamp(start_y, margin, vh - margin)

        dist = math.hypot(target_x - start_x, target_y - start_y)
        steps = max(min_steps, min(max_steps, int(dist / 14) + random.randint(-3, 5)))

        offset_scale = max(18.0, dist * 0.24)
        ctrl1_x = _clamp(
            start_x + (target_x - start_x) * random.uniform(0.2, 0.4) + random.uniform(-offset_scale, offset_scale),
            margin,
            vw - margin,
        )
        ctrl1_y = _clamp(
            start_y + (target_y - start_y) * random.uniform(0.2, 0.4) + random.uniform(-offset_scale, offset_scale),
            margin,
            vh - margin,
        )
        ctrl2_x = _clamp(
            start_x + (target_x - start_x) * random.uniform(0.6, 0.8) + random.uniform(-offset_scale, offset_scale),
            margin,
            vw - margin,
        )
        ctrl2_y = _clamp(
            start_y + (target_y - start_y) * random.uniform(0.6, 0.8) + random.uniform(-offset_scale, offset_scale),
            margin,
            vh - margin,
        )

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

            cur_x = _clamp(cur_x, margin, vw - margin)
            cur_y = _clamp(cur_y, margin, vh - margin)
            page.mouse.move(cur_x, cur_y)
            page.wait_for_timeout(random.uniform(3.5, 9.5) + raw_t * 4.0)

        if dist > 120 and random.random() < 0.30:
            over_x = _clamp(target_x + random.uniform(-5.5, 5.5), margin, vw - margin)
            over_y = _clamp(target_y + random.uniform(-4.5, 4.5), margin, vh - margin)
            page.mouse.move(over_x, over_y, steps=random.randint(2, 4))
            page.wait_for_timeout(random.randint(25, 65))
            page.mouse.move(target_x, target_y, steps=random.randint(2, 4))

        _MOUSE_POS[page] = (target_x, target_y)
        return target_x, target_y
    except Exception:
        return None


def human_reset_gaze(page: Page) -> tuple[float, float] | None:
    """将鼠标移回页面中上方区域并更新坐标记录。"""
    try:
        viewport = page.viewport_size or {"width": 1400, "height": 1000}
        vw, vh = float(viewport["width"]), float(viewport["height"])
        reset_x = random.uniform(vw * 0.35, vw * 0.60)
        reset_y = random.uniform(vh * 0.25, vh * 0.45)
        return human_move_mouse(page, reset_x, reset_y, min_steps=10, max_steps=20)
    except Exception:
        return None


def human_micro_drift(page: Page) -> None:
    """在当前坐标附近随机移动鼠标 1~3 像素。"""
    try:
        viewport = page.viewport_size or {"width": 1400, "height": 1000}
        vw, vh = float(viewport["width"]), float(viewport["height"])
        cur_x, cur_y = _MOUSE_POS.get(page, (vw * 0.45, vh * 0.35))
        new_x = _clamp(cur_x + random.gauss(0, 1.6), 80.0, vw - 80.0)
        new_y = _clamp(cur_y + random.gauss(0, 1.2), 80.0, vh - 80.0)
        page.mouse.move(new_x, new_y)
        _MOUSE_POS[page] = (new_x, new_y)
    except Exception:
        pass


def human_idle_reading_gesture(
    page: Page,
    locator: Locator,
    text_len: int = 240,
    elapsed_sec: float = 0.0,
) -> None:
    """将鼠标移动至目标元素在视口内的可见文字区域，并按字数补充等待时间。"""
    try:
        viewport = page.viewport_size or {"width": 1400, "height": 1000}
        vw, vh = float(viewport["width"]), float(viewport["height"])

        try:
            box = locator.bounding_box(timeout=1000)
        except Exception:
            box = None

        moved = False
        if box and box["width"] > 40 and box["height"] > 20 and random.random() < 0.78:
            # 计算元素与当前视口的交集，确保目标点始终在窗口内部
            vis_left = _clamp(box["x"], 60.0, vw - 60.0)
            vis_right = _clamp(box["x"] + box["width"], 60.0, vw - 60.0)
            vis_top = _clamp(box["y"], 60.0, vh - 60.0)
            vis_bottom = _clamp(box["y"] + box["height"], 60.0, vh - 60.0)

            if (vis_right - vis_left) > 40 and (vis_bottom - vis_top) > 20:
                read_x = vis_left + (vis_right - vis_left) * random.uniform(0.18, 0.58)
                read_y = vis_top + min(vis_bottom - vis_top, 420.0) * random.uniform(0.25, 0.72)
                human_move_mouse(page, read_x, read_y, min_steps=10, max_steps=22)
                moved = True

        if not moved:
            human_reset_gaze(page)

        min_read_sec = min(1.8, max(0.5, text_len / random.uniform(180.0, 260.0)))
        remain_sec = min_read_sec - elapsed_sec
        if remain_sec > 0.1:
            remain_ms = int(remain_sec * 1000) + random.randint(60, 220)
            page.wait_for_timeout(remain_ms)
    except Exception:
        pass


def human_page_scroll(
    page: Page,
    target_distance: float = 500.0,
    fast_mode: bool = False,
) -> float:
    """使用 page.mouse.wheel() 分多次向下滚动页面，并在滚动间隙随机小幅移动鼠标或回滚。"""
    total_scrolled = 0.0
    try:
        viewport = page.viewport_size or {"width": 1400, "height": 1000}
        vh = float(viewport["height"])
        vw = float(viewport["width"])

        cur_x, cur_y = _MOUSE_POS.get(
            page, (random.uniform(vw * 0.35, vw * 0.62), random.uniform(vh * 0.30, vh * 0.58))
        )
        if (
            page not in _MOUSE_POS
            or cur_y > vh * 0.82
            or cur_y < vh * 0.15
            or cur_x < vw * 0.22
            or cur_x > vw * 0.78
        ):
            cur_x = random.uniform(vw * 0.35, vw * 0.62)
            cur_y = random.uniform(vh * 0.32, vh * 0.58)
            page.mouse.move(cur_x, cur_y, steps=random.randint(10, 18))
            _MOUSE_POS[page] = (cur_x, cur_y)

        goal = target_distance * random.uniform(0.85, 1.15)
        flick_count = 0
        next_pause_at = random.randint(4, 6)

        while total_scrolled < goal:
            remaining = goal - total_scrolled
            if fast_mode:
                step_scroll = random.uniform(280, 460)
                pause_ms = random.randint(18, 40)
            elif remaining > 600:
                step_scroll = random.uniform(140, 240)
                pause_ms = random.randint(30, 68)
            elif remaining > 220:
                step_scroll = random.uniform(85, 145)
                pause_ms = random.randint(45, 95)
            else:
                step_scroll = max(40.0, remaining * random.uniform(0.65, 1.0))
                pause_ms = random.randint(65, 130)

            if random.random() < 0.60:
                cur_x = _clamp(cur_x + random.gauss(0, 1.6), 120.0, vw - 120.0)
                cur_y = _clamp(cur_y + random.gauss(0, 1.2), 120.0, vh - 120.0)
                page.mouse.move(cur_x, cur_y)
                _MOUSE_POS[page] = (cur_x, cur_y)

            page.mouse.wheel(0, step_scroll)
            total_scrolled += step_scroll
            flick_count += 1
            page.wait_for_timeout(pause_ms)

            if not fast_mode and flick_count >= next_pause_at:
                next_pause_at += random.randint(4, 6)
                if random.random() < 0.35:
                    page.wait_for_timeout(random.randint(120, 280))

        if not fast_mode and flick_count > 0 and random.random() < 0.25:
            tiny_over = random.uniform(25, 55)
            page.mouse.wheel(0, tiny_over)
            page.wait_for_timeout(random.randint(60, 120))
            back_delta = -tiny_over * random.uniform(0.75, 1.15)
            page.mouse.wheel(0, back_delta)
            total_scrolled += tiny_over + back_delta
            page.wait_for_timeout(random.randint(50, 100))
    except Exception:
        pass
    return total_scrolled


def human_browse_page(page: Page, content_selector: str | None = None) -> None:
    """在页面打开后分多次滚动鼠标滚轮，并将鼠标移动至正文区域或页面中上方停留。"""
    try:
        human_page_scroll(page, target_distance=random.uniform(260.0, 480.0))
        if content_selector:
            loc = page.locator(content_selector).first
            human_idle_reading_gesture(page, loc, text_len=240, elapsed_sec=0.0)
        else:
            human_reset_gaze(page)
    except Exception:
        pass
