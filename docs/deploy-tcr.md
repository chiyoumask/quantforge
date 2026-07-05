# 腾讯云 TCR 部署补充手册（内网拉取，可选）

> **本节是可选补充**。绝大多数用户（含腾讯云轻量）按 [deploy-docker.md](./deploy-docker.md) 从 Docker Hub / ghcr.io 拉镜像即可，**无需读本文档**。
>
> 仅以下场景才启用 TCR：你的服务器在腾讯云国内轻量、追求极致内网拉取速度（秒级、不计外网流量），且**你是仓库 owner**（能在 GitHub 仓库配 TCR secrets 让 CI 推 TCR）。
>
> **非 owner 的部署者无法启用**——CI 默认不推 TCR，本节对你无意义，请直接用 [deploy-docker.md](./deploy-docker.md) 的流程。

**为什么有 TCR**：Docker Hub 国内公网拉取虽可用但偶尔慢；腾讯云国内轻量走 TCR **内网域名**拉镜像可秒级完成，且不占外网流量配额。代价是 owner 需手动配 4 个 secret，且 GitHub runner 海外推 TCR 走跨境公网、可能超时（workflow 已 `timeout-minutes: 30` + `continue-on-error`，失败不阻塞 Docker Hub 主推送）。

---

## 0. 适用场景

- 腾讯云国内轻量服务器（2C2G 也能流畅运行）
- 想避免每次部署在服务器上跑 `pnpm install + vite build + uv sync`（OOM 风险）
- 不想裸拉 ghcr.io

> 海外 / 走 ghcr.io 不卡的环境**无需**配 TCR，公开镜像默认就在 ghcr.io。

---

## 1. 开通腾讯云 TCR 个人版

个人版免费、无需备案、支持轻量云内网域名。

1. 登录腾讯云控制台 → 切到「容器服务 TKE」→ 左侧「**镜像仓库**」→「**个人版**」
2. 首次进入按提示一键开通，约 1-2 分钟
3. **首次开通需设置访问凭证**：在「访问凭证」页面点「设置/重置」→ 自定义一个密码。这串密码后续作为 GitHub Secret 的 `TCR_TOKEN`。

> 个人版访问域名固定为 **`ccr.ccs.tencentyun.com`**（广州地域个人版域名，轻量云内网可达，无需任何备案）。

---

## 2. 创建命名空间 + 仓库

1. 「镜像仓库」→「命名空间」→「新建」，建议名字 `quantforge`（任意，会作为镜像路径中段）
2. 「镜像仓库」→「新建」，命名空间选 `quantforge`，仓库名 `quantforge`，类型选**公开**或**私有**皆可（私有需要在轻量云 `docker login` 才能拉，但更安全）
3. 创建完成后镜像全路径应为：
   ```
   ccr.ccs.tencentyun.com/quantforge/quantforge
   ```
   > 若用了不同的命名空间/仓库名，记得在 GitHub Secret `TCR_NAMESPACE` 里填你实际的命名空间名，且 `docker-compose.yml` 顶部注释或 `.env` 中 `APP_IMAGE` 同步调整路径。

---

## 3. 取登录凭证（填进 GitHub Secrets）

你已经创建好 `ccr.ccs.tencentyun.com/quantforge/quantforge` 仓库,控制台「镜像仓库 → quantforge」页顶部会显示**快捷指令**,长这样:

```
docker login ccr.ccs.tencentyun.com --username=100046653245
```

这串数字 `100046653245` 就是登录用户名(你的腾讯云账号 ID)。**密码**是 TCR 个人版的「访问凭证」,须先设置一次才能登录。

### 在哪里取/设访问凭证

腾讯云控制台 → 顶部搜「容器服务 TKE」→ 左侧「**镜像仓库**」→「**个人版**」→ 顶部「**访问凭证**」标签页:
- **没设过**:点「设置访问凭证」→ 输入密码(自定义,最少 8 位,含字母+数字)→ 确认 → 这串密码即 `TCR_TOKEN`
- **已设过但忘了**:点「重置访问凭证」→ 同上重设
- 设过的密码**不再明文回显**,忘记只能重置,无法找回

> 验证凭证可用:
> ```bash
> docker login ccr.ccs.tencentyun.com --username=100046653245
> # 粘贴你设置的访问凭证密码 → 看到 Login Succeeded 即成功
> ```

### 凭证 ↔ GitHub Secret 映射

| 凭证 | 取值位置 | 示例值 | 对应 GitHub Secret |
|---|---|---|---|
| 访问域名 | TCR 个人版固定 | `ccr.ccs.tencentyun.com` | `TCR_REGISTRY` |
| 命名空间 | 见第 2 步 | `quantforge` | `TCR_NAMESPACE` |
| 登录用户名 | 控制台「快捷指令」里 `--username=` 后那串数字 | `100046653245`(示例,填你的实际值) | `TCR_USERNAME` |
| 登录密码 | 「访问凭证」页设置/重置的密码(必须先设过) | 自定义, 见下文 | `TCR_TOKEN` |

> **没设过访问凭证无法登录** —— 必须**先**在「访问凭证」页设置/重置一次,再用那串密码登录、填进 `TCR_TOKEN`。

---

## 4. 配置 GitHub Secrets

在仓库页面：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

依次添加 4 个 secret（值**保密**，不会在日志中回显）：

1. `TCR_REGISTRY` = `ccr.ccs.tencentyun.com`
2. `TCR_NAMESPACE` = `quantforge`（你的命名空间）
3. `TCR_USERNAME` = 第 3 步的用户名
4. `TCR_TOKEN` = 第 1 步设置的访问凭证密码

