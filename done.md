# 进度记录 · done.md

> 更新时间：2026-09-13（Asia/Shanghai）
> 项目路径：`E:\Users\Admin\github\gupiao`
> 改动前完整备份：`D:\Documents\qwen-agent\dd30gvm1m4\default\backup_gupiao_20260913`（22 个文件，可整体回滚）

---

## 1. 项目盘点结果

技术栈：FastAPI + akshare + pandas 后端，原生 HTML/CSS/JS + ECharts 5.5（CDN）前端。

```
backend/main.py            FastAPI 入口，26 个路由
backend/services/
  data.py            ★已改  行情源（新浪/东财/腾讯）+ 缓存 + 断路器
  indicators.py      ☆待改  MA/MACD/RSI/BOLL 与信号识别
  signal_engine.py          多因子综合评分（0-100）
  portfolio.py       ☆待改  持仓读写与盈亏计算
  monitor.py                开市轮询线程（45s）
  alerts.py          ☆待改  提醒（仅内存，重启即丢）
  market_clock.py    ☆待改  交易时段判断（无节假日日历）
  reference.py              科普 ETF 清单（15 只）
frontend/index.html / js/app.js / css/app.css
data/portfolio.json         持仓持久化
```

运行环境（已实测确认，无需重装）：
- 虚拟环境 `E:\Users\Admin\github\gupiao\.venv\Scripts\python.exe`
- Python 3.12.9 / akshare 1.18.94 / pandas 3.0.5 / numpy 2.5.3 / fastapi 0.141.1 / uvicorn 0.52.4
- 服务已在 `127.0.0.1:8765` 运行中（端口占用已确认）

---

## 2. 可用性检查结论：**能用，但 3 个功能实质已坏**

全部接口 HTTP 200，但存在「返回正常却给错数据 / 慢到不可用」的问题。

| 接口 | 结果 | 实测数据 |
|---|---|---|
| `/api/health` | ✅ 正常 | 208ms |
| `/` 首页 | ✅ 正常 | 14ms |
| `/api/market/clock` | ✅ 正常 | 12ms，周日正确判休市 |
| `/api/history` | ✅ 正常 | 719ms |
| `/api/signals` | ✅ 正常 | 237ms |
| `/api/signals/pro` | ✅ 正常 | 984ms |
| `/api/monitor` | ✅ 正常 | 12ms，线程存活、扫描计数在涨 |
| `/api/portfolio` | ⚠️ **首屏 21~23 秒** | 慢到基本不可用 |
| `/api/fundamentals` | ❌ **PE/PB/市值/换手率全 null** | 贵州茅台返回 12 项但核心指标皆空 |
| `/api/search` | ❌ **完全搜不到任何东西** | 搜"茅台"耗时 25.4 秒返回 `[]` |

根因（诊断复现，非猜测）：**东方财富接口被限流**
```
ak.stock_zh_a_spot_em()      → ConnectionError: RemoteDisconnected   (5.9s)
ak.stock_zh_a_hist()         → ConnectionError: RemoteDisconnected   (230ms)
ak.fund_etf_hist_em()        → ConnectionError: RemoteDisconnected   (230ms)
ak.stock_individual_info_em()→ ConnectionError: RemoteDisconnected   (249ms)
ak.fund_etf_spot_em()        → 20.5 秒才返回（即使成功也慢到不能用）
```
代码里所有回退链都在这条断链上白等，且没有降级机制。

---

## 3. 已修复并验证的 6 项（全部在 `backend/services/data.py`）

### ① 搜索功能失效 → 已修复
- **原因**：`search()` 只依赖东财全量快照表（`fund_etf_spot_em` 20 秒 / `stock_zh_a_spot_em` 直接被拒），表挂 = 搜索恒返回空。
- **改法**：主用新浪 `suggest3.sinajs.cn` 单标的建议接口（实测 250ms、不受东财限流影响），东财表降为「仅在缓存新鲜时才用」的兜底；纯 6 位数字代码额外走行情直查。返回结构完全不变，前端零改动。
- **验证**：
  ```
  search('茅台')     380ms → 600519.SH 贵州茅台
  search('159516')   276ms → 159516.SZ 半导体设备ETF国泰
  search('国债ETF')  254ms → 511010 / 511020 等 3 条
  search('宁德时代') 319ms → 300750.SZ 宁德时代
  search('沪深300')  292ms → 000300 / 160706 / 560180
  ```
  （25.4 秒返回空 → 平均 0.3 秒命中）

