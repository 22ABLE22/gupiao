/* 沪深股票分析前端 */
const API = "";
const state = {
  symbol: "159516",
  market: "SZ",
  name: "159516.SZ",
  days: 250,
  adjust: "qfq",
  indicators: { ma: true, boll: false, vol: true },
  portfolio: null,
  history: null,
};

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

function fmtNum(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
function fmtMoney(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  const x = Number(n);
  const sign = x > 0 ? "+" : "";
  return sign + fmtNum(x, 2);
}
function fmtPct(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  const x = Number(n);
  const sign = x > 0 ? "+" : "";
  return sign + fmtNum(x, 2) + "%";
}
function toneClass(n) {
  const x = Number(n);
  if (Number.isNaN(x) || x === 0) return "flat";
  return x > 0 ? "up" : "down";
}
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2800);
}

async function api(path) {
  const res = await fetch(API + path);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function setActiveSymbol(code, market, name) {
  state.symbol = code;
  state.market = market;
  state.name = name || `${code}.${market}`;
  $("#activeSymbol").innerHTML = `<strong>${escapeHtml(state.name)}</strong>${escapeHtml(code)}.${escapeHtml(market)}`;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/* ---------- Navigation ---------- */
$$(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $$(".view").forEach((v) => v.classList.remove("active"));
    const view = btn.dataset.view;
    $(`#view-${view}`).classList.add("active");
    if (view === "chart") loadChart();
    if (view === "fund") loadFundamentals();
    if (view === "compare") loadCompare();
    if (view === "dashboard") loadPortfolio();
    if (view === "reference") loadReference();
    if (view === "live") loadLive();
  });
});

/* ---------- Search ---------- */
const searchInput = $("#searchInput");
const searchResults = $("#searchResults");
let searchTimer = null;

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = searchInput.value.trim();
  if (!q) {
    searchResults.classList.add("hidden");
    return;
  }
  searchTimer = setTimeout(async () => {
    try {
      const items = await api(`/api/search?q=${encodeURIComponent(q)}`);
      if (!items.length) {
        searchResults.innerHTML = `<div class="search-item muted">无匹配结果</div>`;
      } else {
        searchResults.innerHTML = items
          .map(
            (it) => `<div class="search-item" data-code="${escapeHtml(it.code)}" data-market="${escapeHtml(it.market)}" data-name="${escapeHtml(it.name)}">
              <span>${escapeHtml(it.name)}</span>
              <span class="muted">${escapeHtml(it.full)} · ${it.type === "etf" ? "ETF" : "股票"}</span>
            </div>`
          )
          .join("");
      }
      searchResults.classList.remove("hidden");
    } catch (e) {
      searchResults.innerHTML = `<div class="search-item">搜索失败：${escapeHtml(e.message)}</div>`;
      searchResults.classList.remove("hidden");
    }
  }, 280);
});

searchResults.addEventListener("click", (e) => {
  const item = e.target.closest(".search-item");
  if (!item || !item.dataset.code) return;
  selectSymbol(item.dataset.code, item.dataset.market, item.dataset.name);
  searchResults.classList.add("hidden");
  searchInput.value = "";
});

document.addEventListener("click", (e) => {
  if (!e.target.closest(".symbol-picker")) searchResults.classList.add("hidden");
});

function selectSymbol(code, market, name) {
  setActiveSymbol(code, market, name);
  const active = $(".nav-item.active")?.dataset.view || "dashboard";
  if (active === "chart") loadChart();
  else if (active === "fund") loadFundamentals();
  else if (active === "compare") loadCompare();
  else loadSignalsSide();
}

