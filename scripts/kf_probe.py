"""微信客服连通性探针：gettoken + sync_msg（只读，不发消息）。"""

from __future__ import annotations

import asyncio
import json

from app.config import get_settings
from app.wecom_kf import WeComKFClient


async def main() -> None:
    settings = get_settings()
    print("enabled:", settings.wecom_kf_enabled)
    print("kfid:", settings.wecom_kf_id)
    print("corp_id set:", bool(settings.wecom_corp_id))
    print("secret set:", bool(settings.wecom_kf_secret))

    client = WeComKFClient(settings)
    try:
        await client.get_access_token()
        print("gettoken: ok")
    except Exception as exc:
        print("gettoken failed:", exc)
        return

    try:
        data = await client.sync_msg("", "")
        messages = data.get("msg_list") or []
        print(
            "sync_msg: ok",
            "errcode=", data.get("errcode"),
            "count=", len(messages),
            "has_more=", data.get("has_more"),
        )
        for msg in messages[:5]:
            print(
                json.dumps(
                    {
                        key: msg.get(key)
                        for key in (
                            "msgid",
                            "origin",
                            "msgtype",
                            "external_userid",
                            "open_kfid",
                            "send_time",
                        )
                    },
                    ensure_ascii=False,
                )
            )
    except Exception as exc:
        print("sync_msg failed:", exc)


if __name__ == "__main__":
    asyncio.run(main())
