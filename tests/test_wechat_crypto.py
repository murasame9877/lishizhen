import hashlib

from lxml import etree

from app.wechat.crypto import (
    build_text_reply,
    cdata_escape,
    check_signature,
    parse_message,
)


def test_check_signature():
    token, timestamp, nonce = "abc", "1700000000", "xyz"
    expected = hashlib.sha1(
        "".join(sorted([token, timestamp, nonce])).encode("utf-8")
    ).hexdigest()
    assert check_signature(token, timestamp, nonce, expected)
    assert not check_signature(token, timestamp, nonce, "bad")


def test_check_signature_rejects_missing_values():
    assert not check_signature("", "1", "2", "3")


def test_parse_text_message():
    xml = """<xml>
      <ToUserName><![CDATA[gh_account]]></ToUserName>
      <FromUserName><![CDATA[oUser123]]></FromUserName>
      <CreateTime>1700000000</CreateTime>
      <MsgType><![CDATA[text]]></MsgType>
      <Content><![CDATA[周五晚7点 大礼堂 新生舞会]]></Content>
      <MsgId>1234567890</MsgId>
    </xml>"""
    msg = parse_message(xml)
    assert msg["MsgType"] == "text"
    assert msg["FromUserName"] == "oUser123"
    assert msg["Content"] == "周五晚7点 大礼堂 新生舞会"
    assert msg["MsgId"] == "1234567890"


def test_build_text_reply_roundtrip_and_cdata_escape():
    content = "包含 ]]> 的内容"
    xml = build_text_reply(
        to_user="oUser123",
        from_user="gh_account",
        content=content,
        create_time=1700000000,
    )
    assert "<CreateTime>1700000000</CreateTime>" in xml
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.findtext("Content") == content
    assert root.findtext("ToUserName") == "oUser123"
    assert root.findtext("FromUserName") == "gh_account"


def test_cdata_escape_only_touches_terminator():
    assert cdata_escape("a]]>b") == "a]]]]><![CDATA[>b"
