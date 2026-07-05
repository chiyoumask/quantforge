# 宝塔 Docker Compose 部署指南（腾讯云国内轻量）

针对**国内网络**优化：解决 GitHub 克隆慢、Docker 基础镜像拉取失败、**轻量云机上构建 OOM** 三大痛点。东方财富实时行情源为境内主机，国内 VPS 访问无障碍。

> 仓库（公开）：https://github.com/chiyoumask/quantforge

> **推荐：镜像拉取模式**。GitHub Actions 已自动构建镜像并推送到腾讯云 TCR（国内轻量云内网秒达），服务器端 `docker compose pull && up -d` 即可，**不再需要在 2C2G 小机上跑 pnpm install + vite build**。完整配置见 [deploy-tcr.md](./deploy-tcr.md)。
>
> 本文档下方仍保留「本地构建」作为兜底备用路径，仅在网络好或想自建镜像时使用。

---

## 0. 前置：宝塔安装 Docker

宝塔面板 → **Docker** → 首次进入会提示安装 Docker 引擎（若未装）。装好后命令行 `docker --version` 可用。

---

## 1. 配置 Docker 镜像加速（关键，解决基础镜像拉取）

构建会拉 `node:20-alpine`、`python:3.11-slim` 两个基础镜像，国内直连 Docker Hub 常超时。腾讯云轻量**内网**自带加速器。

**宝塔界面**：Docker → 镜像 → 设置 → 加速器，添加：
```
https://mirror.ccs.tencentyun.com
```
（腾讯云轻量内网专用，仅本机内可访问；若该地址不通，改用 `https://docker.m.daocloud.io` 或 `https://docker.1panel.live`）

**或命令行**（写 daemon.json）：
```bash
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.m.daocloud.io"
  ]
}
EOF
systemctl restart docker
```

> 已配置：Dockerfile 内 `USE_CN_MIRROR=1`（默认）已走 npmmirror / 清华 PyPI / 阿里 PyPI，npm 与 pip 无需额外处理。

---

## 2. 拉取代码（按可靠性三选一）

### 方式 A：直连 GitHub（先试，小仓库可能就够）
```bash
cd /www/wwwroot
git clone https://github.com/chiyoumask/quantforge.git
# 若卡住或超时 → 用方式 B
```

### 方式 B：GitHub 代理（直连失败时）
```bash
cd /www/wwwroot
# ghproxy 系代理（任选一个能通的）
git clone https://ghproxy.com/https://github.com/chiyoumask/quantforge.git
# 或
git clone https://gh-proxy.com/https://github.com/chiyoumask/quantforge.git
# 克隆后改回官方 remote（后续更新仍走代理或换 Gitee）
cd quantforge
git remote set-url origin https://github.com/chiyoumask/quantforge.git
```

### 方式 C：Gitee 镜像（最稳，适合长期更新）
1. Gitee：新建仓库 → 导入已有仓库 → 填 `https://github.com/chiyoumask/quantforge` → 公开
2. VPS 克隆 Gitee：
```bash
cd /www/wwwroot
git clone https://gitee.com/<你的Gitee用户名>/quantforge.git
```
3. 后续更新：Gitee 仓库页点「强制同步」→ VPS `git pull`

> 无 git 也能起步：本地下载 zip → 宝塔「文件 → 上传」→ 解压到 `/www/wwwroot/quantforge`。但后续更新建议转 Git。

---

## 3. 配置 .env

```bash
cd /www/wwwroot/quantforge
cp .env.example .env
```

用宝塔文件编辑器改 `.env`：
```ini
# 多用户超管（公网部署必需，首次启动自动建超管账号）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<至少6位强密码>

# 端口
PORT=3018

# TickFlow Key 可留空；留空也能在面板切「东方财富 push2」免费实时源
TICKFLOW_API_KEY=

# 老旧 VPS 无 AVX2 时取消下面注释
# BACKEND_EXTRAS=legacy-cpu
```

---

## 4. 放行端口

宝塔 → **安全** → 放行 `3018/TCP`。腾讯云控制台 → 防火墙 → 同样放行 `3018`。

---

## 5. 拉取镜像并启动（推荐）

按 [deploy-tcr.md](./deploy-tcr.md) 完成腾讯云 TCR 配置和 GitHub Secrets 设置后，CI 会自动构建并推送镜像到 `ccr.ccs.tencentyun.com/<namespace>/quantforge`。

```bash
# 私有镜像需先登录（公开镜像可跳过）
docker login ccr.ccs.tencentyun.com

cd /www/wwwroot/quantforge
git pull                                  # 拉最新 docker-compose.yml
docker compose pull                       # 秒级从 TCR 内网拉镜像
docker compose up -d                      # 启动 (不再 --build)
docker compose logs -f app                # 看到 "ready; N capabilities active" 即成功
```

