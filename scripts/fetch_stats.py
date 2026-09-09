#!/usr/bin/env python3
"""
办公工具雷达 · 每日数据采集
读取 data/tools.json 的仓库清单 → 调 GitHub API → 更新 data/stats.json
  - star 数 / forks / 最近推送 / license / 最新 release
  - 维护 90 天 star 历史快照,计算日增 delta_1d 与 7 日增 delta_7d
用法:
  python3 scripts/fetch_stats.py             # 全量(本地无 token 时注意 60 次/小时限流)
  python3 scripts/fetch_stats.py --limit 5   # 只取前 5 个仓库(干跑/测试)
环境变量 GITHUB_TOKEN / GH_TOKEN 可选(Actions 里由 secrets.GITHUB_TOKEN 注入)
仅用标准库,Python 3.9+ 可跑。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_PATH = os.path.join(BASE, "data", "tools.json")
STATS_PATH = os.path.join(BASE, "data", "stats.json")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
API = "https://api.github.com"
HIST_DAYS = 90
HISTORY_KEEP = 120  # 多留一点,防止时区差误删


def api(path):
    """GET 一个 GitHub API 路径,带限流退避。返回 (data|None, status)。"""
    req = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "office-tool-radar",
            **({"Authorization": "Bearer " + TOKEN} if TOKEN else {}),
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r), r.status
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, 404
            if e.code in (403, 429) and attempt < 2:  # 二级限流:退避重试
                time.sleep(15 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(5)
                continue
            raise
    return None, None


def stars_days_ago(history, days):
    """取 days 天前(含)最近一次快照的 star 数;没有足够早的快照则返回 None。"""
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    older = [h for h in history if h["d"] <= cutoff]
    return older[-1]["s"] if older else None


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    tools_doc = json.load(open(TOOLS_PATH, encoding="utf-8"))
    repos = [t["repo"] for t in tools_doc["tools"]]
    if limit:
        repos = repos[:limit]

    old = {}
    if os.path.exists(STATS_PATH):
        try:
            old = json.load(open(STATS_PATH, encoding="utf-8")).get("tools", {})
        except (json.JSONDecodeError, OSError):
            pass

    today = datetime.now(timezone.utc).date().isoformat()
    out = {}
    print(f"开始采集 {len(repos)} 个仓库(token={'有' if TOKEN else '无,匿名限流 60 次/小时'})")
    for i, slug in enumerate(repos, 1):
        prev = old.get(slug, {})
        repo, code = api("/repos/" + slug)
        if code == 404:
            out[slug] = {**prev, "missing": True}
            print(f"[{i}/{len(repos)}] ⚠ {slug} 404,标记失联")
            continue
        if repo is None:
            out[slug] = prev  # 本次拉取失败,保留旧数据
            print(f"[{i}/{len(repos)}] × {slug} 拉取失败,保留旧数据")
            continue

        rel, _ = api("/repos/%s/releases/latest" % slug)

        # 历史快照:去掉今天的旧记录再追加,保持升序,截到保留窗口
        history = [h for h in prev.get("history", []) if h["d"] != today]
        history.append({"d": today, "s": repo["stargazers_count"]})
        history.sort(key=lambda h: h["d"])
        history = history[-HISTORY_KEEP:]

        stars = repo["stargazers_count"]
        base_1d = stars_days_ago(history, 1)
        base_7d = stars_days_ago(history, 7)
        out[slug] = {
            "stars": stars,
            "forks": repo.get("forks_count"),
            "pushed_at": repo.get("pushed_at"),
            "archived": repo.get("archived", False),
            "license": (repo.get("license") or {}).get("spdx_id"),
            "release_tag": (rel or {}).get("tag_name"),
            "release_date": (rel or {}).get("published_at"),
            "release_url": (rel or {}).get("html_url"),
            "delta_1d": stars - base_1d if base_1d is not None else None,
            "delta_7d": stars - base_7d if base_7d is not None else None,
            "missing": False,
            "history": history,
        }
        print(
            f"[{i}/{len(repos)}] ✓ {slug} ⭐{stars}"
            f"(日{out[slug]['delta_1d'] if out[slug]['delta_1d'] is not None else '?'}"
            f"/周{out[slug]['delta_7d'] if out[slug]['delta_7d'] is not None else '?'})"
        )
        time.sleep(0.2)  # 对 API 温柔一点

    # --limit 干跑时,未拉取的仓库沿用旧数据,保证 stats.json 完整
    for slug, v in old.items():
        if slug not in out:
            out[slug] = v

    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "tools": out,
    }
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"完成,写入 {STATS_PATH}(共 {len(out)} 个仓库)")


if __name__ == "__main__":
    main()
