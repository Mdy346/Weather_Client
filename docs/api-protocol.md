# API 与协议分析基线

状态：已确认  
调研日期：2026-09-20  
官方文档更新时间：2026-09-22

## 1. 结论摘要

- 天气数据使用彩云天气 v2.6。官方明确标注 v2.6 为 Stable，v3 为 Beta。
- 彩云天气不提供城市名到经纬度的正向地理编码接口。v2.6 天气接口只能按经纬度查询；v3 当前只提供反地理编码。
- 为满足“城市名 -> 经纬度 -> 天气”的产品流程，需要一个独立的 `GeocodingProvider`。
- 地理编码实现使用 Open-Meteo Geocoding API，底层位置数据来自 GeoNames。该接口无需额外密钥，支持中文输入，位置查询与天气数据职责分离。
- 彩云综合接口 `weather` 可在一次请求中返回 `realtime`、`hourly` 和 `daily`，默认应使用该接口，避免把一次数据获取人为拆成三次请求。
- 默认使用 `unit=metric:v2`，可获得摄氏度、km/h、km 和 mm/h，避免 v1 雷达降水强度无法直接解释的问题。
- 认证只实现 App Key + App Secret 签名，不实现 Token 路径认证。
- 按彩云文档，业务流是两个依赖阶段：先获取坐标，再获取天气。当前没有两个必须并行且互不依赖的彩云天气请求。异步并发的学习会通过后端对照、测试夹具和独立并发实验完成，不滥用生产请求。

## 2. 版本与官方来源

使用的官方页面：

