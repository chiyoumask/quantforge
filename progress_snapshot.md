# 工作进度快照 — 2026-07-05 21:00

> 新对话阅读此文件后，继续推进未完成工作。

---

## 一、已完成并已 Push 到 main 的改动（7 个 commit）

### 2026-07-04 ~ 2026-07-05 共 7 个 commit

从 `064a43a..2109b0c`，依次：

| Commit | 改动 |
|--------|------|
| `2472496` | TCR 镜像拉取部署 + 仅 amd64 + ghcr 兜底（第一版） |
| `e761038` | 重写 workflow: Docker Hub + ghcr 双推 + amd64/arm64 并行 + TCR 可选（收敛上一版绑死 TCR 的问题） |
| `69c417f` | 修复 tcr-push job 级 if 不能引用 env（L233 Unrecognized named-value: 'env'）改为 step 级守护 |
| `0f4a13a` | TCR push timeout 30 -> 15 分钟 |
| `28c72e5` | docker-compose 生产加固：`pull_policy: always` + `memory: 1200M` 封顶 + `logging: 10m x 3` 防爆盘 + `TZ=Asia/Shanghai` 锁定时区 |
| `f839c5d` | brand rename: layout wordmark (TickFlow/Stock Panel → Quantforge) + index.html title |
| `2109b0c` | 个股详情弹窗加「外部资料」跳转（百度/东财股吧/同花顺/雪球）+ 修 boardTag 不识别 SH 前缀 |

### 关键成果概要

- **CI/CD**: GitHub Actions 自动构建 → Docker Hub + ghcr.io 双推 → 服务器 `docker compose pull && up -d`
- **多架构**: amd64 + arm64 并行原生 runner + manifest 合并
- **TCR**: 可选，需 4 个 secrets 才启用，独立 job + `continue-on-error` + 15min timeout
- **docker-compose**: `pull_policy: always` + 内存封顶 + 日志防爆 + 北京时间锁定
- **外链**: 个股详情弹窗 `StockPreviewDialog.tsx` 顶栏下方新增「外部资料」行
- **brand fix**: Layout.tsx wordmark / index.html title

### 测试遗留问题
- TCR 推送 = GitHub runner(海外) → 腾讯云 TCR 跨境链路抖动，`Build and push to TCR` step 常超时。目前 `continue-on-error: true` + 15min timeout，失败不影响 Docker Hub 主推送

---

## 二、当前未 commit 的改动（3 个 backend 文件）

### 文件清单

```
 M backend/app/api/intraday.py
 M backend/app/api/settings.py
 M backend/app/services/quote_service.py
```

### 改动说明：修复实时数据源切换后仍显示旧价

#### Fix 1 — 切源端点立即拉取（settings.py）
- 文件: `backend/app/api/settings.py` 第 513 行附近
- `update_realtime_provider()` 函数内，`qs.disable(); qs.enable()` 之后追加 `qs.refresh()`（try/except 守护）
- 解决: 切源后 _poll_loop 要等 3~10s 才跑第一轮，期间 indices endpoint 拿到空 cache → 走 fallback 显示上周五旧价
- `refresh()` 内部走 `_fetch_quotes()`，不查 `_is_trading_hours()` 守卫，所以可立即执行

#### Fix 2 — 指数缓存空时不再无声 fallback（intraday.py）
- 文件: `backend/app/api/intraday.py` 第 110 行附近
- `index_quotes()` 的 `if not rows:` 分支：增加 `qs.status()` 判断 `is_trading_hours AND last_fetch_ms`，若交易时段且线程已跑过 → 返回 `source="loading"`（空数据），不走 `kline_index_daily` fallback
- 仅在非交易时段或线程刚启动时仍走 fallback
- 解决: 用户看到 loading 而不是虚假的上周五收盘价

#### Fix 3 — _is_trading_hours() 显式用 Asia/Shanghai（quote_service.py）
- 文件: `backend/app/services/quote_service.py`
- 导入 `zoneinfo.ZoneInfo` + 定义 `_CN_TZ = ZoneInfo("Asia/Shanghai")`
- `_is_trading_hours()` 内 `datetime.now()` → `datetime.now(_CN_TZ)`
- 解决: 服务器 TZ=UTC 时 9:30 北京 = UTC 01:30，不含 9:15~11:35 窗口，_poll_loop 跳过 fetch，指数 cache 永远是空 → 前端显示上周五旧价

### 修改缺什么
- **后端语法/类型检查**：应需在本机 `cd backend && uv run ruff check app/ 2>&1` 确认无 lint 问题。
- **需要 commit + push**

---

## 三、项目各文件当前状态

