# 重构进度存档：tickflow 降权 → akshare/eastmoney

> 工作目录：`E:\3.Github\quantforge`（后端 `backend/app`）
> 目标：tickflow 仅作为「收盘后可选付费备用」，默认历史/盘后走 **akshare**，盘中实时走 **东方财富(eastmoney)**。
> 状态：P0/P1/P2/P3 全部完成（后端 + 前端 + 依赖 + 文档）。

## 已确认的决策（用户拍板）
1. 实时默认源 = **eastmoney**（免费全市场，已实现）。
2. 前端最小改动：翻转默认 + 弱化 TickFlow Key 卡片，保留档位徽标作为「免费源就绪」状态。
3. 五档盘口改用 **akshare 逐股**（`stock_bid_ask_em`），仅 watchlist/成分股规模。
4. 本环境 **已安装 akshare**（`pip install akshare` 成功，Python 3.12.4）。

## 环境验证（重要）
- akshare 已装，以下函数 **存在**：`stock_info_a_code_name`, `stock_zh_a_hist`, `stock_zh_a_daily`(adjust qfq-factor/hfq-factor), `stock_zh_a_hist_min_em`, `stock_zh_a_spot_em`, `stock_zh_index_spot_em`, `stock_zh_index_daily_em`, `fund_etf_spot_em`, `stock_profit_sheet_by_report_em`, `stock_balance_sheet_by_report_em`, `stock_cash_flow_sheet_by_report_em`, `stock_financial_analysis_indicator`(财务指标，替代不存在的 `stock_financial_indicator`), `stock_bid_ask_em`(逐股盘口)。
- **不存在**：`stock_financial_indicator`（已改用 `stock_financial_analysis_indicator`）。

## akshare 函数映射（AkshareProvider 内部）
- 标的信息：`stock_info_a_code_name()`（沪深京全A）→ 代码前缀判定 SH/SZ/BJ 加后缀；`stock_zh_index_spot_em()`（指数）；`fund_etf_spot_em()`（ETF）。
- 日K：`stock_zh_a_hist(symbol=裸码, period="daily", start_date="YYYYMMDD", end_date="YYYYMMDD", adjust="")`。ETF 同样可用；指数用 `stock_zh_index_daily_em(symbol=裸指数码, start_date, end_date)`（**无 period 参数**）。
- 复权因子：`stock_zh_a_daily` 的 `adjust=""`(未复权) 与 `adjust="qfq"`(前复权) **均不单列因子列**，故 `get_adj_factors` 取两版收盘价算 `ex_factor = 前复权收盘 / 未复权收盘`（单股 2 次请求，已限速）。（早期设想的 `adjust="qfq-factor"` 实不存在，已废弃。）
- 分钟K：`stock_zh_a_hist_min_em(symbol=裸码, period="1"/"5", start_date="YYYY-MM-DD HH:MM:SS", end_date=..., adjust="")`。
- 实时：`stock_zh_a_spot_em()` / `stock_zh_index_spot_em()` / `fund_etf_spot_em()` → 15 字段 records（与 EastMoneyProvider 一致）。
- 财务：`stock_financial_analysis_indicator`(metrics) / `stock_profit_sheet_by_report_em` / `stock_balance_sheet_by_report_em` / `stock_cash_flow_sheet_by_report_em`（EM 用 "SH600519"/"SZ000001" 前缀）。
- 逐股盘口：`stock_bid_ask_em(symbol=裸码)`（depth 任务用）。

## 已完成改动（后端）
### 新增/修改的基础设施
- `backend/app/data_providers/akshare_provider.py` — **新建**。完整实现 `MarketDataProvider`：
  - `name="akshare"`，`capabilities` 全 True（含 realtime 与 financial，作为可选实时/免费财务源）。
  - `get_instruments / get_daily / get_adj_factors / get_minute / get_realtime / get_financial`。
  - 全部调用 try/except 包裹，失败只 warning 不中断整体；列映射「存在才 rename」。
  - 财务列名统一 slug（`_slug`），`symbol` 列注入。
