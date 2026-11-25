"""用真实测试数据渲染三张手机界面示意图（非真机照片，图内标注）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "shots"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 900, 2000
FONT = r"C:\Windows\Fonts\msyh.ttc"
BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
GREEN = (7, 193, 96)
DARK = (24, 28, 33)
GRAY = (120, 128, 136)
LIGHT = (245, 246, 248)
WHITE = (255, 255, 255)
BLUE = (46, 125, 91)


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def status_bar(d, dark=False):
    color = WHITE if dark else DARK
    d.text((40, 24), "10:32", font=font(26), fill=color)
    d.text((720, 24), "5G", font=font(22), fill=color)
    d.rounded_rectangle((770, 30, 830, 52), radius=6, outline=color, width=3)
    d.rectangle((832, 36, 840, 46), fill=color)
    d.rectangle((776, 35, 820, 47), fill=color)
    d.text((690, 24), "82%", font=font(20), fill=color)


def chat_screen():
    img = Image.new("RGB", (W, H), LIGHT)
    d = ImageDraw.Draw(img)
    status_bar(d)
    d.rectangle((0, 76, W, 180), fill=WHITE)
    d.line((0, 180, W, 180), fill=(230, 232, 235), width=2)
    d.text((44, 104), "‹", font=font(52), fill=DARK)
    logo = Image.open(ROOT / "data" / "logo" / "lishizhen.png").convert("RGBA").resize((56, 56))
    img.paste(logo, (108, 100), logo)
    d.text((176, 106), "理时针客服", font=font(30, True), fill=DARK)
    d.text((800, 112), "⋯", font=font(30), fill=DARK)

    # 客户消息：海报
    d.ellipse((40, 220, 100, 280), fill=(220, 226, 232))
    d.text((58, 232), "夏", font=font(28, True), fill=(80, 90, 100))
    d.text((116, 214), "夏季芭乐  09:37", font=font(20), fill=GRAY)
    poster = Image.open(ROOT / "data" / "images" / "20261125-094341-98d5ca00.jpg")
    poster.thumbnail((360, 780))
    card = Image.new("RGB", (380, 800), WHITE)
    card.paste(poster, ((380 - poster.width) // 2, (800 - poster.height) // 2))
    mask = Image.new("L", (380, 800), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 380, 800), radius=16, fill=255)
    img.paste(card, (116, 300), mask)

    # 客服回复卡片
    bubble = (250, 1140, 860, 1770)
    shadow = (bubble[0] + 4, bubble[1] + 6, bubble[2] + 4, bubble[3] + 6)
    d.rounded_rectangle(shadow, radius=24, fill=(228, 231, 235))
    d.rounded_rectangle(bubble, radius=24, fill=WHITE)
    d.ellipse((276, 1168, 316, 1208), fill=GREEN)
    d.line((286, 1188, 294, 1196), fill=WHITE, width=4)
    d.line((294, 1196, 307, 1180), fill=WHITE, width=4)
    d.text((330, 1164), "已记录 #10", font=font(30, True), fill=DARK)
    lines = [
        ("标题", "新火传书·旧卷逢新—2026年赠书转赠活动"),
        ("时间", "11-25 周三 09:00-18:00"),
        ("地点", "清华大学人文社科图书馆G层大同厅"),
        ("状态", "已同步"),
    ]
    y = 1230
    for label, value in lines:
        d.text((276, y), label, font=font(22), fill=GRAY)
        d.text((336, y - 2), value, font=font(22), fill=DARK)
        y += 74
    d.line((276, 1610, 834, 1610), fill=(235, 238, 241), width=2)
    d.text((276, 1632), "回复 #10 看详情｜改 10 时间 ...｜删 10", font=font(18), fill=BLUE)

    # 输入栏
    d.rectangle((0, 1850, W, H), fill=WHITE)
    d.line((0, 1850, W, 1850), fill=(230, 232, 235), width=2)
    d.ellipse((40, 1880, 100, 1940), outline=GRAY, width=3)
    d.rounded_rectangle((120, 1880, 700, 1940), radius=30, fill=LIGHT)
    d.text((150, 1894), "回复 夏季芭乐", font=font(20), fill=(160, 166, 172))
    d.text((740, 1880), "＋", font=font(40), fill=GRAY)
    d.text((810, 1886), "发送", font=font(22, True), fill=GREEN)

    d.text((40, 1960), "界面示意 · 文案来自真实测试记录", font=font(16), fill=(170, 176, 182))
    img.save(OUT / "chat.png")


def calendar_screen():
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    status_bar(d)
    d.text((40, 100), "11 月", font=font(44, True), fill=DARK)
    d.text((190, 110), "2026", font=font(26), fill=GRAY)
    d.text((760, 110), "今天", font=font(24), fill=GREEN)
    d.text((44, 200), "25", font=font(64, True), fill=DARK)
    d.text((150, 215), "星期三", font=font(26), fill=GRAY)
    d.line((0, 300, W, 300), fill=(235, 238, 241), width=2)

    def event(y, time, title, place, color):
        d.rounded_rectangle((70, y, 86, y + 130), radius=8, fill=color)
        d.text((110, y), time, font=font(22, True), fill=color)
        d.text((110, y + 40), title, font=font(24, True), fill=DARK)
        d.text((110, y + 86), place, font=font(20), fill=GRAY)

    d.text((44, 330), "今天", font=font(20, True), fill=GREEN)
    event(370, "09:00 – 18:00", "新火传书·旧卷逢新—2026年赠书转赠活动", "清华大学人文社科图书馆G层大同厅", GREEN)
    d.text((44, 560), "11 月 27 日  周五", font=font(20, True), fill=GRAY)
    event(610, "19:00", "新生舞会", "大礼堂", (66, 133, 244))
    event(770, "20:00 – 22:00", "讲座B", "六教", (66, 133, 244))
    event(930, "19:00", "竞赛招募｜智能产品创意设计应用大赛", "线上/线下", (242, 153, 74))
    d.text((44, 1130), "来自「日程Agent」日历 · DAVx5 同步", font=font(18), fill=(170, 176, 182))
    d.text((40, 1810), "界面示意 · 事件来自真实测试数据", font=font(16), fill=(180, 186, 192))
    d.rectangle((0, 1900, W, H), fill=WHITE)
    d.line((0, 1900, W, 1900), fill=(235, 238, 241), width=2)
    d.text((90, 1930), "日", font=font(24, True), fill=DARK)
    d.text((290, 1930), "周", font=font(24), fill=GRAY)
    d.text((490, 1930), "月", font=font(24), fill=GRAY)
    d.text((690, 1930), "列表", font=font(24), fill=GRAY)
    img.save(OUT / "calendar.png")


def notification_screen():
    img = Image.new("RGB", (W, H), (18, 22, 30))
    d = ImageDraw.Draw(img)
    # 渐变
    for y in range(H):
        t = y / H
        d.line((0, y, W, y), fill=(18 + int(18 * t), 22 + int(26 * t), 30 + int(34 * t)))
    status_bar(d, dark=True)
    d.text((60, 200), "09:53", font=font(120, True), fill=WHITE)
    d.text((66, 340), "11 月 25 日  星期三", font=font(28), fill=(210, 216, 224))
    d.rounded_rectangle((40, 720, 860, 1040), radius=28, fill=(250, 250, 252))
    d.rounded_rectangle((70, 750, 140, 820), radius=18, fill=GREEN)
    d.text((86, 760), "25", font=font(34, True), fill=WHITE)
    d.text((166, 752), "日历", font=font(22), fill=GRAY)
    d.text((166, 790), "提醒测试", font=font(32, True), fill=DARK)
    d.text((70, 870), "上午 9:53 · 309会议室", font=font(24), fill=(70, 78, 88))
    d.text((70, 930), "新火传书活动即将开始？打开日历查看今日安排。", font=font(20), fill=GRAY)
    d.text((640, 970), "稍后提醒", font=font(22, True), fill=GREEN)
    d.text((40, 1960), "界面示意 · 通知已通过真机 dumpsys 验证", font=font(16), fill=(150, 158, 168))
    img.save(OUT / "notification.png")


chat_screen()
calendar_screen()
notification_screen()
print("saved 3 screens")