### ② 基本面 PE/PB/市值/换手率全空 → 已修复
- **原因**：这些字段只从东财快照表取，东财一限流就全 null；新浪 hq 接口本身不返回这些字段。
- **改法**：新增 `_quote_tencent()`，用腾讯 `qt.gtimg.cn` 单标的接口补齐（实测稳定返回，且不受限流）。字段含义经比对确认：`[39]PE [46]PB [45]总市值(亿) [44]流通市值(亿) [38]换手率`，并对市值做 亿→元 换算以适配原有 `_fmt_mv`。
- **验证**：
  ```
  600519 茅台  → PE=19.57  PB=6.34  总市值=1.59 万亿  换手=0.28
  000001 平安  → PE=5.24   PB=0.49  总市值=2278.25 亿 换手=0.43
  ```

### ③ 冷启动触发 20 秒全量快照 → 已修复
- **原因**：`get_quote()` 里判断"缓存是否已预热"用的是 `any(k.startswith(prefix) for k in _cache)` —— **只查键存在、不查是否过期**。快照表缓存过期后仍被判为可用，于是每次都去重拉 20 秒的全量表。这是 `/api/portfolio` 首屏 23 秒的直接原因。
- **改法**：新增 `cache_fresh()`，严格按 TTL 判断新鲜度。
- **验证**：`get_quote` 冷启动 667~688ms（原 20 秒级）。

### ④ 同一标的被重复拉取 → 已修复
- **原因**：`@_cached("hist")` 的 key 用的是**原始入参** `repr((args, kwargs))`，所以 `get_history("159516","SZ")` 与 `get_history("159516.SZ")` 生成两个不同 key，同一份 K 线拉两次（前端切周期时反复发生）。
- **改法**：把归一化提到缓存层之外 —— 新增 `_history_normalized(code, market, days, adjust)` 收标准入参，公开 `get_history()` 先 `parse_symbol(_full_code(...))` 再调用；同时引入 `days` 档位对齐（60/120/250/500），前端切 120↔250 可复用同一份缓存再截断。
- **验证**：3 种不同写法调用后 hist 缓存键数 = 2（正好两档，不再膨胀）。

### ⑤ 失败结果被缓存 180 秒 → 已修复
- **原因**：装饰器无条件写缓存，东财失败产生的空 DataFrame 会被缓存 180 秒 —— 期间该标的恒显示"无历史数据"，即使换源本可成功。
- **改法**：`_cached(..., skip_empty=True)`，空表/空列表不入缓存；另加 `_prune_cache()` 与 `_CACHE_MAX_ENTRIES=512` 上限，修掉原缓存**只增不删**的内存泄漏。

### ⑥ 东财每次调用都白等超时 → 已修复（断路器）
- **改法**：新增 `CircuitBreaker` 类（连续失败 N 次→冷却期内直接跳过该源），对 `eastmoney` 生效（阈值 2 次、冷却 120 秒），覆盖快照表与 K 线两条路径。带 `status()` 可观测。
- **验证**：断路器打开后连续 3 次 `get_history(600519)` 耗时 1173ms / 0ms / 0ms，全程不再尝试东财。

### 附带修掉的一个数据错误
`_fetch_hist_tencent()` 原有两处 bug（会在东财+新浪同时失效时污染 K 线与量能因子）：
- `volume` 未做单位换算：腾讯返回**手**，新浪/东财返回**股**，相差 100 倍 → 量能因子直接失真
- `amount` 被写成 `float(b[5])`，即把成交量当成交额（自造数据）
- **改法**：`volume × 100` 对齐单位；`amount` 置 0 并注明该接口不提供，不再伪造。
- **验证**：修复后 tencent volume=4,276,900,300 vs sina volume=4,276,900,282，比值 1.00 ✅

---

## 4. 其他确认过没问题的部分

- 持仓读写：`data/portfolio.json` 原子写入（临时文件 + `replace`）、加仓自动摊薄成本，逻辑正确
- 监控系统：线程存活，`scans` 在累积，休市时段正确降频，不浪费请求
- 因子引擎：MA/MACD/BOLL/量能计算正确
- 前端：无 null 崩溃、无 XSS（有 `escapeHtml`）、事件绑定正常、图表切换正常
- 依赖：虚拟环境完好，无需重新安装

## 5. 待办见 todo.md
