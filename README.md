# Garmin Connect China & Intervals.icu MCP Server

> **本仓库是基于 [xinyuxinyuxintaihaohao/garmin-cn-mcp](https://github.com/xinyuxinyuxintaihaohao/garmin-cn-mcp) 演进的深度集成版。**
> 
> 1. **认证修复**：将已被佳明下线的 CAS ticket 方式整体迁移至 **garth OAuth**（`domain=garmin.cn`），完美支持佳明国区账号与 token 自动持久化。
> 2. **深度集成 Intervals.icu**：新增全自动中继同步引擎（自动抓取睡眠/HRV/步数/卡路里及原始 FIT 运动文件推送到 ICU）。
> 3. **AI 决策与负荷分析**：新增 **CTL / ATL / TSB 耐力负荷模型**、心率漂移有氧解耦率分析及一键智能训练准备度建议。
> 4. **小米 HyperOS 4.0 适配**：支持标准 stdio 模式以及 SSE HTTP 远程服务模式，方便小爱同学 / 手机端 AI 助手直连调用。

---

## 核心功能

### 1. 自动化中继与智能训练决策（HyperOS 核心入口）

| 工具 | 协议/来源 | 功能说明 |
|:---|:---|:---|
| `auto_sync_to_icu` | Garmin ➔ ICU | **【全自动一键中继】** 自动抓取佳明健康数据及未收录的运动 FIT 压缩包，推送到 Intervals.icu 并返回最新负荷 |
| `get_today_readiness_and_training_advice` | 综合分析 | **【手机晨报/决策专属】** 联动佳明睡眠/HRV 与 ICU Form (TSB) 指标，输出今日能否冲间歇、是否需排酸慢跑的专业建议 |
| `get_icu_fitness_curve` | Intervals.icu | 获取近期 **CTL（体能）、ATL（疲劳）、TSB（Form 表现）** 趋势数据及 Ramp Rate |
| `get_activity_decoupling` | Intervals.icu | 获取单次运动的 **有氧解耦率 (Aerobic Decoupling)**，评估心率漂移与有氧耐力储备 |

### 2. 佳明国区原生数据读取 (20 个原生 Tools)

| 类别 | 工具 | 说明 |
|:---|:---|:---|
| 🏃 运动 | `get_activities` / `get_activities_by_date` | 运动记录列表检索 |
| | `get_activity` / `get_activity_details` | 运动详情与细分指标 |
| | `get_activity_splits` / `get_activity_hr_zones` | 分段配速与心率区间 |
| | `get_last_activity` / `get_activity_types` | 最近运动与支持运动类型 |
| 📊 训练 | `get_training_status` / `get_training_readiness` | 佳明训练状态与训练准备度 |
| 💤 生理 | `get_sleep` / `get_hrv` | 睡眠得分、分期及夜间心率变异性 |
| | `get_stress` / `get_spo2` / `get_respiration` | 压力均值、血氧浓度与呼吸频率 |
| 👤 设备 | `get_profile` / `get_devices` / `get_primary_device` | 个人资料与主训练设备 |
| 🏅 资产 | `get_earned_badges` / `get_gear` | 勋章徽章与跑鞋等装备里程 |

---

## 安装与部署

```bash
git clone https://github.com/anthony11122/garmin-cn-mcp.git
cd garmin-cn-mcp

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 依赖项
- `mcp>=1.0.0,<2` — 基于 FastMCP 规范构建
- `garth>=0.8.0` — 佳明国区 OAuth 认证与 token 管理
- `requests>=2.28.0` — Intervals.icu REST API 交互

---

## 环境变量配置

凭据可通过环境变量注入，或写入 `~/.hermes/.env` 中（程序会自动回退读取）：

```bash
# 佳明国区账号
GARMIN_CN_EMAIL=your-garmin-email@example.com
GARMIN_CN_PASSWORD=your-password

# Intervals.icu 账号（可选，若不配置则优雅降级为纯佳明模式）
INTERVALS_API_KEY=your-intervals-api-key
INTERVALS_ATHLETE_ID=0  # 填 0 或具体运动员 ID
```

---

## 小米 HyperOS 4.0 接入方式

小米澎湃 OS 4.0 原生支持连接 MCP 服务，推荐以下两种方式：

### 方式 A：局域网/服务器常驻 SSE 模式（最省电、最推荐）
在家庭 NAS、内网服务器（如 `10.23.5.4`）或 VPS 上后台运行 SSE 服务：

```bash
python garmin_cn_mcp.py --sse
# 默认监听 0.0.0.0:8000
```

在 HyperOS 4.0 的 MCP 设置中填入服务地址：
```
http://10.23.5.4:8000/sse
```
*手机无需安装 Python 环境，省电且无需在手机存储明文密码。*

### 方式 B：手机本地 Termux / Stdio 模式
在手机 Termux 环境中直接配置 stdio 调用：

```json
{
  "mcpServers": {
    "garmin-icu": {
      "command": "/data/data/com.termux/files/usr/bin/python",
      "args": ["/path/to/garmin_cn_mcp.py"],
      "env": {
        "GARMIN_CN_EMAIL": "your-email",
        "GARMIN_CN_PASSWORD": "your-password",
        "INTERVALS_API_KEY": "your-icu-key",
        "INTERVALS_ATHLETE_ID": "0"
      }
    }
  }
}
```

---

## 常用语音/AI 提问示例

- 🗣️ **“小爱，帮我把昨天的佳明运动和睡眠同步到 ICU”**
  - AI 触发 `auto_sync_to_icu(days=1)`，全自动拉取佳明数据，上传 FIT，并同步健康指标。
- 🗣️ **“小爱，我今天身体状态怎么样，可以跑间歇吗？”**
  - AI 触发 `get_today_readiness_and_training_advice()`，结合昨夜睡眠分数、HRV 和 ICU 的 Form (TSB) 提供精准训练决策。
- 🗣️ **“分析一下我上次长距离跑步的心率漂移”**
  - AI 触发 `get_activity_decoupling()`，输出有氧解耦率百分比与耐力耐受度评估。

---

## 许可证
MIT License
