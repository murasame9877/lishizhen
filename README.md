# 理时针 · 微信日程捕获与系统日历提醒 Agent

用户把公众号文章链接、活动文字或海报截图发给微信服务号，系统抽取结构化日程；用户在对话框内用编号查看/修改/删除；服务端通过 CalDAV 写入手机系统日历，由系统日历本地弹窗提醒。

> **产品名：理时针**（Lishizhen）。
>
> **当前进度**：119 条本地测试全绿。文本、公众号文章链接、活动海报截图（RapidOCR）三条入口均可抽取活动、编号、检测冲突并推送卡片；微信客服网页工作台桥接可自动收发文字/文章/图片。CalDAV → DAVx5 → Android 系统日历 → 到点通知已在 Redmi Note 11 Pro+（Android 13）真机闭环验证。

## 落地页

- 本地预览：`python -m http.server 4173 --directory docs` → <http://127.0.0.1:4173/>
- 线上（GitHub Pages）：`https://murasame9877.github.io/lishizhen/`（推送后替换用户名）

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest

# 启动本地服务（默认 http://127.0.0.1:8000）
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
# 健康检查：http://127.0.0.1:8000/healthz
```

## 已实现

| 模块 | 文件 | 说明 |
|---|---|---|
| 时间归一化 | `app/parsing/time_norm.py` | 明天/周五/下周三/全天/区间/次日/时间待定；Asia/Shanghai；置信度与推断依据 |
| 冲突检测 | `app/parsing/conflict.py` | 半开区间重叠；排除全天；同日轻提示 |
| ICS / VALARM | `app/calendar/ics.py` | 稳定 UID、VTIMEZONE、定时两档提醒、全天 09:00 绝对提醒及特殊规则 |
| 微信接入基础 | `app/wechat/crypto.py` | sha1 验签、安全 XML 解析、文本回复 CDATA 转义 |
| 回调网关 | `app/wechat/gateway.py`、`app/main.py` | echostr 校验、5 秒回执、MsgId 幂等、指令/活动分流、消息落库 |
| 规则抽取 | `app/parsing/extract_rules.py` | 标题、时间、地点、报名截止；纯闲聊不建记录 |
| 文章解析 | `app/parsing/article.py` | 公众号正文抓取、标题/时间/地点/截止抽取、反爬提示 |
| 海报 OCR | `app/parsing/ocr.py` | RapidOCR 中文识别、原图 7 天留存、无文字/低置信度兜底 |
| 分享入口 | `app/share_api.py` | 手机分享链接/文字/图片 base64 → 同步解析并返回卡片 |
| 客服工作台桥接 | `bot/kf_web_bridge.py` | Playwright 轮询工作台；面板级图片扫描、按内容哈希去重、心跳与自动重连 |
| 解析 Worker | `app/jobs/worker.py` | 消费 `parse_queued`，入库、编号、冲突、卡片推送 |
| 客服消息 | `app/wechat/client.py` | access_token 缓存、48 小时窗口内主动推送 |
| 卡片模板 | `app/commands/render.py` | 成功/待确认/信息不完整/冲突/同步状态 |
| 指令服务 | `app/commands/parser.py`、`handlers.py` | 列表分页、详情、改、删二次确认、同步、检索 |
| CalDAV 同步 | `app/calendar/caldav.py`、`sync.py`、`scheduler.py` | UID 幂等、PUT/DELETE、404 成功、失败重试、10 分钟定时 |
| 数据表 | `app/storage/db.py` | activities / user_prefs / messages / pending_actions / sync_logs / user_counters |
| 配置 | `app/config.py` | 全部可调参数走环境变量 |

## 测试覆盖

```powershell
pytest            # 全部用例
pytest tests/test_time_norm.py -v
```

已覆盖 PRD FR-08 的 7 条时间用例、冲突并存/相邻不冲突/全天排除、ICS 两档提醒与全天 09:00、MsgId 幂等唯一索引、CDATA 转义、回调验签与 echostr、重复回调只落一条、指令不误入解析队列。

## 目录

```
app/
  main.py       回调路由、Worker/定时同步启动、健康检查
  config.py
  parsing/      time_norm.py  conflict.py  extract_rules.py  article.py  ocr.py
  calendar/     ics.py  caldav.py  sync.py  scheduler.py  radicale_mount.py
  commands/     parser.py  handlers.py  render.py  format.py
  jobs/         worker.py
  wechat/       crypto.py  gateway.py  client.py
  storage/      db.py  repo_activities.py  repo_pending.py
scripts/        run_app.ps1（守护重启）  start_all.ps1  start_serveo.ps1  stop_all.ps1
bot/            kf_web_bridge.py  kf_web_probe.py
deploy/         radicale.conf
tests/
```

## 配置

复制 `.env.example` 为 `.env`，按需填写。敏感值（appsecret、CalDAV 密码）不要提交到 git。

## 现场演示加固

- 登录自启：`scripts/install_autostart.ps1`（注册后端与桥接两个计划任务）。
- 开场预检：`scripts/preflight.ps1`，检查后端、桥接心跳/登录态、USB 隧道、DAVx5 日历与事件。
- 完整清单与兜底方案：[docs/演示前检查清单.md](docs/演示前检查清单.md)。
- 局限：所有服务跑在演示电脑上，电脑关机即停止；桥接依赖微信客服网页登录态。
- 观众体验：现场由 1–2 人上台操作，桥接自动跟随最新客服会话；不支持 30 人同时扫码（单会话串行处理）。

## 现场演示模式

`.env` 中：

```env
DEMO_MODE=true
CALDAV_SYNC_OPENIDS=<演示负责人的 openid>
```

- 只有白名单 openid 会写入系统日历。
- 其他观众扫码后仍可体验：发活动、卡片、列表、详情、改、删。
- 观众点「同步」或「配置完成」会收到演示模式提示，不会污染演示日历。
- Android 演示机配置见 [docs/Android-DAVx5配置.md](docs/Android-DAVx5配置.md)。

## 演示前需要手动完成

1. 手机安装 DAVx5，添加 CalDAV 账户：
   - 先执行 `adb reverse tcp:8000 tcp:8000`（拔线/adb 重启后需重做）
   - URL `http://127.0.0.1:8000/radicale/`，用户名 `sdg`，密码见 `.env` 的 `CALDAV_PASSWORD`
   - 授予 DAVx5 日历权限，勾选 `sdg/calendar` 日历并开启同步。
2. 桥接 Edge 窗口首次运行需扫码登录微信客服工作台。
3. 发 1 篇文章链接、1 段文字、1 张海报，联调真机链路。
