# Weather Client

天气客户端：Python 异步工程化学习项目。

业务流程：

```text
用户输入城市 -> Open-Meteo Geocoding 解析坐标 -> 彩云天气 v2.6 综合接口取数 -> 校验与渲染
```

开发过程覆盖 `asyncio`、`aiohttp`、`httpx`、Pydantic、重试、日志和测试。

当前状态：项目初始化完成，核心功能开发中。CLI 目前只提供 `--version`。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## 初始化

```powershell
uv sync
```

`uv sync` 会创建 `.venv`、安装依赖并校验 `uv.lock`。需要严格复现锁定的版本时使用：

```powershell
uv sync --frozen
```

创建本地环境变量文件：

```powershell
Copy-Item .env.example .env
```

然后在 `.env` 中填写彩云凭证。`.env` 已被 Git 忽略，不要提交。

## 开发检查

改动后至少跑一遍这三条：

```powershell
uv run ruff check .
uv run mypy src
uv run pytest
```

## 运行

```powershell
uv run weather --version
```

## 目录结构

```text
src/weather_client/
├── cli.py          # 命令行入口
├── config.py       # 配置与凭证加载
├── errors.py       # 错误体系
├── logging.py      # 日志配置
├── geocoding/      # 城市 -> 坐标
├── http/           # aiohttp / httpx 传输后端
├── models/         # 领域模型与协议 DTO
├── providers/      # 彩云天气实现与签名
├── rendering/      # 文本与 JSON 输出
└── services/       # 应用服务编排
```

## 文档

- `docs/api-protocol.md`：彩云与 Open-Meteo 接口协议、认证、错误与重试规则
- `docs/architecture.md`：分层设计、接口契约、错误体系与测试策略

## 数据来源

- 天气数据：彩云天气 v2.6（https://caiyunapp.com）
- 地理编码：Open-Meteo Geocoding API，底层位置数据来自 GeoNames
