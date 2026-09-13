# 待办 · todo.md

> 更新时间：2026-09-14｜已完成明细见 [done.md](./done.md)
> 远程仓库：https://github.com/22ABLE22/gupiao （private）
> 本地备份（改动前基线）：`D:\Documents\qwen-agent\dd30gvm1m4\default\backup_gupiao_20260913`

## 当前状态：P0/P1/P2/P3 全部完成并验证，代码已推送

- [x] 搜索失效（东财限流恒空）→ 新浪 suggest，<400ms
- [x] 基本面 PE/PB/市值/换手率全空 → 腾讯 qt 补齐
- [x] 首屏 23 秒 → 缓存新鲜度修正，0.6 秒
- [x] 缓存键不一致重复拉取 → 归一化 + 天数档位
- [x] 空结果被缓存 180 秒 / 缓存无上限 → skip_empty + 上限清理
- [x] 东财无降级白等超时 → CircuitBreaker
- [x] 腾讯 K线 volume 单位、amount 伪造 → 已校正
- [x] RSI 预热期 fillna(100) 误判超买 → 保持 NaN（假超买行 14→0）
- [x] 2026 官方休市日历 → 内置，26 项断言通过
- [x] 提醒重启丢失 / 跨日去重不重置 → 落盘 alerts.json + 按日失效
- [x] 北交所前缀硬编码 3 处 → 统一 _exch_prefix + BJ 代码段
- [x] 并发批量取价 → 实测 3.8x（7435ms→1932ms）
- [x] /api/history 逐行 iterrows → 向量化转换（并修复 500 事故）
- [x] FastAPI on_event 弃用 → lifespan
- [x] 快照表 TTL 90→600s；requirements 固定已知良好版本
- [x] 启动服务.bat 端口检测 + 自动开浏览器 + 报错 pause
- [x] 持仓表述脱敏（README/页面/清单标签）
- [x] GitHub 私有仓库创建 + 推送 + 远程核验无敏感文件
- [x] SSL 根因定位（Watt Toolkit 自签）→ 仓库级 schannel，未关校验

## 遗留（需要用户参与或低优先）

- [ ] **重启 8765 服务**：当前运行中的旧服务（用户手动启动）未加载新代码；
      关闭旧窗口后双击 `启动服务.bat` 即可。验证实例曾在 8766 端到端通过。
- [ ] **撤销 GitHub PAT**：令牌曾出现在对话中；且推送过程可能已把凭据缓存进
      Windows 凭据管理器（控制面板 → 凭据管理器 → Windows 凭据 → github.com），
      撤销旧 token 后该缓存即失效。建议重新生成 fine-grained token（只给该仓库 Contents:RW）。
- [ ] 2027 年休市安排公布后补录 `market_clock.py` 的 HOLIDAYS
- [ ] 北交所行情：代码路径已正确，但新浪/腾讯实测不覆盖 BJ 数据，
      需东财解除限流后回验（断路器会自动重试）
- [ ] 可选增强：K线页加 MACD 子图；alerts 文件定期截断；ECharts 本地化
      （现为 CDN 引用，断网时图表不渲染）

## 恢复现场关键事实

1. 根因环境：本机 **Watt Toolkit(SteamTools) 拦截加速 GitHub**，Git 需 `http.sslBackend=schannel`（已写入本仓库局部配置）；GitHub API/推送均正常
2. 东财 *_em 系列接口在诊断时段被限流（RemoteDisconnected），修复设计以此为准；恢复后行为只会更好
3. 验证方式：`E:\...\gupiao\.venv\Scripts\python.exe` 起 uvicorn 于 8766 端口 + HTTP 实测；诊断/验证脚本在 `D:\Documents\qwen-agent\dd30gvm1m4\default\`（diag*.py / verify*.py）
4. 修改代码后必须重启 uvicorn 才生效（无 --reload）
