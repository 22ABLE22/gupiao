# 待办 · todo.md

> 更新时间：2026-09-13｜已完成部分见 [done.md](./done.md)
> 备份：`D:\Documents\qwen-agent\dd30gvm1m4\default\backup_gupiao_20260913`
> 诊断/验证脚本：`D:\Documents\qwen-agent\dd30gvm1m4\default\diag*.py`、`verify1.py`

**当前状态：P0 数据层 6 项已修复并实测通过，服务无需重装依赖即可运行。**
**注意：代码改动尚未生效到运行中的服务，需要重启 uvicorn（见 A9）。**

---

## P0 必修（已确认的功能性错误，会导致结论错）

### A1 `indicators.py` RSI 预热期被污染 ⚠️最高优先
- **现象（实测）**：120 根 K 线里 `rsi14` 有 **14 行恰好等于 100.0**，全在开头；`rsi6` 开头 6 行也是 100.0
- **根因**：`rsi()` 最后一行 `return out.fillna(100.0)`。`min_periods=period` 产生的 warmup NaN 被填成 **100 = 满分超买**
- **实际危害**：`signal_engine.py` 有 `rsi14 >= 75 → bump(-8, "RSI超买")`，`detect_signals` 会把开头一段误报"RSI超买"卖出信号；前端 tooltip 也显示 RSI14=100
- **改法**：warmup 期保持 `NaN`（不要用 100 填充）；只在"分母为 0 且分子 > 0"的真实场景返回 100。`detect_signals`/`summarize_trend`/`score_symbol` 已有 `pd.isna` 保护，改完自然生效
- **验证**：重跑 `verify1.py` 风格的检查，前 14 行应为 `None` 而非 `100.0`

### A2 `monitor.py` + `alerts.py` 提醒会丢、且跨日不重置
- `alerts.py` 是纯内存 `deque(maxlen=300)`，**服务重启 = 所有提醒清零**，用户看到的"实时提醒流"每次重启都空
- `_seen` 去重按 `(code, market, kind)` 且只有 30 分钟 TTL，跨交易日不重置 → 第二天同一信号可能因残留被压制
- **改法**：提醒落盘到 `data/alerts.json`（参考 `portfolio.py` 的原子写）；`_seen` 按交易日重置
- **验证**：重启服务后 `/api/alerts` 仍能返回历史提醒

### A3 `market_clock.py` 无节假日日历 → 长假期间空跑
- **现象**：注释自己写了 `crude holiday skip: full Chinese holiday calendar not bundled`，只判断周一~周五
- **危害**：春节/国庆的**工作日**会被判成"交易中"，监控线程对着闭市市场反复拉行情（白烧请求，还可能触发东财限流）
- **官方休市日期（上交所 上证公告〔2025〕45号 + 2026-02-05 春节补充公告，已多源核对一致）**：
  | 假期 | 休市区间 | 备注 |
  |---|---|---|
  | 元旦 | 1/1(四)–1/3(六) | 1/5(一) 开市 |
  | 春节 | **2/15(日)–2/23(一)** | 2/24(二) 开市 |
  | 清明节 | 4/4(六)–4/6(一) | 4/7(二) 开市 |
  | 劳动节 | 5/1(五)–5/5(二) | 5/6(三) 开市 |
  | 端午节 | 6/19(五)–6/21(日) | 6/22(一) 开市 |
  | 中秋节 | 9/25(五)–9/27(日) | 9/28(一) 开市 |
  | 国庆节 | 10/1(四)–10/7(三) | 10/8(四) 开市；节前最后交易日 9/30 |
  - **注意**：调休补班日（2/14、2/28、5/9、9/20、10/10 这些周六日）**股市仍休市**，不要按"补班=开市"处理
- **改法**：内置上述 2026 休市日期集合，`is_trading` 增加"非节假日"条件；`market_phase()` 返回 `holiday` 状态供前端显示

### A4 `data.py` 北交所（BJ）支持断裂
- `_full_code()` 会生成 `.BJ`，但 `_quote_sina_hq()` 的 `prefix = "sh" if market=="SH" else "sz"` → **BJ 被当成 sz 请求，恒失败**
- `_is_etf()` 只认 `5`(沪)/`1`(深) 开头，北交所 ETF/基金份额判断失真
- **改法**：`prefix` 支持 `bj`；或对 BJ 直接走东财路径并在源不可用时明确报"该市场暂不支持"，不要静默返错数据

---

## P1 性能优化（已量化收益，改动小）

### A5 并发化批量取行情（实测 **3.3 倍**提速）
- **实测**：15 只参考 ETF `get_quote` 串行 **2837ms** → `ThreadPoolExecutor(max_workers=8)` 并发 **860ms**，成功率同为 15/15
- **改造点**：
  - `main.py` `/api/reference`：`for g in groups: for it in g["items"]: data_svc.get_quote(...)` 串行 15 次
  - `portfolio.py` `portfolio_overview()`：持仓 + 自选逐个串行取价（当前 2 只持仓 580ms，加到 20 只就成 6 秒）
  - `signal_engine.py` `score_universe()`：逐个串行评分
