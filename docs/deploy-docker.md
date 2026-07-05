# 镜像分发与拉取指南

本项目镜像由 GitHub Actions 自动构建并推送到 **Docker Hub + ghcr.io**，国内国外服务器都能拉，不绑死任何云厂商；腾讯云国内轻量想走内网的用户，可额外启用 TCR 推送（见末节）。

> 改造后的链路：本地 `git push` → GitHub Actions 自动 `build & push` → 服务器 `docker compose pull && up -d`，**服务器不再 build**。

---

## 0. 镜像仓库与默认地址

| 用途 | 仓库 | 默认镜像地址 |
|---|---|---|
| 主分发(国内外通用) | Docker Hub | `docker.io/chiyoumask/quantforge` |
| 备用(GitHub 内置) | GitHub Container Registry | `ghcr.io/chiyoumask/quantforge` |
| 可选(腾讯云内网) | 腾讯云 TCR 个人版 | `ccr.ccs.tencentyun.com/<ns>/quantforge` |

`docker-compose.yml` 默认 `image: docker.io/chiyoumask/quantforge:latest`，可在 `.env` 用 `APP_IMAGE=` 覆盖到任意 registry。

### 可用 tag

- `:latest` —— 最新 main 分支构建，multi-arch（amd64 + arm64 自动适配本机）
- `:sha-<commit>` —— 对应某次提交，固定版本回滚用
- `:v0.1.70` —— 打了 `v*` tag 时生成的语义版本

每次成功 push 到 main，workflow 会自动产出 `latest` + `sha-<commit>`；打 tag 会额外产出 `:v*`。

---

## 1. 服务器拉取运行（通用流程）

适用任何能用 Docker 的服务器，国内国外皆可。

### 1.1 拉代码 + 配 .env

```bash
cd /www/wwwroot          # 或你想放的目录
git clone https://github.com/chiyoumask/quantforge.git
cd quantforge
cp .env.example .env
```

编辑 `.env`：
```ini
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<至少6位强密码>
PORT=3018
TICKFLOW_API_KEY=
# 老 VPS 无 AVX2 时取消下注释：
# BACKEND_EXTRAS=legacy-cpu
```

**Docker Hub 的公开镜像无需 docker login 即可拉**——`.env` 不需要任何 registry 配置。

### 1.2 拉镜像启动

```bash
docker compose pull                       # 从 Docker Hub 拉镜像
docker compose up -d                      # 启动
docker compose logs -f app               # 看到 "ready; N capabilities active" 即成功
```

浏览器 `http://<服务器IP>:3018`，用 `.env` 里的超管账号登录。

### 1.3 国内服务器拉取速度

Docker Hub 国内拉取通常 1-5 MB/s，2-3 GB 镜像约 1-3 分钟。**抢不到 / 慢** 的解决：

1. 配 Docker 镜像加速器（宝塔 Docker → 设置 → 加速器）：
   ```
   https://mirror.ccs.tencentyun.com        # 腾讯云轻量内网
   https://docker.m.daocloud.io
   https://docker.1panel.live
   ```
   或写入 `/etc/docker/daemon.json`：
   ```json
   {
     "registry-mirrors": [
       "https://mirror.ccs.tencentyun.com",
       "https://docker.m.daocloud.io"
     ]
   }
   ```
   `systemctl restart docker` 后再 `docker compose pull`。

2. 走 ghcr.io 公开镜像（网络好时偶尔比 Docker Hub 快）：在 `.env` 设
   ```ini
   APP_IMAGE=ghcr.io/chiyoumask/quantforge:latest
   ```
   再 `docker compose pull`。

3. 走腾讯云 TCR 内网（仅腾讯云国内轻量用户，需作者在 CI 配 TCR secret；见末节）。

---

## 2. 更新部署（日常）

```bash
cd /www/wwwroot/quantforge
git pull                                   # 拉最新 compose / 配置文件
docker compose pull                        # 拉最新镜像
docker compose up -d                       # 重建并切到新容器
```

> `data/` 卷不动，用户/行情/监控/回测数据全部保留。**切勿** `git clean -fdx` 或 `git reset --hard`。

### 固定/回滚到指定版本

每次提交都生成 `sha-<commit>` tag，`.env` 设：
```ini
APP_IMAGE=docker.io/chiyoumask/quantforge:sha-2472496
```
然后 `docker compose pull && docker compose up -d` 即回滚到对应 commit。切回最新：注释掉该行。

---

## 3. 架构说明

`docker pull :latest` 会自动选择匹配本机的架构：
- x86_64 服务器（绝大多数 VPS、轻量服务器）→ 拉到 amd64 镜像
- ARM 服务器（部分云 ARM 实例、树莓派等）→ 拉到 arm64 镜像

CI 是用 GitHub 原生 `ubuntu-24.04-arm` runner 跑 arm64 构建的（非 QEMU 模拟），构建质量稳。

> 想强制只拉某一架构：在镜像名后加 `@sha256:<digest>` 或用 `--platform=linux/amd64`。一般无需这么做。

---

## 4. 排错

| 现象 | 原因 | 解决 |
|---|---|---|
| `docker compose pull` 报 unauthorized | Docker Hub 偶发限流 | `docker login docker.io`（即使无账号也能匿名拉，登录可去除匿名限流） |
| Docker Hub 拉取慢/超时 | 国内公网拉 docker.io 慢 | §1.3 配镜像加速器；或改 `APP_IMAGE=ghcr.io/...` |
| ghcr.io 拉取慢/超时 | 国内拉 ghcr 偶有抖动 | 切回 Docker Hub + 镜像加速器；或腾讯云用户走 TCR |
| `docker compose up` 后没起来 | 配置/端口 | `docker compose logs app` 看具体错误 |
| 想本地 build 兜底 | 想现场改 Dockerfile 验证 | `.env` 设 `APP_IMAGE=`(空) → `docker compose up -d --build` |

---

## 5. 可选：腾讯云 TCR 内网拉取（仅腾讯云国内轻量用户）

腾讯云国内轻量服务器拉 TCR 走**内网域名**，秒级、不计外网流量。适合不想配 Docker Hub 加速器、又想最快的腾讯云用户。

### 5.1 启用步骤（仓库 owner 操作）

镜像默认不推 TCR。仓库 owner 想推到 TCR 需在 GitHub 仓库 Settings → Secrets 配 4 个：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

- `TCR_REGISTRY` = `ccr.ccs.tencentyun.com`
- `TCR_NAMESPACE` = `<你的 TCR 命名空间>`
- `TCR_USERNAME` = TCR 控制台「快捷指令」里 `--username=` 后那串数字（腾讯云账号 ID）
- `TCR_TOKEN` = TCR「访问凭证」页设置/重置的密码

### 5.2 服务器端切换到 TCR

`.env` 覆盖：
```ini
APP_IMAGE=ccr.ccs.tencentyun.com/<namespace>/quantforge:latest
```
私有仓库需先登录：
```bash
docker login ccr.ccs.tencentyun.com
```
之后照常 `docker compose pull && docker compose up -d`。

### 5.3 注意事项

- GitHub runner 海外推 TCR 走跨境公网，可能慢或超时；workflow 已加 `timeout-minutes: 30` + `continue-on-error: true`，**TCR 推送失败不会阻塞 Docker Hub/ghcr 的主推送**。失败可手动 Re-run。
- 非 owner 的部署者**用不到**这一节，照常从 Docker Hub 拉即可。

完整 TCR 配置手册见 [deploy-tcr.md](./deploy-tcr.md)。
