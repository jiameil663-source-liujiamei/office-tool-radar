#!/usr/bin/env python3
"""
办公工具雷达 · AI 提效实战(飞书文档)
工作日每天(北京时间)针对一个工具生成一篇深度文章:
  工具简介 → 适用场景 → 安装指南 → 操作指南(功能模块+步骤) → 进阶技巧 → 常见问题 → 总结
  附:本周热门 TOP5(带每个工具的一句话功能摘要)
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
    info = {}
    for t in tools:
        info[t["repo"]] = t
    entries = []
    for repo, s in stats.items():
        if s.get("missing"):
            continue
        entries.append({
            "repo": repo,
            "name": info.get(repo, {}).get("name", repo.split("/")[-1]),
            "desc": info.get(repo, {}).get("desc", ""),
            "stars": s.get("stars") or 0, "d7": s.get("delta_7d"),
            "tag": s.get("release_tag"),
        })
    return entries


def hot_lines(entries, top_n=5):
    """TOP5:名字 + 数据 + 一句话功能摘要(不只是数字)"""
    with_d7 = [e for e in entries if e["d7"]]
    if len(with_d7) >= 5:
        rows = sorted(with_d7, key=lambda e: e["d7"], reverse=True)[:top_n]
        title = "附:本周热门 TOP5(近 7 天 star 增量)"
        lines = ["%d. %s ↑%+d —— %s" % (i, e["name"], e["d7"], e["desc"]) for i, e in enumerate(rows, 1)]
    else:
        rows = sorted(entries, key=lambda e: e["stars"], reverse=True)[:top_n]
        title = "附:Star 总榜 TOP5(趋势累积中)"
        lines = ["%d. %s ⭐%s —— %s" % (i, e["name"], format(e["stars"], ","), e["desc"]) for i, e in enumerate(rows, 1)]
    return title, lines


def compose(repo_override=None):
    entries = gather()
    arts = jload("data/articles.json")["features"]
    now = datetime.now(CST)
    today = now.date()
    if repo_override:  # 点单模式:指定工具,不看日期
        feat = next((a for a in arts if a["repo"] == repo_override), None)
        if feat is None:
            print("内容库中没有 %s 的文章" % repo_override)
            return False
    else:
        if today.weekday() >= 5:
            return None  # 周末
        days = (today - EPOCH).days
        feat = arts[days % len(arts)]

    # 从实时数据里找该工具的指标
    me = next((e for e in entries if e["repo"] == feat["repo"]), None)
    meta = "%s" % feat["positioning"]
    if me:
        meta += " · ⭐%s · 最新版 %s" % (format(me["stars"], ","), me.get("tag") or "—")
    repo_url = "https://github.com/" + feat["repo"]

    sec = [
        ("h1", "AI 提效实战 · %d月%d日(%s)" % (today.month, today.day, WEEKDAY_CN[today.weekday()])),
        ("h2", feat["headline"]),
        ("text", meta),
        ("h3", "一、工具简介"),
        ("text", feat["intro"]),
        ("textb", "项目地址:" + repo_url),
        ("h3", "二、适用场景"),
        ("bullets", feat["scenarios"]),
    ]

    # 安装指南(分平台)
    sec.append(("h3", "三、安装指南"))
    for plat, steps in feat["install"].items():
        sec.append(("textb", plat))
        sec.append(("bullets", steps))

    # 操作指南(功能模块)
    sec.append(("h3", "四、操作指南"))
    for mod in feat["guide"]:
        sec.append(("textb", mod["title"]))
        sec.append(("bullets", ["%d. %s" % (i, s) for i, s in enumerate(mod["steps"], 1)]))

    sec += [
        ("h3", "五、进阶技巧"),
        ("bullets", feat["tips"]),
        ("h3", "六、常见问题"),
    ]
    for f in feat["faq"]:
        sec.append(("textb", "Q:" + f["q"]))
        sec.append(("text", "A:" + f["a"]))
    sec += [
        ("h3", "七、总结"),
        ("text", feat["summary"]),
    ]

    hot_title, lines = hot_lines(entries)
    sec += [
        ("h2", hot_title),
        ("bullets", lines),
        ("h2", "关于本栏目"),
        ("text", "本文由办公工具雷达自动组稿,数据来自 GitHub 每日采集。发布前请审阅,"
                 "建议补充你自己的使用案例与截图,会更落地。工具雷达:%s" % SITE),
    ]
    return {"title": "AI 提效实战 · %d月%d日 | %s" % (today.month, today.day, feat["repo"].split("/")[-1]), "sections": sec}


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


def runs(text, bold=False):
    style = {"bold": True} if bold else {}
    return [{"text_run": {"content": text, "text_element_style": style}}]


def to_blocks(sections):
    blocks = []
    for kind, content in sections:
        if kind == "bullets":
            for line in content:
                blocks.append({"block_type": 12, "bullet": {"elements": runs(line)}})
        elif kind == "h1":
            blocks.append({"block_type": 3, "heading1": {"elements": runs(content)}})
        elif kind == "h2":
            blocks.append({"block_type": 4, "heading2": {"elements": runs(content)}})
        elif kind == "h3":
            blocks.append({"block_type": 5, "heading3": {"elements": runs(content)}})
        elif kind == "textb":
            blocks.append({"block_type": 2, "text": {"elements": runs(content, bold=True)}})
        else:
            blocks.append({"block_type": 2, "text": {"elements": runs(content)}})
    return blocks


def create_doc(article, app_id, app_secret):
    token = tenant_token(app_id, app_secret)
    r = api("POST", "/docx/v1/documents", {"title": article["title"]}, token)
    if r.get("code") != 0:
        print("建文档失败:", r.get("code"), r.get("msg"))
        return None
    doc_id = r["data"]["document"]["document_id"]
    print("文档已创建:", doc_id)

    blocks = to_blocks(article["sections"])
    for i in range(0, len(blocks), 40):
        chunk = blocks[i:i + 40]
        r = api("POST", "/docx/v1/documents/%s/blocks/%s/children" % (doc_id, doc_id),
                {"children": chunk, "index": -1}, token)
        if r.get("code") != 0:
            print("写入失败(批次 %d):" % (i // 40), r.get("code"), r.get("msg"))
            return doc_id
    print("正文写入完成(%d 块)" % len(blocks))

    api("POST", "/drive/v1/permissions/%s/members?type=docx&need_notification=true" % doc_id,
        {"member_type": "openid", "member_id": YAYI_OPEN_ID, "perm": "full_access"}, token)
    tr = api("POST",
        "/drive/v1/permissions/%s/members/transfer_owner?type=docx&need_notification=true&remove_old_owner=false" % doc_id,
        {"member_type": "openid", "member_id": YAYI_OPEN_ID}, token)
    print("转让所有权:", tr.get("code"), tr.get("msg"))
    return doc_id


def send_link_card(doc_id, app_id, app_secret):
    token = tenant_token(app_id, app_secret)
    url = "https://bytedance.feishu.cn/docx/" + doc_id
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": "📝 今天的工具实战文章写好了"}, "template": "turquoise"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
                "content": "单工具深度文章 + 操作指南已生成,文档已转让给你。\n审阅 → 补充你自己的案例/截图 → 分享"}},
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
    args = sys.argv[1:]
    dry = "--dry" in args
    repo = args[args.index("--repo") + 1] if "--repo" in args else None
    article = compose(repo)
    if article is False:
        sys.exit(1)  # 点单的工具不在内容库
    if article is None:
        print("今天是周末,跳过")
        return
    if dry:
        for kind, content in article["sections"]:
            mark = {"h1": "# ", "h2": "## ", "h3": "### ", "textb": "****"}.get(kind, "")
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
    doc_id = create_doc(article, app_id, app_secret)
    if not doc_id:
        sys.exit(1)
    if not send_link_card(doc_id, app_id, app_secret):
        sys.exit(1)
    print("完成:", "https://bytedance.feishu.cn/docx/" + doc_id)


if __name__ == "__main__":
    main()
