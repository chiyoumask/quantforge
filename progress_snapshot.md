# 工作进度快照 — 2026-07-07 10:00 (迁移版)

> 📂 **工作区迁移通知**: 本仓库将从
>   `C:\Users\Administrator\Desktop\tickflow-stock-panel`
>   迁移到 `E:\3.Github\quantforge` 作为新的正式本地工程目录。
>   `tickflow-stock-panel` 目录将废弃。新对话请在新目录工作。
>
> 📌 本快照已随仓库提交 (commit `53f997a` + 后续),迁移后 `git pull` 即可
>   拿到此文件。新对话打开此文件继续推进未完成事项。

---

## 〇、迁移核对清单 (新对话先看)

### Git 历史一致性 ✅
- 旧目录 `tickflow-stock-panel` HEAD = `origin/main` = `53f997adfefb9ac46aedc5f0cc0f0fb9d5cee6fa`
- 工作区干净,无未提交改动,无未追踪文件
- **本地与远端完全同步,迁移 git 层面无需任何操作** — 直接在新目录 `git clone https://github.com/chiyoumask/quantforge` 即可拿到完整历史

### .gitignore 排除的本地资产 (需手工拷贝或重建)
| 资产 | 旧路径 | 大小 | 是否需要迁移 | 处理方式 |
|------|--------|------|--------------|---------|
| Python venv | `backend/.venv/` | 438M | ❌ 不要拷贝 | 新目录 `cd backend && uv sync` 重建 |
| Node 依赖 | `frontend/node_modules/` | 192M | ❌ 不要拷贝 | 新目录 `cd frontend && pnpm install` 重建 |
| 前端构建产物 | `frontend/dist/` | 2.8M | ❌ 不要拷贝 | 被忽略,新目录 `pnpm build` 重建 |
| 行情/复盘数据 | `data/` | 22K | ⚠️ 选择性 | 本地这台机器基本是空的(仅 capabilities.json + ext_data 8KB),无 parquet 行情历史。新目录首次启动会重建 capabilities,行情历史可从服务器 `data/` 目录 scp 过来或重新刷新 |
| `.env` | 项目根 | - | ⚠️ **从未在本地存在** | 旧目录就只有 `.env.example`,本机所有密钥(TickFlow/AI/Admin 密码)走服务器 docker env,本地开发时按需 `cp .env.example .env` 自填 |
| `tiers.yaml` | 项目根 | 4K | ✅ 已纳入 git | 随 clone 自动到 |
| `progress_snapshot.md` | 项目根 | - | ✅ 已纳入 git | 随 clone 自动到 (本文件) |

### 不在 git 但需关注的项目根文件
- `dev.sh` / `dev.ps1` — 开发启动脚本,在 git 里 ✅
- `screenshots/` — 截图目录,在 git 里 ✅
- `packaging/` — Windows 安装包打包资源 (.iss / .ico / icon 生成脚本),在 git 里 ✅

### 迁移操作步骤 (建议新对话执行)
```bash
# 1. 在新位置 clone (推荐方式, 保证 git 历史完整)
cd E:\3.Github
git clone https://github.com/chiyoumask/quantforge
cd quantforge

# 2. 重建 Python 环境
cd backend
uv sync             # 自动建 .venv + 装依赖

# 3. 重建前端环境
cd ../frontend
pnpm install        # 装依赖

# 4. 本地开发启动 (任选)
#    Linux/Mac:       ./dev.sh
#    Windows Git Bash: bash dev.sh
#    Windows PS:      ./dev.ps1

# 5. (可选) 拷贝旧目录的 data/ 历史数据 — 本机基本为空, 可跳过
#    如确需: cp -r C:\Users\Administrator\Desktop\tickflow-stock-panel\data\* E:\3.Github\quantforge\data\

# 6. (可选) 本地 .env: cp .env.example .env 然后填 TickFlow/AI Key
```

### 注意: 旧目录可保留作兜底
迁移期间不要立刻删 `tickflow-stock-panel` 目录, 等新目录验证可启动
(`pnpm build` 通 + `dev.sh` 起来) 再清理, 防意外丢东西。

---

## 一、已完成并已 Push 到 main 的改动

### 2026-07-04 ~ 2026-07-05 共 7 个 commit (CI/CD 加固 + 外链初版)

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

---

## 九、2026-07-06 ~ 07-07 续推的 3 个 commit (本次会话)

| Commit | 改动 |
|--------|------|
| `65d4a7d` | fix(realtime): 切源不刷新 + TZ 误判 + 指数无声 fallback 三大根因 (3 后端文件) |
| `e14f842` | docs(snapshot): 标注 Actions 观察需人工核验 (本地无 gh/token, API 限流) |
| `53f997a` | fix(ui): 外链块不渲染 — parseSymbol 不认后端 `.SH` 点号格式 |

### Commit `65d4a7d` — 实时数据三大根因 (3 个后端 fix)

**现象**: 交易时段把实时源切到「东方财富 push2」后, 大盘指数和个股
(如 SH688238 和元生物) 仍显示上周五收盘价, 并非今日实时数据。

