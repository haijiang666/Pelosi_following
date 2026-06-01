# Pelosi Following — Stock & Options Trade Alpha Research

分析 **Nancy Pelosi**（含 Paul Pelosi 配偶披露）**House STOCK Act PTR** 股票/ETF 与期权交易：entry、exit、reveal lag、名义加权收益、**股票+期权统一 FIFO** 组合 PnL。

**数据来源**：[U.S. House Clerk Periodic Transaction Reports](https://disclosures-clerk.house.gov/)（STOCK Act，法定 45 天内披露）。

## 在线报告

| 版本 | 链接 |
|------|------|
| GitHub Pages | https://haijiang666.github.io/Pelosi_following/ |
| jsDelivr（单文件） | https://cdn.jsdelivr.net/gh/haijiang666/Pelosi_following@main/docs/index.html |

若 https://haijiang666.github.io/Pelosi_following/ 显示 404，说明尚未开启 Pages。任选其一：

1. **网页**：仓库 [Settings → Pages](https://github.com/haijiang666/Pelosi_following/settings/pages) → **Deploy from a branch** → `main` → **`/docs`** → Save  
2. **脚本**：`export GITHUB_TOKEN=ghp_xxx && bash scripts/enable_github_pages.sh`  
3. **Actions**：Settings → Pages → Source 选 **GitHub Actions**（推送后自动跑 `.github/workflows/deploy-pages.yml`）

等 1–3 分钟再刷新。

## 快速开始

```bash
cd Pelosi_following
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/run_pipeline.py      # 下载 PTR → 解析 → 收益 → 报告
python scripts/generate_report.py   # 仅重新生成 reports/FINAL_REPORT.md
```

## 发布到 GitHub

```bash
export GITHUB_TOKEN=ghp_xxxx   # https://github.com/settings/tokens (repo scope)
bash scripts/github_publish.sh
```

## 与 [Trump_following](https://github.com/haijiang666/Trump_following) 的差异

| | Trump_following | Pelosi_following |
|--|-----------------|------------------|
| 披露 | OGE Form 278-T | House PTR (STOCK Act) |
| 来源 | OGE / White House PDF | disclosures-clerk.house.gov |
| 期权 | — | `[OP]` call/put、行权；100 股/张 |
| 组合 FIFO | 仅股票 | 股票 + 期权/行权（按标的） |
| 分析窗口 | 2025 上任起 | 2023–2026（可配置） |

## 项目结构

```
Pelosi_following/
├── Pelosi_analysis_PLAN.md
├── config/settings.yaml
├── data/raw/disclosures/     # PTR PDF（git 忽略，pipeline 下载）
├── data/processed/           # trades.parquet, combined_timing, prices/
├── docs/index.html           # GitHub Pages 报告（内嵌图表）
├── scripts/
│   ├── run_pipeline.py
│   ├── generate_report.py
│   └── github_publish.sh
├── src/
│   ├── house_disclosures.py  # PTR 下载
│   ├── ptr_trades.py / ptr_options.py
│   ├── unified_portfolio.py  # 股票+期权统一 FIFO
│   └── trade_returns.py, combined_analysis.py, ...
└── reports/FINAL_REPORT.md
```

## Disclaimer

Research use only. Not investment advice.