/* ---------- Chart controls ---------- */
$$("#periodSeg button").forEach((b) => {
  b.addEventListener("click", () => {
    $$("#periodSeg button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    state.days = Number(b.dataset.days);
    loadChart();
  });
});
$$("#adjustSeg button").forEach((b) => {
  b.addEventListener("click", () => {
    $$("#adjustSeg button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    state.adjust = b.dataset.adjust || "";
    loadChart();
  });
});
$$("#indicatorChips input").forEach((c) => {
  c.addEventListener("change", () => {
    state.indicators[c.dataset.ind] = c.checked;
    if (state.history) renderKline(state.history);
  });
});

$("#btnRefresh").addEventListener("click", () => {
  const active = $(".nav-item.active")?.dataset.view || "dashboard";
  if (active === "dashboard") loadPortfolio();
  else if (active === "chart") loadChart();
  else if (active === "fund") loadFundamentals();
  else loadCompare();
  toast("已刷新");
});

/* ---------- Portfolio ---------- */
async function loadPortfolio() {
  const box = $("#statsRow");
  box.innerHTML = `<div class="stat-card"><div class="label">加载中…</div><div class="value">…</div></div>`;
  try {
    const data = await api("/api/portfolio");
    state.portfolio = data;
    renderPortfolio(data);
  } catch (e) {
    box.innerHTML = `<div class="stat-card"><div class="label">加载失败</div><div class="value">${escapeHtml(e.message)}</div></div>`;
  }
}

function renderPortfolio(data) {
  const stats = $("#statsRow");
  stats.innerHTML = `
    <div class="stat-card">
      <div class="label">总市值</div>
      <div class="value">${fmtNum(data.total_mv, 2)}</div>
      <div class="sub">成本合计 ${fmtNum(data.total_cost, 2)}</div>
    </div>
    <div class="stat-card">
      <div class="label">浮动盈亏</div>
      <div class="value ${toneClass(data.total_pnl)}">${fmtMoney(data.total_pnl)}</div>
      <div class="sub ${toneClass(data.total_pnl_pct)}">${fmtPct(data.total_pnl_pct)}</div>
    </div>
    <div class="stat-card">
      <div class="label">今日盈亏</div>
      <div class="value ${toneClass(data.day_pnl)}">${fmtMoney(data.day_pnl)}</div>
      <div class="sub">按最新价变动估算</div>
    </div>
    <div class="stat-card">
      <div class="label">持仓数量</div>
      <div class="value">${data.holdings.length}</div>
      <div class="sub">自选 ${data.watchlist.length} 只</div>
    </div>
  `;

  const tbody = $("#holdingsTable tbody");
  if (!data.holdings.length) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="empty">暂无持仓，点击右上角添加</div></td></tr>`;
  } else {
    tbody.innerHTML = data.holdings
      .map(
        (h, i) => `<tr data-code="${escapeHtml(h.code)}" data-market="${escapeHtml(h.market)}" data-name="${escapeHtml(h.name)}" data-idx="${i}">
          <td>
            <div><strong>${escapeHtml(h.name)}</strong></div>
            <div class="muted">${escapeHtml(h.full || h.code)}.${escapeHtml(h.market)}</div>
          </td>
          <td>${fmtNum(h.shares, 0)}</td>
          <td>${fmtNum(h.cost, 3)}</td>
          <td>${fmtNum(h.price, 3)}</td>
          <td>${fmtNum(h.mv, 2)}</td>
          <td class="${toneClass(h.pnl)}">${fmtMoney(h.pnl)}<div class="muted ${toneClass(h.pnl_pct)}">${fmtPct(h.pnl_pct)}</div></td>
          <td class="${toneClass(h.change_pct)}">${fmtPct(h.change_pct)}<div class="muted ${toneClass(h.day_pnl)}">${fmtMoney(h.day_pnl)}</div></td>
          <td>${fmtNum(h.weight, 1)}%</td>
          <td><button class="btn danger ghost btn-del" data-idx="${i}">删除</button></td>
        </tr>`
      )
      .join("");
  }

  tbody.querySelectorAll("tr[data-code]").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.classList.contains("btn-del")) return;
      selectSymbol(tr.dataset.code, tr.dataset.market, tr.dataset.name);
    });
  });
  tbody.querySelectorAll(".btn-del").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("确认删除该持仓？")) return;
      try {
        const res = await fetch(`${API}/api/portfolio/holdings/${btn.dataset.idx}`, { method: "DELETE" });
        if (!res.ok) throw new Error("删除失败");
        state.portfolio = await res.json();
        renderPortfolio(state.portfolio);
        toast("已删除持仓");
      } catch (err) {
        toast(err.message);
      }
    });
  });

  renderAlloc(data.holdings);
}

function renderAlloc(holdings) {
  const el = $("#allocChart");
  const chart = echarts.getInstanceByDom(el) || echarts.init(el);
  if (!holdings.length) {
    chart.clear();
    chart.setOption({
      backgroundColor: "transparent",
      title: { text: "暂无持仓", left: "center", top: "middle", textStyle: { color: "#6b7a90", fontSize: 14 } },
    });
    return;
  }
  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "item", formatter: "{b}<br/>仓位 {d}%" },
    legend: { bottom: 0, textStyle: { color: "#6b7a90" } },
    series: [
      {
        type: "pie",
        radius: ["42%", "68%"],
        center: ["50%", "46%"],
        itemStyle: { borderColor: "#f4f6fb", borderWidth: 2 },
        label: { color: "#1a2233", formatter: "{b}\n{d}%" },
        data: holdings.map((h) => ({ name: h.name || h.code, value: Number(h.mv.toFixed(2)) })),
      },
    ],
  });
}

/* Add holding */
const holdingDialog = $("#holdingDialog");
$("#btnAddHolding").addEventListener("click", () => {
  const form = $("#holdingForm");
  form.code.value = state.symbol;
  form.market.value = state.market;
  form.shares.value = "";
  form.cost.value = "";
  holdingDialog.showModal();
});
$("#btnHoldingCancel").addEventListener("click", () => {
  holdingDialog.close();
});
$("#holdingForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  const payload = {
    code: form.code.value.trim(),
    market: form.market.value,
    shares: Number(form.shares.value),
    cost: Number(form.cost.value),
  };
  try {
    const res = await fetch(`${API}/api/portfolio/holdings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.detail || "添加失败");
    }
    state.portfolio = await res.json();
    renderPortfolio(state.portfolio);
    holdingDialog.close();
    toast("持仓已添加");
  } catch (err) {
    toast(err.message);
  }
});

