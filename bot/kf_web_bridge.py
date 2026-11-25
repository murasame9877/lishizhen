"""Playwright 桥接：微信客服网页工作台 → 后端 /share/handle → 自动回复。

只处理客户（左侧）的新消息；忽略客服自己发出的消息。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "data" / "kf_web_profile"
EDGE_USER_DATA = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Edge" / "User Data"
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("SHARE_INGEST_TOKEN", "")
API = "http://127.0.0.1:8000/share/handle"
CUSTOMER_NAME = os.getenv("KF_CUSTOMER_NAME", "").strip()
SEEN_FILE = ROOT / "data" / "kf_seen.json"
IMAGE_DOM_LOG = ROOT / "data" / "logs" / "image_dom.log"
STATUS_FILE = ROOT / "data" / "run" / "bridge_status.json"


def call_api(payload: dict) -> str | None:
    try:
        response = httpx.post(
            API,
            headers={"X-Share-Token": TOKEN},
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        return response.json().get("reply")
    except Exception as exc:
        print("api error:", exc, flush=True)
        return None


def target_chat(desk):
    """默认跟随客服列表最新的会话；配置 KF_CUSTOMER_NAME 时固定该客户。"""
    items = desk.locator(".chat_item")
    if items.count() == 0:
        return None
    if CUSTOMER_NAME:
        named = desk.locator(".chat_item", has_text=CUSTOMER_NAME).first
        if named.count():
            return named
    return items.first


def chat_key(desk) -> str:
    items = desk.locator(".chat_item")
    if items.count() == 0:
        return ""
    try:
        return items.first.evaluate(
            "el => el.getAttribute('id') || el.getAttribute('data-id') || "
            "(el.innerText || '').split(String.fromCharCode(10))[0].slice(0, 40)"
        ) or ""
    except Exception:
        return ""


def click_target_chat(desk) -> str:
    item = target_chat(desk)
    if item is None:
        return ""
    label = ""
    try:
        label = (item.inner_text().splitlines() or [""])[0].strip()[:30]
    except Exception:
        pass
    item.click()
    desk.wait_for_timeout(1500)
    return label


def connect_desk(context):
    open_pages = [p for p in context.pages if not p.is_closed()]
    # 重连时优先复用已登录的工作台页面，避免把它导航回 /kf/ 导致重新扫码
    for candidate in open_pages:
        if "helpdesk" not in (candidate.url or ""):
            continue
        try:
            candidate.wait_for_selector(".chat_item", timeout=15000)
            label = click_target_chat(candidate)
            print("reuse workbench:", candidate.url, "chat=", label, flush=True)
            set_status("running")
            return candidate
        except Exception as exc:
            print(
                "reuse workbench failed:", type(exc).__name__, flush=True
            )

    page = open_pages[0] if open_pages else context.new_page()
    page.goto(
        "https://work.weixin.qq.com/kf/",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    print("admin:", page.url, page.title(), flush=True)

    desk = page
    for attempt in range(1, 4):
        try:
            page.wait_for_selector(".kfFrame_msgPop", timeout=20000)
            try:
                with context.expect_page(timeout=20000) as new_page:
                    page.click(".kfFrame_msgPop")
                desk = new_page.value
            except PlaywrightTimeoutError:
                desk = page

            print("desk:", desk.url, flush=True)
            desk.wait_for_selector(".chat_item", timeout=25000)
            label = click_target_chat(desk)
            print("workbench ready:", desk.url, "chat=", label, flush=True)
            set_status("running")
            return desk
        except Exception as exc:
            print("attempt", attempt, "not ready:", type(exc).__name__, flush=True)
            try:
                body = page.locator("body").inner_text(timeout=2000)
            except Exception:
                body = ""
            if "扫码" in body or "登录" in body:
                print(
                    "请在弹出的桥接 Edge 窗口扫码登录（最多 3 分钟）……",
                    flush=True,
                )
                set_status("login_required")
                alert_beeps()
                deadline = time.time() + 180
                while time.time() < deadline:
                    page.wait_for_timeout(3000)
                    try:
                        if page.locator(".kfFrame_msgPop").count():
                            print("检测到登录成功，继续", flush=True)
                            break
                        current = page.locator("body").inner_text(timeout=1000)
                        if "扫码" not in current and "登录" not in current:
                            print("登录页已消失，继续", flush=True)
                            break
                    except Exception:
                        pass
            else:
                page.wait_for_timeout(3000)

        try:
            page.goto(
                "https://work.weixin.qq.com/kf/helpdesk",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_selector(".chat_item", timeout=20000)
            label = click_target_chat(page)
            print("workbench ready:", page.url, "chat=", label, flush=True)
            set_status("running")
            return page
        except Exception as exc:
            print(
                "direct helpdesk attempt", attempt, "failed:",
                type(exc).__name__, flush=True,
            )
            page.wait_for_timeout(2000)

    raise RuntimeError("could not open helpdesk")


def send_reply(desk, text: str) -> bool:
    try:
        desk.locator("textarea.editor").first.fill(text)
        desk.locator("a.send_btn").first.click()
        desk.wait_for_timeout(1200)
        return True
    except Exception as exc:
        print("send failed:", type(exc).__name__, exc, flush=True)
        return False


def fetch_image(desk, src: str, locator=None) -> bytes | None:
    """优先取原始图片；取不到时退化为对聊天气泡截图。"""
    if not src:
        return None
    if src.startswith("data:"):
        _, _, encoded = src.partition(",")
        try:
            return base64.b64decode(encoded)
        except Exception:
            return None
    try:
        response = desk.context.request.get(
            src,
            headers={"Referer": "https://work.weixin.qq.com/"},
            timeout=30000,
        )
        if response.ok:
            body = response.body()
            if body:
                return body
        print("image http:", response.status, src[:100], flush=True)
    except Exception as exc:
        print("image fetch error:", type(exc).__name__, str(exc)[:100], flush=True)
    if locator is not None:
        try:
            shot = locator.screenshot(timeout=10000)
            if shot:
                print("image fell back to screenshot", flush=True)
                return shot
        except Exception as exc:
            print("image screenshot error:", type(exc).__name__, flush=True)
    return None


def describe_item(item) -> str:
    try:
        text = item.inner_text().replace("\n", " ")[:60]
        bubble = item.locator(".ww_chatBubble").first
        classes = bubble.get_attribute("class") if bubble.count() else ""
        box = bubble.bounding_box() if bubble.count() else None
        return (
            f"id={item.get_attribute('id')} cls={classes} "
            f"x={round(box['x'], 1) if box else None} text={text}"
        )
    except Exception:
        return "describe failed"


def set_status(state: str, **extra) -> None:
    """给 preflight/人工检查用的桥接状态文件。"""
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone(timedelta(hours=8))).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        payload = {"state": state, "updated_at": stamp}
        payload.update(extra)
        STATUS_FILE.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def alert_beeps(times: int = 3) -> None:
    try:
        import winsound

        for _ in range(times):
            winsound.Beep(1200, 350)
            time.sleep(0.15)
    except Exception:
        pass


def image_key(src: str) -> str:
    return "img:" + hashlib.sha1(src.encode("utf-8")).hexdigest()[:16]


def scan_panel_images(desk) -> list[dict]:
    """收集消息面板里可见的图片（图片消息不一定包在 .message_item 里）。"""
    try:
        return desk.evaluate(
            """
            () => {
              const root = document.querySelector('.kfh_message_panel .message_list')
                || document.querySelector('.kfh_message_panel')
                || document.querySelector('.message_list');
              if (!root) return [];
              const box = root.getBoundingClientRect();
              const mid = box.x + box.width / 2;
              const out = [];
              for (const img of root.querySelectorAll('img')) {
                const r = img.getBoundingClientRect();
                if (r.width < 100 || r.height < 100) continue;
                const src = img.currentSrc || img.src || '';
                if (!src) continue;
                if (img.closest('a.ww_chatBubble_Link')) continue;
                const chain = [];
                let el = img;
                for (let i = 0; i < 5 && el; i++) {
                  chain.push(el.tagName.toLowerCase() + '.' + (el.className || ''));
                  el = el.parentElement;
                }
                out.push({
                  src: src, x: r.x, y: r.y, w: r.width, h: r.height, mid: mid,
                  inBubble: !!img.closest('.ww_chatBubble'),
                  chain: chain.join(' < ')
                });
              }
              return out;
            }
            """
        ) or []
    except Exception as exc:
        print("panel scan error:", type(exc).__name__, str(exc)[:80], flush=True)
        return []


def seed_seen_images(seen: set[str], image_dir: Path) -> int:
    """把已落盘图片的 SHA1 预置进去重集合，避免重启后重复建记录。"""
    if not image_dir.exists():
        return 0
    added = 0
    for path in image_dir.glob("*"):
        if not path.is_file():
            continue
        try:
            digest = hashlib.sha1(path.read_bytes()).hexdigest()[:16]
        except OSError:
            continue
        key = "sha:" + digest
        if key not in seen:
            seen.add(key)
            added += 1
    return added


def load_seen(path: Path, limit: int = 800) -> set[str]:
    try:
        values = json.loads(path.read_text(encoding="utf-8")).get("seen", [])
    except Exception:
        return set()
    return {str(value) for value in values[-limit:]}


def save_seen(path: Path, seen: set[str], limit: int = 800) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"seen": sorted(seen)[-limit:]}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print("save seen failed:", type(exc).__name__, flush=True)


def dump_image_dom(item, message_id: str, dumped: set[str]) -> None:
    if message_id in dumped:
        return
    dumped.add(message_id)
    try:
        html = item.evaluate("el => el.outerHTML")
        IMAGE_DOM_LOG.parent.mkdir(parents=True, exist_ok=True)
        with IMAGE_DOM_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"\n===== {message_id} =====\n{html}\n")
    except Exception as exc:
        print("dump image dom failed:", type(exc).__name__, flush=True)


def main() -> None:
    if not TOKEN:
        print("SHARE_INGEST_TOKEN missing", flush=True)
        return

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE),
            channel="msedge",
            headless=False,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        desk = connect_desk(context)
        seen: set[str] = load_seen(SEEN_FILE)
        seeded = seed_seen_images(seen, ROOT / "data" / "images")
        if seeded:
            save_seen(SEEN_FILE, seen)
            print(f"预置历史图片哈希 {seeded} 条", flush=True)
        sent_texts: set[str] = set()
        dumped_images: set[str] = set()
        sent_since_customer = 0
        max_unanswered = 5
        # 没有历史状态文件时，第一轮只补处理图片（避免把旧文字重复建记录）
        first_scan = not seen
        last_count = -1
        print(
            f"桥接已启动（seen={len(seen)}, first_scan={first_scan}），等待新消息……",
            flush=True,
        )

        def reply_guarded(text: str) -> bool:
            nonlocal sent_since_customer
            if sent_since_customer >= max_unanswered:
                print(
                    "回复额度已满（等待客户新消息），暂不发送：",
                    text[:30], flush=True,
                )
                return False
            if send_reply(desk, text):
                sent_since_customer += 1
                sent_texts.add(text)
                return True
            return False

        last_heartbeat = time.time()
        last_count_change = time.time()
        last_pin = time.time()
        active_chat_key = ""
        last_chat_count = -1

        while True:
            try:
                try:
                    desk.locator(".message_list").first.evaluate(
                        "el => { el.scrollTop = el.scrollHeight; }"
                    )
                except Exception:
                    pass

                chat_items = desk.locator(".chat_item")
                chat_count = chat_items.count()
                if chat_count != last_chat_count:
                    print("chat items:", chat_count, flush=True)
                    last_chat_count = chat_count
                first_key = chat_key(desk)
                if first_key and first_key != active_chat_key:
                    label = click_target_chat(desk)
                    active_chat_key = first_key
                    print("follow chat:", label, flush=True)
                    last_count = -1
                    time.sleep(1)
                    continue

                items = desk.locator(".message_item")
                count = items.count()
                panel = desk.locator(".kfh_message_panel").bounding_box()
                now = time.time()

                if count != last_count:
                    print(f"messages: {count}", flush=True)
                    for idx in range(max(0, count - 3), count):
                        print("  ", describe_item(items.nth(idx)), flush=True)
                    last_count = count
                    last_count_change = now

                if now - last_heartbeat >= 60:
                    print(
                        f"heartbeat count={count} "
                        f"idle={int(now - last_count_change)}s "
                        f"seen={len(seen)}",
                        flush=True,
                    )
                    set_status(
                        "running",
                        last_heartbeat=datetime.now(
                            timezone(timedelta(hours=8))
                        ).strftime("%Y-%m-%dT%H:%M:%S"),
                        count=count,
                        chat=chat_key(desk),
                    )
                    last_heartbeat = now

                if now - last_count_change > 180 and now - last_pin > 300:
                    print("3 分钟没有新消息，重新点选会话", flush=True)
                    try:
                        click_target_chat(desk)
                    except Exception as exc:
                        print("re-pin failed:", type(exc).__name__, flush=True)
                    last_pin = now

                for index in range(count):
                    item = items.nth(index)
                    message_id = item.get_attribute("id") or f"idx-{index}"
                    if message_id in seen:
                        continue

                    bubble = item.locator(".ww_chatBubble").first
                    has_bubble = bubble.count() > 0
                    classes = bubble.get_attribute("class") if has_bubble else ""
                    box = bubble.bounding_box() if has_bubble else None
                    is_left = bool(
                        box
                        and panel
                        and box["x"] < panel["x"] + panel["width"] / 2
                    )

                    img = item.locator(".ww_chatBubble img").first
                    image_present = "image" in classes.lower() or img.count() > 0

                    if first_scan and not image_present:
                        seen.add(message_id)
                        continue

                    if image_present:
                        dump_image_dom(item, message_id, dumped_images)
                        seen.add(message_id)
                        if not is_left:
                            print("skip agent image", flush=True)
                            continue
                        src = ""
                        if img.count():
                            src = (
                                img.get_attribute("src")
                                or img.get_attribute("data-src")
                                or ""
                            )
                            if src:
                                seen.add(image_key(src))
                            data = fetch_image(desk, src, img)
                        else:
                            data = fetch_image(desk, "", bubble)
                        if not data:
                            print(
                                "image unavailable:",
                                (src or "<no img tag>")[:90], flush=True,
                            )
                            continue
                        content_key = (
                            "sha:" + hashlib.sha1(data).hexdigest()[:16]
                        )
                        if content_key in seen:
                            print("skip duplicate image content", flush=True)
                            continue
                        seen.add(content_key)
                        print("image:", len(data), "bytes", flush=True)
                        sent_since_customer = 0
                        reply = call_api(
                            {"image_base64": base64.b64encode(data).decode()}
                        )
                        if reply:
                            reply_guarded(reply)
                        continue

                    seen.add(message_id)

                    link = item.locator("a.ww_chatBubble_Link").first
                    if link.count():
                        link_classes = link.get_attribute("class") or ""
                        href = link.get_attribute("href") or ""
                        if "_Left" in link_classes and "mp.weixin.qq.com" in href:
                            print("article:", href[:120], flush=True)
                            sent_since_customer = 0
                            reply = call_api({"url": href})
                            if reply:
                                reply_guarded(reply)
                        continue

                    text_el = item.locator(".ww_chatBubble_wordText").first
                    if text_el.count():
                        text = text_el.inner_text().strip()
                        if not text:
                            continue
                        if not is_left:
                            print(
                                "skip agent text (x):", text[:40], flush=True
                            )
                            continue
                        normalized = " ".join(text.split())
                        if any(
                            normalized == " ".join(sent.split())
                            for sent in sent_texts
                        ):
                            print("skip own reply:", text[:40], flush=True)
                            continue
                        print(
                            "text:", text, "left=", is_left,
                            "class=", classes, flush=True,
                        )
                        sent_since_customer = 0
                        reply = call_api({"text": text})
                        if reply:
                            reply_guarded(reply)

                for info in scan_panel_images(desk):
                    src = info.get("src") or ""
                    if not src:
                        continue
                    key = image_key(src)
                    if key in seen:
                        continue
                    if info["x"] + info["w"] / 2 >= info["mid"]:
                        print("skip agent panel image", flush=True)
                        seen.add(key)
                        continue
                    if key not in dumped_images:
                        dumped_images.add(key)
                        print("panel image:", info, flush=True)
                        try:
                            IMAGE_DOM_LOG.parent.mkdir(
                                parents=True, exist_ok=True
                            )
                            with IMAGE_DOM_LOG.open("a", encoding="utf-8") as fh:
                                fh.write(
                                    f"\n===== {key} {src[:120]} =====\n"
                                    f"{info}\n"
                                )
                        except Exception:
                            pass
                    data = fetch_image(desk, src, None)
                    seen.add(key)
                    if not data:
                        print("panel image unavailable:", src[:90], flush=True)
                        continue
                    content_key = "sha:" + hashlib.sha1(data).hexdigest()[:16]
                    if content_key in seen:
                        print("skip duplicate image content", flush=True)
                        continue
                    seen.add(content_key)
                    print("panel image bytes:", len(data), flush=True)
                    sent_since_customer = 0
                    reply = call_api(
                        {"image_base64": base64.b64encode(data).decode()}
                    )
                    if reply:
                        reply_guarded(reply)

                if first_scan:
                    first_scan = False
                    print("首轮扫描完成，已记录历史消息", flush=True)
                save_seen(SEEN_FILE, seen)
            except Exception as exc:
                print("loop error:", type(exc).__name__, exc, flush=True)
                set_status("degraded", error=type(exc).__name__)
                try:
                    desk = connect_desk(context)
                except Exception as reopen_exc:
                    print("reopen failed:", reopen_exc, flush=True)

            time.sleep(2)


if __name__ == "__main__":
    main()