| 根因 | Fix | 位置 |
|------|-----|------|
| 切源后 `_poll_loop` 要等 3~10s 才跑第一轮, 期间 indices endpoint 拿空 cache → 海 `kline_index_daily` fallback 显示旧价 | `update_realtime_provider()` 在 `disable/enable` 后追加 `qs.refresh()` (try/except 守护) | `backend/app/api/settings.py:521-524` |
| 交易时段 fetch 失败时 indices endpoint 无声回退 fallback, 用户感知「切源不生效」 | `index_quotes()` 空缓存分支查 `qs.status()`, 交易时段且线程已跑过 (`last_fetch_ms is not None`) → 返回 `source="loading"`, 仅非交易时段或线程刚启动才走 fallback | `backend/app/api/intraday.py:110-118` |
| 服务器 `TZ=UTC` 时 9:30 北京 = UTC 01:30 不在交易窗口, `_poll_loop` 误判跳过 fetch → `_index_quotes_cache` 永不更新 | 引入 `zoneinfo.ZoneInfo("Asia/Shanghai")` + `_CN_TZ`, `_is_trading_hours()` 用 `datetime.now(_CN_TZ)` | `backend/app/services/quote_service.py:30-36, 695-700` |

**lint 验证**: ruff 78 条全是项目历史存量 (RUF001/002/003 中文全角标点、RUF100 失效 noqa、
SIM105 try-except-pass、I001 import 顺序), 新增代码命中 RUF100/SIM105 均沿用周边同款写法,
未引入新噪声。

