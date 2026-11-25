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
FONT = "微软雅黑"


def set_text(shape, lines, *, size=12, color=INK, bold=False, spacing=1.1, align=PP_ALIGN.LEFT):
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


prs = Presentation(str(TEMPLATE))

# ---------- S1 封面 ----------
s = prs.slides[0]
add_text(s, 0.55, 4.55, 4.4, 0.4, ["理时针"], size=22, bold=True, color=DEEP)
add_text(
    s, 0.55, 4.95, 4.6, 0.3,
    ["把任何 App 里的活动，一键变成会提醒的日程"],
    size=9, bold=True, color=GREEN,
)
add_text(s, 0.55, 5.28, 4.6, 0.25, ["团队：成员 A / B / C    2026.11"], size=8, color=GRAY)

# ---------- S2 一句话小结（只留一句）----------
s = prs.slides[1]
set_text(find(s, "文本框 2"), ["一句话项目小结"], size=18, bold=True, color=DEEP)
one = find(s, "Text Placeholder 1")
one.top = Inches(2.4)
one.height = Inches(1.0)
set_text(one, ["把信息入口和提醒系统连起来。"], size=26, bold=True, color=INK)

# ---------- S3 团队（占位，用户自行替换）----------
s = prs.slides[2]
set_text(find(s, "文本框 5"), ["核心团队  Team"], size=18, bold=True, color=DEEP)
team = [
    ("文本框 12", "成员 A", "产品 / 项目"),
    ("文本框 13", "成员 B", "后端 / 算法"),
    ("文本框 14", "成员 C", "前端 / 测试"),
]
for name, who, role in team:
    set_text(find(s, name), [who, role], size=10, color=INK)
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
set_text(find(s, "文本框 1"), ["问题与创新  Problem & Innovation"], size=18, bold=True, color=DEEP)
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
        "信息散落在公众号、群聊、飞书、小红书、邮件与海报里；",
        "看到不等于记住，报名截止与开始时间靠人脑记。",
        "手动建日程又慢又易错；企业侧的预约与回访同样如此。",
        "",
        "创新：把「信息入口」与「提醒系统」自动化连接——",
        "多源捕获 → 中文时间/地点抽取（规则 + OCR）→ 写入系统日历。",
    ],
    size=10.5,
    color=INK,
)

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
        "活动方与广告主：为精准触达付费。",
    ],
    size=10.5,
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
    size=9.5,
    color=INK,
)

# ---------- S6 市场规模（数字 + 增长曲线）----------
s = prs.slides[5]
set_text(find(s, "文本框 1"), ["市场规模"], size=20, bold=True, color=DEEP)
set_text(find(s, "Shape 81"), [""], size=11, color=GRAY)
remove(s, {"Shape 103", "Shape 104", "Shape 106", "Shape 107", "Shape 110", "Shape 111", "Shape 119", "Shape 102", "Shape 105", "Shape 108", "Shape 116"})

stats = [
    ("TAM 总体市场", "4,700 万+", "在校生 + 企业服务与泛职场人群", 1.62),
    ("SAM 可服务市场", "50 万+", "10 所高校 + 联想服务坐席（假设）", 2.72),
    ("SOM 首年目标", "2 万+", "1 所高校 30% MAU + 300 企业坐席", 3.82),
]
for label, number, desc, y in stats:
    add_text(s, 0.45, y, 2.2, 0.25, [label], size=10, bold=True, color=GREEN)
    add_text(s, 0.45, y + 0.28, 2.2, 0.4, [number], size=20, bold=True, color=DEEP)
    add_text(s, 2.55, y + 0.28, 2.7, 0.5, [desc], size=8.5, color=GRAY)

chart_data = CategoryChartData()
chart_data.categories = ["2026 首年", "2027", "2028"]
chart_data.add_series("覆盖用户（万）", (2, 50, 200))
gf = s.shapes.add_chart(
    XL_CHART_TYPE.LINE_MARKERS, Inches(5.35), Inches(1.55), Inches(4.3), Inches(3.2), chart_data
)
chart = gf.chart
chart.has_legend = False
chart.has_title = True
chart.chart_title.text_frame.text = "覆盖用户增长（假设）"
plot = chart.plots[0]
plot.has_data_labels = True
plot.data_labels.position = XL_LABEL_POSITION.ABOVE
plot.data_labels.font.size = Pt(9)
series = plot.series[0]
series.format.line.color.rgb = GREEN
series.format.line.width = Pt(2.5)
chart.font.name = FONT
chart.font.size = Pt(9)
chart.font.color.rgb = GRAY
chart.value_axis.has_major_gridlines = False
chart.value_axis.tick_labels.font.size = Pt(9)
chart.category_axis.tick_labels.font.size = Pt(8.5)
chart.value_axis.format.line.color.rgb = RGBColor(0xC9, 0xD6, 0xCF)
chart.category_axis.format.line.color.rgb = RGBColor(0xC9, 0xD6, 0xCF)
chart.value_axis.tick_labels.font.color.rgb = GRAY
chart.category_axis.tick_labels.font.color.rgb = GRAY
chart.chart_title.text_frame.paragraphs[0].font.size = Pt(11)
add_text(s, 0.45, 4.75, 4.5, 0.3, ["路径：校园 → 企业服务 → 泛人群"], size=9, color=GREEN, bold=True)
add_text(s, 5.35, 4.85, 4.3, 0.3, ["数据：教育部 2023；规模为假设，待试点校准"], size=8, color=GRAY)

