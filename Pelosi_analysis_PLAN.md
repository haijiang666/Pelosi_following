# Pelosi 股票交易分析计划

参照 `Trump_following` 架构，分析 **Nancy Pelosi / Paul Pelosi** 在 House **Periodic Transaction Report (PTR)** 中披露的股票/ETF 交易。

## 1. 研究问题

1. **Reveal lag**：交易发生日 → PTR 披露日 的中位滞后（STOCK Act 上限 45 天）。
2. **Pelosi timing**：以 **transaction date** 为 anchor 的名义加权 horizon 收益。
3. **Follow disclosure**：以 **PTR 签署/提交日** 为 anchor 的跟单收益。
4. **FIFO 持仓**：买→卖配对、未平仓 lot、组合 MTM 时间序列。
5. （可选）新闻/政策事件与交易窗口重叠。
6. **期权**（`[OP]`）：与股票相同 pipeline — 解析、双锚点 NW、FIFO、报告 §O1/O2（标的价 horizon）。

## 2. 数据

- **官方**：https://disclosures-clerk.house.gov/
  - 年度索引 XML：`/public_disc/financial-pdfs/{year}FD.xml`
  - PTR PDF：`/public_disc/ptr-pdfs/{year}/{DocID}.pdf`
- **FilingType `P`** = Periodic Transaction Report
- **Owner 字段**：`SP` = Spouse（Paul Pelosi）等
- **价格**：yfinance

## 3. Pipeline（与 Trump 项目对齐）

1. 下载 Pelosi PTR PDF
2. Cross-check manifest
3. 解析 ticker / action / amount bracket / dates
4. FIFO + 价格 + 双 anchor 收益
5. 图表 + FINAL_REPORT

## 4. 配置

`config/settings.yaml` → `house.analysis_start_date` / `analysis_end_date`

## 5. 限制

- PTR 金额为 **区间下限**（如 $1,000,001–$5,000,000），非精确成交价。
- 期权行权等复杂交易需读 Description 字段（如 AVGO call exercise）。
- 2023 年前 filing 需扩展 `index_years`。
