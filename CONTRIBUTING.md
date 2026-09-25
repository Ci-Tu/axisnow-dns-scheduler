# 贡献指南

欢迎提交 Issue 和 Pull Request。

## 开发环境

- Python 3.10+，Node.js 20.19+
- 后端：`cd backend && pip install -e ".[dev]"`
- 前端：`cd frontend && npm install`

提交前请确保以下命令全部通过（CI 会执行同样的检查）：

```bash
cd backend && ruff check . && pytest
cd frontend && npm run build        # 包含 vue-tsc 类型检查
```

## 代码约定

- **后端**：路由只做参数解析与响应组装，业务逻辑放 `services/`，与 AxisNow / Cloudflare 的交互只经过 `clients/`。
  用户输入错误抛 `ValidationError` 或 `ApiError`，由蓝图统一转换成 JSON 响应，不要在路由里写 try/except。
- **写配置**只能通过 `config_store.mutate()`：它在副本上修改、全程持锁，中途抛异常不会留下半截状态。
- **任何「读后写」**（先读规则再 PUT 回去）必须使用新鲜数据：`axisnow()` 默认就是，只有纯展示接口才传 `stale=True`。
- **凭据**永远不写日志、不返回前端；错误信息只包含上游返回的摘要。
- **前端**：所有显示 IP 的地方使用 `IpBadge`，线路使用 `LineTag`，颜色只用 `styles/base.css` 里的设计令牌。
- 新行为要有测试。后端测试使用 `tests/conftest.py` 里的 `FakeAxisNow`，不会访问真实 API。

## 新增功能模块

1. 在 `backend/axisnow_scheduler/features/` 新建 `xxx.py`，继承 `Feature`，填写 `id / name / description / order`。
2. 实现：
   - `applicable(ctx)`：返回 `(是否可用, 不可用原因)`；
   - `desired(cfg, ctx)`：返回 `Desired` 增量，`None` 表示此刻不表态；
   - 可选 `default_config()`、`summary()`、`validate()`。
3. 在 `features/__init__.py` 中 `register(XxxFeature())`。

`ctx.ip_pool` 是线上当前顺序；`ctx.order_in_progress()` 是前面功能已经合并出的候选顺序——
需要叠加在其它功能之上时用后者。`order` 越大越晚合并，可以覆盖前面的决定。

简单的开关型配置可以直接通过 `POST /api/rules/<uuid>/features/<id>/config` 保存；
需要专门编辑器的功能，参考潮汐调度（`api/rules.py` 的 tide 接口与前端 `TideEditor.vue`）。

## 提交信息

一行简短说明做了什么，必要时空一行后补充原因。中英文均可。