/* ---------- K-line ---------- */
let klineChart = null;

async function loadChart() {
  const el = $("#klineChart");
  if (!klineChart) klineChart = echarts.init(el);
  klineChart.showLoading({ text: "加载中", color: "#2f6fed", maskColor: "rgba(244,246,251,0.6)" });
  try {
    const data = await api(
      `/api/history?symbol=${encodeURIComponent(state.symbol)}&market=${encodeURIComponent(state.market)}&days=${state.days}&adjust=${encodeURIComponent(state.adjust)}`
    );
    state.history = data;
    setActiveSymbol(data.code, data.market, data.name);
    renderKline(data);
    await loadSignalsSide();
  } catch (e) {
    klineChart.hideLoading();
    toast("K线加载失败：" + e.message);
  }
}

function renderKline(data) {
  if (!klineChart) klineChart = echarts.init($("#klineChart"));
  const bars = data.bars || [];
  if (!bars.length) {
    klineChart.hideLoading();
    return;
  }
  const dates = bars.map((b) => b.date);
  const ohlc = bars.map((b) => [b.open, b.close, b.low, b.high]);
  const vols = bars.map((b) => b.volume);
  const showMA = state.indicators.ma;
  const showBoll = state.indicators.boll;
  const showVol = state.indicators.vol;

  const series = [
    {
      name: "K线",
      type: "candlestick",
      data: ohlc,
      xAxisIndex: 0,
      yAxisIndex: 0,
      itemStyle: {
        color: "#e03131",
        color0: "#0ca678",
        borderColor: "#e03131",
        borderColor0: "#0ca678",
      },
    },
  ];

  if (showMA) {
    ["ma5", "ma10", "ma20", "ma60"].forEach((key, i) => {
      const colors = ["#f5c542", "#2f6fed", "#c084fc", "#38bdf8"];
      series.push({
        name: key.toUpperCase(),
        type: "line",
        data: bars.map((b) => b[key]),
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 1.2, color: colors[i] },
        xAxisIndex: 0,
        yAxisIndex: 0,
      });
    });
  }

  if (showBoll) {
    [
      ["boll_upper", "#f5a524"],
      ["boll_mid", "#6b7a90"],
      ["boll_lower", "#0ca678"],
    ].forEach(([key, color]) => {
      series.push({
        name: key,
        type: "line",
        data: bars.map((b) => b[key]),
        showSymbol: false,
        lineStyle: { width: 1, type: key === "boll_mid" ? "solid" : "dashed", color },
        xAxisIndex: 0,
        yAxisIndex: 0,
      });
    });
  }

  if (showVol) {
    series.push({
      name: "成交量",
      type: "bar",
      data: vols.map((v, i) => ({
        value: v,
        itemStyle: {
          color: bars[i].close >= bars[i].open ? "rgba(224,49,49,0.55)" : "rgba(12,166,120,0.55)",
        },
      })),
      xAxisIndex: 1,
      yAxisIndex: 1,
      barMaxWidth: 8,
    });
  }

  const grid = showVol
    ? [
        { left: 56, right: 16, top: 40, height: "58%" },
        { left: 56, right: 16, top: "76%", height: "14%" },
      ]
    : [{ left: 56, right: 16, top: 40, bottom: 48 }];

  const xAxis = showVol
    ? [
        { type: "category", data: dates, gridIndex: 0, axisLine: { lineStyle: { color: "#c5d0e0" } }, axisLabel: { color: "#6b7a90" } },
        { type: "category", data: dates, gridIndex: 1, axisLine: { lineStyle: { color: "#c5d0e0" } }, axisLabel: { show: false } },
      ]
    : [{ type: "category", data: dates, axisLine: { lineStyle: { color: "#c5d0e0" } }, axisLabel: { color: "#6b7a90" } }];

  const yAxis = showVol
    ? [
        { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: "rgba(107,122,144,0.08)" } }, axisLabel: { color: "#6b7a90" } },
        { scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { color: "#6b7a90", formatter: (v) => (v > 1e8 ? (v / 1e8).toFixed(1) + "亿" : v > 1e4 ? (v / 1e4).toFixed(0) + "万" : v) } },
      ]
    : [{ scale: true, splitLine: { lineStyle: { color: "rgba(107,122,144,0.08)" } }, axisLabel: { color: "#6b7a90" } }];

  klineChart.setOption(
    {
      backgroundColor: "transparent",
      animation: false,
      legend: { top: 8, textStyle: { color: "#6b7a90" }, selectedMode: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: "rgba(255,255,255,0.95)",
        borderColor: "rgba(107,122,144,0.2)",
        textStyle: { color: "#1a2233", fontSize: 12 },
        formatter: (params) => {
          const i = params[0]?.dataIndex ?? 0;
          const b = bars[i];
          if (!b) return "";
          const lines = [
            `<div style="font-weight:600;margin-bottom:4px">${b.date}</div>`,
            `开 ${fmtNum(b.open, 3)}　收 <b>${fmtNum(b.close, 3)}</b>`,
            `高 ${fmtNum(b.high, 3)}　低 ${fmtNum(b.low, 3)}`,
          ];
          if (b.change_pct !== undefined && b.change_pct !== null) {
            const t = toneClass(b.change_pct);
            lines.push(`<span style="color:${t === "up" ? "#e03131" : t === "down" ? "#0ca678" : "#6b7a90"}">涨跌 ${fmtPct(b.change_pct)}</span>`);
          }
          if (b.rsi14 != null) lines.push(`RSI14 ${fmtNum(b.rsi14, 1)}`);
          if (b.macd_dif != null) lines.push(`MACD DIF ${fmtNum(b.macd_dif, 3)}`);
          return lines.join("<br/>");
        },
      },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      dataZoom: [
        { type: "inside", xAxisIndex: showVol ? [0, 1] : 0 },
        { type: "slider", xAxisIndex: showVol ? [0, 1] : 0, bottom: 8, height: 16, borderColor: "rgba(107,122,144,0.2)", fillerColor: "rgba(47,111,237,0.12)", textStyle: { color: "#6b7a90" } },
      ],
      grid,
      xAxis,
      yAxis,
      series,
    },
    true
  );
  klineChart.hideLoading();
}

