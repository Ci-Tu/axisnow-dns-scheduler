# AxisNow DNS Scheduler

[English](README.en.md) · 简体中文

一个自托管的 [AxisNow](https://axisnow.io) DNS 路由控制台，外加可插拔的自动调度引擎。

- **替代官方控制台的日常操作**：调度域、路由规则、线路（境内 / 境外 / 运营商）、地址池、拨测模板，一处管理；登录一次保持 180 天，容器重建也不掉线。
- **官方没有的能力**：
  - **潮汐调度**：按时间段自动切换 IP 优先级顺序（如晚高峰切到另一条线路）；
  - **拨测故障切换**：探针发现某个 IP 不可用时自动降到末尾，恢复后自动归位；
  - **统一探针向导**：为自建服务器生成可用的 HTTP 拨测模板，清理重复拨测任务；
  - **Cloudflare 一键接入**：在自己的域名上创建指向调度域的 CNAME（强制仅 DNS）。
- **每个 IP 都带国旗与运营商**：基于 DB-IP Lite 离线数据库，自动识别，无需手工维护。

> 本项目与 AxisNow 官方无关，使用其公开的客户端 API。

## 快速开始

需要 Docker 与 Docker Compose。

```bash
git clone https://github.com/Ci-Tu/axisnow-dns-scheduler.git
cd axisnow-dns-scheduler
cp .env.example .env        # 可选，按需修改端口、时区、运行用户
docker compose up -d --build
```

打开 `http://<服务器>:4894`，首次访问设置访问密码，然后在「设置」里填入 AxisNow API Token。

所有运行数据都在 `./data`（配置、会话密钥、运行历史、GeoIP 数据），**请持久化并备份这个目录**。

### 配置项

全部通过环境变量（或 `.env`）设置，都是可选的：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `4894` | 宿主机端口 |
| `PUID` / `PGID` | `1000` | 容器内运行用户；启动时会把 `data/` 的属主修正为它 |
| `APP_TIMEZONE` | `Asia/Shanghai` | 潮汐时间段按这个时区生效 |
| `AXISNOW_API_TOKEN` | — | 通过环境变量提供 Token，设置后界面不可修改，也不会写入磁盘 |
| `CLOUDFLARE_API_TOKEN` | — | 同上，Cloudflare 需要 `Zone → DNS → Edit` 权限 |
| `GEOIP_AUTO_DOWNLOAD` | `1` | 自动下载并每月更新 DB-IP Lite 数据库，`0` 关闭 |
| `SESSION_DAYS` | `180` | 登录态保持天数 |
| `DISABLE_SCHEDULER` | `0` | `1` 时只提供 Web 界面，不跑调度和采样（用于只读 / 调试实例） |

## 工作原理

```
          ┌──────────── 浏览器（Vue 3 单页应用）────────────┐
          │  仪表盘 · 域名与规则 · 调度 · 拨测 · Cloudflare   │
          └───────────────────────┬─────────────────────────┘
                                  │ /api（JSON）
┌─────────────────────────────────┴───────────────────────────────────┐
│ Flask                                                               │
│  api/        按领域拆分的路由，统一错误处理、登录与 CSRF 校验          │
│  services/   规则构建、视图模型、GeoIP、后台任务                       │
│  clients/    AxisNow / Cloudflare 客户端 + 共享读缓存（stale-while-revalidate）│
│  features/   可插拔功能模块：潮汐调度、拨测故障切换 …                  │
│  scheduler   每轮：拉规则 → 各功能求解 → 合并 → 有变化才下发             │
│  storage/    config.json（配置）+ history.db（SQLite：采样与下发记录）  │
└─────────────────────────────────────────────────────────────────────┘
```

几个关键设计：

- **读缓存分两级**：后端对上游只读请求做 20 秒新鲜缓存；展示类接口在 10 分钟内可以先返回旧值并后台刷新，页面几乎不需要等待上游。任何「读后写」路径（编辑、下发）一律读新鲜数据，不会基于过期规则覆盖线上。
- **调度只在需要时写入**：每轮算出目标顺序的指纹，与上次下发一致就跳过；线上本来就是目标状态时也不写。
- **功能模块可叠加**：多个功能按 `order` 依次求解，后面的功能在前面的结果之上继续调整（例如先按时间段定顺序，再把故障 IP 挪到末尾）。

## 新增一个功能模块

在 `backend/axisnow_scheduler/features/` 下新建文件，继承 `Feature`：

```python
class QuietHoursFeature(Feature):
    id = "quiet_hours"
    name = "闲时降 TTL"
    order = 30

    def applicable(self, ctx):         # 这条规则能不能用
        return True, ""

    def desired(self, cfg, ctx):       # 想把它改成什么样；None 表示不表态
        return Desired(ip_order=ctx.order_in_progress())
```

然后在 `features/__init__.py` 里 `register(QuietHoursFeature())`。调度引擎、规则详情页的功能开关会自动识别它。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 从 1.x 升级

直接用新版本替换代码、保留原来的 `data/` 目录即可，首次启动会自动完成迁移：

- `config.json` 原样沿用（新增 `ip_labels` 字段）；
- `probe_history.json` 导入 SQLite 后改名为 `probe_history.json.migrated`；
- `servers.json` 里的节点名称导入为全局 IP 名称（国旗与运营商改为自动识别，不再需要手写）；
- 会话密钥不变，已登录的浏览器无需重新登录。

## 本地开发

```bash
# 后端
cd backend
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
DATA_DIR=./.devdata flask --app axisnow_scheduler.wsgi run --port 4894
pytest && ruff check .

# 前端（另开终端，/api 会代理到 4894）
cd frontend
npm install
npm run dev
```

## 致谢

- IP 地理数据：[IP Geolocation by DB-IP](https://db-ip.com)（CC BY 4.0）
- 国旗图标：[flag-icons](https://github.com/lipis/flag-icons)（MIT）

## 许可证

[MIT](LICENSE)
