"""wcferry 接收探针：验证备用号能收到主号转发的公众号文章。

只读探针，不发送消息、不自动回复。
运行前：
1. 用备用号登录微信 3.9.12.51；
2. 主号加备用号为好友；
3. 关闭 4.x 微信，只保留 3.9.12.51 进程（避免 hook 注入错进程）。
"""

from __future__ import annotations

import time
from queue import Empty

from wcferry import Wcf


def main() -> None:
    wcf = Wcf()
    wcf.enable_receiving_msg()
    print(f"WCF ready, self wxid={wcf.get_self_wxid()}", flush=True)
    print("请从主号转发一篇公众号文章给这个微信号……", flush=True)

    while True:
        try:
            msg = wcf.get_msg()
        except Empty:
            continue
        if msg is None:
            time.sleep(0.5)
            continue
        content = (msg.content or "").replace("\n", " ")[:800]
        xml = (msg.xml or "").replace("\n", " ")[:1200]
        print(
            f"type={msg.type} sender={msg.sender} content={content} xml={xml}",
            flush=True,
        )


if __name__ == "__main__":
    main()