# ---------- S7 价值主张（三列卡片）----------
s = prs.slides[6]
add_text(s, 0.25, 1.04, 3.0, 0.4, ["价值主张"], size=20, bold=True, color=DEEP)
remove(s, {"矩形 3", "Shape 95"})
values = [
    ("个人", "不遗漏", "转发/截图即入日历\n到点提醒，不再靠记忆"),
    ("企业", "可量化", "少一次爽约，少一次上门\nSLA 与人效可被衡量"),
    ("生态", "更精准", "活动与服务的触达\n发生在用户需要的那一刻"),
]
for idx, (who, tag, desc) in enumerate(values):
    x = 0.4 + idx * 3.2
    card(s, x, 1.7, 3.0, 2.55, PALE)
    add_text(s, x + 0.22, 1.9, 2.6, 0.3, [who], size=10, color=GRAY)
    add_text(s, x + 0.22, 2.28, 2.6, 0.5, [tag], size=24, bold=True, color=GREEN if idx < 2 else RGBColor(0xB8, 0x86, 0x00))
    add_text(s, x + 0.22, 3.0, 2.65, 1.2, desc.split("\n"), size=9.5, color=INK)

add_text(s, 0.4, 4.55, 9.3, 0.35, ["价值公式：正确的时间 + 正确的地点 + 一次不会错过的提醒"], size=10, bold=True, color=GREEN)

# ---------- S8 资源与伙伴 ----------
s = prs.slides[7]
set_text(find(s, "文本框 1"), ["关键资源与伙伴"], size=20, bold=True, color=DEEP)
set_text(
    find(s, "Text Placeholder 1"),
    [
        "微信生态：客服、公众号文章与分享入口。",
        "企业场景：售后预约、回访与保修到期（如联想）。",
        "校园与社团：首批验证场景与种子用户。",
        "开源组件：Radicale、DAVx5、RapidOCR、FastAPI。",
    ],
    size=10.5,
    color=INK,
)

# ---------- S9 技术与 MVP ----------
s = prs.slides[8]
set_text(find(s, "文本框 1"), ["技术实现与 MVP"], size=18, bold=True, color=DEEP)
set_text(
    find(s, "Text Placeholder 1"),
    [
        "多源入口 → 中文时间规则 + RapidOCR → FastAPI/SQLite",
        "→ CalDAV/Radicale → DAVx5 → Android 系统日历 → 通知。",
        "",
        "已跑通：文字/文章/海报；119 条测试；OCR 3–10 秒；",
        "真机写入系统日历，2 分钟内事件准时弹窗。",
    ],
    size=9.5,
    color=INK,
)
montage = SHOTS / "montage.png"
if montage.exists():
    s.shapes.add_picture(str(montage), Inches(6.4), Inches(1.55), width=Inches(3.3))

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
    add_text(photo, x, 5.35, 2.7, 0.3, [caption], size=9, color=GRAY)
add_text(photo, 0.25, 1.05, 4.0, 0.2, [""], size=7.5, color=GRAY)
# ---------- S10 商业模式（价值交换，不催联想买单）----------
s = prs.slides[9]
set_text(find(s, "文本框 1"), ["商业模式"], size=20, bold=True, color=DEEP)
set_text(
    find(s, "Shape 147"),
    [
        "C 端免费；",
        "B 端为结果付费。",
        "",
        "企业服务：交付少爽约/高 SLA",
        "终端合作：交付系统级入口",
        "消费 App：交付精准触达",
    ],
    size=10,
    color=INK,
)
for sh in list(s.shapes):
    if sh.shape_type == 13:
        sh._element.getparent().remove(sh._element)
