# 📡 办公工具雷达

> 全员可用的开源效率神器导航站 —— 剪贴板、截图录屏、文件传输、文档知识库、本地 AI……
> 拒绝订阅制付费,精选免费开源的办公实用工具。

**网址:** `https://<用户名>.github.io/office-tool-radar/`

## 这个站解决什么问题

找到像 [vorssaint-utils](https://github.com/vorssaint/vorssaint-utils) 这样"一个顶一打付费 App"的开源工具并不难,
难的是:**知道它存在**、**确认它还活着**。本站:

- 人工精选 65+ 个办公场景的开源工具,按 12 个分类整理,标注平台与一句话痛点
- **每天 09:30 自动采集**每个工具的 GitHub star 数、最新版本、最近更新时间
- 计算 star 日增 / 周增,生成"本周热门 TOP5",一眼看出哪些工具正在爆发
- 工具停更或仓库失联会在卡片上标记,不用担心推荐给同事一个弃坑项目

## 目录结构

```
├── index.html              # 页面(单文件,无构建,纯 vanilla JS)
├── data/
│   ├── tools.json          # 选品清单(人工维护:分类/描述/平台/标签/安装命令)
│   └── stats.json          # 每日数据(机器人自动生成,请勿手改)
├── scripts/fetch_stats.py  # 采集脚本(本地可干跑:--limit 5)
└── .github/workflows/update.yml  # 每日定时任务
```

## 如何推荐新工具

提一个 [Issue](../../issues/new?template=tool-recommend.md),写清楚:
工具仓库地址、解决什么办公痛点、支持平台。审核标准:

1. 开源(或官方免费且无功能限制)
2. 面向办公场景有明确痛点,不是纯开发玩具
3. 活跃维护(近 6 个月有提交),star 趋势健康
4. 不收录需要付费解锁核心功能的产品

## 如何维护选品

编辑 `data/tools.json` 增删工具(字段说明见文件内示例),push 到 main 后
Actions 会自动重新采集数据并部署,无需任何手动操作。

## 本地开发

```bash
python3 -m http.server 8931          # 打开 http://localhost:8931
python3 scripts/fetch_stats.py --limit 3   # 干跑采集(本地无 token 注意限流)
```

## 数据说明

- star 数、版本、更新时间来自 GitHub 公开 API,每日 09:30(北京时间)采集一次,非实时
- 日增/周增基于本站自己的 90 天历史快照计算,**收录次日起**才有趋势数据
- 页面支持按分类/平台筛选、搜索、四种排序;`#cat=xxx&pf=xxx` 的链接可直接分享筛选后的视图
