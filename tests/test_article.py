from datetime import datetime

import httpx
import pytest

from app.parsing.article import (
    Article,
    ArticleFetchError,
    extract_article_activity,
    extract_wechat_url,
    fetch_article,
)
from app.parsing.time_norm import TZ

BASE = datetime(2026, 11, 22, 10, 0, tzinfo=TZ)

ARTICLE_HTML = """
<html><head>
  <meta property="og:title" content="新生舞会 | 清华大学" />
</head><body>
  <h1 id="activity-name"> 新生舞会 </h1>
  <div id="js_content">
    <p>发布时间：2026-11-24 18:00</p>
    <p>活动时间：11月27日（周五）19:00-21:00</p>
    <p>活动地点：大礼堂</p>
    <p>报名截止：11月25日 24:00</p>
    <p>主办单位：计算机系学生会</p>
    <p>欢迎同学们参加。</p>
  </div>
</body></html>
"""

ANTI_BOT_HTML = """
<html><body>
  <h1>环境异常</h1>
  <p>完成验证后即可继续访问。</p>
</body></html>
"""


def mock_transport(html: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"Content-Type": "text/html"})

    return httpx.MockTransport(handler)


def test_fetch_article_extracts_title_and_body():
    article = fetch_article(
        "https://mp.weixin.qq.com/s/abc",
        transport=mock_transport(ARTICLE_HTML),
    )
    assert article.title == "新生舞会"
    assert "活动时间" in article.text
    assert "大礼堂" in article.text


def test_fetch_article_rejects_anti_bot_page():
    with pytest.raises(ArticleFetchError) as exc:
        fetch_article(
            "https://mp.weixin.qq.com/s/abc",
            transport=mock_transport(ANTI_BOT_HTML),
        )
    assert "验证" in str(exc.value)


def test_fetch_article_rejects_non_wechat_url():
    with pytest.raises(ArticleFetchError):
        fetch_article("https://example.com/a")


def test_extract_article_activity_fields():
    article = Article(
        title="新生舞会",
        text=(
            "发布时间：2026-11-24 18:00\n"
            "活动时间：11月27日（周五）19:00-21:00\n"
            "活动地点：大礼堂\n"
            "报名截止：11月25日 24:00\n"
            "主办单位：计算机系学生会"
        ),
        url="https://mp.weixin.qq.com/s/abc",
    )
    parsed = extract_article_activity(article, BASE)
    assert parsed is not None
    assert parsed.title == "新生舞会"
    assert parsed.start_at == datetime(2026, 11, 27, 19, 0, tzinfo=TZ)
    assert parsed.end_at == datetime(2026, 11, 27, 21, 0, tzinfo=TZ)
    assert parsed.location == "大礼堂"
    assert parsed.deadline_at == datetime(2026, 11, 25, 23, 59, tzinfo=TZ)
    assert parsed.organizer == "计算机系学生会"
    assert not parsed.unresolved_time


def test_publish_date_is_not_used_as_activity_date():
    article = Article(
        title="社团招新",
        text=(
            "发布时间：2026-11-24 18:00\n"
            "活动时间：12月1日 14:00\n"
            "活动地点：紫操"
        ),
        url="https://mp.weixin.qq.com/s/abc",
    )
    parsed = extract_article_activity(article, BASE)
    assert parsed is not None
    assert parsed.start_at == datetime(2026, 12, 1, 14, 0, tzinfo=TZ)
    assert parsed.start_at.date() != datetime(2026, 11, 24).date()


def test_missing_time_still_creates_incomplete_activity():
    article = Article(
        title="有个讲座",
        text="这是一篇没有明确时间的活动介绍。",
        url="https://mp.weixin.qq.com/s/abc",
    )
    parsed = extract_article_activity(article, BASE)
    assert parsed is not None
    assert parsed.start_at is None
    assert parsed.unresolved_time


def test_extract_wechat_url():
    text = "看看这个 https://mp.weixin.qq.com/s/abc123，周五晚7点"
    assert extract_wechat_url(text) == "https://mp.weixin.qq.com/s/abc123"
    assert extract_wechat_url("没有链接") is None
