# 待办 · todo.md

> 更新时间：2026-09-14（本轮源码复盘后重写）
> 已完成明细见 [done.md](./done.md)
> 远程仓库：https://github.com/22ABLE22/gupiao （private）
> 本地路径：`E:\Users\Admin\github\gupiao`

---

## 当前基线（源码已核对）

| 层 | 状态 | 说明 |
|---|---|---|
| 数据层 `data.py` | 可用 | 新浪/腾讯主源 + 东财断路器；搜索、批量取价、缓存治理已完成 |
| 日历 `market_clock.py` | 可用 | 2026 官方休市已内置；`is_holiday` 生效 |
| 指标 `indicators.py` | 可用 | RSI 预热 NaN 已修；MA/MACD/BOLL/信号检测正常 |
| 评分 `signal_engine.py` | 可用 | 多因子 0–100 + 观察价位 |
| 监控 `monitor.py` / 提醒 `alerts.py` | 可用 | 开市轮询；alerts 落盘 + 跨日去重 |
| 持仓 `portfolio.py` | 可用 | 原子写、批量报价、本地 `portfolio.json`（已 gitignore） |
| 后端入口 `main.py` | 可用 | lifespan 启动监控；约 21 条路由 |
| 前端 | 可用 | 6 页：总览/实时/K线/基本面/对比/稳健参考；浅色主题 |
| 部署 | 可用 | `启动服务.bat` 端口检测 + 自动开浏览器 |
| 仓库 | 已推送 | master 与 origin 同步；无私密持仓文件 |

**结论：基础功能闭环成立，可以进入第二轮「体验与专业度」改进，而不是继续修崩溃级 bug。**

---

## P0 · 必须先做（环境/安全，无代码也可先处理）

- [ ] **轮换 GitHub PAT**  
  令牌曾再次出现在对话中。请到 GitHub → Settings → Developer settings →  
  **撤销 classic token**，改发 fine-grained（仅 `22ABLE22/gupiao`，Contents: Read & Write）。  
  若 Windows 凭据管理器里缓存了旧 token（控制面板 → 凭据管理器 → `github.com`），一并清除后再用新 token。
- [ ] **确认 8765 跑的是最新代码**  
  关掉旧 uvicorn 窗口 → 双击 `启动服务.bat`。改代码后必须重启（未开 `--reload`）。
- [ ] **工作日开盘实测监控一次**  
  周一 09:30 后打开「实时提醒」→ 开启系统通知 → 观察扫描计数与提醒流是否正常写入。

---

## P1 · 下一轮功能改进（建议按此顺序做）

### 1. 行情与分析深度
- [ ] K 线页增加 **MACD 子图**（DIF/DEA/柱，红涨绿跌）
- [ ] K 线增加 **KDJ** 或 **成交量均线**（可选开关）
- [ ] 分时图（开市日：当日 1 分钟/5 分钟线；数据源需再选型）
- [ ] 信号历史回看：把近 N 日金叉/死叉标注画在 K 线上（ECharts markPoint）

### 2. 实时提醒专业化
- [ ] **价格位提醒**：对持仓/自选设「跌破止损观察价 / 触及目标观察价」推送
- [ ] 提醒等级可配置（只推 strong / 全部 / 静音）
- [ ] 提醒音效（可关）
- [ ] `alerts.json` 定期截断/归档（当前仅保留最近 200 条，长期可再分日文件）
- [ ] 开市时段前端轮询加快到 10–15s（后台扫描仍 45s，避免打爆接口）

### 3. 持仓与组合
- [ ] **交易流水**（买卖/加减仓记录）：现在只有「当前持仓」，没有历史成交
- [ ] 持仓导入/导出 CSV
- [ ] 组合层面：行业/类型占比图（债/货基/宽基/成长）
- [ ] 编辑持仓（目前删除后重加，缺 PATCH 入口的前端编辑）

### 4. 离线与部署
- [ ] **ECharts 本地化**（下载到 `frontend/vendor/`，断网可画图）
- [ ] 可选：打包为单机版（仍以网页为主，桌面壳后置）

### 5. 数据源稳健性
- [ ] 东财限流恢复后，回验 **北交所 BJ** 行情与搜索
- [ ] 基本面字段在腾讯源上的单位/口径再抽查 3–5 只票
- [ ] 2027 休市安排公布后补录 `market_clock.py` 的 `HOLIDAYS`

---

## P2 · 更远期（可选，依赖 P1 完成度）

- [ ] 简单回测页：近 1 年「按综合分阈值」的历史胜率/最大回撤（教学用，非实盘）
- [ ] 接 Qlib / FinRL 做因子研究（需另装环境；RTX 4060 8GB 可跑小模型）
- [ ] 新闻/公告情绪辅助（FinBERT 或本地 LLM；需自备新闻源）
- [ ] 深色/浅色主题切换
- [ ] 移动端布局细调

---

## 恢复现场关键事实

1. 虚拟环境：`E:\Users\Admin\github\gupiao\.venv\Scripts\python.exe`
2. 服务：`http://127.0.0.1:8765`；改后端后必须重启 uvicorn
3. 本机 Watt Toolkit 会拦 GitHub HTTPS，仓库已配 `http.sslBackend=schannel`（不要关 SSL 校验）
4. 东财 `*_em` 曾被限流；断路器会跳过，恢复后自动再用
5. 真实持仓只在本地 `data/portfolio.json`，已 gitignore，勿提交
6. 备份基线目录（若仍存在）：`D:\Documents\qwen-agent\dd30gvm1m4\default\backup_gupiao_20260913`