- 版本说明：[https://docs.caiyunapp.com/weather-api/version-guide.html](https://docs.caiyunapp.com/weather-api/version-guide.html)
- 认证文档：[https://docs.caiyunapp.com/weather-api/auth.html](https://docs.caiyunapp.com/weather-api/auth.html)
- v2.6 认证：[https://docs.caiyunapp.com/weather-api/v2/v2.6/auth.html](https://docs.caiyunapp.com/weather-api/v2/v2.6/auth.html)
- v2.6 综合天气：[https://docs.caiyunapp.com/weather-api/v2/v2.6/6-weather.html](https://docs.caiyunapp.com/weather-api/v2/v2.6/6-weather.html)
- v2.6 实况：[https://docs.caiyunapp.com/weather-api/v2/v2.6/1-realtime.html](https://docs.caiyunapp.com/weather-api/v2/v2.6/1-realtime.html)
- v2.6 小时预报：[https://docs.caiyunapp.com/weather-api/v2/v2.6/3-hourly.html](https://docs.caiyunapp.com/weather-api/v2/v2.6/3-hourly.html)
- v2.6 天级预报：[https://docs.caiyunapp.com/weather-api/v2/v2.6/4-daily.html](https://docs.caiyunapp.com/weather-api/v2/v2.6/4-daily.html)
- v2.6 错误：[https://docs.caiyunapp.com/weather-api/v2/v2.6/tables/errors.html](https://docs.caiyunapp.com/weather-api/v2/v2.6/tables/errors.html)
- v2.6 单位：[https://docs.caiyunapp.com/weather-api/v2/v2.6/tables/unit.html](https://docs.caiyunapp.com/weather-api/v2/v2.6/tables/unit.html)
- Open-Meteo Geocoding：[https://open-meteo.com/en/docs/geocoding-api](https://open-meteo.com/en/docs/geocoding-api)

## 3. 彩云天气请求协议

### 3.1 综合天气端点

```http
GET https://api.caiyunapp.com/v2.6/{credential}/{longitude},{latitude}/weather
```

路径规则：

- URL 中经度在前、纬度在后。
- 响应中的 `location` 是 `[latitude, longitude]`，顺序与请求路径相反。
- URL 路径中的 `credential` 使用 App Key。

默认查询参数：

| 参数 | 值 | 说明 |
|---|---:|---|
| `lang` | `zh_CN` | 中文展示 |
| `unit` | `metric:v2` | 摄氏度、km/h、km、mm/h |
| `alert` | `true` | 请求预警；无权限时可能不返回该块 |
| `hourlysteps` | `24` | 未来 24 小时逐小时数据 |
| `dailysteps` | `7` | 未来 7 天逐日数据 |
| `dailystart` | `0` | 从当前日开始 |

综合接口的主要响应结构：

```json
{
  "status": "ok",
  "api_version": "v2.6",
  "api_status": "active",
  "lang": "zh_CN",
  "unit": "metric:v2",
  "tzshift": 28800,
  "timezone": "Asia/Shanghai",
  "server_time": 1640758065,
  "location": [39.976, 116.3176],
  "result": {
    "realtime": {},
    "minutely": {},
    "hourly": {},
    "daily": {},
    "alert": {},
    "primary": 0,
    "forecast_keypoint": "..."
  }
}
```

`minutely` 仅在企业套餐等具备权限时返回。领域模型不能假定它始终存在。

### 3.2 认证

认证模式：App Key + App Secret。

- App Key 放在 URL 路径中的 `{credential}` 位置。
- 每个请求生成 16 到 40 位随机 `nonce`。
- 请求头包含：
  - `x-cy-nonce`
  - `x-cy-timestamp`
  - `x-cy-signature`
- 签名原文格式：

```text
{method}:{path}:{sorted_query}:{app_key}:{nonce}:{timestamp}
```

- 使用 `app_secret` 做 HMAC-SHA256。
- 签名结果使用 URL-safe Base64 编码。
- query 参与签名前必须按参数名排序，并使用与官方示例一致的 URL 编码。

配置规则：

1. `CAIYUN_APP_KEY` 和 `CAIYUN_APP_SECRET` 都是必需项。
2. 任一项缺失或为空白时，返回配置错误。
3. `AppSecret` 只用于本地签名计算，不写入 URL、日志、错误消息或测试夹具。
4. `.env` 只用于本地开发并且必须保持被 Git 忽略。

Token 路径认证不进入 MVP，也不保留兼容分支。

## 4. 响应校验规则

1. 首先检查 HTTP 状态码是否等于 200。不能只检查响应 JSON。
2. 网关故障可能返回 HTML 或纯文本，反序列化前必须验证来源和内容类型。
3. 200 响应必须是合法 JSON 对象。
4. 校验 `status == "ok"`、`api_version`、`unit` 和 `location`。
5. 请求坐标与响应坐标使用容差比较，明确处理纬经度顺序。
6. `result.realtime`、`result.hourly` 和 `result.daily` 是当前需求的必需块。
7. `result.minutely`、`result.alert`、`precipitation.nearest` 是可选块。
8. 未知字段允许忽略，以便上游增加字段时不立即破坏客户端。
9. 必需字段缺失或类型错误时，抛出带 JSONPath 的响应校验异常。
10. 温度、湿度、风速、降水和坐标需设置合理范围校验。

## 5. 错误与重试

彩云 v2.6 的错误响应样例：

```json
{
  "status": "failed",
  "error": "token is invalid",
  "api_version": "2.6"
}
```

官方状态码：

| HTTP | 含义 | 客户端动作 |
|---:|---|---|
| 200 | 成功 | 校验并转换响应 |
| 400 | Token 非法、版本非法、签名错误 | 不重试，配置或请求错误 |
| 401 | 凭证无权限 | 不重试，提示权限问题 |
| 403 | 凭证禁用或 IP 不在白名单 | 不重试，提示配置或网络环境问题 |
| 422 | 参数错误 | 不重试，修正请求参数 |
| 429 | 额度耗尽或 QPS 超限 | 读取 `Retry-After`，有限重试 |
| 500 | 服务端错误 | 有限指数退避重试 |

需要重试的传输故障：

- DNS 解析失败。
- 连接失败。
- 连接或读取超时。
- 请求发送后连接被上游中断。

默认策略：

- 单次请求超时 10 秒。
- 最多额外重试 2 次。
- 指数退避并加入随机抖动。
- 429 优先采用 `Retry-After`，但设置最大等待上限。
- 不在 GET 请求失败后盲目无限重试。

## 6. 城市到坐标的协议补充

### 6.1 彩云能力边界

彩云 v2.6 天气接口只接收经纬度。官方 v2.6 文档没有城市查询参数，也没有正向地理编码端点。v3 文档当前提供的是坐标到地址的反地理编码。

因此不能声称“输入城市后由彩云直接定位”。城市解析必须作为单独的协议适配器。

### 6.2 选定实现

```http
GET https://geocoding-api.open-meteo.com/v1/search
```

推荐参数：

| 参数 | 值 | 说明 |
|---|---:|---|
| `name` | 用户输入 | 城市或地点名称 |
| `count` | `10` | 返回最多 10 个候选 |
| `language` | `zh` | 返回中文本地化名称 |
| `format` | `json` | 结构化响应 |

响应核心字段：

| 字段 | 用途 |
|---|---|
| `id` | 地点稳定标识 |
| `name` | 地点名称 |
| `latitude`、`longitude` | WGS84 坐标 |
| `feature_code` | 地点类型 |
| `country_code`、`country` | 国家信息 |
| `admin1`、`admin2` 等 | 行政区层级 |
| `timezone` | IANA 时区 |
| `population` | 候选排序依据 |

城市选择规则：

1. 去除首尾空白并做大小写归一化。
2. 精确名称匹配优先。
3. 城市级 `feature_code` 优先，例如 `PPLC`、`PPLA`。
4. 同级候选按 `population` 降序。
5. 仅返回零个结果时抛出 `CityNotFoundError`。
6. 存在多个难以区分的候选时返回 `AmbiguousLocationError`，携带候选列表。

CLI 遇到歧义候选时：

- 文本模式列出候选名称、国家、行政区和坐标。
- JSON 模式返回结构化错误和候选列表。
- 两种模式都不进入交互式选择，退出后由用户补全省份或更完整名称。

中文输入验证：

Open-Meteo 的 `language` 参数控制返回文案的本地化语言，不限制 `name` 参数的输入语言。查询名称必须作为 UTF-8 参数交给 HTTP 客户端编码，不能手工拼接未编码 URL。

2026-09-22 已实际验证：

- `北京` 的首候选是经纬度 `39.9075, 116.39723` 的北京市。
- `上海` 或 `Shanghai` 的首候选是经纬度 `31.22222, 121.45806` 的上海市。
- `杭州`、`成都`、`西安`、`乌鲁木齐` 均能返回中国城市坐标。
- `朝阳` 返回多个中国候选，证明候选列表和退出机制是必要的。

Open-Meteo 的位置数据来源为 GeoNames。最终输出和 README 需要保留来源说明。

## 7. 领域映射

### 7.1 当前天气

| 领域字段 | 彩云 JSONPath |
|---|---|
| 温度 | `$.result.realtime.temperature` |
| 体感温度 | `$.result.realtime.apparent_temperature` |
| 相对湿度 | `$.result.realtime.humidity` |
| 天气现象 | `$.result.realtime.skycon` |
| 风速 | `$.result.realtime.wind.speed` |
| 风向 | `$.result.realtime.wind.direction` |
| 气压 | `$.result.realtime.pressure` |
| 能见度 | `$.result.realtime.visibility` |
| 本地降水强度 | `$.result.realtime.precipitation.local.intensity` |

`metric:v2` 下：

- 温度为摄氏度。
- 风速为 km/h。
- 风向为从北顺时针的角度。
- 气压为 Pa。
- 能见度为 km。
- 降水强度为 mm/h。

### 7.2 小时预报

小时级数据由多个独立数组组成，不能用固定索引直接假设所有数组长度完全相同。转换规则：

1. 以 `datetime` 建立索引。
2. 对目标字段按时间对齐。
3. 缺失项形成明确的可选值或跳过策略。
4. 输出按时间升序排列。

使用字段：

- `$.result.hourly.temperature[].value`
- `$.result.hourly.apparent_temperature[].value`
- `$.result.hourly.precipitation[].value`
- `$.result.hourly.precipitation[].probability`
- `$.result.hourly.wind[].speed`
- `$.result.hourly.wind[].direction`
- `$.result.hourly.humidity[].value`
- `$.result.hourly.skycon[].value`

### 7.3 天级预报

使用字段：

- `$.result.daily.temperature[].max`
- `$.result.daily.temperature[].min`
- `$.result.daily.precipitation[].max`
- `$.result.daily.precipitation[].probability`
- `$.result.daily.skycon[].value`
- `$.result.daily.skycon_08h_20h[].value`
- `$.result.daily.skycon_20h_32h[].value`
- `$.result.daily.astro[].sunrise.time`
- `$.result.daily.astro[].sunset.time`

## 8. 并发与执行顺序

业务请求顺序是：

```text
用户城市
  -> 地理编码请求
  -> 坐标
  -> 彩云综合天气请求
  -> 校验和领域转换
  -> 输出
```

天气请求依赖地理编码结果，因此这两步不能并行。综合接口已经包含实况、小时和天级数据，也不应为了展示 `asyncio.gather()` 而拆成三个请求。


- 核心客户端统一使用 `async/await`，网络等待期间不阻塞事件循环。
- 地理编码和天气客户端均使用异步 HTTP。
- 测试中通过模拟两个无依赖请求演示 `asyncio.gather()` 与异常聚合。
- `aiohttp` 与 `httpx` 后端通过相同契约测试保证结果一致。
- 可选开发命令可并发请求两种后端做对照，但不得成为默认用户路径，避免重复消耗 API 额度。

## 9. 已确认决策

1. 使用 Open-Meteo Geocoding 作为城市转坐标提供方。
2. 只实现 App Key + App Secret 签名认证。
3. 天气只调用彩云综合 `weather` 接口。
4. 地名有歧义时列出候选并退出，由用户补全省份或完整名称。

## 10. 协议阶段完成标准

- 每个请求都能追溯到官方协议。
- 请求参数、认证、响应壳、必选字段和可选字段有明确规则。
- 错误码与重试动作有明确对应关系。
- 城市到坐标的数据来源不再含糊。
- 领域模型字段都有来自第三方响应的映射。
- 不把依赖请求错误地设计成并发请求。
- 后续架构设计和测试样例能够直接引用本文件。