async function loadSignalsSide() {
  const trendBox = $("#trendBox");
  const signalList = $("#signalList");
  trendBox.innerHTML = `<div class="muted">加载中…</div>`;
  signalList.innerHTML = `<div class="muted">加载中…</div>`;
  try {
    const data = await api(`/api/signals?symbol=${encodeURIComponent(state.symbol)}&market=${encodeURIComponent(state.market)}&days=${Math.max(state.days, 120)}`);
    const t = data.trend || {};
    const tone = t.tone === "up" ? "up" : t.tone === "down" ? "down" : "flat";
    trendBox.innerHTML = `
      <div class="trend-label ${tone}" style="background:${tone === "up" ? "rgba(224,49,49,0.12)" : tone === "down" ? "rgba(12,166,120,0.12)" : "rgba(107,122,144,0.12)"}">
        综合倾向：${escapeHtml(t.label || "—")}
      </div>
      <ul>${(t.points || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("") || "<li>暂无结论</li>"}</ul>
      <div class="muted" style="margin-top:10px">多头计分 ${t.buy_votes ?? 0} · 空头计分 ${t.sell_votes ?? 0}</div>
    `;
    const sigs = data.signals || [];
    if (!sigs.length) {
      signalList.innerHTML = `<div class="empty">近期无经典交叉信号（属正常，信号较稀疏）</div>`;
    } else {
      signalList.innerHTML = sigs
        .map(
          (s) => `<div class="signal-item">
            <div class="date">${escapeHtml(s.date)}</div>
            <div>
              <div class="name">${escapeHtml(s.name)} <span class="muted">强度 ${escapeHtml(s.strength)}</span></div>
              <div class="detail">${escapeHtml(s.detail)} · 收盘 ${fmtNum(s.close, 3)}</div>
            </div>
            <div class="badge ${s.kind}">${s.kind === "buy" ? "偏多" : s.kind === "sell" ? "偏空" : "中性"}</div>
          </div>`
        )
        .join("");
    }
  } catch (e) {
    trendBox.innerHTML = `<div class="muted">${escapeHtml(e.message)}</div>`;
    signalList.innerHTML = `<div class="muted">信号加载失败</div>`;
  }
}

