"""在官方模板副本中填入理时针内容（14 页，按用户反馈重排）。"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "myagents_files" / "2026SDG-Pitch框架&模版（建议）.pptx"
OUT = ROOT / "docs" / "2026SDG-Pitch-理时针.pptx"
SHOTS = ROOT / "data" / "shots"

INK = RGBColor(0x1F, 0x2A, 0x37)
GRAY = RGBColor(0x5B, 0x6B, 0x7A)
GREEN = RGBColor(0x2F, 0x7D, 0x5B)
DEEP = RGBColor(0x12, 0x3F, 0x5A)
YELLOW = RGBColor(0xF2, 0xB7, 0x05)
RED = RGBColor(0xB4, 0x45, 0x3A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PALE = RGBColor(0xE9, 0xF3, 0xEC)
LIGHT = RGBColor(0xF7, 0xF9, 0xF8)
FONT = "微软雅黑"


def set_text(shape, lines, *, size=12, color=INK, bold=False, spacing=1.18, align=PP_ALIGN.LEFT):
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    for idx, line in enumerate(lines):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.line_spacing = spacing
        p.space_after = Pt(3)
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color


def add_text(slide, x, y, w, h, lines, **kwargs):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    set_text(box, lines, **kwargs)
    return box


def find(slide, name):
    for sh in slide.shapes:
        if sh.name == name:
            return sh
    raise KeyError(name)


def remove(slide, names):
    for sh in list(slide.shapes):
        if sh.name in names:
            sh._element.getparent().remove(sh._element)


def card(slide, x, y, w, h, fill=PALE):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    shape.adjustments[0] = 0.08
    return shape


def arrow(slide, x, y, w=0.25, h=0.2, color=GREEN):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()



def add_table(slide, x, y, w, rows, cols, widths, data, *, size=8, header_fill=GREEN, row_h=0.56, header_h=0.42):
    shape = slide.shapes.add_table(
        rows, cols, Inches(x), Inches(y), Inches(w), Inches(0.5 * rows)
    )
    tbl = shape.table
    for i, width in enumerate(widths):
        tbl.columns[i].width = Inches(width)
    tbl.rows[0].height = Inches(header_h)
    for r in range(1, rows):
        tbl.rows[r].height = Inches(row_h)
    for r in range(rows):
        for c in range(cols):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.06)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            cell.text = str(data[r][c])
            for para in cell.text_frame.paragraphs:
                for run in para.runs:
                    run.font.name = FONT
                    run.font.size = Pt(size)
                    run.font.color.rgb = WHITE if r == 0 else INK
                    run.font.bold = r == 0
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = header_fill
            else:
                cell.fill.fore_color.rgb = WHITE if r % 2 else RGBColor(0xF2, 0xF7, 0xF3)
    return tbl

prs = Presentation(str(TEMPLATE))

# ---------- S1 封面 ----------
s = prs.slides[0]
add_text(s, 0.55, 4.55, 4.4, 0.4, ["理时针"], size=22, bold=True, color=DEEP)
add_text(
    s, 0.55, 4.95, 4.6, 0.3,
    ["看到即日程：把活动与预约，变成会响的日历提醒"],
    size=9.5, bold=True, color=GREEN,
)
add_text(s, 0.55, 5.28, 4.6, 0.25, ["团队：成员 A / B / C    2026.11"], size=9, color=GRAY)

# ---------- S2 一句话小结（只留一句）----------
s = prs.slides[1]
set_text(find(s, "文本框 2"), ["一句话项目小结"], size=20, bold=True, color=DEEP)
one = find(s, "Text Placeholder 1")
one.top = Inches(2.4)
one.height = Inches(1.0)
set_text(one, ["看到即日程。"], size=28, bold=True, color=INK)

# ---------- S3 团队（占位，用户自行替换）----------
s = prs.slides[2]
set_text(find(s, "文本框 5"), ["核心团队  Team"], size=20, bold=True, color=DEEP)
team = [
    ("文本框 12", "成员 A", "产品 / 项目"),
    ("文本框 13", "成员 B", "后端 / 算法"),
    ("文本框 14", "成员 C", "前端 / 测试"),
]
for name, who, role in team:
    set_text(find(s, name), [who, role], size=11, color=INK)
add_text(s, 0.55, 4.35, 8.8, 0.4, ["从需求、解析、OCR 到真机日历同步，全部自己实现。"], size=10.5, color=GRAY)
for sh in list(s.shapes):
    if sh.name in {"文本框 15", "文本框 16"}:
        sh._element.getparent().remove(sh._element)
    elif sh.shape_type == 13:
        sh._element.getparent().remove(sh._element)
for cx, letter in [(0.56, "A"), (2.49, "B"), (4.38, "C")]:
    oval = s.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(cx), Inches(2.11), Inches(0.98), Inches(0.98)
    )
    oval.fill.solid()
    oval.fill.fore_color.rgb = RGBColor(0xE3, 0xEF, 0xE8)
    oval.line.fill.background()
    tf = oval.text_frame
    tf.text = letter
    for p in tf.paragraphs:
        p.alignment = PP_ALIGN.CENTER
        for r in p.runs:
            r.font.name = FONT
            r.font.size = Pt(22)
            r.font.bold = True
            r.font.color.rgb = GREEN

# ---------- S4 问题与创新 ----------
s = prs.slides[3]
set_text(find(s, "文本框 1"), ["痛点：错过的成本"], size=20, bold=True, color=DEEP)
for sh in list(s.shapes):
    if sh.left is not None and sh.left >= Inches(5.7):
        sh._element.getparent().remove(sh._element)
poster = ROOT / "data" / "images" / "20261125-094341-98d5ca00.jpg"
if poster.exists():
    s.shapes.add_picture(str(poster), Inches(6.55), Inches(1.5), height=Inches(3.5))
    add_text(s, 6.35, 5.1, 3.2, 0.3, ["真实输入：公众号活动海报"], size=9, color=GRAY)
set_text(
    find(s, "文本框 2"),
    [
        "信息散落在公众号、群聊、海报、邮件里，人靠脑子记、靠手抄日历，必然漏。",
        "个人：高频学生每月错过 1–2 次；机会成本难计价，但可测提醒覆盖率。",
        "企业：一次爽约 = 一次二次上门；行业锚点 100–130 元/单，二次售后率 6.7%。",
        "月损失 = N × r × C；例：1000 单 × 10% × 120 元 ≈ 1.2 万元/月。",
        "",
        "创新：捕获 → 规则 + OCR 理解 → 写入系统日历，由系统负责到点提醒。",
    ],
    size=9.6,
    color=INK,
)
add_text(s, 0.25, 4.72, 5.4, 0.3, ["来源：鲁班到家/中国家电网 2024；爽约率为假设，待试点校准"], size=7.5, color=GRAY)

# ---------- S5 目标客户（先讲获益，不催付费）----------
s = prs.slides[4]
set_text(find(s, "文本框 1"), ["目标客户"], size=20, bold=True, color=DEEP)
remove(s, {"矩形 8"})
set_text(
    find(s, "Subtitle 17"),
    [
        "免费使用：学生、职场人、社群成员，",
        "以及任何在 App 里收到活动/预约信息的人。",
        "",
        "校园是首批场景：活动密度高、传播快，",
        "但同样的能力可平移到企业与社群。",
        "",
        "活动主办方：为报名 → 到场转化付费。",
    ],
    size=11,
    color=INK,
)
add_text(s, 5.95, 1.65, 3.3, 0.35, ["企业为什么愿意投入？"], size=13, bold=True, color=GREEN)
add_text(
    s, 5.95, 2.1, 3.3, 2.6,
    [
        "更少爽约：预约自动进日历",
        "更高 SLA：回访/保修到期不遗漏",
        "更高人效：客服少做手工登记",
        "新增机会：保修到期与耗材复购",
        "",
        "先证明 ROI，再谈合作。",
    ],
    size=10.2,
    color=INK,
)
add_text(s, 0.45, 5.05, 9.2, 0.3, ["C 端免费 · 企业为结果付费 · 活动方为到场转化付费"], size=9.5, bold=True, color=GREEN)

# ---------- S6 市场规模 ----------
s = prs.slides[5]
_t = find(s, "文本框 1")
_t.width = Inches(8.6)
set_text(_t, ["市场：消费端种子，企业端付费"], size=20, bold=True, color=DEEP)
remove(s, {"Shape 81", "Shape 103", "Shape 104", "Shape 106", "Shape 107", "Shape 110", "Shape 111", "Shape 119", "Shape 102", "Shape 105", "Shape 108", "Shape 116"})

card(s, 0.35, 1.45, 4.45, 3.15, PALE)
add_text(s, 0.55, 1.62, 4.0, 0.3, ["消费端（获客层，不直接变现）"], size=11, bold=True, color=GREEN)
add_text(s, 0.55, 2.0, 4.0, 2.4, [
    "TAM：4,763 万在校生（教育部 2023）",
    "SAM：其中 1%–5% 愿意做一次性日历配置（待验证）",
    "SOM：1 所高校 + 若干社群，数千 MAU",
    "目标：验证留存，不追求数字好看",
], size=9.5, color=INK)

card(s, 5.0, 1.45, 4.6, 3.15, LIGHT)
add_text(s, 5.2, 1.62, 4.2, 0.3, ["企业端（付费层，可量化 ROI）"], size=11, bold=True, color=GREEN)
add_text(s, 5.2, 2.0, 4.2, 2.4, [
    "上门/售后服务市场大，但坐席与爽约率无权威统计",
    "联想售后是现成标杆：预约、回访、保修到期",
    "用 N×r×C 验证：爽约率每降 1 个点都能算清",
    "目标：验证付费意愿与续约",
], size=9.5, color=INK)
add_text(s, 0.45, 4.85, 9.2, 0.3, ["不做「4,700 万 → 增长曲线」的拍脑袋叙事；消费端验证留存，企业端验证付费。"], size=9.2, bold=True, color=GREEN)

# ---------- S7 价值主张 ----------
s = prs.slides[6]
add_text(s, 0.25, 1.04, 3.0, 0.4, ["价值主张"], size=20, bold=True, color=DEEP)
remove(s, {"矩形 3", "Shape 95"})
values = [
    ("个人", "不遗漏", "看到即日程，不再靠记忆"),
    ("企业", "可量化", "爽约率下降，SLA 可衡量"),
    ("活动方", "到场转化", "报名 → 到场，主办方愿付费"),
]
for idx, (who, tag, desc) in enumerate(values):
    x = 0.4 + idx * 3.2
    card(s, x, 1.7, 3.0, 2.45, PALE)
    add_text(s, x + 0.22, 1.9, 2.6, 0.3, [who], size=10, color=GRAY)
    add_text(s, x + 0.22, 2.25, 2.6, 0.5, [tag], size=24, bold=True, color=GREEN if idx < 2 else RGBColor(0xB8, 0x86, 0x00))
    add_text(s, x + 0.22, 2.95, 2.65, 1.0, [desc], size=10, color=INK)
add_text(s, 0.4, 4.5, 9.3, 0.5, ["提醒交给系统日历：微信 48 小时窗口、订阅消息逐次授权，都撑不起准时提醒。"], size=9.5, bold=True, color=GREEN)

# ---------- S8 资源与伙伴 ----------
s = prs.slides[7]
set_text(find(s, "文本框 1"), ["关键资源与伙伴"], size=20, bold=True, color=DEEP)
set_text(
    find(s, "Text Placeholder 1"),
    [
        "微信生态：客服、公众号文章与分享入口。",
        "企业场景：售后预约、回访、保修到期（联想为标杆）。",
        "活动主办方：社团、院系、活动公司，提供场景与付费。",
        "开源组件：Radicale、DAVx5、RapidOCR、FastAPI。",
    ],
    size=11,
    color=INK,
)

# ---------- S9 技术与 MVP ----------
s = prs.slides[8]
_t = find(s, "文本框 1")
_t.width = Inches(8.0)
set_text(_t, ["技术实现与 MVP（诚实边界）"], size=20, bold=True, color=DEEP)
remove(s, {"Text Placeholder 1"})
card(s, 0.35, 1.45, 4.45, 3.0, PALE)
add_text(s, 0.55, 1.62, 4.0, 0.3, ["已实现（可演示）"], size=11, bold=True, color=GREEN)
add_text(s, 0.55, 2.0, 4.0, 2.2, [
    "文字 / 文章链接 / 海报 OCR 三入口",
    "中文相对时间、区间、截止归一化",
    "冲突检测、编号管理、改 / 删",
    "CalDAV → 系统日历 → 到点提醒",
    "119 条测试 + 真机闭环",
], size=9.5, color=INK)
card(s, 5.05, 1.45, 4.55, 3.0, LIGHT)
add_text(s, 5.25, 1.62, 4.1, 0.3, ["待实现（规划）"], size=11, bold=True, color=GRAY)
add_text(s, 5.25, 2.0, 4.1, 2.2, [
    "官方微信客服 API（替代网页桥接）",
    "自研 App，去掉 DAVx5 配置",
    "多用户隔离、正式 CalDAV 账户",
    "企业私有化 / 远期端侧",
    "跨 App 捕获（分享面板 / 识屏）",
], size=9.5, color=INK)
add_text(s, 0.35, 4.65, 9.3, 0.5, ["规则 + OCR，不是大模型；当前数据经微信与服务端，企业版可私有化部署。不夸大「数据不出端」。"], size=8.8, color=GRAY)

# ---------- 新增：实测画面页（插在第 9 页之后）----------
layout = next(l for l in prs.slide_layouts if l.name == "3_Title and two columns")
photo = prs.slides.add_slide(layout)
for sh in list(photo.shapes):
    if sh.is_placeholder:
        sh._element.getparent().remove(sh._element)
add_text(photo, 0.25, 0.85, 8.0, 0.4, ["实测画面"], size=20, bold=True, color=DEEP)
shots = [
    ("chat.png", "客服卡片 · 界面示意"),
    ("calendar_real.png", "系统日历 · 真机截图"),
    ("notification_real.png", "到点通知 · 真机截图"),
]
for idx, (name, caption) in enumerate(shots):
    path = SHOTS / name
    if not path.exists():
        continue
    x = 0.75 + idx * 2.85
    photo.shapes.add_picture(str(path), Inches(x), Inches(1.35), height=Inches(3.9))
    add_text(photo, x, 5.35, 2.7, 0.3, [caption], size=10, color=GRAY)
add_text(photo, 0.25, 1.05, 4.0, 0.2, [""], size=7.5, color=GRAY)
# ---------- S10 商业模式（两条路线）----------
s = prs.slides[9]
set_text(find(s, "文本框 1"), ["商业模式：两条路线"], size=20, bold=True, color=DEEP)
set_text(
    find(s, "Shape 147"),
    [
        "C 端永久免费；",
        "两条产品路线，各有定位。",
        "",
        "路线一：独立 App → 广告收益",
        "路线二：融合天禧 AI → 产品爆点",
    ],
    size=10,
    color=INK,
)
for sh in list(s.shapes):
    if sh.shape_type == 13:
        sh._element.getparent().remove(sh._element)

# 路线一：App + 广告
c1 = card(s, 0.4, 1.85, 4.35, 2.85, PALE)
add_text(s, 0.65, 2.0, 3.9, 0.3, ["路线一 · 独立 App"], size=13, bold=True, color=GREEN)
add_text(s, 0.65, 2.4, 3.9, 0.3, ["免费 + 广告，对标超级课程表"], size=10.5, bold=True, color=DEEP)
add_text(s, 0.65, 2.82, 3.9, 1.7, [
    "开屏 / 信息流 / 活动推广",
    "校园是天然高密度场景",
    "收入随 MAU 规模增长",
    "属于中长期可持续收益",
], size=9.5, color=INK)
add_text(s, 0.65, 4.42, 3.9, 0.25, ["需要规模，短期不做收入预期"], size=8, color=GRAY)

# 路线二：天禧 AI
c2 = card(s, 5.0, 1.85, 4.35, 2.85, LIGHT)
add_text(s, 5.25, 2.0, 3.9, 0.3, ["路线二 · 融合天禧 AI"], size=13, bold=True, color=RGBColor(0xB8,0x86,0x00))
add_text(s, 5.25, 2.4, 3.9, 0.3, ["产品小流量爆点"], size=10.5, bold=True, color=DEEP)
add_text(s, 5.25, 2.82, 3.9, 1.7, [
    "系统级「截图即日程」",
    "从问答走向办事的高频入口",
    "做口碑与差异化，把产品做好",
    "不是持续收益，但奠定产品心智",
], size=9.5, color=INK)
add_text(s, 5.25, 4.42, 3.9, 0.25, ["价值在于产品，不在于现金流"], size=8, color=GRAY)

bar = s.shapes.add_shape(
    MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.4), Inches(4.95), Inches(9.0), Inches(0.6)
)
bar.fill.solid()
bar.fill.fore_color.rgb = DEEP
bar.line.fill.background()
tf = bar.text_frame
tf.text = "C 端永久免费｜App 负责收入，天禧融合负责产品｜共享同一套「捕获 → 结构化 → 日历」能力"
for p_ in tf.paragraphs:
    p_.alignment = PP_ALIGN.CENTER
    for r in p_.runs:
        r.font.name = FONT
        r.font.size = Pt(9)
        r.font.bold = True
        r.font.color.rgb = WHITE

# ---------- S11 验证计划（光路图）----------
s = prs.slides[10]
set_text(find(s, "文本框 1"), ["验证：已经走到哪一步"], size=20, bold=True, color=DEEP)
remove(s, {"Text Placeholder 1", "Text Placeholder 2"})
band = s.shapes.add_shape(
    MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.35), Inches(2.02), Inches(8.9), Inches(0.16)
)
band.fill.solid()
band.fill.fore_color.rgb = RGBColor(0xC9, 0xE6, 0xD5)
band.line.fill.background()
nodes = [
    ("01", "捕获", "微信/截图"),
    ("02", "解析", "时间/地点"),
    ("03", "成卡", "编号/冲突"),
    ("04", "同步", "CalDAV"),
    ("05", "提醒", "系统日历"),
]
for idx, (num, name, desc) in enumerate(nodes):
    x = 0.45 + idx * 1.78
    circle = s.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(x + 0.45), Inches(1.72), Inches(0.42), Inches(0.42)
    )
    circle.fill.solid()
    circle.fill.fore_color.rgb = GREEN
    circle.line.fill.background()
    tf = circle.text_frame
    tf.text = "✓"
    for p in tf.paragraphs:
        p.alignment = PP_ALIGN.CENTER
        for r in p.runs:
            r.font.name = FONT
            r.font.size = Pt(10)
            r.font.bold = True
            r.font.color.rgb = WHITE
    add_text(s, x, 2.25, 1.35, 0.25, [f"{num} {name}"], size=9, bold=True, color=DEEP, align=PP_ALIGN.CENTER)
    add_text(s, x, 2.52, 1.35, 0.3, [desc], size=7.5, color=GRAY, align=PP_ALIGN.CENTER)
    if idx < 4:
        arrow(s, x + 1.48, 2.08, 0.2, 0.12, GREEN)

add_text(s, 5.9, 1.08, 3.6, 0.3, ["MVP：已闭环"], size=11, bold=True, color=GREEN, align=PP_ALIGN.RIGHT)
milestones = [
    ("已完成", "三入口 + 真机闭环|119 条测试|到点通知", GREEN),
    ("0–3 个月", "联想 1 个事业部|1 所高校种子|2 家活动方", DEEP),
    ("3–24 个月", "官方客服 API|自研 App 去 DAVx5|企业复制扩张", GRAY),
]
for idx, (title, desc, color) in enumerate(milestones):
    x = 0.45 + idx * 3.05
    card(s, x, 3.15, 2.85, 1.55, PALE if idx == 0 else RGBColor(0xF7, 0xF9, 0xF8))
    add_text(s, x + 0.18, 3.28, 2.5, 0.3, [title], size=11, bold=True, color=color)
    add_text(s, x + 0.18, 3.65, 2.55, 0.95, desc.split("|"), size=9.3, color=INK)
add_text(s, 0.45, 4.95, 9.2, 0.3, ["测量：写入成功率 ≥95% · 爽约率降 ≥5% · 留存/续约"], size=9, color=GRAY)

# ---------- S12 SDG 指标 ----------
s = prs.slides[11]
set_text(find(s, "文本框 1"), ["SDG 成功指标"], size=20, bold=True, color=DEEP)
remove(s, {"文本占位符 2"})
sdg_items = [
    ("减少错过", "每用户每月减少 1–2 次错过活动/预约"),
    ("写入与触达", "日程写入成功率 ≥ 95%，提醒到达率 ≥ 90%"),
    ("企业效率", "试点企业爽约率下降 ≥ 5%"),
    ("覆盖规模", "首年种子：数千 MAU + 1 个事业部试点"),
]
for idx, (title, desc) in enumerate(sdg_items):
    x = 0.45 + (idx % 2) * 4.5
    y = 1.55 + (idx // 2) * 1.65
    card(s, x, y, 4.25, 1.45, RGBColor(0xF7, 0xF9, 0xF8))
    add_text(s, x + 0.2, y + 0.14, 3.8, 0.3, [title], size=12, bold=True, color=GREEN)
    add_text(s, x + 0.2, y + 0.55, 3.85, 0.7, [desc], size=10, color=INK)
add_text(s, 0.45, 5.05, 9.0, 0.3, ["定性：让信息更可达，让服务更高效（SDG 4 / SDG 9）。"], size=10, color=GRAY)

# ---------- S13 风险（2×2 卡片）----------
s = prs.slides[12]
set_text(find(s, "文本框 1"), ["风险与应对"], size=20, bold=True, color=DEEP)
remove(s, {"文本占位符 2"})
risks = [
    ("平台依赖", "桥接或入口失效", "官方 API / 自研 App / 多入口", 0.45, 1.55),
    ("配置门槛", "DAVx5 劝退用户", "iOS 原生 CalDAV；App 用 CalendarContract", 4.95, 1.55),
    ("大厂竞争", "系统 AI / 微信自己做", "做深垂直闭环，先落企业付费", 0.45, 3.35),
    ("付费意愿", "效果费模式未验证", "试点 + 真实 ROI，效果付费降低门槛", 4.95, 3.35),
]
for title, risk, action, x, y in risks:
    card(s, x, y, 4.3, 1.55, RGBColor(0xF7, 0xF9, 0xF8))
    add_text(s, x + 0.2, y + 0.12, 3.9, 0.3, [title], size=11, bold=True, color=DEEP)
    add_text(s, x + 0.2, y + 0.48, 3.9, 0.3, ["风险：" + risk], size=9.3, color=RED)
    add_text(s, x + 0.2, y + 0.85, 3.9, 0.5, ["应对：" + action], size=9.3, color=GREEN)
add_text(s, 0.45, 5.1, 9.0, 0.3, ["本地化口径：不声称数据不出端；B 端私有化、远期端侧，能力按场景演进。"], size=9, color=GRAY)

# ---------- S14 结语 ----------
s = prs.slides[13]
set_text(find(s, "文本框 2"), ["期待与您合作"], size=34, bold=True, color=DEEP)
add_text(s, 0.5, 3.35, 4.3, 0.5, ["让每一条被看到的信息，都不会被错过。"], size=13, bold=True, color=GREEN)
add_text(s, 0.5, 4.0, 4.3, 0.35, ["理时针 · 2026 SDG Open Hack @ Tsinghua"], size=9, color=GRAY)

xml_slides = prs.slides._sldIdLst
sld_ids = list(xml_slides)
xml_slides.remove(sld_ids[-1])
xml_slides.insert(9, sld_ids[-1])


# ---------- 与联想命题的关联：重构 AI 时代的工作方式 ----------
layout = next(l for l in prs.slide_layouts if l.name == "3_Title and two columns")
s = prs.slides.add_slide(layout)
for sh in list(s.shapes):
    if sh.is_placeholder:
        sh._element.getparent().remove(sh._element)
add_text(s, 0.25, 0.8, 9.4, 0.42, ["重构 AI 时代的工作方式：从天禧「问答」到「办事」"], size=19, bold=True, color=DEEP)
add_text(s, 0.25, 1.2, 9.4, 0.24, ["命题一 · AI 办公任务助手｜选定角色：售后服务工程师 / 客户成功专员"], size=9, color=GRAY)

# 顶部一句立意
band = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.35), Inches(1.55), Inches(9.3), Inches(0.82))
band.fill.solid(); band.fill.fore_color.rgb = DEEP; band.line.fill.background()
tf = band.text_frame; tf.word_wrap = True; tf.margin_left = Inches(0.2); tf.margin_right = Inches(0.2); tf.margin_top = Inches(0.1)
lines = [("今天的 AI 是你问它答；理时针让它「替你在对的时刻推动下一步」。", 11.5, True),
         ("人不再靠记、靠抄、靠切换 App——信息一出现，就自动落到该落的地方。", 9, False)]
for i,(t,sz,b) in enumerate(lines):
    para = tf.paragraphs[0] if i==0 else tf.add_paragraph()
    para.alignment = PP_ALIGN.CENTER
    run = para.add_run(); run.text = t; run.font.name = FONT; run.font.size = Pt(sz); run.font.bold = b; run.font.color.rgb = WHITE

# 三层价值（近期/中期/远期）
vals = [
    ("近期 · 场景价值", GREEN, "售后预约 / 回访 / 保修到期自动进日历；降爽约、提 SLA、少手工登记，可量化 ROI。"),
    ("中期 · 产品价值", RGBColor(0xB8,0x86,0x00), "系统级「截图即日程」，让天禧 AI 从问答走向办事，多一个高频日常入口。"),
    ("远期 · 生态价值", GRAY, "跨文档 / 跨软件 / 跨生态的统一「信息→日程」，成为联想终端的差异化能力模块。"),
]
for idx,(title,color,desc) in enumerate(vals):
    x = 0.35 + idx*3.2
    card(s, x, 2.62, 2.95, 1.95, PALE if idx!=2 else LIGHT)
    add_text(s, x+0.2, 2.78, 2.55, 0.4, [title], size=11, bold=True, color=color)
    add_text(s, x+0.2, 3.22, 2.6, 1.2, [desc], size=8.8, color=INK)

# 底部：任务 + 诚实边界
add_text(s, 0.35, 4.8, 9.3, 0.28, ["任务：把会话、邮件、纪要、截图里的时间承诺，变成跟进日程与提醒。"], size=9.5, bold=True, color=DEEP)
add_text(s, 0.35, 5.16, 9.3, 0.26, ["诚实边界：当前规则 + OCR，非大模型、非全端侧；企业版可私有化部署，远期端侧。每条日程保留来源，可溯源。"], size=8.3, color=GRAY)
s.notes_slide.notes_text_frame.text = (
    "60 秒：联想命题一要求选定一个角色 + 一项办公任务。我们选售后服务工程师，"
    "任务是把握会话、邮件、纪要、截图里的时间承诺变成跟进日程。"
    "但这一页想讲的是更根本的东西：我们不是在某个软件里加个日历按钮，"
    "而是重构 AI 时代的工作方式——把天禧 AI 从「你问它答」变成「它替你在对的时刻推动下一步」。"
    "近期是售后场景的可量化 ROI；中期让天禧从问答走向办事；远期成为联想终端的跨生态能力模块。"
    "诚实地说：当前是规则 + OCR，不是大模型，也不是全端侧；企业版私有化、远期端侧。"
)

xml_slides = prs.slides._sldIdLst
ids = list(xml_slides)
xml_slides.remove(ids[-1])
xml_slides.insert(2, ids[-1])

# ---------- 竞品与真实威胁 ----------
layout = next(l for l in prs.slide_layouts if l.name == "3_Title and two columns")
s = prs.slides.add_slide(layout)
for sh in list(s.shapes):
    if sh.is_placeholder:
        sh._element.getparent().remove(sh._element)
add_text(s, 0.25, 0.8, 9.4, 0.4, ["竞品与真实威胁"], size=20, bold=True, color=DEEP)

data = [
    ["类型", "代表", "一键添加", "我们的差异"],
    ["原生日历", "手机 / 电脑", "否，只能手动", "不会从中文内容抽取"],
    ["生态日历", "飞书 / Teams", "仅自家生态", "跨生态就失效"],
    ["活动工具", "活动行 / 超级课程表", "报名 / 课程", "不做通用信息→日历"],
    ["系统 AI", "小爱 / 小艺 / 天禧", "通用识屏，可能降维", "我们做垂直 + 企业落地"],
    ["微信自己", "微信", "若原生做，直接覆盖", "先跑企业付费，不押单一入口"],
    ["理时针", "我们", "微信→日历已跑通", "企业 ROI + 来源可溯源"],
]
add_table(s, 0.35, 1.28, 9.3, 7, 4, [1.55, 2.1, 2.0, 2.75], data, size=8.3, row_h=0.45, header_h=0.36)
add_text(s, 0.35, 5.02, 9.3, 0.25, ["护城河很薄：靠企业场景先发 + 数据闭环逐步建立，不靠概念。"], size=8.5, bold=True, color=DEEP)
add_text(s, 0.35, 5.3, 9.3, 0.25, ["对联想：企业售后是可量化 ROI 的现成场景；系统级入口是中期产品价值。"], size=7.8, color=GRAY)
s.notes_slide.notes_text_frame.text = (
    "45 秒：原生日历只能手动；飞书和 Teams 只在自己生态里；活动工具只覆盖报名。"
    "真正的威胁是手机厂商系统 AI 和微信自己。我们的打法是先做深垂直闭环，"
    "先落企业付费场景，用 ROI 和数据闭环逐步建立壁垒，而不是现在就说护城河很深。"
)

xml_slides = prs.slides._sldIdLst
ids = list(xml_slides)
xml_slides.remove(ids[-1])
xml_slides.insert(5, ids[-1])

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print("saved:", OUT, "slides:", len(prs.slides))
