# 待办 · todo.md

> 更新时间：2026-09-14（千问中断后续：P1 部分落地）
> 已完成明细见 [done.md](./done.md)
> 远程仓库：https://github.com/22ABLE22/gupiao （private）
> 本地路径：`E:\Users\Admin\github\gupiao`

---

## 当前基线

| 层 | 状态 | 说明 |
|---|---|---|
| 数据层 | 可用 | 新浪/腾讯 + 东财断路器；**分时分钟线**已接入（`/api/intraday`） |
| 日历 | 可用 | 2026 官方休市 |
| 指标/评分 | 可用 | MA/MACD/RSI/BOLL + 综合分 |
| 监控/提醒 | 可用 | 开市轮询；**持仓止损/目标提醒线**已接入 |
| 持仓 | 可用 | 支持 `stop_line` / `take_line`；批量报价 |
| 前端 | 可用 | 6 页 + **分时切换** + **MACD 子图** + **K线信号标注** + **设线编辑** |
| 离线 | 可用 | ECharts 已本地化 `frontend/vendor/echarts.min.js`（失败仍回退 CDN） |
| 部署 | 可用 | `启动服务.bat` |

**P1 已完成项（本轮接续千问）：** MACD 子图、分时图、信号 markPoint、价格提醒线（前后端）、ECharts 本地化。

---

## P0 · 环境/安全

- [ ] **轮换 GitHub PAT**（令牌曾出现在对话中；撤销 classic，改 fine-grained 只授权本仓库）
- [ ] 工作日 09:30 实测「实时提醒」+ 系统通知 + 价格线推送
- [ ] 改代码后重启 8765（`启动服务.bat`，无 `--reload`）

---

## P1 剩余（下一波）

### 提醒体验
- [ ] 提醒等级可配置（只推 strong / 全部 / 静音）
- [ ] 提醒音效（可关）
- [ ] 开市前端轮询加快到 10–15s（后台扫描仍 45s）
- [ ] `alerts.json` 按日归档/清理策略

### 行情深化
- [ ] 分时：1/5/15 分钟档切换 UI（后端已支持 scale）
- [ ] KDJ 或成交量均线开关
- [ ] 信号列表可点击跳转到 K 线对应日期

### 持仓与组合
- [ ] **交易流水**（买卖历史，不只是当前持仓）
- [ ] 持仓 CSV 导入/导出
- [ ] 组合类型占比（债/货基/宽基/成长）辅助分类

### 数据稳健性
- [ ] 东财恢复后回验北交所 BJ
- [ ] 2027 休市公告发布后补录 `HOLIDAYS`

---

## P2 · 远期

- [ ] 教学向回测页（综合分阈值历史表现）
- [ ] Qlib / FinRL / 本地情绪模型（RTX 4060）
- [ ] 主题切换、移动端细调、桌面壳

---

## 恢复现场关键事实

1. 虚拟环境：`E:\Users\Admin\github\gupiao\.venv\Scripts\python.exe`
2. 服务：`http://127.0.0.1:8765`；改后端必须重启
3. Watt Toolkit 拦 GitHub HTTPS → 仓库已配 `http.sslBackend=schannel`
4. 真实持仓仅本地 `data/portfolio.json`（gitignore）
5. 分时源：新浪 `getKLineData`，缓存 60s；均价 = 累计额/累计量
