<div align="center">

# 📈 A股智能量化工作台

**自托管、零运维的 A 股「选股 + 监控 + 回测」量化工作台**

**面向个人散户与量化爱好者而生**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-≥3.11-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](https://react.dev/)
[![Data: akshare + 东方财富](https://img.shields.io/badge/Data-akshare%20%7C%20eastmoney-00b386.svg)](https://akshare.akfamily.xyz/)
[![Deploy: Docker](https://img.shields.io/badge/Deploy-Docker-2496ed.svg)](./Dockerfile)
[![GitHub stars](https://img.shields.io/github/stars/chiyoumask/quantforge?style=social)](https://github.com/chiyoumask/quantforge/stargazers)

</div>

<div align="center">

**[快速开始](#-快速开始)** · **[核心功能](#-核心功能)** · **[数据源](#️-数据源)** · **[配置](#️-配置)** · **[路线图](#-路线图)**

</div>

- 🆓 **开箱即用,完全免费** — 默认 **akshare(历史/盘后) + 东方财富(盘中实时)** 双免费源,**无需任何 API Key、无需付费**
- 🏠 **自托管零运维** — Docker 单容器部署,数据完全掌握在自己手里
- 🔍 **三位一体** — 选股(20 内置策略)+ 实时监控 + 向量化回测,Polars 毫秒级扫描全 A 股
- 🤖 **AI 加持** — 一句话生成策略代码,任意 OpenAI 兼容接口均可接入(留空即关闭)
- 🔌 **自由扩展** — 自有量化项目数据,与内置数据同台分析
- 🇨🇳 **A 股专用** — 盘后自动 AI 复盘并推送至飞书等;连板梯队、涨停动量、内置 ths 概念 / 行业

> 数据源说明:本项目默认数据来自社区开源的 [akshare](https://akshare.akfamily.xyz/) 与东方财富公开行情接口,**完全免费、无需注册**。若你需要更高阶的付费能力(全市场实时 / 分钟 K / 盘口 / WebSocket / 财务),可额外填入 [TickFlow](https://tickflow.org/auth/register?ref=V3KDKGXPEA) 的 API Key 作为**可选付费兜底源**,不填也能用。

> 有更多稳定免费数据源推荐,或提交建议/意见,欢迎邮件至 415333856@qq.com,Q 群 109338242。

觉得有用可以点个 Star,蟹蟹 🌹

---

## 🎯 项目定位

**面向个人散户与量化爱好者的 A 股分析工作台**,聚焦「**选股 + 监控 + 回测**」三大场景,LLM 能力驱动进行市场分析,掌控市场节奏;让普通投资者也能拥有一套可自定义策略的量化工具。

**明确不做**:不对标同花顺 / 通达信,不内置「AI 荐股 / 涨停预测」。

---

## 📸 界面预览

<table>
  <tr>
    <td width="50%" align="center"><b>看板 Dashboard</b></td>
    <td width="50%" align="center"><b>策略 Screener</b></td>
  </tr>
  <tr>
    <td width="50%"><img src="./screenshots/dashboard.png" alt="看板页面"></td>
    <td width="50%"><img src="./screenshots/screener.png" alt="策略页"></td>
  </tr>
  <tr>
    <td width="50%" align="center"><b>回测 Backtest</b></td>
    <td width="50%" align="center"><b>监控中心 Monitor</b></td>
  </tr>
  <tr>
    <td width="50%"><img src="./screenshots/backtest.png" alt="回测页"></td>
    <td width="50%"><img src="./screenshots/monitor.png" alt="监控中心"></td>
  </tr>
  <tr>
    <td width="50%" align="center"><b>连板梯队 Limit Ladder</b></td>
    <td width="50%" align="center"><b>概念分析 Concept</b></td>
  </tr>
  <tr>
    <td width="50%"><img src="./screenshots/limit-ladder.png" alt="连板梯队页"></td>
    <td width="50%"><img src="./screenshots/concept-analysis.png" alt="概念分析"></td>
  </tr>
</table>

<div align="center">

### 📸 [查看更多界面截图 »](./screenshots/README.md)

</div>

---

## 🚀 快速开始

### 前置依赖

| 工具                               | 版本   | 安装                                               |
| :--------------------------------- | :----- | :------------------------------------------------- |
| Python                             | ≥ 3.11 | [python.org](https://www.python.org/)              |
| Node                               | ≥ 20   | [nodejs.org](https://nodejs.org/)                  |
| [`uv`](https://docs.astral.sh/uv/) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `pnpm`                             | 9      | `npm i -g pnpm`                                    |

### 方式 A:Dev 模式(二次开发推荐,由于刚开源近期更新频繁,可以开发模式定时 git pull)

```bash
cp .env.example .env       # 默认即可,无需填任何 Key 即可免费使用
./dev.sh                   # Windows: .\dev.ps1
```

自动检查 / 下载依赖、释放端口、同时起前后端,Ctrl-C 一并关闭。默认:

- 后端 → <http://localhost:3018> · 前端 → <http://localhost:3011>
- 自定义端口:`BACKEND_PORT=8000 FRONTEND_PORT=5173 ./dev.sh`

### 方式 B:Docker(部署最省心)

```bash
cp .env.example .env
docker compose up --build
# 打开 http://localhost:3018
```

> **生产部署**:推荐用镜像拉取模式 —— GitHub Actions 自动构建镜像并推送到 Docker Hub(国内外通用) + ghcr.io(兜底),服务器 `docker compose pull && up -d` 即可,不在小机上构建。完整步骤见 **[docs/deploy-docker.md](./docs/deploy-docker.md)**;宝塔/腾讯云国内轻量从零部署见 **[docs/bt-deploy.md](./docs/bt-deploy.md)**。腾讯云轻量想走内网可额外启用 TCR 见 [docs/deploy-tcr.md](./docs/deploy-tcr.md)。

<details>
<summary><b>环境适配与高级选项(老 CPU · 手动启动 · 回测依赖)</b></summary>

**老 CPU 兼容(avx2/fma 缺失报错或 exit 132)**:桌面客户端安装包已内置兼容内核(新老 CPU 通吃)。Docker / 源码用户在 `.env` 打开 `BACKEND_EXTRAS=legacy-cpu` 后重建,会给 Polars 切到 `rtcompat` 运行时;需回测则 `BACKEND_EXTRAS=legacy-cpu backtest`。

**手动分别启动:**

```bash
# 后端
cd backend && uv sync --extra backtest   # 含回测依赖
uv run uvicorn app.main:app --reload --port 3018

# 前端
cd frontend && pnpm install && pnpm dev   # http://localhost:3011
```

**回测依赖**:vectorbt → numba 体积较大,作为可选 extras(`uv sync --extra backtest`)。macOS / Intel 无预构建 wheel 时需 `brew install cmake` 现场编译。

**仅装免费源依赖**:akshare 作为可选 extra,若不想常驻主依赖可只装 `uv sync --extra akshare`。

</details>

### 🔄 更新代码(已部署用户必读)

拉取新版本只需一条命令:

```bash
git pull
```

**整个 `data/` 目录都不纳入 git**——行情 K线、财务、自选、回测、监控记录,乃至概念/行业扩展数据,全部是程序运行时生成/拉取的用户数据,`git pull` 物理上无法影响它们。新用户首次启动时,概念/行业两份扩展数据会自动从远程接口拉取,无需任何手动操作。

> ⚠️ **切勿使用以下命令"解决冲突"或"清理",它们会一次性删光 `data/` 下所有未被 git 跟踪的数据:**
> - `git clean -fdx`(最危险,会删掉所有 `.gitignore` 忽略的文件)
> - `git reset --hard`
> - 直接删除整个项目文件夹重新 `git clone`
>
> 若 `git pull` 报冲突,通常是本地误改了被跟踪的文件,请先 `git stash` 暂存再 pull,或单独联系作者,不要直接执行上面的命令。

### 🧭 跑起来后的第一次使用

1. **设置 → 数据源**:默认已经是 akshare(历史)+ 东方财富(实时)免费组合,无需任何操作即可用
2. **设置** → **立即跑盘后管道**:拉日 K + 计算 enriched 表(akshare 当日数据盘后 1-2 小时可用)
3. **自选**页加标的 → **选股**页点策略卡片扫描 / 配自定义信号
4. **回测**页选策略 + 区间 → 看净值 / 夏普 / 交易明细(SSE 实时进度)
5. **监控中心**配规则(策略 / 个股信号 / 价格 / 异动),盘中实时弹窗 + 持久化记录

---

## ✨ 核心功能

### 🔍 选股引擎(Screener)

**20 个内置策略**,每个策略一个独立 Python 文件,基于 Polars 表达式向量化实现(`backend/app/strategy/builtin/`):

| 类型        | 代表策略                                                 |
| :---------- | :------------------------------------------------------- |
| 趋势 / 形态 | 趋势突破 · 均线多头 · MA 金叉 · MACD 金叉放量 · 布林突破 |
| 量价 / 涨停 | 量价齐升 · 高换手强势 · 连板股 · 断板反包 · 涨停动量     |
| 反转 / 波动 | 超跌反弹 · 超卖反转 · 新低反转 · 低波动龙头 · 回踩 MA20  |

**扩展策略的三种方式:**

| 方式              | 说明                                                                                                  |
| :---------------- | :---------------------------------------------------------------------------------------------------- |
| **🎛️ 自定义信号** | 不写代码,UI 上 `字段 + 操作符 + 阈值` 组合编译成 Polars 表达式热加载                                  |
| **🤖 AI 生成**    | 一句话描述思路,LLM 读 `strategy-guide.md` 生成完整策略文件(经 `ast` 校验)→ 落入 `data/strategies/ai/` |
| **📝 代码迁移**   | 参照开发指南把已有策略改写为 Polars 文件放入 `data/strategies/custom/`,引擎自动发现                   |

### 📊 指标流水线(Indicators)

原生 Polars 向量化,全 A 股一次扫表落盘 enriched Parquet:

- **均线 / 趋势**:MA(5-60)· EMA · MACD · 动量 · 布林带
- **震荡 / 波动**:RSI · KDJ · ATR · 年化波动率 · 振幅
- **量能 / 涨跌停**:量比 · 量均线 · 涨停信号 · 连板数
- **原子信号**:MA / MACD 金叉死叉 · N 日新高新低 · 布林突破
- **复权**:基于除权因子自动前复权,回测与指标口径一致

### 🧪 回测引擎(Backtest)

基于 vectorbt:**三种模式**(个股 / 策略组合 / 自由信号组合),真实约束(T+1 · 手续费 · 滑点 · 止损 · 最大持仓天数),组合管理(最大持仓 · 敞口 · 等权 / 自定义仓位)。SSE 流式进度支持切页重连,输出净值曲线 · 夏普 · 最大回撤 · 胜率 · 交易明细。

### 📡 监控中心(Monitor)

统一规则引擎,一个页面管理**四类监控**(策略 · 个股信号 · 价格涨跌 · 全市场异动):

- 多条件 AND/OR + 冷却期去重 + 严重级别(info/warn/critical)
- 多入口配置:监控中心新建 / 个股详情页「加监控」/ 策略卡片一键开启
- 命中后右下角弹窗(可配声效)+ 持久化到 `alerts.jsonl`,菜单未读徽标
- **触发记录详情**:每条记录展示命中的具体条件(如 `RSI>80`)与当前价位,一眼看清为何触发
- **飞书 Webhook 推送**:全局一处配置飞书群机器人地址,启用推送的规则命中即推送到飞书群(支持签名校验);可在设置页设「默认推送渠道」,新建规则自动预填

### 📈 个股分析(Beta)

以「行情 + 关键价位」为主体的单标的决策页:

- **专用日 K 图表**:主图 + 成交量 + 滑块,默认近 6 个月
- **9 类关键价位**(纯函数实时计算,毫秒级):压力支撑 · 成交密集区 · 枢轴点 · 前高前低 · Keltner 通道 · ATR 止损 · 缺口位 · 斐波那契 · 整数关口
- **AI 四维分析**:技术 / 基本面 / 财务 / 消息面流式生成,实战派交易员视角

### 🧰 数据与扩展

- **多源数据(默认免费)**:历史 / 盘后走 **akshare**(日 K / 分钟 K / 指数 / ETF / 财务 / 复权),盘中实时走 **东方财富 push2** 免费全市场快照;**TickFlow** 作为付费兜底源
- **🔌 第三方接入(重点)**:Tushare 等 HTTP 定时拉取 · CSV / Excel 上传 · JSON 写入,自动 schema 发现 + 符号归一,页面可视化配置,**可与自有量化项目数据并入 DuckDB 同台分析**
- **盘后定时管道**:APScheduler 15:30 CST 自动拉日 K + 重算 enriched + 跑监控
- **令牌桶限流**:适配各源 rpm / batch,批量合并 + 增量拉取

### 🪜 连板梯队(Limit Ladder)

专攻涨停 / 跌停情绪:

- 连板数分组、涨停梯队、封板强度排序
- **真假涨停判定**:基于五档盘口(卖一量 / 买一量)区分真封板 / 炸板 / 待确认,盘后定版
- 封单监控规则:封单量 / 额低于阈值自动告警

### 📊 市场看板(Overview)

- 涨跌分布、情绪雷达、资金流向、行业 / 概念轮动排名
- 龙头股、涨停 / 跌停、成交量 / 换手领先榜
- 概念涨幅轮动矩阵(每日各概念涨幅排序)

### 🧠 AI 能力(可选)

- **策略生成**:自然语言 → Polars 策略文件(经 `ast` 校验)
- **个股 / 财务 / 大盘复盘**:流式分析,任意 OpenAI 兼容接口(DeepSeek / 通义 / Ollama 等)
- **全部配置留空即跳过**,不影响核心功能

---

## 🗄️ 数据源

> 默认 **完全免费、无需任何 Key**。只有想用 TickFlow 付费能力时才需要填 Key。

### 默认免费组合(开箱即用)

| 用途         | 数据源                                                       | 说明                                          |
| :----------- | :----------------------------------------------------------- | :-------------------------------------------- |
| 历史 / 盘后  | [akshare](https://akshare.akfamily.xyz/)                     | 日 K / 分钟 K / 指数 / ETF / 财务 / 复权因子  |
| 盘中实时     | 东方财富 push2 公开接口                                       | 全市场实时快照,一次请求,无需 Key              |
| 备用实时源   | akshare / 新浪财经 / 腾讯财经                                | 东方财富不可达时手动切换                      |

### TickFlow(可选付费兜底)

当你需要以下**付费高级能力**时,在 **设置 → 数据源** 填入 `TICKFLOW_API_KEY` 即可启用,TickFlow 作为额外数据源叠加使用:

- 全市场实时行情(Starter+)
- 分钟 K + 盘口(Pro)
- WebSocket 实时推送 + 财务数据(Expert)

> 不填 Key 也能正常使用 —— 默认 akshare + 东方财富免费源已覆盖绝大多数场景。

### 数据架构

- **计算**:Polars(向量化,毫秒级扫全 A 股)
- **存储**:DuckDB(查询)+ Parquet(落盘)
- **回测**:vectorbt(全项目唯一 pandas 边界,见 `ADR-19`)

---

## 🛠️ 技术栈

| 层           | 选型                                                                                              |
| :----------- | :------------------------------------------------------------------------------------------------ |
| **后端**     | FastAPI · Pydantic v2 · APScheduler · sse-starlette                                               |
| **数据**     | Polars(计算)· DuckDB(查询)· Parquet(存储)                                                         |
| **数据源**   | akshare(默认免费历史/盘后) · 东方财富 push2(默认免费实时) · TickFlow(可选付费兜底)                 |
| **回测**     | vectorbt(全项目唯一 pandas 边界)                                                                  |
| **AI**(可选) | OpenAI 兼容接口(DeepSeek / 通义 / Ollama 等)                                                      |
| **前端**     | React 18 · Vite · TypeScript · Tailwind · Tanstack Query · Lightweight Charts · ECharts · dnd-kit |
| **部署**     | Docker · Docker Compose · GitHub Actions 自动构建镜像                                             |

---

## 🗺️ 路线图

- [x] 默认免费数据栈(akshare + 东方财富),TickFlow 降为可选付费兜底
- [x] 五档盘口真假涨停判定(akshare 逐股)
- [ ] 更多免费数据源适配(雪球 / 交易所官方等)
- [ ] 因子库与多因子回测增强
- [ ] 策略市场 / 社区策略分享

---

## ⚠️ 免责声明

本项目仅供**学习与量化研究**,**不构成任何投资建议**。回测结果不代表未来收益。A 股有风险,入市需谨慎。数据准确性以各数据源(akshare / 东方财富 / TickFlow)官方为准;使用 TickFlow 付费能力时请遵守其服务条款。

---

## 📄 开源协议

[MIT](./LICENSE) © quantforge contributors
