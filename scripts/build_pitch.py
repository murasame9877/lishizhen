"""生成 2026 SDG 答辩 PPT（基于官方模板结构，重新排版）。"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data" / "ppt_assets"
OUT = ROOT / "docs" / "2026SDG-Pitch-日程Agent.pptx"

FONT = "微软雅黑"
INK = RGBColor(0x1F, 0x2A, 0x37)
GRAY = RGBColor(0x5B, 0x6B, 0x7A)
GREEN = RGBColor(0x2F, 0x7D, 0x5B)
DEEP = RGBColor(0x12, 0x3F, 0x5A)
YELLOW = RGBColor(0xF2, 0xB7, 0x05)
LIGHT = RGBColor(0xF2, 0xF7, 0xF3)
PALE = RGBColor(0xE8, 0xF1, 0xEC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED = RGBColor(0xB4, 0x45, 0x3A)

W, H = 13.333, 7.5
prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)
BLANK = prs.slide_layouts[6]


def add_slide():
    return prs.slides.add_slide(BLANK)


def tx(
    slide,
    x,
    y,
    w,
    h,
    text,
    *,
    size=16,
    bold=False,
    color=INK,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    spacing=1.15,
    font=FONT,
    italic=False,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        run = p.add_run()
        run.text = line
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
    return box


def bullets(slide, x, y, w, h, items, *, size=14, color=INK, gap=8, bullet_color=GREEN):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for idx, item in enumerate(items):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.line_spacing = 1.18
        p.space_after = Pt(gap)
        mark = p.add_run()
        mark.text = "•  "
        mark.font.name = FONT
        mark.font.size = Pt(size)
        mark.font.color.rgb = bullet_color
        mark.font.bold = True
        run = p.add_run()
        run.text = item
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.color.rgb = color
    return box


def header(slide, zh, en, page):
    slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(0.62), Inches(0.09), Inches(0.52)
    ).fill.solid()
    slide.shapes[-1].fill.fore_color.rgb = GREEN
    slide.shapes[-1].line.fill.background()
    tx(slide, 0.78, 0.52, 10.5, 0.35, en.upper(), size=10.5, bold=True, color=GREEN)
    tx(slide, 0.78, 0.78, 10.8, 0.55, zh, size=26, bold=True, color=DEEP)
    footer(slide, page)


def footer(slide, page):
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(7.05), Inches(12.2), Inches(0.012)
    )
    line.fill.solid()
    line.fill.fore_color.rgb = RGBColor(0xDD, 0xE5, 0xE0)
    line.line.fill.background()
    tx(
        slide,
        0.55,
        7.12,
        9,
        0.25,
        "日程Agent · 2026 第八届清华大学 SDG 开放创新马拉松挑战赛",
        size=9,
        color=GRAY,
    )
    tx(slide, 11.9, 7.12, 0.9, 0.25, str(page), size=9, color=GRAY, align=PP_ALIGN.RIGHT)


def card(slide, x, y, w, h, fill=LIGHT, line=None):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(0.75)
    shape.adjustments[0] = 0.06
    return shape


def arrow(slide, x, y, w=0.35, h=0.22, color=GREEN):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def table(slide, x, y, w, rows, cols, col_widths, data, header_fill=GREEN, size=11):
    shape = slide.shapes.add_table(
        rows, cols, Inches(x), Inches(y), Inches(w), Inches(0.3 * rows)
    )
    tbl = shape.table
    for idx, width in enumerate(col_widths):
        tbl.columns[idx].width = Inches(width)
    for r in range(rows):
        for c in range(cols):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.06)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            cell.text = str(data[r][c])
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER
                for run in p.runs:
                    run.font.name = FONT
                    run.font.size = Pt(size)
                    run.font.color.rgb = WHITE if r == 0 else INK
                    run.font.bold = r == 0
            if r == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = header_fill
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if r % 2 else LIGHT
    return tbl


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# ---------------------------------------------------------------- 1 封面
s = add_slide()
s.shapes.add_picture(
    str(ASSETS / "s1_1_image.png"), Inches(2.1), Inches(0.32), width=Inches(9.1)
)
tx(s, 1.05, 3.12, 11, 0.9, "日程Agent", size=52, bold=True, color=DEEP)
tx(
    s,
    1.05,
    4.08,
    11,
    0.9,
    "把任何 App 里的活动信息，一键变成会提醒的日程",
    size=23,
    bold=True,
    color=GREEN,
)
tx(
    s,
    1.05,
    4.92,
    11,
    0.6,
    "微信内已验证 · 截图 / 转发 / 拖拽 · 写入手机系统日历",
    size=14,
    color=GRAY,
)
card(s, 1.05, 5.55, 4.6, 0.55, PALE)
tx(s, 1.25, 5.65, 4.3, 0.35, "团队：成员 A / B / C（待替换）", size=12, color=DEEP)
tx(s, 1.05, 6.45, 6, 0.3, "2026 年 11 月", size=11, color=GRAY)
footer(s, 1)
notes(
    s,
    "开场 15 秒：大家好，我们是日程Agent。一句话：你在任何 App 里看到活动或预约，"
    "截图或转发一下，它就会自动出现在手机系统日历里，并准时提醒。",
)

# ---------------------------------------------------------------- 2 一句话小结
s = add_slide()
header(s, "一句话小结", "Deal Summary", 2)
card(s, 0.55, 1.65, 12.2, 1.5, DEEP)
tx(
    s,
    0.95,
    1.92,
    11.4,
    1.0,
    "信息在哪里，日程就从哪里长出来。",
    size=28,
    bold=True,
    color=WHITE,
)
tx(
    s,
    0.95,
    2.55,
    11.4,
    0.5,
    "从微信开始，但不限于微信：飞书、小红书、邮件、网页，截图/转发/拖拽即可捕获。",
    size=13,
    color=RGBColor(0xD8, 0xE8, 0xDF),
)
steps = [
    ("01  捕获", "转发 / 截图 / 拖拽 / 系统识屏"),
    ("02  理解", "规则 + OCR 抽取时间、地点、截止"),
    ("03  落地", "写入系统日历，到点本地提醒"),
]
for idx, (name, desc) in enumerate(steps):
    x = 0.55 + idx * 4.15
    card(s, x, 3.55, 3.85, 1.55, LIGHT)
    tx(s, x + 0.25, 3.75, 3.3, 0.4, name, size=18, bold=True, color=GREEN)
    tx(s, x + 0.25, 4.35, 3.35, 0.55, desc, size=12, color=GRAY)
tx(
    s,
    0.55,
    5.55,
    12.2,
    0.9,
    "当前 MVP 已打通「微信 → 解析 → CalDAV → Android 系统日历 → 到点通知」；"
    "同一套能力可复用到任意信息入口。",
    size=14,
    color=INK,
)
footer(s, 2) if False else None
notes(
    s,
    "30 秒：我们是三层能力——捕获、理解、落地。今天现场演示的是微信入口，"
    "但底层不依赖微信，未来任何 App 的截图都能进来。",
)

# ---------------------------------------------------------------- 3 团队
s = add_slide()
header(s, "核心团队", "Team", 3)
team = [
    ("成员 A", "产品 / 项目", "需求、演示、商业化"),
    ("成员 B", "后端 / 算法", "解析、OCR、CalDAV"),
    ("成员 C", "前端 / 测试", "交互、真机联调"),
]
for idx, (name, role, skill) in enumerate(team):
    x = 0.55 + idx * 4.15
    card(s, x, 1.85, 3.8, 2.35, LIGHT)
    circle = s.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(x + 1.45), Inches(2.1), Inches(0.9), Inches(0.9)
    )
    circle.fill.solid()
    circle.fill.fore_color.rgb = PALE
    circle.line.fill.background()
    tx(s, x + 1.45, 2.33, 0.9, 0.45, name[-1], size=22, bold=True, color=GREEN, align=PP_ALIGN.CENTER)
    tx(s, x + 0.25, 3.2, 3.3, 0.35, name, size=16, bold=True, color=DEEP, align=PP_ALIGN.CENTER)
    tx(s, x + 0.25, 3.6, 3.3, 0.3, role, size=12, color=GREEN, align=PP_ALIGN.CENTER)
    tx(s, x + 0.25, 3.95, 3.3, 0.3, skill, size=11, color=GRAY, align=PP_ALIGN.CENTER)
tx(
    s,
    0.55,
    4.55,
    12.2,
    1.2,
    "团队优势：既做过完整的产品闭环，也能把解析、OCR、日历同步落到真机。"
    "从需求到演示，全部自己实现。",
    size=14,
    color=INK,
)
notes(s, "20 秒：介绍三位成员与分工。名字请替换为真实姓名。")

# ---------------------------------------------------------------- 4 问题
s = add_slide()
header(s, "问题：信息散落，提醒缺失", "Problem", 4)
bullets(
    s,
    0.55,
    1.65,
    6.1,
    4.7,
    [
        "活动信息分散在公众号、群聊、飞书、小红书、邮件和海报里，没有一个统一的入口。",
        "看到不等于记住：报名截止、活动开始时间，靠人脑和截图收藏，极易错过。",
        "手动建日程成本高：复制时间、地点、标题，重复且容易出错。",
        "企业侧同样存在：售后预约、上门服务、回访时间散落在客服会话里，爽约与二次上门成本高。",
    ],
    size=15,
)
card(s, 6.95, 1.65, 5.8, 4.7, DEEP)
card(s, 0.55, 6.35, 6.0, 0.5, PALE)
tx(
    s,
    0.75,
    6.44,
    5.7,
    0.3,
    "每一条被错过的活动，都是一次没有发生的连接。",
    size=10.5,
    color=GREEN,
)
tx(s, 7.25, 1.95, 5.2, 0.4, "一个被忽略的落差", size=12, color=RGBColor(0xD8, 0xE8, 0xDF))
tx(s, 7.25, 2.45, 5.2, 1.2, "信息已经送达，\n但日程没有发生。", size=26, bold=True, color=WHITE)
tx(
    s,
    7.25,
    3.75,
    5.2,
    2.2,
    "用户需要的不是又一个信息流，\n而是一个「看到即记住」的动作。\n\n"
    "对联想这样的服务型企业：\n每一次错过的预约，都是成本。",
    size=14,
    color=RGBColor(0xE6, 0xF1, 0xEA),
)
notes(s, "40 秒：讲三个具体场景——错过讲座报名、群里的聚餐、客服承诺的上门时间。")

# ---------------------------------------------------------------- 5 解决方案与创新
s = add_slide()
header(s, "解决方案：多源捕获，自动成日程", "Solution & Innovation", 5)
features = [
    ("零跳转", "在微信/飞书/小红书里直接转发或截图，不打断当前操作。"),
    ("多模态", "文字、文章链接、海报截图都能解析；中文时间规则 + OCR。"),
    ("真正落地", "不是生成待办，而是写入系统日历，由系统负责提醒。"),
    ("可复制", "同一套抽取与日历能力，可嵌入 App 或手机系统 AI。"),
]
for idx, (name, desc) in enumerate(features):
    x = 0.55 + (idx % 2) * 6.2
    y = 1.65 + (idx // 2) * 1.55
    card(s, x, y, 5.9, 1.3, LIGHT)
    tx(s, x + 0.25, y + 0.18, 5.3, 0.35, name, size=16, bold=True, color=GREEN)
    tx(s, x + 0.25, y + 0.62, 5.4, 0.55, desc, size=12, color=INK)
card(s, 0.55, 4.9, 12.2, 1.4, PALE)
tx(
    s,
    0.85,
    5.1,
    11.6,
    1.0,
    "创新点：把「信息入口」和「提醒系统」接起来。过去两者之间靠人手动搬运；"
    "我们用规则 + OCR + CalDAV 把这一步自动化，并且已经在一台 Android 真机上闭环验证。",
    size=13,
    color=DEEP,
)
notes(s, "40 秒：四个关键词——零跳转、多模态、真正落地、可复制。")

# ---------------------------------------------------------------- 6 目标客户
s = add_slide()
header(s, "目标客户与付费方", "Target Customers", 6)
card(s, 0.55, 1.65, 3.9, 4.6, LIGHT)
tx(s, 0.8, 1.85, 3.4, 0.35, "免费使用", size=13, bold=True, color=GREEN)
tx(s, 0.8, 2.25, 3.4, 0.5, "C 端个人用户", size=20, bold=True, color=DEEP)
bullets(
    s,
    0.8,
    2.85,
    3.4,
    3.1,
    ["学生与研究生", "职场人", "社群/兴趣组织成员", "任何收到活动或预约信息的人"],
    size=12,
    gap=6,
)
card(s, 4.75, 1.65, 3.9, 4.6, PALE)
tx(s, 5.0, 1.85, 3.4, 0.35, "付费方（近期）", size=13, bold=True, color=GREEN)
tx(s, 5.0, 2.25, 3.4, 0.5, "联想及服务型企业", size=18, bold=True, color=DEEP)
bullets(
    s,
    5.0,
    2.85,
    3.4,
    3.1,
    ["售后预约 / 上门服务", "回访与保修到期", "企业客户活动", "客服 SLA 与爽约率"],
    size=12,
    gap=6,
)
card(s, 8.95, 1.65, 3.8, 4.6, LIGHT)
tx(s, 9.2, 1.85, 3.3, 0.35, "付费方（中期）", size=13, bold=True, color=GREEN)
tx(s, 9.2, 2.25, 3.3, 0.5, "活动方与广告主", size=18, bold=True, color=DEEP)
bullets(
    s,
    9.2,
    2.85,
    3.3,
    3.1,
    ["活动主办方 / 场馆", "票务与报名平台", "本地商家", "品牌广告主"],
    size=12,
    gap=6,
)
tx(
    s,
    0.55,
    6.45,
    12.2,
    0.5,
    "校园是首批验证场景（活动密度高、传播快），不是天花板。",
    size=12,
    color=GRAY,
)
notes(s, "40 秒：明确谁免费用、谁付钱。学生免费；联想为服务效率付费；活动方和广告主为触达付费。")

# ---------------------------------------------------------------- 7 市场规模
s = add_slide()
header(s, "市场规模：先校园，再企业与泛人群", "Market Opportunity", 7)
cols = [
    ("TAM 总体市场", "4,700 万+", "中国高等教育在学总规模（教育部 2023：4,763 万）\n+ 企业售后服务与泛职场人群"),
    ("SAM 可服务市场", "50 万+", "首批 10 所高校约 50 万学生\n+ 联想中国服务坐席（假设 5,000）"),
    ("SOM 首年目标", "2 万+", "1 所高校 2 万学生，30% MAU\n+ 1 个联想事业部 300 坐席"),
]
for idx, (name, number, desc) in enumerate(cols):
    x = 0.55 + idx * 4.15
    card(s, x, 1.65, 3.8, 3.1, LIGHT)
    tx(s, x + 0.25, 1.85, 3.3, 0.3, name, size=12, bold=True, color=GREEN)
    tx(s, x + 0.25, 2.25, 3.3, 0.7, number, size=30, bold=True, color=DEEP)
    tx(s, x + 0.25, 3.1, 3.35, 1.4, desc, size=11, color=GRAY)
card(s, 0.55, 5.0, 12.2, 1.25, PALE)
tx(
    s,
    0.85,
    5.18,
    11.6,
    0.9,
    "测算口径：TAM 用公开教育规模数据；SAM/SOM 为保守假设，需在试点中校准。"
    "企业侧市场按「预约型服务坐席」估算，不与消费级用户重复计算。",
    size=12,
    color=DEEP,
)
tx(s, 0.55, 6.4, 12, 0.3, "数据来源：教育部《2023 年全国教育事业发展统计公报》；企业坐席数为内部假设。", size=9, color=GRAY)
notes(s, "30 秒：先讲 4,700 万在校生这个大盘，再讲 10 所高校的 SAM 和首年 2 万用户。数字要说明是假设。")

# ---------------------------------------------------------------- 8 价值主张
s = add_slide()
header(s, "价值主张", "Value Proposition", 8)
values = [
    ("对个人", "不遗漏", "看到就记住：转发/截图即入日历，到点提醒。", GREEN),
    ("对企业", "可量化", "降低爽约与二次上门，提升 SLA 与客服人效。", DEEP),
    ("对联想", "差异化", "系统级「截图即日程」，让 AI 助手真正进入日常。", YELLOW),
]
for idx, (who, tag, desc, color) in enumerate(values):
    x = 0.55 + idx * 4.15
    card(s, x, 1.7, 3.8, 3.4, LIGHT)
    tx(s, x + 0.25, 1.95, 3.2, 0.35, who, size=13, bold=True, color=GRAY)
    tx(s, x + 0.25, 2.4, 3.2, 0.8, tag, size=30, bold=True, color=color)
    tx(s, x + 0.25, 3.45, 3.3, 1.3, desc, size=13, color=INK)
card(s, 0.55, 5.4, 12.2, 1.05, DEEP)
tx(
    s,
    0.85,
    5.62,
    11.6,
    0.65,
    "一句话：把「看到的信息」变成「不会错过的日程」。个人省心，企业省钱，联想多一个系统级 AI 场景。",
    size=15,
    bold=True,
    color=WHITE,
)
notes(s, "30 秒：个人、企业、联想三层价值。")

# ---------------------------------------------------------------- 9 产品形态演进
s = add_slide()
header(s, "产品形态：从微信 Agent 到系统级 AI", "Product Roadmap", 9)
stages = [
    ("现在", "微信内 Agent", "文字 / 文章 / 海报\n已验证真机闭环", GREEN),
    ("近期", "独立 App", "分享面板 / 截图 / 拖拽\n跨微信、飞书、小红书", DEEP),
    ("未来", "联想系统 AI", "识屏 / 截图即触发\n预装或联合运营", YELLOW),
]
for idx, (when, name, desc, color) in enumerate(stages):
    x = 0.55 + idx * 4.15
    card(s, x, 1.75, 3.8, 2.9, LIGHT)
    tx(s, x + 0.25, 1.95, 3.2, 0.3, when, size=12, bold=True, color=color)
    tx(s, x + 0.25, 2.35, 3.2, 0.6, name, size=19, bold=True, color=DEEP)
    tx(s, x + 0.25, 3.1, 3.35, 1.2, desc, size=12, color=GRAY)
    if idx < 2:
        arrow(s, x + 3.88, 3.05, 0.2, 0.25, color=GRAY)
card(s, 0.55, 5.0, 12.2, 1.3, PALE)
tx(
    s,
    0.85,
    5.2,
    11.6,
    0.95,
    "底层是同一套能力：多源捕获 → 结构化抽取 → 日历写入。"
    "入口可以从微信换成 App、再换成手机系统，用户不需要改变习惯。",
    size=13,
    color=DEEP,
)
notes(s, "40 秒：强调演进路径，不是推翻现在，而是同一套能力换入口。")

# ---------------------------------------------------------------- 10 技术与 MVP
s = add_slide()
header(s, "技术实现与 MVP", "Technology & MVP", 10)
boxes = [
    ("多源入口", "微信 / 飞书 / 小红书\n截图 · 转发 · 拖拽", LIGHT),
    ("解析层", "中文时间规则\nRapidOCR 海报识别", PALE),
    ("日程服务", "FastAPI + SQLite\n冲突检测 / 编号", LIGHT),
    ("系统日历", "CalDAV / Radicale\nDAVx5 → 系统提醒", PALE),
]
for idx, (name, desc, fill) in enumerate(boxes):
    x = 0.55 + idx * 3.15
    card(s, x, 1.75, 2.85, 1.55, fill)
    tx(s, x + 0.2, 1.92, 2.45, 0.35, name, size=14, bold=True, color=GREEN)
    tx(s, x + 0.2, 2.35, 2.5, 0.8, desc, size=10.5, color=INK)
    if idx < 3:
        arrow(s, x + 2.88, 2.42, 0.22, 0.2, color=GRAY)
stats = [
    ("119", "自动化测试全绿"),
    ("3–10s", "单张海报 OCR"),
    ("真机", "2 分钟到点通知已验证"),
    ("0 元", "全部使用免费/开源组件"),
]
for idx, (num, label) in enumerate(stats):
    x = 0.55 + idx * 3.15
    tx(s, x, 3.75, 2.9, 0.6, num, size=26, bold=True, color=DEEP)
    tx(s, x, 4.35, 2.9, 0.5, label, size=11, color=GRAY)
bullets(
    s,
    0.55,
    5.15,
    12.2,
    1.5,
    [
        "已实现：微信客服/测试号接入、文本/文章/图片解析、列表/改/删/同步、冲突提示、CalDAV 真机闭环。",
        "当前限制：网页桥接依赖登录态；正式版可切换官方客服 API 或系统级集成。",
    ],
    size=12,
    gap=6,
)
notes(s, "50 秒：讲架构和四个数字。强调是真机闭环，不是 PPT 概念。")

# ---------------------------------------------------------------- 11 商业模式总览
s = add_slide()
header(s, "商业模式：用户免费，B 端付费", "Business Model", 11)
data = [
    ["收入线", "付费方", "收费方式", "阶段"],
    ["企业服务", "联想及同类服务企业", "试点项目费 / 坐席年费 / 私有化", "近期"],
    ["终端集成", "联想", "设备授权 / 联合运营分成", "中期"],
    ["消费 App", "广告主 / 活动方 / 票务", "广告 / 推广位 / 成交分成", "中长期"],
]
table(s, 0.55, 1.7, 12.2, 4, 4, [2.4, 3.6, 4.4, 1.8], data, size=11)
tx(s, 0.55, 3.75, 12.2, 0.5, "C 端用户始终免费；收入来自 B 端预算。", size=15, bold=True, color=GREEN)
card(s, 0.55, 4.45, 12.2, 1.9, LIGHT)
bullets(
    s,
    0.85,
    4.65,
    11.6,
    1.6,
    [
        "近期靠企业服务验证付费意愿：联想售后是天然场景，按坐席/项目收费。",
        "中期靠终端集成放大入口：系统级「截图即日程」可按设备授权或联合运营。",
        "长期靠消费 App 做规模：广告、活动推广、票务分成，用户免费使用。",
    ],
    size=12,
    gap=5,
)
notes(s, "40 秒：先讲清楚谁付钱，再展开两条测算。")

# ---------------------------------------------------------------- 12 联想 B2B
s = add_slide()
header(s, "路径一：联想企业客服（To B）", "Lenovo Enterprise", 12)
bullets(
    s,
    0.55,
    1.6,
    5.6,
    4.5,
    [
        "场景：售后预约、上门维修、回访、保修到期、企业客户活动。",
        "能力：从客服会话/邮件/截图中抽取时间承诺，写入客服与客户日历并提醒。",
        "给联想的收益：降低爽约与二次上门成本；提升 SLA、CSAT 与客服人效；保修到期/耗材更换的交叉销售机会。",
        "收费：试点项目费 → 按坐席年订阅 → 私有化部署与集成费。",
    ],
    size=12,
    gap=7,
)
data = [
    ["假设 / 情景", "保守", "基准", "乐观"],
    ["试点坐席数", "100", "300", "500"],
    ["单价（元/坐席/月）", "30", "50", "80"],
    ["年收入（万元）", "3.6", "18", "48"],
    ["实施成本（万元）", "8", "10", "12"],
    ["推理+运维/年（万元）", "0.6", "1.8", "3"],
    ["毛利（万元/年）", "-5.0", "6.2", "33"],
]
table(s, 6.45, 1.65, 6.3, 7, 4, [2.5, 1.25, 1.25, 1.3], data, size=10)
tx(
    s,
    6.45,
    4.55,
    6.3,
    1.8,
    "联想侧 ROI（基准假设）：300 坐席 × 8 个预约/天 × 20 天 = 4.8 万预约/月；"
    "爽约率降 5% → 2,400 次；单次上门成本 60 元 → 14.4 万/月 ≈ 173 万/年；"
    "对比 18 万/年的服务费，ROI ≈ 9.6 倍。",
    size=10,
    color=DEEP,
)
tx(s, 6.45, 6.35, 6.3, 0.3, "以上为试点假设，需与联想共同校准。", size=8.5, color=GRAY)
notes(s, "60 秒：重点讲给联想带来的收益和 ROI，数字标注为假设。")

# ---------------------------------------------------------------- 13 终端 + App
s = add_slide()
header(s, "路径二：终端集成 + 消费 App", "OEM & Consumer App", 13)
card(s, 0.55, 1.65, 5.9, 2.3, PALE)
tx(s, 0.8, 1.85, 5.4, 0.4, "联想终端集成", size=15, bold=True, color=DEEP)
bullets(
    s,
    0.8,
    2.3,
    5.4,
    1.5,
    [
        "系统级「截图/识屏即日程」，预装或联合运营。",
        "收费：设备授权（元/台）或广告/服务分成。",
        "价值：AI 助手差异化、日活与用户黏性。",
    ],
    size=11,
    gap=4,
)
card(s, 0.55, 4.15, 5.9, 2.2, LIGHT)
tx(s, 0.8, 4.35, 5.4, 0.4, "消费 App：免费 + 广告/交易", size=15, bold=True, color=DEEP)
bullets(
    s,
    0.8,
    4.8,
    5.4,
    1.4,
    [
        "广告：开屏 / 信息流 / 激励视频。",
        "活动推广：主办方、场馆、商家置顶。",
        "票务/报名/线索分成。",
    ],
    size=11,
    gap=4,
)
data = [
    ["App 情景", "保守", "基准", "乐观"],
    ["MAU", "5,000", "20,000", "100,000"],
    ["DAU/MAU", "20%", "25%", "30%"],
    ["人均曝光/日", "2", "3", "4"],
    ["eCPM（元）", "10", "15", "20"],
    ["广告年收入（万元）", "0.7", "8.2", "87.6"],
    ["推广/分成（万元）", "1.0", "6.0", "30"],
    ["成本（万元/年）", "2.0", "5.0", "15"],
    ["净收入（万元）", "-0.3", "9.2", "102.6"],
]
table(s, 6.75, 1.65, 6.0, 9, 4, [2.3, 1.2, 1.2, 1.3], data, size=9.5)
tx(
    s,
    6.75,
    5.75,
    6.0,
    0.7,
    "盈亏平衡：基准情景约 6,000 MAU；广告加载率设上限，保护工具体验。",
    size=9.5,
    color=DEEP,
)
notes(s, "60 秒：终端按设备授权，App 用广告和交易变现；用户始终免费。")

# ---------------------------------------------------------------- 14 对标
s = add_slide()
header(s, "对标：同类产品怎么赚钱", "Benchmarks", 14)
data = [
    ["产品", "类型", "主要收入", "对我们的启示"],
    ["超级课程表", "校园工具", "广告、校园营销、服务导流", "学生免费，B 端预算变现"],
    ["滴答清单", "效率工具", "免费 + 订阅 Pro", "重度用户可付费，但转化有限"],
    ["扫描全能王", "OCR 工具", "免费 + 订阅 / 广告", "OCR 是入口，需绑定场景"],
    ["活动行", "活动平台", "推广服务、票务分成", "活动主办方是天然付费方"],
    ["Calendly", "预约 SaaS", "按坐席订阅 + 企业版", "企业预约按坐席收费成立"],
    ["售后宝 / 瑞云", "现场服务 SaaS", "坐席年费 + 实施", "联想售后可直接对标"],
]
table(s, 0.55, 1.65, 12.2, 7, 4, [2.5, 2.2, 3.7, 3.8], data, size=10.5)
tx(
    s,
    0.55,
    5.85,
    12.2,
    0.8,
    "结论：C 端免费是行业惯例；真正付费的是企业、活动方和广告主。我们两条路径分别对标 Calendly/售后宝 与 超级课程表/活动行。",
    size=11.5,
    color=DEEP,
)
notes(s, "40 秒：快速过对标表，强调我们的两条路径都有成熟参照。")

# ---------------------------------------------------------------- 15 验证计划
s = add_slide()
header(s, "验证：已经跑通，下一步试点", "Validation", 15)
card(s, 0.55, 1.65, 5.9, 4.6, LIGHT)
tx(s, 0.8, 1.85, 5.4, 0.4, "已完成（MVP）", size=14, bold=True, color=GREEN)
bullets(
    s,
    0.8,
    2.3,
    5.4,
    3.6,
    [
        "微信文字 / 文章 / 海报三条入口全部跑通。",
        "119 条自动化测试；OCR、冲突检测、改删同步。",
        "CalDAV → DAVx5 → Android 系统日历真机闭环。",
        "2 分钟内的事件到点弹出系统通知。",
    ],
    size=11,
    gap=6,
)
card(s, 6.95, 1.65, 5.8, 4.6, PALE)
tx(s, 7.2, 1.85, 5.3, 0.4, "下一步（3 个月）", size=14, bold=True, color=DEEP)
bullets(
    s,
    7.2,
    2.3,
    5.3,
    3.6,
    [
        "联想 1 个事业部 300 坐席试点，验证爽约率与 SLA。",
        "1 所高校 2 万学生试点，验证 MAU 与留存。",
        "2 家活动主办方/广告主，验证推广位付费。",
        "App 内测：分享面板 + 截图 OCR + 跨 App 捕获。",
    ],
    size=11,
    gap=6,
)
notes(s, "40 秒：先说已经完成的真机闭环，再说三个试点。")

# ---------------------------------------------------------------- 16 SDG 指标
s = add_slide()
header(s, "SDG 成功指标", "SDG Success Metrics", 16)
items = [
    ("减少错过", "每用户每月减少 1–2 次错过活动/预约"),
    ("提醒触达", "日程写入成功率 ≥ 95%，提醒到达率 ≥ 90%"),
    ("企业效率", "试点坐席爽约率下降 ≥ 5%，SLA 达标率提升"),
    ("覆盖人数", "首年覆盖 2 万+ 用户、300+ 企业坐席"),
]
for idx, (name, desc) in enumerate(items):
    x = 0.55 + (idx % 2) * 6.2
    y = 1.7 + (idx // 2) * 2.0
    card(s, x, y, 5.9, 1.7, LIGHT)
    tx(s, x + 0.25, y + 0.2, 5.3, 0.4, name, size=17, bold=True, color=GREEN)
    tx(s, x + 0.25, y + 0.75, 5.4, 0.7, desc, size=12, color=INK)
tx(
    s,
    0.55,
    6.1,
    12.2,
    0.6,
    "对应 SDG 4（优质教育）与 SDG 9（产业创新）：让信息更可达，让服务更高效。",
    size=12,
    color=DEEP,
)
notes(s, "30 秒：四个指标，个人、系统、企业、规模。")

# ---------------------------------------------------------------- 17 风险
s = add_slide()
header(s, "风险与应对", "Threats", 17)
data = [
    ["风险", "影响", "应对"],
    ["依赖微信/第三方页面", "入口或桥接失效", "官方 API、系统级集成、多入口并行"],
    ["隐私与数据安全", "用户不信任", "最小化存储、图片 7 天清理、本地优先"],
    ["商业化验证不足", "付费意愿不确定", "先做联想试点，用 ROI 说话"],
    ["大厂竞争", "系统自带日程/助手", "做深中文活动抽取与跨 App 捕获"],
]
table(s, 0.55, 1.7, 12.2, 5, 3, [3.6, 3.6, 4.8], data, size=11)
tx(s, 0.55, 5.9, 12.2, 0.8, "原则：入口可以变，能力不变；先用可验证的场景活下来，再扩入口。", size=12, color=DEEP)
notes(s, "30 秒：主动讲风险，给出应对。")

# ---------------------------------------------------------------- 18 结语
s = add_slide()
s.shapes.add_picture(str(ASSETS / "s1_2_image.png"), Inches(7.4), Inches(1.3), width=Inches(5.2))
tx(s, 0.8, 2.1, 6.3, 0.9, "期待与您合作", size=40, bold=True, color=DEEP)
tx(s, 0.8, 3.1, 6.3, 1.2, "让每一条被看到的信息，\n都不会被错过。", size=22, bold=True, color=GREEN)
tx(s, 0.8, 4.55, 6.3, 0.5, "日程Agent · 2026 SDG Open Hack @ Tsinghua", size=12, color=GRAY)
card(s, 0.8, 5.25, 5.6, 0.9, LIGHT)
tx(s, 1.0, 5.45, 5.2, 0.5, "现场演示：扫码联系客服，发「列表」", size=12, color=DEEP)
notes(s, "结尾 20 秒：回到一句话，邀请评委体验。")

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print("saved:", OUT, "slides:", len(prs.slides))