- `backend/app/data_providers/base.py` — Protocol 新增 `get_financial(statement, symbols, start_year, end_year)`（默认 raise `NotImplementedError`）。
- `backend/app/data_providers/registry.py` — 注册 `"akshare": AkshareProvider`；`get_provider` 默认改 `"akshare"`。
- `backend/app/data_providers/caps_build.py` — **新建**。`active_capabilities(capset)`：当前日K源为免费源(akshare/eastmoney/sina/qq)→返回全能力；为 tickflow→沿用真实 capset（保留档位门控）。

### 默认值翻转
- `backend/app/services/preferences.py`：
  - `_ALLOWED_DATA_PROVIDERS` 加 `"akshare"`。
  - `get_daily_data_provider()`→`"akshare"`；`get_minute_data_provider()`→`"akshare"`；`get_adj_factor_provider()` 默认 `"same_as_daily"`；`get_realtime_data_provider()`→`"eastmoney"`；`set_realtime_data_provider` 允许集合加 akshare。
- `backend/app/config.py`：`use_free_mode` 不再依赖 tickflow key——当前日K源为免费源且无 tickflow key 即 True。
- `backend/app/secrets_store.py`：保留 `get_tickflow_key()`（仅作可选付费备用 Key），不再作为 free-mode 开关。

### 同步服务改走 provider（核心）
- `kline_sync.py`：
  - 去掉 `from app.tickflow.client import get_client`；加 `active_capabilities` + `get_provider` + `_daily_provider()` 辅助。
  - `sync_daily_batch`：委托 `provider.get_daily`（无日期时按 count 推算 1.6×日历日起点）。
  - `sync_and_persist_daily_batch` / `sync_and_persist_minute`：`capset.has/limits` → `active_capabilities(capset).has/limits`。
  - `sync_daily_by_quotes`：改走 `get_provider(get_realtime_data_provider()).get_realtime(universes=["CN_Equity_A"])` 填今日日K。
  - `sync_adj_factor`：委托 `provider.get_adj_factors`（`capset.has(Cap.ADJ_FACTOR)` → active）。
  - `sync_minute_batch` / `fetch_minute_single` / `fetch_adj_factor_single`：委托 `provider.get_minute / get_adj_factors`。
  - 旧 `_normalize_daily/_minute/_adj_factor` 已不再被调用（保留无害）。
- `instrument_sync.py`：`sync_instruments` 改 `provider.get_instruments(asset_type="stock")`，删除 tickflow `get_instruments` + quotes 补 name。
- `index_sync.py`：`_fetch_instruments_by_type` 改 `provider.get_instruments`；`sync_index_instruments` 删除 tickflow `get_by_universes` 付费补充；`sync_and_persist_index_daily/etf_daily` 的 `Cap.KLINE_DAILY_BATCH` 门控 → `active_capabilities`。`_quotes_to_index_instruments` 现未使用（无害）。
- `financial_sync.py`：`_sync_table` 改 `provider.get_financial`（捕获 `NotImplementedError` 跳过无财务的源）；所有 `capset.has(Cap.FINANCIAL)`（6 处，含调度器 start/run/trigger）→ `active_capabilities(capset).has(Cap.FINANCIAL)`。
- `extend_history.py`：`_resolve_universe` 删除 `Cap.KLINE_DAILY_BATCH` 门控，改以全量 instruments(parquet) + watchlist；`capset.has(Cap.ADJ_FACTOR)` → active。新增 `get_watchlist_symbols()` 辅助。
- `daily_pipeline.py`：**已改**（`_resolve_universe`/`run_now` 已用 `active_capabilities(capset)`）。

## 待办（按优先级）
### P0 — 收尾后端同步/实时（用户核心痛点）✅ 已完成
1. ✅ **`watchlist.fetch_quotes`**：已改为 `get_provider(get_realtime_data_provider())` 拉取，删除提前返回空逻辑，免费源也能看自选股实时。
2. ✅ **`quote_service.realtime_mode()`**：`"akshare"` 已加入免费 full_market 源集合。
3. ✅ **`daily_pipeline.py`**：`_resolve_universe`/`run_now` 全部改用 `active_capabilities(capset).has(...)`。
4. ✅ **`main.py`**：`get_daily_data_provider()!=tickflow` 时构造全能力 CapabilitySet 喂 `app.state.capabilities`（前端徽标显示「免费源就绪」）。