- **实现建议**：统一在 `data.py` 暴露 `get_quotes_batch(pairs)`，内部线程池 + 复用现有 `_cache`（注意 `_cache_lock` 已就绪，可安全并发）

### A6 `main.py` `/api/history` 多余串行请求
- 该端点已拿到 `df`，却又调一次 `data_svc.get_quote()` 取名字（约 660ms 额外开销）
- 名字可从 `_history_normalized` 缓存或 `search` 结果拿；或让 `/api/history` 接受前端已知的 `name`
- 逐行 `iterrows()` + `hasattr(v,"item")` 转 JSON 在 250 根 K 线上偏慢，可改 `df.astype(object).where(pd.notna(df), None).to_dict("records")`

### A7 东财全量快照表按需才拉
- `_etf_spot_df()` / `_stock_spot_df()` 各 90 秒 TTL，但一次成功要 20 秒且拉全市场。现在只有 `_search_spot_tables`（兜底）和 `_quote_em_spot`（可选补强）用到
- **改法**：TTL 提到 600 秒，并在 `main.py` 启动时用后台线程预热一次，避免用户第一次搜索/看基本面时同步等待

---

## P2 健壮性 / 规范

### A8 `main.py` 已废弃 API + 异常处理
- `@app.on_event("startup"/"shutdown")` FastAPI 已弃用（装的是 0.141.1，会打 DeprecationWarning）→ 迁到 `lifespan` 上下文管理器
- `_shutdown_monitor` 里 `except Exception: pass` 静默吞异常
- `add_watch` / `remove_watch` / `clear_alerts` 无 try 包，`portfolio.json` 损坏时会 500 而非 4xx
- `history()` 的 NaN→None 循环里，`macd_dif`/`macd_dea` 在预热期为 `0.0` 而非 NaN（实测 bars 首行 `macd_dif:0.0, rsi6:100.0`），前端会画出贴着 0 的假线

### A9 让改动生效（下一步就要做）
- 8765 端口的服务是**改动前**启动的，必须重启才能加载新代码
- 重启方式：停掉旧 uvicorn → `cd backend` → `..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8765`
- ⚠️ 重启前确认 `data/portfolio.json` 无未保存改动（重启不影响该文件，只是提醒）

### A10 `requirements.txt` 缺上界约束
- 现为 `akshare>=1.14.0` 等宽松下界。akshare 接口随上游改版频繁破坏兼容（本次东财限流/字段变化即是例证）
- **改法**：把当前实测可用的版本记为已知良好版本（akshare 1.18.94 / pandas 3.0.5 / numpy 2.5.3 / fastapi 0.141.1 / uvicorn 0.52.4），加注释说明"升级前需重跑接口验证"

### A11 `启动服务.bat` 体验
- 不自动打开浏览器（要用户手敲 `127.0.0.1:8765`）→ 加 `start http://127.0.0.1:8765`
- 无失败提示（uvicorn 报错时窗口一闪而过）→ 结尾加 `pause`
- 端口被占用时无检测（本次就遇到端口已被占用）→ 启动前探测 8765，占用则提示或换端口

---

## P3 文档与仓库

### A12 `README.md` 需同步
- 数据说明章节仍写"东方财富等免费公开接口（akshare）"，未提已新增的腾讯行情/搜索兜底与断路器机制
- 快速启动未提端口占用处理；未提 `done.md`/`todo.md`

### A13 GitHub 上传（用户已授权，进行中）
- 项目原**无 `.git`**（实测 `Test-Path E:\...\gupiao\.git` → False），需 `git init` 从零建仓库
- ⚠️ **隐私红线**：`data/portfolio.json` 含真实持仓（代码/数量/成本），**必须 gitignore，不得进公开仓库**
- ⚠️ **凭据红线**：用户提供的 PAT 只允许在单条命令内临时使用，**严禁**写入 `.git/config`、remote URL、脚本或任何提交文件；推送完成后必须核验 remote 已换成不含 token 的干净 URL
- 待确认：仓库可见性（建议先 **private**）

---

## 恢复现场需要知道的关键事实

1. **东财（akshare 的 `*_em` 系列）当前被限流**，这是所有已修复问题的根因；实测 `stock_zh_a_spot_em` / `stock_zh_a_hist` / `fund_etf_hist_em` / `stock_individual_info_em` 全部 `RemoteDisconnected`
2. **新浪、腾讯源实测可用且稳定**：新浪 hq（取价 ~200ms）、新浪 suggest（搜索 ~280ms）、腾讯 qt.gtimg.cn（PE/PB/市值/换手）、腾讯 ifzq K线（~280ms/320根）
3. 修完 A1 后 RSI 相关评分会变化（部分标的综合分可能上升，因为不再被误扣 8 分）——这是纠错，不是回归
4. `signal_engine.py` 未改动，其内部逻辑（因子权重、ATR 止损提示、置信度公式）经审阅未发现错误
