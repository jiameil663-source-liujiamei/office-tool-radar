#!/usr/bin/env python3
"""
办公工具雷达 · AI 提效日报(飞书文档)
工作日每天(北京时间)自动组稿一篇可分享的提效日报:
  周一~周四:主打工具深度(内容库轮换)+ 本周热门 + 新版本 + 提效技巧
  周五:一周盘点(热门增量 TOP10 + 本周新版本汇总 + 技巧)
流程:组稿 → 群小汇创建飞书文档 → 授权并转让给芽衣 → 私聊发文档链接
周末自动跳过(exit 0,不影响采集与卡片日报)。
用法:python3 scripts/feishu_article.py [--dry]   # --dry 只打印文稿不建文档
环境变量:FEISHU_APP_ID + FEISHU_APP_SECRET(群小汇)+ FEISHU_OPEN_ID(芽衣)
仅标准库,Python 3.9+。
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPEN_API = "https://open.feishu.cn/open-apis"
SITE = "https://jiameil663-source-liujiamei.github.io/office-tool-radar/"
YAYI_OPEN_ID = os.environ.get("FEISHU_OPEN_ID") or "ou_da427f81e981135cf0a18d8f894d8017"
CST = timezone(timedelta(hours=8))
EPOCH = date(2026, 9, 10)  # 轮换起点(第一个工作日)
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def jload(p):
    return json.load(open(os.path.join(BASE, p), encoding="utf-8"))


# ── 组稿 ────────────────────────────────────────────
def gather():
    stats = jload("data/stats.json").get("tools", {})
    tools = jload("data/tools.json")["tools"]
    name_by_repo = {t["repo"]: t["name"] for t in tools}
    plat_by_repo = {t["repo"]: " / ".join(t["platforms"]) for t in tools}
    entries = []
    for repo, s in stats.items():
        if s.get("missing"):
            continue
        entries.append({"repo": repo, "name": name_by_repo.get(repo, repo.split("/")[-1]),
                        "stars": s.get("stars") or 0, "d7": s.get("delta_7d"),
                        "d1": s.get("delta_1d"), "tag": s.get("release_tag"),
                        "rel_ts": s.get("release_date")})
    return entries, name_by_repo, plat_by_repo


def hot_block(entries, top_n=5, weekly=False):
    """热门段:有周增量用增量榜,否则 star 总榜。返回 (标题, 行列表)"""
    with_d7 = [e for e in entries if e["d7"]]
    if len(with_d7) >= 5:
        rows = sorted(with_d7, key=lambda e: e["d7"], reverse=True)[:top_n]
        title = "本周热门 TOP%d(近 7 天 star 增量)" % top_n if weekly else "🔥 本周热门 TOP5"
        return title, ["%d. %s　↑%+d" % (i, e["name"], e["d7"]) for i, e in enumerate(rows, 1)]
    rows = sorted(entries, key=lambda e: e["stars"], reverse=True)[:top_n]
    return "🔥 Star 总榜 TOP%d(趋势累积中)" % top_n, \
           ["%d. %s　⭐%s" % (i, e["name"], format(e["stars"], ",")) for i, e in enumerate(rows, 1)]


def releases_block(entries, days=1):
    """近 N 天(UTC)发布的版本"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    rels = [e for e in entries if e["rel_ts"] and e["rel_ts"][:10] >= cutoff]
    lines = ["%s 发布 %s" % (e["name"], e["tag"]) for e in rels[:12]]
    return lines or (["今日无新版本发布"] if days == 1 else ["本周无新版本发布"])


def compose():
    entries, name_by_repo, plat_by_repo = gather()
    arts = jload("data/articles.json")["features"]
    tips = jload("data/tips.json")["tips"]
    now = datetime.now(CST)
    today = now.date()
    wd = today.weekday()
    if wd >= 5:
        return None  # 周末
    days = (today - EPOCH).days
    tip = tips[(days + 7) % len(tips)]
    head = "AI 提效日报 · %d月%d日(%s)" % (today.month, today.day, WEEKDAY_CN[wd])

    if wd == 4:  # 周五:一周盘点
        hot_title, hot_lines = hot_block(entries, top_n=10)
        sec = [
            ("h1", head + " | 一周盘点"),
            ("text", "办公工具雷达本周数据回顾,内容自动组稿,分享前可增删。"),
            ("h2", "📈 " + hot_title),
            ("bullets", hot_lines),
            ("h2", "🏷 本周新版本汇总"),
            ("bullets", releases_block(entries, days=7)),
            ("h2", "💡 今日提效技巧:" + tip["title"]),
            ("text", tip["body"]),
        ]
    else:  # 周一~周四:主打工具
        feat = arts[days % len(arts)]
        s = {"stars": 0, "tag": "", "d7": None}
        for e in entries:
            if e["repo"] == feat["repo"]:
                s = e
                break
        meta = "%s · ⭐%s · 最新版 %s · 平台:%s" % (
            feat["positioning"], format(s["stars"], ","), s.get("tag") or "—",
            plat_by_repo.get(feat["repo"], "—"))
        hot_title, hot_lines = hot_block(entries)
        sec = [
            ("h1", head),
            ("h2", "🎯 今日主打:" + feat["headline"]),
            ("text", meta),
            ("h3", "为什么值得装"),
            ("bullets", feat["why"]),
            ("h3", "三步上手"),
            ("bullets", ["第 %d 步:%s" % (i, st) for i, st in enumerate(feat["steps"], 1)]),
            ("h3", "进阶玩法"),
            ("bullets", feat["advanced"]),
            ("h3", "适合谁"),
            ("text", feat["fit"]),
            ("h2", hot_title),
            ("bullets", hot_lines),
            ("h2", "🏷 今日新版本"),
            ("bullets", releases_block(entries, days=1)),
            ("h2", "💡 今日提效技巧:" + tip["title"]),
            ("text", tip["body"]),
        ]
    sec += [
        ("h2", "关于本栏目"),
        ("text", "本文由办公工具雷达自动组稿:数据来自 GitHub 每日采集,主打内容来自栏目内容库。"
                 "发布前请审阅调整,加上你自己的案例更好。工具雷达:%s" % SITE),
    ]
    return {"title": head, "sections": sec}