### P1 — 五档盘口 + API 层 Cap 重解释 ✅ 已完成
5. ✅ **`depth_service.py`**：`tf.depth.batch` 替换为 akshare `stock_bid_ask_em` 逐股 + 限速；新增 `is_available()`（akshare 逐股始终可用；tickflow 选中保留批量分支）。`monitor_rules.py:138` 门控改 `depth_service.is_available()`。
6. ✅ **API 层 Cap 门控重解释**：`api/financials.py`、`api/indices.py`、`api/kline.py`（5 处）、`api/settings.py`（3 处 depth 端点）、`api/monitor_rules.py` 全部重写——financials/indices/kline 的 `capset.has/require` 包 `active_capabilities(...)`；depth/五档门控改 `depth_service.is_available()`。

### P2 — 前端最小改动 ✅ 已完成
7. ✅ `frontend/src/lib/api.ts`：新增 `saveDailyProvider/SaveMinuteProvider/SaveAdjProvider`（PUT `/api/settings/preferences/{daily,minute,adj}-provider`）；后端 `preferences.py` 加对应 setter、`settings.py` 加三个端点。
8. ✅ `frontend/src/pages/settings/Keys.tsx`：`realtime_data_provider` 默认 fallback 改 `'eastmoney'`；`RealtimeSourceCard` 加 akshare 选项；新增「历史/盘后数据源」卡片（日K/分钟K/复权，akshare 默认，tickflow 作付费备用）；TickFlow Key 卡片收进可折叠「高级 / TickFlow 付费备用(可选)」区。
9. ✅ `frontend/src/pages/Onboarding.tsx`：Step1 与 None 档卡片/结果页/完成页文案改为「akshare 历史 + 东方财富实时开箱即用，TickFlow 付费可选填」。
10. ✅ `frontend/src/components/Layout.tsx`：侧边栏徽标由「TickFlow 档位」改为「数据源 · 免费源就绪 / akshare+东财免费」。
11. ✅ `frontend/src/components/EndpointTestDialog.tsx` + `pages/Data.tsx`：仅当 `daily_data_provider==tickflow` 时按钮/弹窗可渲染（legacy）。
12. ✅ `frontend/src/pages/Financials.tsx`：去掉「需 Expert 套餐」硬性文案，改为「免费源(akshare)可用」；未启用财务能力时的提示改为引导设置 akshare 或填 TickFlow Key。

### P3 — 冒烟 + 依赖 + 文档 ✅ 已完成
13. ✅ 后端启动冒烟：临时脚本 `_smoke_test.py` 实例化 `AkshareProvider`，验证 `_to_symbol`/深度解析/快照映射/`active_capabilities`/`get_adj_factors`（qfq 因子=前复权收盘/未复权收盘），全部通过；脚本已删除。
14. ✅ `backend/pyproject.toml`：加 `akshare>=1.13`（主依赖 + `akshare` extra）；`.env.example` 注明 `TICKFLOW_API_KEY` 为可选备用、新增 `DAILY/MINUTE/REALTIME_DATA_PROVIDER`；`README.md` 数据源章节与徽标已更新为「akshare+东方财富 默认免费，TickFlow 付费兜底」。

## 关键风险/注意
- akshare 逐股循环拉全市场日K 较慢（盘后用，provider 内部已限速 `_DEFAULT_RPM=80`、`_DEFAULT_BATCH=50`）。
- 财务列 schema 与现有 financials 页/存储不完全一致（最佳努力 slug 映射），字段级打磨待前端联调核验。
- `app/tickflow` 模块**保留不删**（作备用），默认路径已无 tickflow 依赖。
- `kline_sync._normalize_*`、`index_sync._quotes_to_index_instruments` 现为死代码但无害，可后续清理。
- 冒烟前建议先 `cd backend && python -c "import app.data_providers.akshare_provider"` 确认无语法/导入错误。
