# 架构设计

状态：已确认  
设计日期：2026-09-22  
Python 基线：3.12+

## 1. 架构目标

客户端需要在保持功能简单的同时，完整展示以下工程边界：

- CLI、应用服务、第三方协议和 HTTP 传输分离。
- `aiohttp` 与 `httpx` 可以互换，但上层不感知其差异。
- 第三方 JSON 先通过 Pydantic 校验，再映射为稳定的领域模型。
- 认证、重试、日志和错误转换各自有明确归属。
- 核心逻辑可以在不访问网络的情况下测试。
- 不把有依赖关系的地理编码和天气请求错误地并行化。

## 2. 总体分层

```text
CLI / Renderer
      |
      v
WeatherService
      |
      +---------------------+
      |                     |
      v                     v
GeocodingProvider     WeatherProvider
      |                     |
      v                     v
OpenMeteoGeocoder     CaiyunWeatherProvider
                            |
                            v
                       CaiyunAuth
                            |
                            v
                AsyncHttpTransport Protocol
                       /            \
                      v              v
             AiohttpTransport   HttpxTransport
```

依赖方向只能从上到下。领域模型和错误类型不依赖具体 HTTP 库。

## 3. 目录结构

```text
Weather_Client/
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
├── uv.lock
├── docs/
│   ├── api-protocol.md
│   └── architecture.md
├── src/
│   └── weather_client/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── errors.py
│       ├── logging.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── domain.py
│       │   ├── caiyun.py
│       │   └── geocoding.py
│       ├── geocoding/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── open_meteo.py
│       ├── http/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── aiohttp_transport.py
│       │   ├── httpx_transport.py
│       │   ├── request.py
│       │   └── retry.py
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── caiyun.py
│       │   └── caiyun_auth.py
│       ├── services/
│       │   ├── __init__.py
│       │   └── weather_service.py
│       └── rendering/
│           ├── __init__.py
│           ├── text.py
│           └── json.py
└── tests/
    ├── fixtures/
    ├── unit/
    ├── contract/
    ├── integration/
    └── e2e/
```

## 4. 核心接口

### 4.1 地理编码

```python
class GeocodingProvider(Protocol):
    async def search(self, query: str) -> list[LocationCandidate]: ...
```

职责：

- 调用 Open-Meteo Geocoding。
- 将响应校验为地理编码 DTO。
- 转换为 `LocationCandidate`。
- 不负责选择最终城市，最终唯一性判断由应用服务完成。

### 4.2 天气提供方

```python
class WeatherProvider(Protocol):
    async def fetch_report(self, location: Location) -> WeatherReport: ...
```

职责：

- 构建彩云综合天气请求。
- 使用 `CaiyunAuth` 生成签名。
- 通过抽象 HTTP 传输发送请求。
- 校验彩云响应并映射为 `WeatherReport`。

### 4.3 HTTP 传输

```python
class AsyncHttpTransport(Protocol):
    async def request(self, request: RequestSpec) -> HttpResponse: ...
```

`RequestSpec` 至少包含：

- `method`
- `url`
- `params`
- `headers`
- `timeout`

`HttpResponse` 至少包含：

- `status_code`
- `headers`
- `content_type`
- `body`

传输层只负责发送请求和返回原始响应。JSON 解析、第三方状态码解释和领域转换不放在传输层。

### 4.4 应用服务

```python
class WeatherService:
    async def get_report(self, city: str) -> WeatherReport: ...
```

执行顺序：

1. 规范化和校验城市输入。
2. 调用地理编码。
3. 对候选排序。
4. 唯一候选时选择坐标。
5. 多个难以区分时抛出 `AmbiguousLocationError`。
6. 无候选时抛出 `CityNotFoundError`。
7. 调用彩云综合天气接口。
8. 返回 `WeatherReport`。

## 5. 领域模型

领域模型使用 Pydantic v2，但保持与第三方字段名隔离。

核心模型：

- `Coordinates`
- `LocationCandidate`
- `Location`
- `CurrentWeather`
- `HourlyForecast`
- `DailyForecast`
- `WeatherAlert`
- `WeatherReport`
- `WeatherSource`

关键约束：

- 纬度范围 `[-90, 90]`。
- 经度范围 `[-180, 180]`。
- 湿度范围 `[0, 1]`。
- 降水概率范围 `[0, 100]`。
- 时间使用带时区的 `datetime`。
- 日期使用 `date`。
- 单位写入字段名或模型说明，不在格式化阶段猜测单位。
- `None` 只表示上游合法可选字段，不能用于掩盖解析失败。

## 6. 协议 DTO 与映射

彩云和 Open-Meteo 各有一组 Pydantic DTO，专门描述原始响应。

规则：

- DTO 字段名尽量反映原始 JSON。
- 未知字段默认忽略，防止上游新增字段导致客户端失效。
- 必需字段缺失时产生结构化校验错误。
- 映射函数独立放置，不能把第三方字段名扩散到服务和 CLI。
- 小时预报按 `datetime` 对齐，不能依赖多个数组具有相同索引。

## 7. 认证设计

`CaiyunAuth` 只接受 `SecretStr` 类型的 AppSecret。

请求签名流程：