# ── 飞书文档(群小汇)──────────────────────────────
def tenant_token(app_id, app_secret):
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(OPEN_API + "/auth/v3/tenant_access_token/internal",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["tenant_access_token"]


def api(method, path, payload, token, params=""):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(OPEN_API + path + params, data=data,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json; charset=utf-8"},
        method=method)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def runs(text, bold=False, url=None):
    style = {}
    if bold:
        style["bold"] = True
    if url:
        style["link"] = {"url": url}
    return [{"text_run": {"content": text, "text_element_style": style}}]


def to_blocks(sections):
    blocks, kind_map = [], {"h1": 3, "h2": 4, "h3": 5, "text": 2, "bullet": 12}
    for kind, content in sections:
        if kind == "bullets":
            for line in content:
                blocks.append({"block_type": 12, "bullet": {"elements": runs(line)}})
        elif kind in ("h1", "h2", "h3"):
            key = {"h1": "heading1", "h2": "heading2", "h3": "heading3"}[kind]
            blocks.append({"block_type": kind_map[kind], key: {"elements": runs(content)}})
        else:
            blocks.append({"block_type": 2, "text": {"elements": runs(content)}})
    return blocks


def create_doc(article, app_id, app_secret):
    token = tenant_token(app_id, app_secret)
    r = api("POST", "/docx/v1/documents", {"title": article["title"]}, token)
    if r.get("code") != 0:
        print("建文档失败:", r.get("code"), r.get("msg"))
        return None, None
    doc_id = r["data"]["document"]["document_id"]
    print("文档已创建:", doc_id)

    blocks = to_blocks(article["sections"])
    for i in range(0, len(blocks), 40):  # 分批,每批 ≤40
        chunk = blocks[i:i + 40]
        r = api("POST", "/docx/v1/documents/%s/blocks/%s/children" % (doc_id, doc_id),
                {"children": chunk, "index": -1}, token)
        if r.get("code") != 0:
            print("写入失败(批次 %d):" % (i // 40), r.get("code"), r.get("msg"))
            return None, token
    print("正文写入完成(%d 块)" % len(blocks))

    # 授权芽衣完全访问 + 转让所有权
    api("POST", "/drive/v1/permissions/%s/members?type=docx&need_notification=true" % doc_id,
        {"member_type": "openid", "member_id": YAYI_OPEN_ID, "perm": "full_access"}, token)
    tr = api("POST",
        "/drive/v1/permissions/%s/members/transfer_owner?type=docx&need_notification=true&remove_old_owner=false" % doc_id,
        {"member_type": "openid", "member_id": YAYI_OPEN_ID}, token)
    print("转让所有权:", tr.get("code"), tr.get("msg"))
    return doc_id, token


def send_link_card(doc_id, app_id, app_secret):
    token = tenant_token(app_id, app_secret)
    url = "https://bytedance.feishu.cn/docx/" + doc_id
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": "📝 今天的提效日报写好了"}, "template": "turquoise"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
                "content": "已在飞书创建今日文档并转让给你,审阅后即可分享。\n打开 → 略作增删(建议加一条你自己的案例)→ 分享到群"}},
            {"tag": "action", "actions": [
                {"tag": "button", "type": "primary", "text": {"tag": "plain_text", "content": "打开文档"}, "url": url},
                {"tag": "button", "text": {"tag": "plain_text", "content": "工具雷达"}, "url": SITE},
            ]},
        ],
    }
    msg = {"receive_id": YAYI_OPEN_ID, "msg_type": "interactive", "content": json.dumps(card)}
    r = api("POST", "/im/v1/messages?receive_id_type=open_id", msg, token)
    print("文档链接卡片: code =", r.get("code"), "|", r.get("msg"))
    return r.get("code") == 0


def main():
    article = compose()
    if article is None:
        print("今天是周末,跳过日报文档")
        return
    if "--dry" in sys.argv:
        for kind, content in article["sections"]:
            mark = {"h1": "# ", "h2": "## ", "h3": "### "}.get(kind, "")
            if isinstance(content, list):
                print("\n".join("- " + c for c in content))
            else:
                print(mark + content)
        return
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not (app_id and app_secret):
        print("未设置 FEISHU_APP_ID/SECRET,跳过文档生成")
        return
    doc_id, _ = create_doc(article, app_id, app_secret)
    if not doc_id:
        sys.exit(1)
    if not send_link_card(doc_id, app_id, app_secret):
        sys.exit(1)
    print("完成:", "https://bytedance.feishu.cn/docx/" + doc_id)


if __name__ == "__main__":
    main()
