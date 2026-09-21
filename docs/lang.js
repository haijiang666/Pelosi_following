(function () {
  const DICT = {
    "Trump 股票/ETF 交易分析报告": "Trump stock/ETF trade analysis",
    "Pelosi 股票/ETF 交易分析报告": "Pelosi stock/ETF trade analysis",
    "Trump 交易分析报告 · 手机版": "Trump trade report · mobile",
    "Pelosi 交易分析报告 · 手机版": "Pelosi trade report · mobile",
    "报告目录": "Contents",
    "展开目录 ▾": "Contents ▾",
    "收起目录 ▴": "Hide contents ▴",
    "数据范围": "Data range",
    "Trump 当前净多头持仓（Top 10）": "Trump net long holdings (top 10)",
    "Pelosi 当前净多头持仓（Top 10）": "Pelosi net long holdings (top 10)",
    "Trump 组合持仓与 PnL 时间序列": "Trump portfolio and PnL over time",
    "Pelosi 组合持仓与 PnL 时间序列": "Pelosi portfolio and PnL over time",
    "已纳入文件（逐份统计）": "Included filings",
    "样本验证": "Sample checks",
    "Trump 本人发帖匹配": "Matches to Trump's own posts",
    "Trump 发帖 × 收益 / 行为规律": "Posts × returns / behavior",
    "是否存在「先买 → 发帖 → 卖」？": "Is there a buy → post → sell pattern?",
    "Top 交易×Trump 发帖（按交易名义金额排序）": "Top trades × Trump posts (by notional)",
    "Top3 匹配 ticker 时间线（买 → 发帖 → 卖 / 仍持有）": "Top 3 ticker timelines (buy → post → sell / still held)",
    "Trump 发帖匹配的 Top Ticker（按 Trump 名义金额排序）": "Top tickers matched to posts (by Trump notional)",
    "「买→发帖→卖」样例（ticker 必须在帖中出现）": "Buy → post → sell examples (ticker must appear in the post)",
    "持仓时间（FIFO 买→卖配对）": "Holding period (FIFO buy → sell)",
    "Top tickers（按 Trump 名义金额）": "Top tickers (by Trump notional)",
    "Top tickers（按 Pelosi 名义金额）": "Top tickers (by Pelosi notional)",
    "1. Trump 自身交易 timing（锚点 = 交易发生日）": "1. Trump's own timing (anchor = trade date)",
    "1. Pelosi 自身交易 timing（锚点 = 交易发生日）": "1. Pelosi's own timing (anchor = trade date)",
    "1a. 合计（买 + 卖）": "1a. Combined (buys + sells)",
    "1a. 合计（买 + 卖，卖按 sign=−1）": "1a. Combined (sells use sign=−1)",
    "1b. Trump 买（仅 purchase）": "1b. Trump buys (purchases only)",
    "1b. 买入（purchase）": "1b. Buys (purchases)",
    "1c. Trump 卖（仅 sale，按做空计 sign=−1）": "1c. Trump sells (short, sign=−1)",
    "1c. 卖出（sale，sign=−1 跟单口径）": "1c. Sells (sign=−1, follow-trade convention)",
    "1d. 已实现收益（FIFO entry → exit）": "1d. Realized PnL (FIFO entry → exit)",
    "2. Follow Trump（锚点 = OGE 披露日）": "2. Follow Trump (anchor = OGE disclosure date)",
    "2. Follow Pelosi（锚点 = PTR 披露日）": "2. Follow Pelosi (anchor = PTR disclosure date)",
    "2a. 合计（买 + 卖）": "2a. Combined (buys + sells)",
    "2b. Follow 买（仅 purchase，做多）": "2b. Follow buys (long)",
    "2b. Follow 买（purchase）": "2b. Follow buys",
    "2c. Follow 卖（仅 sale，做空）": "2c. Follow sells (short)",
    "2c. Follow 卖（sale，sign=−1）": "2c. Follow sells (sign=−1)",
    "股票 Top Tickers（trump_timing 名义合计）": "Top tickers (trump_timing notional)",
    "股票 Top Tickers（pelosi_timing 名义合计）": "Top tickers (pelosi_timing notional)",
    "说明": "Notes",
    "名义与口径（读表前必读）": "Notional and definitions (read first)",
    "股票 + 期权合并 PnL（期权按 100 股/张）": "Stock + options PnL (options = 100 shares/contract)",
    "合并 timing（锚点 = 交易发生日）": "Combined timing (anchor = trade date)",
    "期权交易分析（House PTR [OP]）": "Options analysis (House PTR [OP])",
    "O1. 期权 timing（锚点 = 交易发生日，标的价）": "O1. Options timing (anchor = trade date, underlying price)",
    "O2. Follow 披露日（标的价）": "O2. Follow from disclosure date (underlying price)",
    "期权合约明细（解析样本）": "Option contract details (parsed sample)",
    "与股票组合的关系": "Relation to the stock portfolio",
    "窗口(交易日)": "Window (trading days)",
    "笔数": "Trades",
    "总名义($)": "Total notional ($)",
    "总PnL($)": "Total PnL ($)",
    "总 PnL($)": "Total PnL ($)",
    "名义加权收益率": "Notional-weighted return",
    "已实现（买→卖）": "Realized (buy → sell)",
    "未平仓（MTM）": "Open (mark to market)",
    "胜率": "Win rate",
    "交易日": "Trade date",
    "披露日": "Disclosure date",
    "方向": "Side",
    "动作": "Action",
    "买": "Buy",
    "卖": "Sell",
    "类型": "Type",
    "状态": "Status",
    "持有天": "Days held",
    "持仓d": "Days held",
    "中位持仓(天)": "Median hold (days)",
    "名义($)": "Notional ($)",
    "股票名义($)": "Stock notional ($)",
    "已实现收益": "Realized PnL",
    "已实现 PnL": "Realized PnL",
    "配对/笔数": "Matched / trades",
    "股票/ETF笔数": "Stock/ETF trades",
    "解析笔数": "Parsed trades",
    "页数": "Pages",
    "内容": "Contents",
    "平台": "Platform",
    "帖文": "Post",
    "日期": "Date",
    "发帖日": "Post date",
    "匹配": "Match",
    "样例": "Example",
    "买/卖链接": "Buy/sell link",
    "最早买入": "First buy",
    "最近买入": "Latest buy",
    "未平笔数": "Open lots",
    "独立事件": "Distinct events",
    "交易笔数": "Trade count",
    "净名义($)": "Net notional ($)",
    "全文件名义($)": "Filing notional ($)",
    "名义下限合计": "Sum of notional floors",
    "占总额比例": "Share of total",
    "Δ天": "Δ days",
    "发帖-买(d)": "Post − buy (d)",
    "NW 收益率": "NW return",
    "生成时间: 2026-06-02 22:31 · OGE Form 278-T · 第二任期上任以来": "Generated 2026-06-02 22:31 · OGE Form 278-T · since the second term began",
    "生成时间: 2026-06-02 23:38 · House STOCK Act PTR · 2023-03-09 起": "Generated 2026-06-02 23:38 · House STOCK Act PTR · from 2023-03-09",
    "分析区间": "Period",
    "278-T 文件数": "278-T filings",
    "House PTR 文件数": "House PTR filings",
    ": 6 份（有效 5）": ": 6 filings (5 usable)",
    ": 15 份（有效 15）": ": 15 filings (15 usable)",
    "股票/ETF 可交易笔数": "Tradable stock/ETF trades",
    "只 ticker）": "tickers)",
    "求和）": "sum of floors)",
    "求和，仅有金额行）": "sum of floors, rows with amounts only)",
    "全部解析行": "All parsed rows",
    "（含债券等；全文件名义合计约": "(including bonds; filing notional about",
    "表格解析率": "Table parse rate",
    "天": "days",
    "笔": "trades",
    "条": "items",
    "仍持有": "still held",
    "买入": "Buy",
    "卖出": "Sell",
    "合计": "Total",
    "交易发生日": "trade date",
    "先进先出": "first in, first out",
    "完整数据:": "Full data:",
    "（暂无数据）": "(no data)",
    "有 ticker（可交易）": "Rows with a ticker (tradable)",
    "可算 NW 收益（有": "Rows with a notional-weighted return (",
    "（另有": "(another",
    "笔因金额缺失未进入 horizon 表）": "trades lack an amount and are left out of the horizon table)",
    "买卖结构（股票 + 期权原始行；买入含": "Buy/sell mix (raw stock + option rows; buys include",
    "；名义：股票=PTR 下限，期权=张数×100×行权价或 PTR 下限）": "; notional: stock = PTR floor, options = contracts×100×strike or the PTR floor)",
    "类别": "Category",
    "名义合计": "Total notional",
    "占名义比例": "Share of notional",
    "股票买入": "Stock buys",
    "股票卖出": "Stock sells",
    "期权买入/行权": "Option buys / exercises",
    "期权卖出": "Option sells",
    "股票": "Stock",
    "期权": "Options",
    "本报告并行使用": "This report uses, side by side,",
    "三套名义": "three notionals",
    "两套 FIFO / MTM": "two FIFO / mark-to-market books",
    "，请勿混读数字：": ". Do not mix the figures:",
    "名义类型": "Notional type",
    "定义": "Definition",
    "用于": "Used for",
    "经济名义": "Economic notional",
    "合并账": "Combined book",
    "统一 FIFO": "Unified FIFO",
    "金额缺失": "Missing amounts",
    "未": "not",
    "去重净敞口。": "netted into one exposure.",
    "仍持有": "still held",
    "净名义不是精确市值": "Net notional is not a precise market value",
    "张数×100 股": "contracts × 100 shares",
    "买入 call": "Buy call",
    "卖出 call": "Sell call",
    "买入 put": "Buy put",
    "卖出 put": "Sell put",
    "行权": "Exercise",
    "100 股/张": "100 shares/contract",
    "其中：股票": "Of which: stock",
    "其中：期权（标的价 × 100 股/张名义）": "Of which: options (underlying × 100 shares)",
    "合计（股票 + 期权）": "Total (stock + options)",
    "1. Pelosi 自身交易 timing（锚点 =": "1. Pelosi's own timing (anchor =",
    "2. Follow Pelosi（锚点 =": "2. Follow Pelosi (anchor =",
    "PTR 披露日": "PTR disclosure date",
    "标的": "Underlying",
    "行权价": "Strike",
    "到期": "Expiry",
    "张数": "Contracts",
    "House Clerk 官方 PTR: ✅": "Official House Clerk PTR: ✅",
    "PTR PDF 校验: ✅": "PTR PDF check: ✅",
    "数据来源为": "Source:",
    "），非总统 OGE Form 278-T。": "), not presidential OGE Form 278-T.",
    "「名义与口径」": "“Notional and definitions”",
    "图表已内嵌为本页数据，可直接用浏览器打开本地 HTML（无需": "Charts are embedded in this page, so the HTML opens locally with no",
    "子目录）。 手机/微信可发": "folder). On a phone or WeChat, send",
    "或 GitHub Pages：": "or the GitHub Pages link:",
    "成功配对:": "Matched lots:",
    "对，涉及": "lots across",
    "个 ticker": "tickers",
    "持仓中位:": "Median hold:",
    "天，均值:": "days, mean:",
    "规则: 同 ticker 按日期排序，": "Rule: same ticker, sorted by date,",
    "FIFO 持仓天数分布": "FIFO holding-period distribution",
    "已纳入文件（逐份统计）": "Included filings",
    "样本交易日:": "Sample days:",
    "截止": "As of",
    "基于": "Based on",
    "按": "Using",
    "下限": "floor",
    "来源": "Source",
    "或": "or",
    "非": "not",
  };
  if (window.DASH_EXTRA) Object.assign(DICT, window.DASH_EXTRA);

  window.DASH_LANG = localStorage.getItem("dash-lang") === "en" ? "en" : "zh";
  window.t = function (s) {
    if (window.DASH_LANG !== "en") return s;
    return lookup(s) || s;
  };
  const orig = new WeakMap();
  function canon(s) {
    return s.replace(/\s+/g, " ").replace(/\s+([）)])/g, "$1").replace(/([（(])\s+/g, "$1").trim();
  }
  function lookup(s) {
    if (Object.prototype.hasOwnProperty.call(DICT, s)) return DICT[s];
    const c = canon(s);
    const hit = Object.keys(DICT).find((k) => canon(k) === c);
    if (hit) return DICT[hit];
    if (!/[\u4e00-\u9fff]/.test(s)) return null;
    const keys = Object.keys(DICT).filter((k) => /[\u4e00-\u9fff]/.test(k) && k.length >= 2);
    keys.sort((a, b) => b.length - a.length);
    let next = s;
    keys.forEach((k) => {
      if (next.includes(k)) next = next.split(k).join(DICT[k]);
    });
    return next !== s ? next : null;
  }
  function translate(node) {
    const parent = node.parentElement;
    if (!parent || parent.closest("script, style, .lang-switch")) return;
    if (!orig.has(node)) orig.set(node, node.nodeValue);
    const raw = orig.get(node);
    if (!raw || !/[\u4e00-\u9fff]/.test(raw)) return;
    if (window.DASH_LANG !== "en") {
      node.nodeValue = raw;
      return;
    }
    const trimmed = raw.trim();
    const hit = lookup(trimmed);
    if (hit) node.nodeValue = raw.replace(trimmed, hit);
  }
  window.applyPageLang = function () {
    document.documentElement.lang = window.DASH_LANG === "en" ? "en" : "zh-CN";
    document.querySelectorAll(".lang-switch button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.setLang === window.DASH_LANG);
    });
    const title = document.querySelector("title");
    if (title) {
      if (!title.dataset.zh) title.dataset.zh = title.textContent;
      title.textContent = window.DASH_LANG === "en" ? window.t(title.dataset.zh) : title.dataset.zh;
    }
    document.querySelectorAll("[aria-label]").forEach((el) => {
      if (!el.dataset.ariaZh) el.dataset.ariaZh = el.getAttribute("aria-label");
      const src = el.dataset.ariaZh;
      el.setAttribute("aria-label", window.DASH_LANG === "en" ? (window.t(src) || src) : src);
    });
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(translate);
  };
  window.setDashLang = function (lang) {
    window.DASH_LANG = lang === "en" ? "en" : "zh";
    localStorage.setItem("dash-lang", window.DASH_LANG);
    window.applyPageLang();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", window.applyPageLang);
  else window.applyPageLang();
})();
