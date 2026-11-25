"""从微信客服管理页点击“客户咨询消息”进入 helpdesk，抓取聊天页结构。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "data" / "kf_web_profile"
LOGS = ROOT / "data" / "logs"


def dump_analysis(page) -> None:
    page.screenshot(path=str(LOGS / "kf_helpdesk.png"), full_page=True)
    (LOGS / "kf_helpdesk.html").write_text(page.content(), encoding="utf-8")
    analysis = page.evaluate(
        """
        () => {
          const result = {inputs: [], buttons: [], hits: [], links: []};
          document.querySelectorAll('textarea').forEach((e) => {
            result.inputs.push({tag: e.tagName, cls: e.className, ph: e.placeholder});
          });
          document.querySelectorAll('[contenteditable]').forEach((e) => {
            result.inputs.push({tag: e.tagName, cls: e.className, ce: e.getAttribute('contenteditable')});
          });
          document.querySelectorAll('button, [class*=send], [class*=Send]').forEach((e) => {
            const text = (e.innerText || '').trim().slice(0, 20);
            if (text || (e.className || '').toLowerCase().includes('send')) {
              result.buttons.push({tag: e.tagName, cls: e.className, text});
            }
          });
          document.querySelectorAll('a[href]').forEach((e) => {
            const href = e.getAttribute('href') || '';
            if (href.includes('mp.weixin.qq.com')) {
              result.links.push({href, text: (e.innerText || '').trim().slice(0, 40)});
            }
          });
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          while (walker.nextNode()) {
            const text = (walker.currentNode.textContent || '').trim();
            if (text.includes('测试') || text.includes('竞赛招募')) {
              let el = walker.currentNode.parentElement;
              const chain = [];
              for (let i = 0; i < 6 && el; i++) {
                chain.push(el.tagName + '.' + (el.className || ''));
                el = el.parentElement;
              }
              result.hits.push({text: text.slice(0, 40), chain});
            }
          }
          return result;
        }
        """
    )
    print(json.dumps(analysis, ensure_ascii=False, indent=2)[:7000], flush=True)


def main() -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE),
            channel="msedge",
            headless=False,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(
            "https://work.weixin.qq.com/kf/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        print("admin page:", page.url, page.title(), flush=True)

        desk = page
        try:
            page.wait_for_selector(".kfFrame_msgPop", timeout=20000)
            print("clicking 客户咨询消息", flush=True)
            try:
                with context.expect_page(timeout=8000) as new_page_info:
                    page.click(".kfFrame_msgPop")
                desk = new_page_info.value
            except PlaywrightTimeoutError:
                desk = page
        except PlaywrightTimeoutError:
            print("no .kfFrame_msgPop, trying direct helpdesk", flush=True)

        try:
            desk.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        print("desk url:", desk.url, flush=True)

        if "helpdesk" not in desk.url:
            try:
                desk.goto(
                    "https://work.weixin.qq.com/kf/helpdesk",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                print("direct helpdesk url:", desk.url, flush=True)
            except Exception as exc:
                print("direct helpdesk failed:", exc, flush=True)

        try:
            desk.wait_for_selector(".chat_item", timeout=30000)
            print("chat items:", desk.locator(".chat_item").count(), flush=True)
            desk.locator(".chat_item", has_text="夏季芭乐").first.click()
            print("clicked customer", flush=True)
            desk.wait_for_timeout(4000)
            dump_analysis(desk)
        except Exception as exc:
            print("chat not ready:", type(exc).__name__, exc, flush=True)
            dump_analysis(desk)

        time.sleep(3)
        context.close()


if __name__ == "__main__":
    main()