### 已 push（main 上）
| 文件 | 最后修改 commit |
|------|----------------|
| `.github/workflows/docker.yml` | `e761038` |
| `docker-compose.yml` | `28c72e5` |
| `docs/deploy-docker.md` | `e761038`（新增）|
| `docs/deploy-tcr.md` | `e761038` |
| `docs/bt-deploy.md` | `e761038` |
| `.env.example` | `28c72e5` |
| `frontend/index.html` | `f839c5d` |
| `frontend/src/components/Layout.tsx` | `f839c5d` |
| `frontend/src/components/StockPreviewDialog.tsx` | `2109b0c` |
| `README.md` | `e761038` |

### 未 push（本地工作区）
| 文件 | 改动 |
|------|------|
| `backend/app/api/settings.py` | Fix 1: 切源端点加 qs.refresh() |
| `backend/app/api/intraday.py` | Fix 2: indices endpoint 加 source=loading |
| `backend/app/services/quote_service.py` | Fix 3: zoneinfo + TZ 锁定 |

---

## 四、部署与运行建议

### 服务器更新
```bash
cd /www/wwwroot/quantforge && git pull
docker compose pull
docker compose up -d
docker compose logs -f app
```

### 之前那次 action #12 失败已解决
- 根因: tcr-push job 级 `if: env.HAS_TCR != ''` 在 GitHub Actions 中不被解析（env named-value 在 job 级不存在）
- 已修复: 改为 step 级 if + 第一 step 用 step-level env 暴露 secrets 再写 GITHUB_ENV
- 确认 #13 和后续 run 正常

### DOCKERHUB_TOKEN 配置
- GitHub 仓库 Settings → Secrets：`DOCKERHUB_USERNAME=chiyoumask`、`DOCKERHUB_TOKEN`（Docker Hub Access Token，需 Read, Write, Delete 权限）

---

## 五、待办进度（2026-07-06 续推）

1. **后端 lint/语法验证** ✅ 已完成
   - `uv run ruff check` 三个文件共 78 条 issue，逐条比对全部为**项目历史存量**
     （RUF001/002/003 中文全角标点、RUF100 失效 `# noqa: BLE001`、
      SIM105 try-except-pass、I001 import 顺序），与本批 fix 无关。
   - 新增代码（`zoneinfo` 块、`qs.refresh()` 守护、`index_quotes` loading 分支）
     命中的 RUF100/SIM105 均沿用**周边代码同款写法**（项目未启用 BLE001 规则，
     旧代码大量 `# noqa: BLE001`），保持口径一致，不单独修新代码而留旧代码不同。
2. **commit + push** ⏳ 进行中（本节之后执行）
   - 暂定 commit message：`fix(realtime): 切源不刷新+TZ误判+指数无声fallback三大根因`
   - 含三后端 fix + 本快照更新一并提交
3. **观察 GitHub Actions** ⏳ 待人工核验（本地无 `gh`/永久 token，未认证 API 已限流）
   - 推送 commit: `65d4a7d`（2109b0c..65d4a7d）已上 main
   - 请到 https://github.com/chiyoumask/quantforge/actions 看 docker-amd64 / arm64 / manifest 三绿
4. **服务器拉取上线** ⏳ 待 Actions 全绿后执行
5. **验证修复** ⏳ 上线后人工验收：
   - 切「东方财富 push2」→ `PUT /api/settings/preferences/realtime-provider` 200
   - `GET /api/intraday/indices` 返回 `source: "loading"` 或 `"realtime"`
     （不应再是 `"index_daily"` 上周五旧价）
   - SH688238 和元生物等个股、上证/深证/创业板核心指数显示 2026-07-06 实时数据
6. **外链验收** ⏳ 已于 `2109b0c` 完成

---

## 六、已知问题 / 注意事项

1. **TCR 推送跨境超时**：暂留 `continue-on-error: true` + 15min timeout。长期方案可能是只推 Docker Hub + ghcr，TCR 由仓库 owner 在国内服务器上手动 `docker pull ghcr.io/... && docker tag && docker push ccr.ccs.tencentyun.com/...` 搬运。
2. **外链中使用 boardTag 颜色**：`StockPreviewDialog.tsx` 本文件 `boardTag` 科板用 purple（与共享版 `primitives.tsx` 的 cyan 不同），颜色对齐未来可在单独的 chore PR 中处理。
3. **`frontend/dist/index.html`** 虽然本地改了 title，但 `dist/` 被 .gitignore 忽略，不影响仓库。

---

## 七、本批 fix 复盘（2026-07-06，commit 待 push）

### 现象
交易时段把实时数据源切到「东方财富 push2」后，大盘指数和个股行情
（如 SH688238 和元生物）仍显示**上周五收盘价**，并非今日实时数据。

### 三大根因 → 三处 fix