/* ---------- Fundamentals ---------- */
async function loadFundamentals() {
  const grid = $("#fundGrid");
  const tips = $("#fundTips");
  grid.innerHTML = `<div class="fund-item"><div class="k">加载中</div><div class="v">…</div></div>`;
  try {
    const data = await api(`/api/fundamentals?symbol=${encodeURIComponent(state.symbol)}&market=${encodeURIComponent(state.market)}`);
    setActiveSymbol(data.code, data.market, data.name);
    $("#fundName").textContent = `${data.name || ""} · ${data.code}.${data.market}`;
    const items = data.items || [];
    if (!items.length) {
      grid.innerHTML = `<div class="empty">暂无基本面数据</div>`;
    } else {
      grid.innerHTML = items
        .map(
          (it) => `<div class="fund-item">
            <div class="k">${escapeHtml(it.label)}</div>
            <div class="v">${escapeHtml(typeof it.value === "number" ? fmtNum(it.value, 3) : it.value)}</div>
            <div class="h">${escapeHtml(it.hint || "")}</div>
          </div>`
        )
        .join("");
    }

    const tipLines = buildFundTips(data);
    tips.innerHTML = tipLines.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  } catch (e) {
    grid.innerHTML = `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

function buildFundTips(data) {
  const tips = [];
  const isEtf = data.type === "etf";
  if (isEtf) {
    tips.push("你当前看的是 ETF：更贴近一篮子资产的表现，费率通常低于主动基金，适合观察行业/指数趋势。");
    tips.push("ETF 重点看跟踪误差、流动性（成交额）和溢价率；市盈率对债券/货币类 ETF 参考意义有限。");
  } else {
    tips.push("市盈率（PE）反映“按当前利润多少年回本”，过高可能透支成长，过低也可能说明基本面弱。");
    tips.push("市净率（PB）适合重资产行业；轻资产成长股 PB 天然更高，需结合行业对比。");
    tips.push("换手率突然放大，往往伴随情绪或事件驱动，需结合价格位置看。");
  }
  tips.push("市值越大，通常波动相对温和；小市值弹性大，风险也更高。");
  tips.push("基本面是慢变量，买卖决策建议结合 K线信号与仓位管理，不要单指标重仓。");
  return tips;
}

/* ---------- Compare / Watchlist ---------- */
let compareChart = null;

async function loadCompare() {
  try {
    const data = await api("/api/portfolio");
    state.portfolio = data;
    renderWatch(data.watchlist || []);
    await renderCompareChart(data.watchlist || []);
  } catch (e) {
    toast("自选加载失败：" + e.message);
  }
}

function renderWatch(list) {
  const box = $("#watchList");
  if (!list.length) {
    box.innerHTML = `<div class="empty">暂无自选，添加代码后可对比走势</div>`;
    return;
  }
  box.innerHTML = list
    .map(
      (w) => `<div class="watch-item" data-code="${escapeHtml(w.code)}" data-market="${escapeHtml(w.market)}" data-name="${escapeHtml(w.name || w.code)}">
        <div class="meta">
          <strong>${escapeHtml(w.name || w.code)}</strong>
          <span class="muted">${escapeHtml(w.full || w.code)}.${escapeHtml(w.market)} · ${w.type === "etf" ? "ETF" : "股票"}</span>
        </div>
        <div style="text-align:right">
          <div>${fmtNum(w.price, 3)}</div>
          <div class="${toneClass(w.change_pct)}">${fmtPct(w.change_pct)}</div>
        </div>
        <div class="actions">
          <button class="btn ghost btn-open">查看</button>
          <button class="btn danger ghost btn-unwatch">移除</button>
        </div>
      </div>`
    )
    .join("");

  box.querySelectorAll(".watch-item").forEach((el) => {
    el.querySelector(".btn-open").addEventListener("click", () => {
      selectSymbol(el.dataset.code, el.dataset.market, el.dataset.name);
      $$(".nav-item").forEach((b) => b.classList.remove("active"));
      $('.nav-item[data-view="chart"]').classList.add("active");
      $$(".view").forEach((v) => v.classList.remove("active"));
      $("#view-chart").classList.add("active");
      loadChart();
    });
    el.querySelector(".btn-unwatch").addEventListener("click", async () => {
      try {
        const res = await fetch(
          `${API}/api/portfolio/watch?code=${encodeURIComponent(el.dataset.code)}&market=${encodeURIComponent(el.dataset.market)}`,
          { method: "DELETE" }
        );
        if (!res.ok) throw new Error("移除失败");
        state.portfolio = await res.json();
        renderWatch(state.portfolio.watchlist || []);
        renderCompareChart(state.portfolio.watchlist || []);
      } catch (e) {
        toast(e.message);
      }
    });
  });
}

async function renderCompareChart(list) {
  const el = $("#compareChart");
  if (!compareChart) compareChart = echarts.init(el);
  if (!list.length) {
    compareChart.clear();
    compareChart.setOption({
      backgroundColor: "transparent",
      title: { text: "添加自选后显示对比", left: "center", top: "middle", textStyle: { color: "#6b7a90", fontSize: 14 } },
    });
    return;
  }

  compareChart.showLoading({ text: "加载中", color: "#2f6fed", maskColor: "rgba(244,246,251,0.5)" });
  try {
    const series = [];
    let dates = null;
    const colors = ["#2f6fed", "#e03131", "#f5c542", "#38bdf8", "#c084fc", "#0ca678"];
    for (let i = 0; i < list.length; i++) {
      const w = list[i];
      const hist = await api(`/api/history?symbol=${encodeURIComponent(w.code)}&market=${encodeURIComponent(w.market)}&days=250`);
      const bars = hist.bars || [];
      if (!bars.length) continue;
      if (!dates) dates = bars.map((b) => b.date);
      const base = bars.find((b) => b.close > 0)?.close || 1;
      series.push({
        name: hist.name || w.code,
        type: "line",
        showSymbol: false,
        smooth: true,
        data: bars.map((b) => Number(((b.close / base) * 100).toFixed(2))),
        lineStyle: { width: 2, color: colors[i % colors.length] },
        itemStyle: { color: colors[i % colors.length] },
      });
    }
    compareChart.setOption(
      {
        backgroundColor: "transparent",
        tooltip: { trigger: "axis", backgroundColor: "rgba(255,255,255,0.95)", textStyle: { color: "#1a2233" } },
        legend: { top: 8, textStyle: { color: "#6b7a90" } },
        grid: { left: 48, right: 16, top: 40, bottom: 40 },
        xAxis: { type: "category", data: dates || [], axisLabel: { color: "#6b7a90" } },
        yAxis: { scale: true, splitLine: { lineStyle: { color: "rgba(107,122,144,0.08)" } }, axisLabel: { color: "#6b7a90" } },
        series,
      },
      true
    );
  } catch (e) {
    toast("对比图失败：" + e.message);
  } finally {
    compareChart.hideLoading();
  }
}

$("#btnAddWatch").addEventListener("click", async () => {
  const code = $("#watchInput").value.trim();
  const market = $("#watchMarket").value.trim().toUpperCase() || "";
  if (!code) return toast("请输入代码");
  try {
    const res = await fetch(`${API}/api/portfolio/watch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, market }),
    });
    if (!res.ok) throw new Error("添加失败");
    state.portfolio = await res.json();
    $("#watchInput").value = "";
    renderWatch(state.portfolio.watchlist || []);
    renderCompareChart(state.portfolio.watchlist || []);
    toast("已加入自选");
  } catch (e) {
    toast(e.message);
  }
});

