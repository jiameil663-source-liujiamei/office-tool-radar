#!/usr/bin/env python3
"""
办公工具雷达 · 飞书日报
读取 data/tools.json + data/stats.json → 生成日报卡片 → POST 到飞书群机器人 webhook
内容:本周热门 TOP5(趋势不足时降级为 star 总榜)/ 今日新版本 / 仓库失联警告
用法:python3 scripts/feishu_digest.py [--dry]   # --dry 只打印卡片不发送
环境变量:
  FEISHU_WEBHOOK  必填(群机器人 webhook 地址)
  FEISHU_SECRET   可选(机器人开了"签名校验"时填)
仅标准库,Python 3.9+。
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://jiameil663-source-liujiamei.github.io/office-tool-radar/"
CST = timezone(timedelta(hours=8))  # 北京时间


def load():
    tools = json.load(open(os.path.join(BASE, "data", "tools.json"), encoding="utf-8"))
    stats = json.load(open(os.path.join(BASE, "data", "stats.json"), encoding="utf-8"))
    name_by_repo = {t["repo"]: t["name"] for t in tools["tools"]}
    return tools, stats, name_by_repo


def build_digest():
    tools_doc, stats, name_by_repo = load()
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
            "d1": s.get("delta_1d"),
            "tag": s.get("release_tag"),
            "release_ts": s.get("release_date"),
        })

    # ── 热门 TOP5:优先周增量,趋势不足降级 star 总榜
    with_d7 = [e for e in entries if e["d7"]]
    if len(with_d7) >= 5:
        hot = sorted(with_d7, key=lambda e: e["d7"], reverse=True)[:5]
        hot_title = "本周热门 TOP5(近 7 天 star 增量)"
        hot_lines = [f"**{i}.** [{e['name']}](https://github.com/{e['repo']})　↑{e['d7']:+,}" for i, e in enumerate(hot, 1)]
    else:
        hot = sorted(entries, key=lambda e: e["stars"], reverse=True)[:5]
        hot_title = "Star 总榜 TOP5(趋势累积中,几天后切换为周增量榜)"
        hot_lines = [f"**{i}.** [{e['name']}](https://github.com/{e['repo']})　⭐{e['stars']:,}" for i, e in enumerate(hot, 1)]

    # ── 今日新版本(北京时间今天发布的)
    today = now.strftime("%Y-%m-%d")
    releases = [
        e for e in entries
        if e["release_ts"] and e["release_ts"][:10] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ]
    rel_lines = [f"- **{e['name']}** 发布 `{e['tag']}`" for e in releases[:8]] or ["- 今日无新版本发布"]

    # ── 失联警告
    missing = [name_by_repo.get(r, r) for r, s in stats.get("tools", {}).items() if s.get("missing")]

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 {hot_title}**\n" + "\n".join(hot_lines)}},
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
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📡 办公工具雷达日报 · {now.strftime('%m月%d日')}"},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def sign(payload, secret):
    """飞书自定义机器人签名校验:sign = base64(hmac_sha256(key=f'{ts}\n{secret}', msg=''))"""
    ts = str(int(time.time()))
    digest = hmac.new((ts + "\n" + secret).encode(), b"", hashlib.sha256).digest()
    payload["timestamp"] = ts
    payload["sign"] = base64.b64encode(digest).decode()
    return payload


def main():
    dry = "--dry" in sys.argv
    payload = build_digest()
    if dry:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    webhook = os.environ.get("FEISHU_WEBHOOK")
    if not webhook:
        print("未设置 FEISHU_WEBHOOK,跳过推送(不影响采集)")
        return
    if os.environ.get("FEISHU_SECRET"):
        payload = sign(payload, os.environ["FEISHU_SECRET"])
    req = urllib.request.Request(
        webhook, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.load(r)
    print("飞书返回:", resp)
    if resp.get("code") not in (0, None):
        sys.exit(1)


if __name__ == "__main__":
    main()