revenues = [
    ("企业服务", "服务型企业", "按坐席 / 项目"),
    ("终端合作", "设备厂商", "授权 / 联合运营"),
    ("消费 App", "广告主·活动方", "广告 / 推广 / 票务"),
]
for idx, (name, payer, desc) in enumerate(revenues):
    x = 3.45 + idx * 2.15
    box = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.85), Inches(1.95), Inches(2.35)
    )
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xF2, 0xF7, 0xF3)
    box.line.fill.background()
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.1)
    tf.margin_right = Inches(0.1)
    for i, (text, size, bold, color) in enumerate(
        [(name, 12, True, DEEP), (payer, 9, True, GREEN), ("", 5, False, INK), (desc, 9, False, INK)]
    ):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = PP_ALIGN.CENTER
        run = para.add_run()
        run.text = text
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
bar = s.shapes.add_shape(
    MSO_SHAPE.ROUNDED_RECTANGLE, Inches(3.45), Inches(4.35), Inches(6.25), Inches(0.55)
)
bar.fill.solid()
bar.fill.fore_color.rgb = DEEP
bar.line.fill.background()
tf = bar.text_frame
tf.text = "客户获得：更少爽约 · 更高 SLA · 更精准触达｜C 端始终免费"
for p in tf.paragraphs:
    p.alignment = PP_ALIGN.CENTER
    for r in p.runs:
        r.font.name = FONT
        r.font.size = Pt(9.5)
        r.font.bold = True
        r.font.color.rgb = WHITE

# ---------- S11 验证计划（光路图）----------
s = prs.slides[10]
set_text(find(s, "文本框 1"), ["验证：已经走到哪一步"], size=18, bold=True, color=DEEP)
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
    ("已完成", "文字/文章/海报\n119 条测试\n真机通知", GREEN),
    ("下一步", "企业 300 坐席\n高校 2 万学生\n2 家活动方", DEEP),
    ("未来", "独立 App\n联想系统 AI\n跨 App 捕获", GRAY),
]
for idx, (title, desc, color) in enumerate(milestones):
    x = 0.45 + idx * 3.05
    card(s, x, 3.15, 2.85, 1.55, PALE if idx == 0 else RGBColor(0xF7, 0xF9, 0xF8))
    add_text(s, x + 0.18, 3.28, 2.5, 0.3, [title], size=11, bold=True, color=color)
    add_text(s, x + 0.18, 3.65, 2.55, 0.95, desc.split("\n"), size=8.5, color=INK)
add_text(s, 0.45, 4.95, 9.2, 0.3, ["下一步验证：付费意愿、爽约率下降、广告 eCPM"], size=8.5, color=GRAY)

# ---------- S12 SDG 指标 ----------
s = prs.slides[11]
set_text(find(s, "文本框 1"), ["SDG 成功指标"], size=20, bold=True, color=DEEP)
set_text(
    find(s, "文本占位符 2"),
    [
        "量化：",
        "· 每用户每月减少 1–2 次错过活动/预约",
        "· 日程写入成功率 ≥ 95%，提醒到达率 ≥ 90%",
        "· 试点企业爽约率下降 ≥ 5%",
        "· 首年覆盖 2 万+ 用户、300+ 企业坐席",
        "",
        "定性：让信息更可达，让服务更高效（SDG 4 / SDG 9）。",
    ],
    size=10.5,
    color=INK,
)

# ---------- S13 风险（2×2 卡片）----------
s = prs.slides[12]
set_text(find(s, "文本框 1"), ["风险与应对"], size=20, bold=True, color=DEEP)
remove(s, {"文本占位符 2"})
risks = [
    ("平台依赖", "入口或桥接失效", "官方 API / 系统级集成 / 多入口", 0.45, 1.55),
    ("隐私与安全", "用户不信任", "最小化存储 / 图片 7 天清理", 4.95, 1.55),
    ("商业化验证", "付费意愿不确定", "先用试点与 ROI 说话", 0.45, 3.35),
    ("大厂竞争", "系统自带日程/助手", "做深中文抽取与跨 App 捕获", 4.95, 3.35),
]
for title, risk, action, x, y in risks:
    card(s, x, y, 4.3, 1.55, RGBColor(0xF7, 0xF9, 0xF8))
    add_text(s, x + 0.2, y + 0.12, 3.9, 0.3, [title], size=11, bold=True, color=DEEP)
    add_text(s, x + 0.2, y + 0.48, 3.9, 0.3, ["风险：" + risk], size=8.5, color=RED)
    add_text(s, x + 0.2, y + 0.85, 3.9, 0.5, ["应对：" + action], size=8.5, color=GREEN)
add_text(s, 0.45, 5.1, 9.0, 0.3, ["原则：入口可以变，能力不变；先用可验证的场景活下来。"], size=9, color=GRAY)

# ---------- S14 结语 ----------
s = prs.slides[13]
set_text(find(s, "文本框 2"), ["期待与您合作"], size=34, bold=True, color=DEEP)
add_text(s, 0.5, 3.35, 4.3, 0.5, ["让每一条被看到的信息，都不会被错过。"], size=13, bold=True, color=GREEN)
add_text(s, 0.5, 4.0, 4.3, 0.35, ["理时针 · 2026 SDG Open Hack @ Tsinghua"], size=9, color=GRAY)

xml_slides = prs.slides._sldIdLst
sld_ids = list(xml_slides)
xml_slides.remove(sld_ids[-1])
xml_slides.insert(9, sld_ids[-1])

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print("saved:", OUT, "slides:", len(prs.slides))