/* ---------- Reference (稳健参考) ---------- */
async function loadReference() {
  const box = $("#refGroups");
  box.innerHTML = `<div class="empty">加载参考清单…</div>`;
  try {
    const data = await api("/api/reference");
    const groups = data.groups || [];
    box.innerHTML = groups
      .map((g) => {
        const cards = (g.items || [])
          .map((it) => {
            const name = it.live_name || it.name;
            return `<div class="ref-card" data-code="${escapeHtml(it.code)}" data-market="${escapeHtml(it.market)}" data-name="${escapeHtml(name)}">
              <div class="top">
                <div>
                  <div class="nm">${escapeHtml(name)}</div>
                  <div class="cd">${escapeHtml(it.full)} · ${it.type === "etf" ? "ETF" : "股票"}</div>
                </div>
                ${it.tag ? `<span class="tag">${escapeHtml(it.tag)}</span>` : ""}
              </div>
              <div>
                <div class="px">${fmtNum(it.price, 3)}</div>
                <div class="${toneClass(it.change_pct)}">${fmtPct(it.change_pct)}</div>
              </div>
              <div class="acts">
                <button class="btn ghost btn-view">看K线</button>
                <button class="btn btn-watch">加自选</button>
              </div>
            </div>`;
          })
          .join("");
        return `<div class="ref-group">
          <div class="ref-group-title">
            <h3>${escapeHtml(g.title)}</h3>
            <span class="ref-risk">风险：${escapeHtml(g.risk)}</span>
          </div>
          <p class="ref-blurb">${escapeHtml(g.blurb)}</p>
          <div class="ref-grid">${cards}</div>
        </div>`;
      })
      .join("");

    box.querySelectorAll(".ref-card").forEach((card) => {
      const code = card.dataset.code;
      const market = card.dataset.market;
      const name = card.dataset.name;
      card.querySelector(".btn-view").addEventListener("click", () => {
        selectSymbol(code, market, name);
        $$(".nav-item").forEach((b) => b.classList.remove("active"));
        $('.nav-item[data-view="chart"]').classList.add("active");
        $$(".view").forEach((v) => v.classList.remove("active"));
        $("#view-chart").classList.add("active");
        loadChart();
      });
      card.querySelector(".btn-watch").addEventListener("click", async () => {
        try {
          const res = await fetch(`${API}/api/portfolio/watch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code, market }),
          });
          if (!res.ok) throw new Error("添加失败");
          state.portfolio = await res.json();
          toast(`${name} 已加入自选`);
        } catch (e) {
          toast(e.message);
        }
      });
    });
  } catch (e) {
    box.innerHTML = `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

/* ---------- Live alerts ---------- */
let lastAlertTs = 0;
let liveTimer = null;
let notifiedIds = new Set();

function notifyBrowser(title, body) {
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  try {
    new Notification(title, { body: body || "", tag: title });
  } catch (_) {}
}

$("#btnNotify")?.addEventListener("click", async () => {
  if (!("Notification" in window)) {
    toast("当前浏览器不支持系统通知");
    return;
  }
  const p = await Notification.requestPermission();
  toast(p === "granted" ? "系统通知已开启（请保持本页打开）" : "通知权限未授予");
});

$("#btnScanNow")?.addEventListener("click", async () => {
  try {
    toast("扫描中…");
    const res = await fetch(`${API}/api/monitor/scan`, { method: "POST" });
    if (!res.ok) throw new Error("扫描失败");
    await loadLive();
    toast("扫描完成");
  } catch (e) {
    toast(e.message);
  }
});

$("#btnToggleMon")?.addEventListener("click", async () => {
  try {
    const st = await api("/api/monitor");
    const url = st.running ? "/api/monitor/stop" : "/api/monitor/start";
    const res = await fetch(API + url, { method: "POST" });
    if (!res.ok) throw new Error("操作失败");
    await loadLive();
    toast(st.running ? "监控已暂停" : "监控已启动");
  } catch (e) {
    toast(e.message);
  }
});

$("#btnClearAlerts")?.addEventListener("click", async () => {
  try {
    await fetch(`${API}/api/alerts`, { method: "DELETE" });
    await loadLive();
    toast("提醒已清空");
  } catch (e) {
    toast(e.message);
  }
});

function scoreColor(score) {
  const s = Number(score) || 50;
  if (s >= 72) return "var(--up)";
  if (s >= 58) return "#e8590c";
  if (s > 42) return "var(--muted)";
  if (s > 30) return "#0b7285";
  return "var(--down)";
}

function renderAlerts(alerts, clock, monitor) {
  const live = clock?.is_trading && monitor?.running;
  $("#liveStats").innerHTML = `
    <div class="stat-card">
      <div class="label">市场状态</div>
      <div class="value" style="font-size:20px">
        <span class="live-dot ${live ? "" : "off"}"></span>${escapeHtml(clock?.detail || "—")}
      </div>
      <div class="sub">${escapeHtml((clock?.now || "").replace("T", " ").slice(0, 19))}</div>
    </div>
    <div class="stat-card">
      <div class="label">监控</div>
      <div class="value" style="font-size:20px">${monitor?.running ? "运行中" : "已停止"}</div>
      <div class="sub">间隔约 ${monitor?.interval_sec || 45}s · 扫描 ${monitor?.scans || 0} 次</div>
    </div>
    <div class="stat-card">
      <div class="label">监控标的</div>
      <div class="value">${(monitor?.watch_codes || []).length}</div>
      <div class="sub">持仓 + 自选</div>
    </div>
    <div class="stat-card">
      <div class="label">已推送提醒</div>
      <div class="value">${alerts.length}</div>
      <div class="sub">累计 ${monitor?.alerts_emitted || 0}</div>
    </div>
  `;

  const btn = $("#btnToggleMon");
  if (btn) btn.textContent = monitor?.running ? "暂停监控" : "启动监控";

  const box = $("#alertList");
  if (!alerts.length) {
    box.innerHTML = `<div class="empty">暂无提醒。开市时段或点「立即扫描」后，若触发阈值会出现在这里。</div>`;
  } else {
    box.innerHTML = alerts
      .map(
        (a) => `<div class="alert-item ${escapeHtml(a.kind || "")}">
          <div class="hd">
            <div class="ttl">${escapeHtml(a.title || a.name)}</div>
            <div class="tm">${escapeHtml(a.time_str || "")}</div>
          </div>
          <div class="bd">${escapeHtml(a.body || a.advice || "")}</div>
          <div class="sc">
            <span class="pill">分 ${fmtNum(a.score, 0)}</span>
            ${a.price != null ? `<span class="pill">价 ${fmtNum(a.price, 3)}</span>` : ""}
            ${a.stop_hint != null ? `<span class="pill">止损观察 ${fmtNum(a.stop_hint, 3)}</span>` : ""}
            ${a.target_hint != null ? `<span class="pill">目标观察 ${fmtNum(a.target_hint, 3)}</span>` : ""}
          </div>
        </div>`
      )
      .join("");
  }

  // browser notify new alerts
  for (const a of alerts) {
    const id = a.id || a.ts;
    if (!id || notifiedIds.has(id)) continue;
    if ((a.ts || 0) * 1 < lastAlertTs) continue;
    if (a.kind && a.kind !== "info") {
      notifyBrowser(a.title || "行情提醒", (a.body || a.advice || "").slice(0, 120));
    }
    notifiedIds.add(id);
  }
  if (alerts.length) lastAlertTs = Math.max(lastAlertTs, ...alerts.map((a) => a.ts || 0));
}

async function loadScoreBoard() {
  const box = $("#scoreBoard");
  box.innerHTML = `<div class="empty">计算中…</div>`;
  try {
    const data = await api("/api/signals/pro");
    const items = (data.items || []).filter((x) => x.ok);
    if (!items.length) {
      box.innerHTML = `<div class="empty">无标的，请先添加持仓或自选</div>`;
      return;
    }
    box.innerHTML = items
      .map((it) => {
        const pct = Math.max(0, Math.min(100, Number(it.score) || 50));
        const color = scoreColor(it.score);
        return `<div class="score-row" data-code="${escapeHtml(it.code)}" data-market="${escapeHtml(it.market)}" data-name="${escapeHtml(it.name)}">
          <div>
            <div class="nm">${escapeHtml(it.name)}</div>
            <div class="sub">${escapeHtml(it.action)} · ${escapeHtml(it.full || "")}${it.pos_note ? " · " + escapeHtml(it.pos_note) : ""}</div>
          </div>
          <div class="score-bar"><i style="width:${pct}%;background:${color}"></i></div>
          <div class="score-num" style="color:${color}">${fmtNum(it.score, 0)}</div>
        </div>`;
      })
      .join("");
    box.querySelectorAll(".score-row").forEach((row) => {
      row.addEventListener("click", () => {
        selectSymbol(row.dataset.code, row.dataset.market, row.dataset.name);
        $$(".nav-item").forEach((b) => b.classList.remove("active"));
        $('.nav-item[data-view="chart"]').classList.add("active");
        $$(".view").forEach((v) => v.classList.remove("active"));
        $("#view-chart").classList.add("active");
        loadChart();
      });
    });
  } catch (e) {
    box.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
  }
}

async function loadLive() {
  try {
    const data = await api("/api/alerts");
    renderAlerts(data.alerts || [], data.clock, data.monitor);
  } catch (e) {
    $("#liveStats").innerHTML = `<div class="stat-card"><div class="label">错误</div><div class="value" style="font-size:14px">${escapeHtml(e.message)}</div></div>`;
  }
  loadScoreBoard();
}

function startLivePolling() {
  if (liveTimer) return;
  liveTimer = setInterval(async () => {
    const active = $(".nav-item.active")?.dataset.view;
    // always refresh alerts quietly; scoreboard only when live view open
    try {
      const data = await api("/api/alerts");
      if (active === "live") {
        renderAlerts(data.alerts || [], data.clock, data.monitor);
      } else if ((data.alerts || []).length && data.clock?.is_trading) {
        // background toast for new strong alerts
        const newest = data.alerts[0];
        if (newest && (newest.ts || 0) > lastAlertTs && (newest.kind || "").includes("strong")) {
          notifyBrowser(newest.title, (newest.body || "").slice(0, 120));
          toast(newest.title || "新提醒");
          lastAlertTs = newest.ts;
        }
      }
    } catch (_) {}
  }, 20000);
}

/* ---------- Boot ---------- */
window.addEventListener("resize", () => {
  klineChart?.resize();
  compareChart?.resize();
  const alloc = echarts.getInstanceByDom($("#allocChart"));
  alloc?.resize();
});

async function boot() {
  setActiveSymbol("159516", "SZ", "159516.SZ");
  await loadPortfolio();
  loadSignalsSide();
  startLivePolling();
}

boot();
