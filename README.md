# Garmin Connect China MCP Server（上游修复版）

> **本仓库是 [xinyuxinyuxintaihaohao/garmin-cn-mcp](https://github.com/xinyuxinyuxintaihaohao/garmin-cn-mcp) 的修复版（fork 意义上的下游修复分支，独立维护）。**
>
> 上游的登录实现（`sso.garmin.cn/mobile/api/login` 取 ticket → `connect.garmin.cn/modern?ticket=...` 换 session）已于 2026 年 8 月被佳明下线：消费 ticket 时会被重定向到新版 `/signin/` 页面，导致所有 API 调用 401。
>
> 本修复版将认证层整体迁移到 **garth OAuth**（`garminconnect` 同源的底层库，官方支持国区 `domain=garmin.cn`），工具层 20 个接口保持不变。已在真实国区账号上完成端到端验证（2026-08-30）。

佳明中国大陆版 (garmin.cn) 的 MCP 数据读取服务。

通过 MCP (Model Context Protocol) 协议，让 AI 助手可以直接读取你的佳明健康和运动数据。

## 与上游的差异

| 项目 | 上游 (xinyuxinyuxintaihaohao) | 本修复版 |
|------|------------------------------|----------|
| 登录方式 | CAS ticket + `/gc-api/` 代理 + curl_cffi TLS 伪装（已失效） | garth OAuth1/OAuth2（`domain=garmin.cn`） |
| 会话持久化 | cookie 缓存 4 小时 | garth token 落盘（`~/.hermes/garmin_tokens/garth_cn`），过期自动刷新、失效自动重登 |
| 依赖 | mcp, curl_cffi | mcp(<2), garth |
| 凭据注入 | 仅环境变量 | 环境变量 + `~/.hermes/.env` 兜底自读（MCP 子进程常拿不到环境变量时的保底） |
| 工具数量 | 20 | 20（接口签名不变） |

## 功能

| 类别 | 工具 | 说明 |
|------|------|------|
| 🏃 运动 | `get_activities` | 运动列表 |
| | `get_activities_by_date` | 按日期查运动 |
| | `get_activity` | 运动详情 |
| | `get_activity_details` | 运动详细数据 |
| | `get_activity_splits` | 每公里配速 |
| | `get_activity_hr_zones` | 心率区间 |
| | `get_activity_types` | 运动类型列表 |
| | `get_last_activity` | 最近一次运动 |
| 📊 训练 | `get_training_status` | 训练状态/VO2 Max |
| | `get_training_readiness` | 训练准备度 |
| 👤 资料 | `get_profile` | 用户信息 |
| | `get_devices` | 设备列表 |
| | `get_primary_device` | 主训练设备 |
| 💤 睡眠 | `get_sleep` | 睡眠数据/得分/阶段 |
| ❤️ HRV | `get_hrv` | 心率变异性 |
| 😰 压力 | `get_stress` | 全天压力数据 |
| 🩸 血氧 | `get_spo2` | SpO2 数据 |
| 🫁 呼吸 | `get_respiration` | 呼吸频率 |
| 🏅 其他 | `get_earned_badges` | 已获徽章 |
| | `get_gear` | 装备数据 |

## 安装

```bash
git clone https://github.com/anthony11122/garmin-cn-mcp.git
cd garmin-cn-mcp

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

依赖说明：

- `mcp>=1.0.0,<2` — 代码基于 v1 的 `FastMCP` API；mcp 2.x 已将其改名，装 2.x 会 `ModuleNotFoundError`
- `garth>=0.8.0` — Garmin OAuth 认证（国区 `domain=garmin.cn`）

## 配置

凭据通过环境变量注入，**绝不要写进任何提交到仓库的文件**：

```bash
# ~/.hermes/.env（权限建议 chmod 600）
GARMIN_CN_EMAIL=your-garmin-email@example.com
GARMIN_CN_PASSWORD=your-password
```

### Hermes Agent 配置

```bash
hermes mcp add garmin-cn --command /path/to/garmin-cn-mcp/.venv/bin/python --args /path/to/garmin-cn-mcp/garmin_cn_mcp.py
```

### 其他 MCP 客户端

```json
{
  "mcpServers": {
    "garmin-cn": {
      "command": "python3",
      "args": ["/path/to/garmin_cn_mcp.py"],
      "env": {
        "GARMIN_CN_EMAIL": "your-garmin-email@example.com",
        "GARMIN_CN_PASSWORD": "your-password"
      }
    }
  }
}
```

## 使用示例

配置好后，AI 助手可以直接查询你的佳明数据：

- "我昨天睡得怎么样？"
- "最近一周的运动记录"
- "今天的 HRV 和压力数据"
- "我的训练状态和 VO2 Max"

## 技术细节

### 认证流程（本修复版）

1. 磁盘有 garth token → `garth.resume()` 恢复会话，探活成功即免登录
2. token 缺失/失效 → 环境变量（或 `~/.hermes/.env` 兜底）读取账号密码 → `garth.configure(domain="garmin.cn")` + `garth.login()`
3. 登录成功后 `garth.save()` 落盘 token；会话中 API 401/异常时自动重登一次

### API 路径

| 数据类型 | API 路径 |
|---------|---------|
| 运动列表 | `/activitylist-service/activities/search/activities` |
| 运动详情 | `/activity-service/activity/{id}` |
| 睡眠数据 | `/wellness-service/wellness/dailySleepData?date=` |
| HRV | `/hrv-service/hrv/{date}` |
| 压力 | `/wellness-service/wellness/dailyStress/{date}` |
| 血氧 | `/wellness-service/wellness/daily/spo2/{date}` |
| 呼吸 | `/wellness-service/wellness/daily/respiration/{date}` |

## 许可证

MIT License
