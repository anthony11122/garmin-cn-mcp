# 佳明 Garmin Connect × 小米澎湃OS 4.0 (HyperOS 4.0) 专属 MCP 服务

<p align="center">
  <b>针对小米澎湃OS 4.0（Xiaomi HyperOS 4.0+）及超级小爱同学原生深度定制的 Model Context Protocol (MCP) 服务</b><br>
  无需依赖任何外部服务器或内网环境，手机端直接运行，实现佳明健康数据读取、秒级全自动中继 Intervals.icu 与科学耐力决策。
</p>

---

> ⚠️ **【重要系统要求】**
> **本服务仅适用于运行 小米澎湃OS 4.0（Xiaomi HyperOS 4.0）及以上版本的设备。**
> 小米从 **HyperOS 4.0** 起，才在系统底层原生引入了端侧 MCP（Model Context Protocol）服务框架，并打通超级小爱同学智能体工具调用链。低于 4.0 的旧版本系统（如 HyperOS 1.0 / 2.0 / 3.0 或传统 MIUI）未开放系统级 MCP 服务管理入口，无法直接通过系统设置添加原生 MCP 服务。

---

## 💡 为什么需要本服务？

1. **HyperOS 4.0 原生端侧承载，彻底告别服务器束缚**：
   传统佳明中继方案往往需要在家庭 NAS、树莓派或 VPS 上常驻搭建 Python/Docker 服务，一旦离开家庭局域网或服务器宕机便无法使用。**本项目专为小米澎湃OS 4.0 原生设计，由手机端独立调度运行，随身随行，零外部基础设施依赖**。
2. **佳明国区生态与 Intervals.icu 完美打通**：
   - 佳明手表的强项是 **底层原始生理指标精确采集**（睡眠分期、夜间 HRV、静息心率、体能电量、活动 FIT）；
   - Intervals.icu 的强项是 **专业耐力建模分析**（CTL 体能、ATL 疲劳、TSB 竞技状态、有氧心率漂移解耦）；
   - 本服务将两者端到端粘合，**实现全自动秒级中继（无需手动导出导入任何文件）**。
3. **超级小爱原生语音交互**：
   只需对小爱同学说一句话，自动完成后台跨区数据推送或评估今日训练负荷。

---

## ✨ 核心能力与工具清单 (共 24 个 Tools)

### 1. 自动化中继与智能训练决策（手机端 / 小爱核心工具）

| 工具 | 协议/来源 | 功能说明 |
|:---|:---|:---|
| `auto_sync_to_icu` | Garmin ➔ ICU | **【全自动一键秒级中继】** 一键抓取佳明健康指标（睡眠分、HRV、静息心率、步数、卡路里）推送到 Intervals.icu；自动比对未收录运动并静默上传原始 FIT 压缩包，返回最新负荷报告。 |
| `get_today_readiness_and_training_advice` | 综合分析 | **【今日晨报与训练决策】** 联动昨夜佳明深睡/HRV 恢复指标与 ICU Form (TSB) 负荷值，向小爱同学直接输出今日能否跑高强度间歇、是否需排酸慢跑或休息的专业建议。 |
| `get_icu_fitness_curve` | Intervals.icu | 查询近期 **CTL（体能）、ATL（疲劳）、TSB（表现/状态）** 曲线与爬升率（Ramp Rate）。 |
| `get_activity_decoupling` | Intervals.icu | 深度诊断单次长距离运动的 **心率漂移有氧解耦率 (Aerobic Decoupling)**，精准评估心率与配速是否匹配，防范耐力透支。 |

### 2. 佳明国区原生数据读取 (20 个工具全量支持)

| 类别 | 工具 | 说明 |
|:---|:---|:---|
| 🏃 运动 | `get_activities` / `get_activities_by_date` | 运动记录列表检索 |
| | `get_activity` / `get_activity_details` | 运动详情与细分指标 |
| | `get_activity_splits` / `get_activity_hr_zones` | 每公里分段配速与心率区间 |
| | `get_last_activity` / `get_activity_types` | 最近运动与支持运动类型 |
| 📊 训练 | `get_training_status` / `get_training_readiness` | 佳明训练状态与训练准备度 |
| 💤 生理 | `get_sleep` / `get_hrv` | 睡眠得分、分期及夜间心率变异性 |
| | `get_stress` / `get_spo2` / `get_respiration` | 压力均值、血氧浓度与呼吸频率 |
| 👤 设备 | `get_profile` / `get_devices` / `get_primary_device` | 个人资料与主训练设备 |
| 🏅 资产 | `get_earned_badges` / `get_gear` | 勋章徽章与跑鞋装备里程 |