**Actions 验证**: commit `65d4a7d` (#18, 1m51s) + `e14f842` (#19, 1m20s) 全绿; Docker Hub `:latest` 刷新于 2026-07-06 10:34:24, 对应 `sha-e14f842`。
  ⚠️ #18/#19 只跑 1 分钟是因为 GHA buildx cache 几乎全命中 (前后 commit 前端代码未动), 是正常现象, 不是 build 跳过。

### Commit `53f997a` — 外链块不渲染 (前端 parseSymbol bug)

**现象**: 用户无痕窗口实测弹窗里看不到「外部资料」一行, 但容器内
`/app/static/assets/index-CGTbuxms.js` 含 `finance.baidu.com` 字符串,
排除镜像/缓存问题。

**根因** (排查链路复盘):
- 本地源码 → `StockPreviewDialog.tsx` 含外链逻辑 ✅
- 本地 dist build → 含外链字符串 ✅
- GitHub Actions #17/#18/#19 → 全绿, Docker Hub `:latest` 推送于 10:34:24 ✅
- 服务器 `docker compose exec grep` → 容器内 JS bundle 含外链字符串 ✅
- **无痕窗口实测** → ❌ 外链不出现  ← 真现象, 镜像与缓存都不是

回到源码读 `parseSymbol` (StockPreviewDialog.tsx 第 50-59 行 旧版):
```ts
// 原代码只支持 SH688238 前缀 和 裸 688238, 漏掉了后端标准
const m = /^(SH|SZ|BJ)(\d{6})$/.exec(symbol)   // 不认 688238.SH
```
后端 eastmoney provider 第 105 行明确 `return f"{code}.SH"` —— 实际传给弹窗的
symbol 是 `688238.SH` 点号格式。两种正则都不命中 → `parseSymbol` 返回
`exchange=null` → `buildExternalLinks` 返回 `[]` → IIFE `if (links.length === 0) return null`
→ **整块外链跳过不渲染**。

**修复** (三级兼容):
```ts
function parseSymbol(symbol: string) {
  // 1. 点号后缀:  688238.SH / 000001.SZ / 430047.BJ  (后端 eastmoney 标准)
  const dot = /^(\d{6})\.(SH|SZ|BJ)$/.exec(symbol)
  if (dot) return { exchange: dot[2], code: dot[1] }
  // 2. 前缀无点:  SH688238 / SZ000001 / BJ430047
  const pref = /^(SH|SZ|BJ)(\d{6})$/.exec(symbol)
  if (pref) return { exchange: pref[1], code: pref[2] }
  // 3. 纯数字:    688238 (按首位推断交易所)
  ...
}
```
顺带: `boardTag` 也加 `.SH/.SZ/.BJ` 后缀剥除, 显式兼容而非依赖正则副作用。

**验证**: `pnpm exec tsc --noEmit` 零错误, `pnpm build` 产出的 `index-Dy7upQSo.js`
含 `finance.baidu.com/stock/ab-${r}` 字符串。

**本次 2 小时排查的教训**:
> **bundle 里有字符串 ≠ 运行时这条分支会被执行**。判断 bug 不能只看
> 「代码里有没有」+ 「镜像里有没有」, 还要看运行时分支条件是否会其实命中。
> 若一开始就先 grep 后端实际返回的 symbol 格式, 会比排查两小时快很多。

### 与 commit `2109b0c` 的关系
- `2109b0c` 引入了外链功能, 但 `boardTag` 的 SH 前缀剥离其实也只对
  `SH688238` 前缀形态工作, 后端 `688238.SH` 格式当时就已经让 `boardTag`
  哑火 (但科创板星级标签不出现没人留意到)。
- `53f997a` 一次修两个: 优先让外链渲染 + 顺带让 `boardTag` 在点号格式上也对。

---

## 十、迁移后新对话待办 (按优先级)

### 高优 (验证迁移完整性 + 上线外链修复)
1. **新目录 clone + 环境重建**
   ```bash
   cd E:\3.Github && git clone https://github.com/chiyoumask/quantforge
   cd quantforge/quantforge  # 注意 clone 出来可能多一层 quantforge/
   cd backend && uv sync
   cd ../frontend && pnpm install
   ```
2. **验证新环境可启动**
   ```bash
   # 在新目录根
   bash dev.sh    # 或 ./dev.ps1
   # 浏览器打开 http://localhost:5173 (Vite dev) 或 http://localhost:3018
   # 验证: 页面正常加载, 登录页出得来
   ```
3. **服务器验证外链修复已生效** (commit `53f997a` 之后 Actions 跑完后):
   ```bash
   # 在服务器
   cd /www/wwwroot/quantforge && docker compose pull && docker compose up -d
   # 无痕窗口打开域名, 点任意个股, 弹窗顶栏下方应有「外部资料」一行 (4 个外链按钮)
   # 以 SH688238 和元生物为例:
   #   百度股市通 → https://finance.baidu.com/stock/ab-688238
   #   东方财富股吧 → https://guba.eastmoney.com/list,sh688238.html
   #   同花顺 → https://stockpage.10jqka.com.cn/688238/
   #   雪球 → https://xueqiu.com/S/SH688238
   ```
4. **服务器验证实时修复已生效** (commit `65d4a7d` 之后):
   - 设置 → 实时数据源切「东方财富 push2」
   - `GET /api/intraday/indices` 返回 `source: "loading"` 或 `"realtime"` (不应再是 `"index_daily"`)
   - SH688238 等个股和上证/深证/创业板指数显示当日实时数据

### 中优 (文档/对齐改进)
5. **README / docs/deploy-docker.md** 补一段数据源能力对照矩阵 (见第八节表)
6. **设置页 → 实时数据源** 对 TickFlow 标签加灰色「仅收盘」提示
   (`frontend/src/pages/settings/Keys.tsx` 或对应组件), 减少误用
7. **外链板块颜色** `StockPreviewDialog.tsx` boardTag 科板仍用 purple,
   与共享版 `frontend/src/components/stock-table/primitives.tsx` 的 cyan 不一致,
   可在单独的 chore PR 中对齐

### 已知遗留 (非阻塞)
8. **TCR 推送跨境超时** 仍走 `continue-on-error: true` + 15min timeout。
   长期方案: 只推 Docker Hub + ghcr, TCR 由 owner 在国内服务器上手动
   `docker pull ghcr.io/... && docker tag && docker push ccr.ccs.tencentyun.com/...`
9. **`frontend/dist/index.html`** title 已在 `f839c5d` commit 调整, 但 dist 被 .gitignore 忽略,
   实际生产 title 由 Dockerfile build 时 pnpm build 再生成, 不影响线上。

### 完全 done (本次会话已闭环)
- ✅ 后端三大根因 fix (TZ/切源/fallback) — `65d4a7d`
- ✅ 外链不渲染修复 (parseSymbol .SH 兼容) — `53f997a`
- ✅ 本快照随 `53f997a` 之后的提交上 git, 新对话可 git pull 拿到

### 迁移安全: 旧目录暂留兜底
新目录验证可启动并正常拉起前端后, 再清理
`C:\Users\Administrator\Desktop\tickflow-stock-panel` 旧目录。
**验证前不要删旧目录**, 防意外丢东西。

---

## 十一、新对话快速对接 Checklist

新对话打开此快照后, 按此顺序 30 秒可对接:
1. `cd E:\3.Github\quantforge` (或实际 clone 出的多层路径)
2. `git log --oneline -3` → 应见 `53f997a` `e14f842` `65d4a7d` (本次会话三个 commit 都在)
3. `cat progress_snapshot.md | head -100` → 见本快照第〇节迁移核对
4. 跟用户确认下一步: 是先验证外链修复上线, 还是先推进中优文档/对齐改进
5. **不再使用** `C:\Users\Administrator\Desktop\tickflow-stock-panel` 旧目录

---

## 十二、给未来的我一句话

- 本项目数据源定位: TickFlow = 盘后复盘 (免费档非实时), 东方财富 push2 = 盘中实时 (免费全市场), 切源前请先确认需求
- 改前端弹窗组件时, 永远先问一句「传进来的 symbol 是 `SH688238` 还是 `688238.SH`?」 — 后端默认是后者
- 判断 bug: **代码里有没有 ≠ 运行时分支会不会跑**, 务必打通到运行时再下结论
- 迁移到 E:\3.Github\quantforge 是新起点, 旧 Desktop/tickflow-stock-panel 在验证后清理