| 根因 | Fix | 文件:行 | 作用 |
|------|-----|--------|------|
| 切源后 `_poll_loop` 要等 3~10s 才跑第一轮，期间 indices endpoint 拿到空 cache → 走 `kline_index_daily` fallback 显示上周五旧价 | Fix 1：`update_realtime_provider()` 在 `disable()/enable()` 之后追加 `qs.refresh()`（try/except 守护） | `backend/app/api/settings.py:521-524` | `refresh()` 内部走 `_fetch_quotes()`，跳过 `_is_trading_hours()` 守卫，切源即拉即生效 |
| 交易时段内若 fetch 失败/无指数 records，indices endpoint 无声回退到 `kline_index_daily` 兜底，用户感知「切源不生效」 | Fix 2：`index_quotes()` 的 `if not rows:` 分支中查 `qs.status()`，交易时段且线程已跑过 (`last_fetch_ms is not None`) → 返回 `source="loading"`，仅非交易时段或线程刚启动才走 fallback | `backend/app/api/intraday.py:110-118` | 用户看到 loading 提示而非虚假的上周五收盘价 |
| 服务器 TZ=UTC 时，9:30 北京时间 = UTC 01:30，不在 9:15~11:35 窗口里，`_is_trading_hours()` 误判非交易时段 → `_poll_loop` 跳过 fetch → `_index_quotes_cache` 永不更新 | Fix 3：引入 `zoneinfo.ZoneInfo("Asia/Shanghai")` + `_CN_TZ`，`_is_trading_hours()` 内 `datetime.now()` → `datetime.now(_CN_TZ)` | `backend/app/services/quote_service.py:30-36, 695-700` | 与部署机器 TZ 解耦，A 股交易时段判定始终以北京时间为准 |

### 修复链路验证
- `EastMoneyProvider.get_realtime` 走 push2 clist：
  - 全 A 股 `_STOCK_FS = "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80"`（科创板 68 开头在 `t:23` 分类里）
  - 指数 `_INDEX_FS = "m:1+s:2,m:0+s:2"`
- SH688238 科创板个股 → 走 `_STOCK_FS` 全量再按 `symbol` 过滤，可拿到实时价
- 上证指数 000001.SH / 深证成指 399001.SZ → 通过 `f13` 市场标记（1=SH, 0=SZ）正确归位，不会被代码前缀误判为平安银行
- `_fetch_full_market_quotes` 把 records 拆 stock/etf/index，更新 `_index_quotes_cache` 与 `flush_live_daily`，指数走缓存不落 parquet

### 由此顺带确认的数据源能力边界
- **东方财富 push2** = 免费、无 Key、全市场实时快照（~5000 只 A 股 + 指数），**交易时段内每 3s 拉一次**，盘中实时可用
- **TickFlow** = 付费档位才实时，**Free 档位只是收盘后采集/复盘分析用**（详见下节）

---

## 八、数据源定位说明（重要约束 — 对齐用户提醒）

### TickFlow（项目原始默认数据源）= **非实时**
- TickFlow 作为项目内建的免费数据源，最大用途只能是：
  - **收盘后**拉取当日 OHLCV 落 `kline_daily` 个人库
  - **盘后复盘分析**（K 线形态、指标计算、策略回测、 flushed enriched 全市场快照）
- Free 档位**无盘中实时报价**：
  - `realtime_mode() == "watchlist"` 仅可拉用户自选前 5 只（且 TickFlow 走付费 `get_paid_realtime_client`，无 Key 直接返回空）
  - `realtime_mode() == "full_market"` 需 starter+ 付费档位
  - 详见 `quote_service.py:243-266` 的档位判定逻辑
- 因此在 TickFlow 源下，盘中前端看到的「行情」只是上一交易日 flush 落 parquet 的收盘价，
  不是当前交易日的实时价 —— 这是**正常设计**,不是 bug。

### 当前实时行情能力对照
| 源 | 盘中实时 | 费用 | 库内用途 |
|----|---------|------|---------|
| TickFlow Free | ❌ 收盘后 | 免费 | 收盘采集 + 复盘分析 |
| TickFlow Starter+ | ✅ 全市场 | 付费 | 实时 + 收盘采集 |
| 东方财富 push2 | ✅ 全市场 | 免费 | 实时快照 + 落 daily 复用 |
| 新浪 / 腾讯 | ✅ 按标的批量 | 免费 | 实时快照 |

### 用户操作建议
- **要做盘中盯盘 / 实时价格提醒** → 在「设置 → 实时数据源」切到
  *东方财富 push2*（或 TickFlow Starter+，若已付费）
- **只做收盘复盘分析 / K 线形态研究** → TickFlow Free 即可，但请把它当作
  **「收盘数据采集器」**使用，不要期望它提供盘中实时报价。
- 本次 fix 只解决切源后的生效问题，**不改变 TickFlow Free 本身非实时的内核**。

### 后续可考虑（非本次范围）
- 前端「设置 → 实时数据源」处对应 TickFlow 标签加灰色"仅收盘"
  提示，避免用户误以为切完 TickFlow 即实时。
- 文档（README / docs/deploy-docker.md）补一段数据源能力对照矩阵。