---

## 🚀 小米澎湃OS 4.0 (HyperOS 4.0) 接入指南

在搭载 **小米澎湃OS 4.0** 的设备上，进入系统设置或超级小爱管理中心：

### 1. 服务基本信息
- **系统版本**：确认系统为 **Xiaomi HyperOS 4.0 或更高版本**
- **服务名称**：`佳明小爱助手`（或 `garmin-hyperos`）
- **代码仓库/源**：`https://github.com/anthony11122/garmin-hyperos-mcp`
- **执行入口**：`python garmin_hyperos_mcp.py`

### 2. 环境变量配置
在手机端添加服务时，直接填入以下环境变量凭据：

```bash
# 佳明国区账号
GARMIN_CN_EMAIL=your-garmin-email@example.com
GARMIN_CN_PASSWORD=your-garmin-password

# Intervals.icu 配置 (可在 https://intervals.icu/settings 获取)
INTERVALS_API_KEY=your-intervals-api-key
INTERVALS_ATHLETE_ID=0  # 填 0 或具体运动员 ID（如 i12345）
```

*(服务支持自动从手机本地 `.env` 文件读取，也可以在添加时直接填入环境变量)*

### 3. 标准客户端配置示例 (`mcp_config.json`)
若使用支持配置文件导入的 MCP 客户端：

```json
{
  "mcpServers": {
    "garmin-hyperos": {
      "command": "python",
      "args": ["garmin_hyperos_mcp.py"],
      "env": {
        "GARMIN_CN_EMAIL": "your-garmin-email@example.com",
        "GARMIN_CN_PASSWORD": "your-garmin-password",
        "INTERVALS_API_KEY": "your-intervals-api-key",
        "INTERVALS_ATHLETE_ID": "0"
      }
    }
  }
}
```

---

## 🗣️ 小爱同学语音对话示范 (HyperOS 4.0)

在 HyperOS 4.0 中成功绑定后，唤醒小爱同学即可实现自然语言驱动的运动健康自动化：

- 🗣️ **“小爱，帮我把佳明数据同步到 ICU”**
  ➔ 小爱自动调用 `auto_sync_to_icu(days=1)`，1~2 秒内自动拉取睡眠、HRV、步数与运动 FIT 上传至 Intervals.icu。
- 🗣️ **“小爱，我今天身体状态能跑间歇吗？”**
  ➔ 小爱自动调用 `get_today_readiness_and_training_advice()`，根据昨晚深睡恢复质量与当前 Form (TSB) 指标，告知适宜跑间歇、排酸慢跑还是充分休息。
- 🗣️ **“小爱，分析一下我今天跑步的心率漂移”**
  ➔ 小爱自动调用 `get_activity_decoupling()`，播报后半程有氧解耦率，提示有氧耐力基础与补水建议。
- 🗣️ **“小爱，查一下我昨晚的睡眠和 HRV 数据”**
  ➔ 小爱自动调用 `get_sleep()` 和 `get_hrv()` 播报睡眠阶段和平均心率变异性。

---

## 🛠️ 技术实现特性

1. **OAuth 免密会话持久化**：
   采用 `garth OAuth` 认证层（针对佳明国区 `domain=garmin.cn` 优化），在手机首次成功鉴权后将安全 Token 持久化存储。后续请求全部走免密 Token 刷新，即使长久不打开也不会频繁失效。
2. **多源配置自适应**：
   内置 `_load_env_fallback()` 容错加载机制，自适应查找脚本同级目录 `.env`、用户主目录 `.env` 与系统环境变量，杜绝手机端子进程拿不到环境变量导致的认证失败。
3. **双通道支持**：
   默认以高效的标准 `stdio` 管道与手机宿主交互；同时支持 `--sse` 模式，满足多场景灵活扩展。

---

## 📄 开源许可证
MIT License