> 首次拉取约 1-3 分钟；之后每次只拉增量层，通常 < 10 秒。`data/` 卷不动，数据不丢。

也可在宝塔 → Docker → Compose → 添加项目（路径选 `/www/wwwroot/quantforge`），全程 UI 管理。

### 备用：本地构建模式（网络好 / 想自建镜像时）

仅在以下情况使用本地 `--build`：
- 服务器能稳定访问 GitHub + npm + PyPI 源
- 或想自建镜像（如改了 Dockerfile 后立即在服务器验证）

```bash
cd /www/wwwroot/quantforge
# 关键：把 .env 中的 APP_IMAGE 置空才能走 build 分支
#   APP_IMAGE=
docker compose up -d --build              # 首次约 3-8 分钟（拉镜像+装依赖+构建前端）
docker compose logs -f app
```

> ⚠️ 2C2G 小机本地构建易 OOM（尤其 vite 压缩大 bundle 时）。建议优先用 TCR 镜像拉取模式；本地构建前临时 `fallocate -l 4G /swapfile && mkswap /swapfile && swapon /swapfile` 加 swap 兜底。

---

## 6. 访问与初始化

1. 浏览器 `http://<VPS公网IP>:3018`
2. 首次用 `.env` 里的 `ADMIN_USERNAME/ADMIN_PASSWORD` 登录（超管）
3. **设置 → TickFlow → 实时数据源** 切「东方财富 push2」→ 无需 Key 全市场实时监控 ✅
4. **设置 → 用户管理** 增删用户、设使用周期/暂停/延期

---

## 7. 更新代码（镜像模式）

```bash
cd /www/wwwroot/quantforge
git pull                          # 拉最新 compose / 配置文件
docker compose pull                # 拉最新镜像（TCR 内网秒级）
docker compose up -d               # 重建容器（data/ 卷不动，数据不丢）
```

> `data/` 目录（用户/行情/策略/回测/监控全部数据）通过 volume 持久化，重建容器不丢失。`git pull` 不影响 `data/`（已 gitignore）。**切勿** `git clean -fdx` / `git reset --hard`。

### 固定 / 回滚到指定版本

每次提交都生成 `sha-<commit>` tag，可固定回滚到任意历史版本。在 `.env` 设：
```ini
APP_IMAGE=ccr.ccs.tencentyun.com/quantforge/quantforge:sha-064a43a
```
然后 `docker compose pull && docker compose up -d` 即可。切回最新：注释掉 `APP_IMAGE` 这行。

### 备用：本地构建模式更新
```bash
cd /www/wwwroot/quantforge
git pull
# .env 中 APP_IMAGE= （置空）
docker compose up -d --build
```

---

## 8. 网络问题排查

| 现象 | 原因 | 解决 |
|---|---|---|
| `git clone` 卡住/超时 | GitHub 国内慢 | 方式 B 代理 或 方式 C Gitee |
| `docker compose build` 拉 `node:`/`python:` 超时 | Docker Hub 慢 | 第 1 步镜像加速；`docker pull node:20-alpine` 手动验证 |
| `docker compose pull` 慢 / 超时 | 未配 TCR 或未登录 | 见 [deploy-tcr.md](./deploy-tcr.md)；私有仓库需先 `docker login ccr.ccs.tencentyun.com` |
| `docker compose pull` 报 401/403 | TCR 登录过期 | 重新 `docker login ccr.ccs.tencentyun.com`；私有仓库必需 |
| `pip install uv` 失败 | PyPI 单源同步延迟 | Dockerfile 已三重兜底（清华→阿里→官方），重试即可 |
| `pnpm install` 慢 | npm 官方源 | 已走 npmmirror，无需处理（仅本地 build 时涉及） |
| 容器内访问 `push2.eastmoney.com` 失败 | 极少数 VPS 段被东财限流 | 切回 TickFlow 付费档；或 VPS 出口换弹性公网 |
| 容器起不来、日志报错 | 配置/端口 | `docker compose logs app` 看具体错误 |

---

## 9. 公网安全建议

- **别裸跑 3018**：宝塔 → 网站 → 反向代理，域名 + HTTPS（Let's Encrypt），反代到 `127.0.0.1:3018`
- 改密码走 UI（`设置 → 账户`），不改 `.env`
- 多用户下，超管账号用强密码，普通用户按需分配到期

---

## 附：从原 tickflow-stock-panel 单用户版迁移

若 VPS 上跑过原项目，把旧 `data/user_data/` 下的 `auth.json`、`watchlist.parquet`、`preferences.json`、`monitor_rules/` 等放到新部署的 `./data/user_data/` 下，启动时自动迁移：
- `auth.json`（单密码）→ `users.json`（admin 账号，复用旧密码哈希）
- 顶层用户态文件 → `data/user_data/admin/`（per-user 隔离）
- `secrets.json`（TickFlow Key）保留全局

迁移幂等，安全可重复。
