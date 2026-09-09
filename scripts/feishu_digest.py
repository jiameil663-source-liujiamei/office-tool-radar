#!/usr/bin/env python3
"""
办公工具雷达 · 飞书日报
读取 data/tools.json + data/stats.json → 生成日报卡片 → 推送飞书
内容:本周热门 TOP5(趋势不足时降级为 star 总榜)/ 今日新版本 / 仓库失联警告

两种推送模式(按环境变量自动选择):
  A. 应用私聊(群小汇):FEISHU_APP_ID + FEISHU_APP_SECRET + FEISHU_OPEN_ID
  B. 群机器人 webhook:FEISHU_WEBHOOK(+ 可选 FEISHU_SECRET 签名)
都没设置则跳过(不影响采集)。

用法:python3 scripts/feishu_digest.py [--dry]   # --dry 只打印卡片不发送
仅标准库,Python 3.9+。
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://jiameil663-source-liujiamei.github.io/office-tool-radar/"
OPEN_API = "https://open.feishu.cn/open-apis"
CST = timezone(timedelta(hours=8))  # 北京时间


def load():
    tools = json.load(open(os.path.join(BASE, "data", "tools.json"), encoding="utf-8"))
    stats = json.load(open(os.path.join(BASE, "data", "stats.json"), encoding="utf-8"))
    name_by_repo = {t["repo"]: t["name"] for t in tools["tools"]}
    return stats, name_by_repo


def build_card():
    """构建飞书卡片 dict(header + elements,IM 与 webhook 通用)。"""
    stats, name_by_repo = load()
    now = datetime.now(CST)
    entries = []
    for repo, s in stats.get("tools", {}).items():
        if s.get("missing"):
            continue
        entries.append({
            "repo": repo,
            "name": name_by_repo.get(repo, repo.split("/")[-1]),
            "stars": s.get("stars") or 0,
            "d7": s.get("delta_7d"),
            "tag": s.get("release_tag"),
            "release_ts": s.get("release_date"),
        })

    # ── 热门 TOP5:优先周增量,趋势不足降级 star 总榜
    with_d7 = [e for e in entries if e["d7"]]
    if len(with_d7) >= 5:
        hot = sorted(with_d7, key=lambda e: e["d7"], reverse=True)[:5]
        hot_title = "🔥 本周热门 TOP5(近 7 天 star 增量)"
        hot_lines = [f"**{i}.** [{e['name']}](https://github.com/{e['repo']})　↑{e['d7']:+,}" for i, e in enumerate(hot, 1)]
    else:
        hot = sorted(entries, key=lambda e: e["stars"], reverse=True)[:5]
        hot_title = "🔥 Star 总榜 TOP5(趋势累积中,几天后切换为周增量榜)"
        hot_lines = [f"**{i}.** [{e['name']}](https://github.com/{e['repo']})　⭐{e['stars']:,}" for i, e in enumerate(hot, 1)]

    # ── 今日新版本(按 UTC 日期对齐采集时刻)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    releases = [e for e in entries if e["release_ts"] and e["release_ts"][:10] == today]
    rel_lines = [f"- **{e['name']}** 发布 `{e['tag']}`" for e in releases[:8]] or ["- 今日无新版本发布"]

    # ── 失联警告
    missing = [name_by_repo.get(r, r) for r, s in stats.get("tools", {}).items() if s.get("missing")]

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**{hot_title}**\n" + "\n".join(hot_lines)}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": "**🏷 今日新版本**\n" + "\n".join(rel_lines)}},
    ]
    if missing:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": "**⚠ 仓库失联**\n" + "\n".join("- " + m for m in missing)}})
    elements += [
        {"tag": "hr"},
        {"tag": "action", "actions": [{
            "tag": "button", "type": "primary",
            "text": {"tag": "plain_text", "content": "📡 打开工具雷达"},
            "url": SITE,
        }]},
        {"tag": "note", "elements": [{
            "tag": "plain_text",
            "content": f"共 {len(entries)} 个工具 · 数据更新于 {now.strftime('%m-%d %H:%M')} · 每天自动采集",
        }]},
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📡 办公工具雷达日报 · {now.strftime('%m月%d日')}"},
            "template": "blue",
        },
        "elements": elements,
    }


# ── 模式 A:应用私聊(群小汇)──────────────────────
def tenant_token(app_id, app_secret):
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        OPEN_API + "/auth/v3/tenant_access_token/internal",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["tenant_access_token"]


def send_via_app(card, app_id, app_secret, open_id):
    token = tenant_token(app_id, app_secret)
    msg = {"receive_id": open_id, "msg_type": "interactive", "content": json.dumps(card)}
    req = urllib.request.Request(
        OPEN_API + "/im/v1/messages?receive_id_type=open_id",
        data=json.dumps(msg).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json; charset=utf-8"},
        method="POST")
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        resp = json.loads(e.read() or b"{}")
    print("飞书(应用私聊)返回: code =", resp.get("code"), "|", resp.get("msg"))
    return resp.get("code") == 0


# ── 模式 B:群机器人 webhook ──────────────────────
def send_via_webhook(card, webhook, secret=None):
    payload = {"msg_type": "interactive", "card": card}
    if secret:
        ts = str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = base64.b64encode(
            hmac.new((ts + "\n" + secret).encode(), b"", hashlib.sha256).digest()).decode()
    req = urllib.request.Request(
        webhook, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        resp = json.loads(e.read() or b"{}")
    print("飞书(webhook)返回: code =", resp.get("code"), "|", resp.get("msg"))
    return resp.get("code") in (0, None)


def main():
    dry = "--dry" in sys.argv
    card = build_card()
    if dry:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    app_id = os.environ.get("FEISHU_APP_ID")
    if app_id and os.environ.get("FEISHU_APP_SECRET") and os.environ.get("FEISHU_OPEN_ID"):
        ok = send_via_app(card, app_id, os.environ["FEISHU_APP_SECRET"], os.environ["FEISHU_OPEN_ID"])
        sys.exit(0 if ok else 1)

    webhook = os.environ.get("FEISHU_WEBHOOK")
    if webhook:
        ok = send_via_webhook(card, webhook, os.environ.get("FEISHU_SECRET"))
        sys.exit(0 if ok else 1)

    print("未设置 FEISHU_APP_ID/FEISHU_WEBHOOK,跳过推送(不影响采集)")


if __name__ == "__main__":
    main()