> **未配置这些 secret 时**：`.github/workflows/docker.yml` 中的 TCR 推送 step 会**自动跳过**，仅推 ghcr。所以可以先把代码 push、之后再补 secrets，下一次 push 即开始推送 TCR，无回归风险。

---

## 5. 触发流水线

满足以下任一条件，`Build and Push Docker Image` workflow 会自动执行：

- `git push origin main`（main 分支更新）
- 打 tag：`git tag v0.1.70 && git push --tags`（生成版本镜像）
- 手动：仓库 → `Actions` → `Build and Push Docker Image` → `Run workflow`

执行成功后，Actions 页面会看到三段：
1. `Build and push to ghcr.io` ✅（永远执行）
2. `Push to Tencent Cloud TCR (optional)` ✅（配齐 4 个 secret 才出现）
3. `Build and push to TCR` ✅

TCR 控制台「镜像仓库 → quantforge → 标签」可看到推送结果，会同时存在 `latest` 与 `sha-<commit>` 两种 tag。

---

## 6. 服务器端：登录 + 拉取 + 启动

> 假设宝塔已装 Docker，并已按 `docs/bt-deploy.md` 第 2 步把仓库克隆到 `/www/wwwroot/quantforge`。

### 6.1 配置 .env

```bash
cd /www/wwwroot/quantforge
cp .env.example .env
```

编辑 `.env`，**关键是这一行无需改**（`docker-compose.yml` 默认已指向 TCR）：

```ini
# 默认指向 TCR，无需写；只在固定版本/换源时才覆盖：
# APP_IMAGE=ccr.ccs.tencentyun.com/quantforge/quantforge:latest
```

同时确认（公网部署必需）：
```ini
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<至少6位强密码>
PORT=3018
TICKFLOW_API_KEY=
# 老 VPS 无 AVX2 时取消下注释：
# BACKEND_EXTRAS=legacy-cpu
```

### 6.2 登录 TCR（若仓库设为私有）

```bash
docker login ccr.ccs.tencentyun.com
# 输入第 3 步的用户名 + 访问凭证密码
```

> 仓库设为「公开」可跳过此步，但**强烈建议私有 + 登录**，避免镜像被任意人拉取。

### 6.3 拉取并启动

```bash
cd /www/wwwroot/quantforge
git fetch && git pull --ff-only          # 同步最新 docker-compose.yml 等部署配置
docker compose pull                       # 秒级拉取(轻量云内网)
docker compose up -d                      # 启动 (不再 --build)
docker compose logs -f app               # 看到 "ready; N capabilities active" 即成功
```

> 第 1 次拉取约 1-3 分钟（镜像 1-2GB，内网很快），之后每次只拉增量层，通常 < 10 秒。

---

## 7. 更新部署（日常）

服务器上不再需要任何构建：

```bash
cd /www/wwwroot/quantforge
git pull                                   # 拉最新 compose / 配置文件
docker compose pull                        # 拉最新镜像
docker compose up -d                       # 重建并切到新容器
```

> `data/` 卷不动，用户/行情/监控/回测数据全部保留。**切勿** `git clean -fdx` 或 `git reset --hard`。

---

## 8. 版本固定 / 回滚

每次提交都生成一个 `sha-<commit>` tag，可固定回到任意历史版本。

在 `.env` 设：
```ini
APP_IMAGE=ccr.ccs.tencentyun.com/quantforge/quantforge:sha-064a43a
```
然后：
```bash
docker compose pull
docker compose up -d
```

切回最新版：把 `.env` 中 `APP_IMAGE` 注释掉（或设回 `:latest`）再 `docker compose pull && up -d`。

---

## 9. 排错

| 现象 | 原因 | 解决 |
|---|---|---|
| CI 中没看到 TCR 推送 step | 4 个 secret 未配全 | 按「§4 配置 GitHub Secrets」补齐；下一次 push 即生效 |
| CI 报 `unauthorized: authentication required` | `TCR_USERNAME` 或 `TCR_TOKEN` 写错 | 在控制台「访问凭证」页核对，必要时重置后更新 secret |
| CI 报 `repository does not exist or access denied` | 命名空间 / 仓库名对不上 | `TCR_NAMESPACE` 必须与控制台命名空间一致；CI 路径要为 `<registry>/<namespace>/quantforge` |
| 服务器 `docker compose pull` 401 / 403 | 私有仓库未登录或登录过期 | `docker login ccr.ccs.tencentyun.com` 重新登录 |
| 服务器 `pull` 仍慢 | 走了公网而非内网 | 确认登录用的域名是 `ccr.ccs.tencentyun.com`（轻量云内网域名）。若轻量云与 TCR 不在同一地域，改用同地域 |
| 镜像拉通但起不来 | 配置/端口 | `docker compose logs app` 看具体错误 |
| 想换回 ghcr 兜底 | — | `.env` 设 `APP_IMAGE=ghcr.io/chiyoumask/quantforge:latest` 后 `pull && up -d` |
| 紧急情况想本地 build | 服务器无法联网 | `.env` 设 `APP_IMAGE=`(空) → `docker compose up -d --build` |

---

## 10. 配套：保留公开 ghcr.io 路径

仓库公开，所有镜像都会同时推到：

- `ghcr.io/chiyoumask/quantforge:latest`
- `ghcr.io/chiyoumask/quantforge:sha-<commit>`

任何能拉 ghcr.io 的环境（海外服务器、CI 复用）都能直接用，无需任何 secret。TCR 只是给国内轻量云加的一条快速路，**完全可选**。