1. 生成 UUID 风格 nonce。
2. 生成 Unix 秒时间戳。
3. 对 query 参数名和值做规范化 URL 编码。
4. 按参数名排序并构造签名原文。
5. 使用 HMAC-SHA256 和 AppSecret 计算签名。
6. 使用 URL-safe Base64 编码。
7. 写入 `x-cy-nonce`、`x-cy-timestamp`、`x-cy-signature`。

安全要求：

- AppSecret 不进入 `repr`、异常、日志或序列化输出。
- 请求日志默认隐藏签名和认证头。
- App Key 出现在请求路径中，日志中仍应遮盖。
- 单元测试使用固定假凭证，不使用真实凭证。

## 8. 错误体系

```text
WeatherClientError
├── ConfigError
├── InputError
├── GeocodingError
│   ├── CityNotFoundError
│   └── AmbiguousLocationError
├── TransportError
│   ├── NetworkError
│   ├── RequestTimeoutError
│   └── HttpStatusError
├── UpstreamAuthError
├── RateLimitError
├── ResponseDecodeError
├── ResponseValidationError
└── UpstreamServiceError
```

异常必须保留安全的上下文：

- 第三方服务名。
- 请求阶段。
- HTTP 状态码。
- 有界重试次数。
- 字段 JSONPath。

不得记录：

- AppSecret。
- 完整签名头。
- 未脱敏的认证 URL。

建议 CLI 退出码：

| 退出码 | 含义 |
|---:|---|
| 0 | 成功 |
| 2 | 命令参数错误 |
| 3 | 配置错误 |
| 4 | 城市未找到 |
| 5 | 城市候选有歧义 |
| 6 | 网络或超时错误 |
| 7 | 上游鉴权或权限错误 |
| 8 | 上游限流或服务错误 |
| 9 | 响应解析或校验错误 |
| 10 | 未处理内部错误 |

## 9. 异步与并发

- `asyncio.run()` 只出现在 CLI 入口。
- 所有 HTTP 调用通过 `async/await` 执行。
- `aiohttp.ClientSession` 和 `httpx.AsyncClient` 都必须在单次运行中复用。
- 使用 `async with` 保证连接正常释放。
- 重试等待使用 `asyncio.sleep()`，不能使用 `time.sleep()`。
- 两个传输后端共享相同契约测试。
- 线程用于解释阻塞 I/O 的对照实验，不进入默认生产路径。
- 不为展示并发而拆分彩云综合接口。

## 10. 重试与超时

`RetryPolicy` 是独立组件，负责：

- 判断错误是否可重试。
- 计算指数退避。
- 加入随机抖动。
- 读取并遵守 429 的 `Retry-After`。
- 限制总尝试次数和最大等待时间。

默认值：

- 总尝试次数：3 次，即首次请求加 2 次重试。
- 单次总超时：10 秒。
- 不可重试：400、401、403、422 和响应校验错误。

## 11. 日志与输出

- 正常业务输出写标准输出。
- 日志写标准错误。
- `--json` 模式下标准输出必须是纯 JSON。
- 日志采用结构化字段，至少包含事件名、阶段、耗时和重试次数。
- 默认日志不输出完整第三方响应，避免隐私和体积问题。
- 调试完整响应需要显式开关，并先进行敏感字段脱敏。

## 12. 依赖边界

运行时依赖：

- `pydantic`
- `pydantic-settings`
- `aiohttp`
- `httpx`

开发与测试依赖：

- `pytest`
- `pytest-asyncio`
- `respx`
- `aioresponses`
- `ruff`
- `mypy`

依赖选择会在项目初始化阶段通过 `uv` 或 `poetry` 落实。本机当前安装 Python 3.12.11，但尚未安装 `uv` 或 `poetry`。

## 13. 测试策略

单元测试：

- 签名计算与官方示例。
- 查询参数排序和 URL 编码。
- 候选排序和歧义判断。
- Pydantic 模型边界。
- 彩云 DTO 到领域模型的映射。
- 错误分类和退出码。

契约测试：

- `aiohttp` 与 `httpx` 对相同 `RequestSpec` 产生等价结果。
- 相同响应夹具经过两个后端后得到相同领域模型。

集成测试：

- 模拟 Open-Meteo 的成功、无结果和错误响应。
- 模拟彩云 200、400、401、403、422、429、500 和非法 JSON。
- 验证重试次数、退避和 `Retry-After`。

端到端测试：

- 通过 CLI 调用注入的假提供方。
- 验证文本和 JSON 输出、退出码、标准错误日志。

真实网络测试：

- 使用 `live` 标记。
- 默认不执行。
- 只读取本地环境变量中的轮换后凭证。
- 不对真实接口进行高频重试测试。

## 14. 已确认决策

1. 接受本架构和目录结构。
2. 包管理器使用 `uv`。
3. 控制台命令名称使用 `weather`。
4. 接受默认退出码表。

## 15. 架构阶段完成标准

- 每层职责和允许依赖方向明确。
- 两个 HTTP 后端有统一接口。
- 第三方协议与领域模型分离。
- 认证、重试、日志和错误处理有独立边界。
- 异步执行与依赖顺序符合真实协议。
- 测试策略覆盖单元、契约、集成和端到端。
- 项目初始化可以直接按照目录和依赖设计执行。
