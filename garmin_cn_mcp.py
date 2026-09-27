#!/usr/bin/env python3
"""
Garmin Connect China & Intervals.icu MCP Server
通过 MCP 协议实现：
1. 佳明中国大陆版 (garmin.cn) 的健康与运动数据读取
2. Intervals.icu 专业耐力负荷模型 (CTL/ATL/TSB) 与运动解耦分析
3. 佳明与 Intervals.icu 的全自动端到端中继同步（健康数据、原始 FIT 文件）
"""

import os
import re
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple

import requests
from mcp.server.fastmcp import FastMCP

# ─── 初始化 MCP 服务器 ───────────────────────────────────────────
mcp = FastMCP(
    "garmin-cn-icu",
    instructions=(
        "佳明国区与 Intervals.icu 运动健康与自动同步中继服务。"
        "提供睡眠/HRV/活动数据读取、自动将佳明数据与 FIT 文件中继推送到 Intervals.icu、"
        "并提供 CTL/ATL/TSB 耐力负荷与心率漂移解耦分析。"
    ),
)

logger = logging.getLogger("garmin_cn_mcp")

# ─── 凭据与持久化目录 ──────────────────────────────────────────
_token_dir = Path.home() / ".hermes" / "garmin_tokens"
_token_dir_cn = _token_dir / "garth_cn"
_env_loaded = False


def _load_env_fallback():
    """自动加载 .env 中的配置，确保在各种 MCP 宿主环境下免配直接运行"""
    global _env_loaded
    if _env_loaded:
        return
    candidates = [
        Path(__file__).parent / ".env",
        Path.home() / ".hermes" / ".env",
        Path.home() / ".env"
    ]
    for env_file in candidates:
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
            except Exception:
                pass
    _env_loaded = True


_load_env_fallback()

# ─── Garmin Connect (garth OAuth 会话管理) ──────────────────────
_garth_ready = False
_display_name_cache = None


def _get_display_name() -> str:
    """获取佳明用户的 displayName（用于 usersummary 等核心端点）"""
    global _display_name_cache
    if _display_name_cache:
        return _display_name_cache
    try:
        p = _api_get("/userprofile-service/socialProfile") or {}
        _display_name_cache = p.get("displayName") or ""
        return _display_name_cache
    except Exception:
        return ""


def _get_garmin_session():
    """获取已认证的 garth 客户端（模块级缓存 + 磁盘 token 复用）"""
    global _garth_ready
    if _garth_ready:
        return

    import garth

    _token_dir.mkdir(parents=True, exist_ok=True)

    # 1) 尝试从磁盘 token 恢复会话（免登录）
    if (_token_dir_cn / "oauth1_token.json").exists():
        try:
            garth.resume(str(_token_dir_cn))
            garth.connectapi("/userprofile-service/socialProfile")
            garth.save(str(_token_dir_cn))
            _garth_ready = True
            return
        except Exception:
            pass  # Token 失效，走重新登录

    # 2) 账号密码登录（国区 domain=garmin.cn）
    email = os.environ.get("GARMIN_CN_EMAIL") or os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_CN_PASSWORD") or os.environ.get("GARMIN_PASSWORD")

    if not email or not password:
        raise RuntimeError(
            "未配置佳明账号密码。请在环境变量或 ~/.hermes/.env 中添加:\n"
            "  GARMIN_CN_EMAIL=你的佳明邮箱\n"
            "  GARMIN_CN_PASSWORD=密码"
        )

    garth.configure(domain="garmin.cn")
    garth.login(email, password)
    garth.save(str(_token_dir_cn))
    _garth_ready = True


def _api_get(path: str, backend: str = "gc-api") -> Any:
    """通过 garth OAuth 调用国区 connect API"""
    import garth
    from urllib.parse import parse_qsl

    _get_garmin_session()

    if "?" in path:
        path, _, qs = path.partition("?")
        params = dict(parse_qsl(qs))
    else:
        params = {}

    try:
        return garth.connectapi(path, params=params)
    except Exception:
        global _garth_ready
        _garth_ready = False
        _get_garmin_session()
        return garth.connectapi(path, params=params)


def _api_download(path: str) -> bytes:
    """通过 garth 下载二进制数据（例如运动 FIT 压缩包）"""
    import garth

    _get_garmin_session()
    try:
        return garth.client.download(path)
    except Exception:
        global _garth_ready
        _garth_ready = False
        _get_garmin_session()
        return garth.client.download(path)


# ─── Intervals.icu 客户端封装 ────────────────────────────────────
class IntervalsClient:
    BASE_URL = "https://intervals.icu/api/v1"

    def __init__(self):
        pass

    @property
    def athlete_id(self) -> str:
        _load_env_fallback()
        return (os.environ.get("INTERVALS_ATHLETE_ID") or "0").strip()

    @property
    def api_key(self) -> str:
        _load_env_fallback()
        return (os.environ.get("INTERVALS_API_KEY") or "").strip()

    @property
    def auth(self) -> Tuple[str, str]:
        return ("API_KEY", self.api_key)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def test_connection(self) -> Tuple[bool, str, Optional[dict]]:
        if not self.is_configured:
            return False, "未配置 INTERVALS_API_KEY", None
        try:
            url = f"{self.BASE_URL}/athlete/{self.athlete_id}/profile"
            res = requests.get(url, auth=self.auth, timeout=10)
            if res.status_code == 200:
                data = res.json()
                name = data.get("name") or "Athlete"
                real_id = data.get("id") or self.athlete_id
                return True, f"成功连接 Intervals.icu (运动员: {name}, ID: {real_id})", data
            return False, f"连接失败 (HTTP {res.status_code}): {res.text[:100]}", None
        except Exception as e:
            return False, f"请求异常: {e}", None

    def upload_wellness(self, date_str: str, payload: dict) -> Tuple[bool, str]:
        if not self.is_configured:
            return False, "未配置 INTERVALS_API_KEY"
        try:
            url = f"{self.BASE_URL}/athlete/{self.athlete_id}/wellness/{date_str}"
            body = {
                "id": date_str,
                "restingHR": payload.get("resting_hr"),
                "hrv": payload.get("hrv"),
                "sleepSecs": payload.get("sleep_duration_seconds"),
                "sleepScore": payload.get("sleep_score"),
                "avgSleepingHR": payload.get("avg_sleep_hr"),
                "steps": payload.get("steps"),
                "kcalConsumed": payload.get("calories"),
            }
            body = {k: v for k, v in body.items() if v is not None}
            res = requests.put(url, auth=self.auth, json=body, timeout=12)
            if res.status_code in [200, 201]:
                return True, "健康数据成功同步至 Intervals.icu"
            return False, f"上传失败 (HTTP {res.status_code}): {res.text[:100]}"
        except Exception as e:
            return False, f"上传异常: {e}"

    def get_wellness(self, oldest: str, newest: str) -> Optional[List[dict]]:
        if not self.is_configured:
            return None
        try:
            url = f"{self.BASE_URL}/athlete/{self.athlete_id}/wellness?oldest={oldest}&newest={newest}"
            res = requests.get(url, auth=self.auth, timeout=12)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception:
            return None

    def upload_activity(self, fit_bytes: bytes, filename: str) -> Tuple[bool, Optional[str]]:
        if not self.is_configured:
            return False, None
        try:
            url = f"{self.BASE_URL}/athlete/{self.athlete_id}/activities"
            files = {"file": (filename, fit_bytes, "application/octet-stream")}
            res = requests.post(url, auth=self.auth, files=files, timeout=30)
            if res.status_code in [200, 201]:
                data = res.json()
                return True, str(data.get("id"))
            return False, None
        except Exception:
            return False, None

    def get_activity(self, icu_act_id: str) -> Optional[dict]:
        if not self.is_configured or not icu_act_id:
            return None
        try:
            url = f"{self.BASE_URL}/activity/{icu_act_id}"
            res = requests.get(url, auth=self.auth, timeout=12)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception:
            return None

    def get_activities(self, oldest: str, newest: str) -> Optional[List[dict]]:
        if not self.is_configured:
            return None
        try:
            url = f"{self.BASE_URL}/athlete/{self.athlete_id}/activities?oldest={oldest}&newest={newest}"
            res = requests.get(url, auth=self.auth, timeout=12)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception:
            return None


icu_client = IntervalsClient()


# ─── 辅助函数 ───────────────────────────────────────────────────
def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _jd(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
# 自动化中继与智能训练准备度工具 (HyperOS 核心入口)
# ═══════════════════════════════════════════════════════════════════


@mcp.tool()
def auto_sync_to_icu(days: int = 1, sync_activities: bool = True) -> str:
    """【全自动一键中继】自动抓取佳明健康与运动数据，并同步上传到 Intervals.icu。

    自动执行流水线：
    1. 提取指定天数内佳明睡眠、HRV、静息心率、步数、卡路里，上传至 Intervals.icu 每日健康日历；
    2. 检查佳明最近的运动记录，若 Intervals.icu 尚未收录，自动下载原始 FIT 文件并推送到 ICU；
    3. 同步后立即拉取 ICU 最新的 CTL/ATL/TSB 负荷指标；
    4. 返回清晰的同步简报。

    Args:
        days: 回溯同步的天数（默认1天，即今天和昨天）
        sync_activities: 是否自动下载并同步运动 FIT 文件（默认 True）
    """
    if not icu_client.is_configured:
        return _jd({
            "success": False,
            "message": "未配置 Intervals.icu 凭据。请在环境变量或 ~/.hermes/.env 中添加 INTERVALS_API_KEY 与 INTERVALS_ATHLETE_ID。"
        })

    report = {
        "sync_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "wellness_synced": [],
        "activities_synced": [],
        "current_fitness": None,
        "errors": []
    }

    # 1. 批量同步 Wellness 健康数据
    for i in range(days, -1, -1):
        d_str = _days_ago(i)
        try:
            # 抓取睡眠
            sleep_data = _api_get(f"/wellness-service/wellness/dailySleepData?date={d_str}") or {}
            daily_sleep = sleep_data.get("dailySleepDTO") or {}
            sleep_duration = daily_sleep.get("sleepTimeSeconds")
            scores = daily_sleep.get("sleepScores") or {}
            sleep_score = scores.get("overall", {}).get("value")

            # 抓取 HRV
            hrv_data = _api_get(f"/hrv-service/hrv/{d_str}") or {}
            hrv_summary = hrv_data.get("hrvSummary") or {}
            hrv_last_night = hrv_summary.get("lastNightAvg")

            # 抓取日常概览 (步数、静息心率、热量)
            disp_name = _get_display_name()
            if disp_name:
                user_summary = _api_get(f"/usersummary-service/usersummary/daily/{disp_name}?calendarDate={d_str}") or {}
            else:
                user_summary = _api_get(f"/usersummary-service/usersummary/daily/{d_str}") or {}
            steps = user_summary.get("totalSteps")
            calories = user_summary.get("totalKilocalories")
            resting_hr = user_summary.get("restingHeartRate")
            min_hr = user_summary.get("minHeartRate")

            payload = {
                "resting_hr": resting_hr,
                "hrv": hrv_last_night,
                "sleep_duration_seconds": sleep_duration,
                "sleep_score": sleep_score,
                "avg_sleep_hr": min_hr,
                "steps": steps,
                "calories": calories
            }

            ok, msg = icu_client.upload_wellness(d_str, payload)
            if ok:
                report["wellness_synced"].append({
                    "date": d_str,
                    "sleep_score": sleep_score,
                    "hrv": hrv_last_night,
                    "resting_hr": resting_hr,
                    "steps": steps
                })
            else:
                report["errors"].append(f"Wellness [{d_str}]: {msg}")
        except Exception as e:
            report["errors"].append(f"Wellness [{d_str}] 异常: {e}")

    # 2. 检查并同步运动 FIT 文件
    if sync_activities:
        try:
            # 获取佳明最近 5 条活动
            activities = _api_get("/activitylist-service/activities/search/activities?start=0&limit=5") or []
            
            # 获取 ICU 现有活动对比去重
            start_date = _days_ago(days + 2)
            end_date = _today()
            icu_acts = icu_client.get_activities(start_date, end_date) or []
            icu_act_names = {a.get("name"): a.get("id") for a in icu_acts if isinstance(a, dict)}

            for act in activities:
                act_id = str(act.get("activityId"))
                act_name = act.get("activityName")
                act_start = (act.get("startTimeLocal") or "")[:10]

                # 若已有或重名则跳过
                if act_name in icu_act_names:
                    continue

                try:
                    # 从佳明下载原始 FIT 压缩包
                    fit_bytes = _api_download(f"/download-service/files/activity/{act_id}")
                    if fit_bytes and len(fit_bytes) > 100:
                        ok, new_icu_id = icu_client.upload_activity(fit_bytes, f"garmin_{act_id}.zip")
                        if ok:
                            report["activities_synced"].append({
                                "garmin_id": act_id,
                                "icu_id": new_icu_id,
                                "name": act_name,
                                "date": act_start
                            })
                except Exception as ex:
                    report["errors"].append(f"运动 {act_id} 上传失败: {ex}")
        except Exception as e:
            report["errors"].append(f"拉取运动列表异常: {e}")

    # 3. 拉取最新的 CTL / ATL / TSB 状态
    today_w = icu_client.get_wellness(_days_ago(1), _today())
    if today_w and isinstance(today_w, list) and len(today_w) > 0:
        latest = today_w[-1]
        ctl = latest.get("ctl")
        atl = latest.get("atl")
        tsb = (round(ctl - atl, 1)) if (ctl is not None and atl is not None) else None
        report["current_fitness"] = {
            "date": latest.get("id"),
            "fitness_ctl": ctl,
            "fatigue_atl": atl,
            "form_tsb": tsb,
            "ramp_rate": latest.get("rampRate")
        }

    return _jd(report)


@mcp.tool()
def get_today_readiness_and_training_advice() -> str:
    """【手机端晨报/决策专属】获取今日训练准备度、昨夜睡眠与耐力负荷综合建议。

    自动调用佳明获取睡眠与 HRV，并联动 Intervals.icu 计算当前 Form（TSB 状态），
    直接向小爱同学/AI助手输出今日能否冲间歇、是否需排酸慢跑或休息的专业建议。
    """
    _load_env_fallback()
    today_str = _today()
    yesterday_str = _days_ago(1)

    result = {
        "date": today_str,
        "garmin_wellness": {},
        "intervals_model": None,
        "advice": ""
    }

    # 1. 抓取昨夜睡眠与 HRV
    try:
        sleep_data = _api_get(f"/wellness-service/wellness/dailySleepData?date={yesterday_str}") or {}
        daily_sleep = sleep_data.get("dailySleepDTO") or {}
        scores = daily_sleep.get("sleepScores") or {}
        sleep_score = scores.get("overall", {}).get("value")
        sleep_sec = daily_sleep.get("sleepTimeSeconds") or 0

        hrv_data = _api_get(f"/hrv-service/hrv/{yesterday_str}") or {}
        hrv_summary = hrv_data.get("hrvSummary") or {}

        result["garmin_wellness"] = {
            "sleep_score": sleep_score,
            "sleep_duration_hours": round(sleep_sec / 3600, 1),
            "hrv_last_night": hrv_summary.get("lastNightAvg"),
            "hrv_status": hrv_summary.get("status"),
            "hrv_weekly_avg": hrv_summary.get("weeklyAvg")
        }
    except Exception as e:
        result["garmin_wellness"]["error"] = str(e)

    # 2. 如果配置了 Intervals.icu，获取负荷模型
    form_val = None
    if icu_client.is_configured:
        w_list = icu_client.get_wellness(_days_ago(14), today_str) or []
        valid_items = [w for w in w_list if w.get("ctl") is not None or w.get("atl") is not None]
        if valid_items:
            latest = valid_items[-1]
            ctl = latest.get("ctl")
            atl = latest.get("atl")
            tsb = (round(ctl - atl, 1)) if (ctl is not None and atl is not None) else None
            form_val = tsb
            result["intervals_model"] = {
                "date": latest.get("id"),
                "fitness_ctl": ctl,
                "fatigue_atl": atl,
                "form_tsb": tsb,
                "ramp_rate": latest.get("rampRate")
            }

    # 3. 智能训练建议生成
    advice_lines = []
    sc = result["garmin_wellness"].get("sleep_score")
    if sc:
        if sc >= 80:
            advice_lines.append(f"昨夜睡眠得分 {sc} 分（充沛），神经系统恢复良好。")
        elif sc >= 65:
            advice_lines.append(f"昨夜睡眠得分 {sc} 分（一般），建议关注日间体能消耗。")
        else:
            advice_lines.append(f"昨夜睡眠仅 {sc} 分（欠佳），今日强烈避免大强度刺激。")

    if form_val is not None:
        if form_val > 15:
            advice_lines.append(f"当前 Form (TSB) 为 +{form_val}（极度充沛/状态过渡），体能处于竞技峰值或处于停训恢复期。")
        elif -10 <= form_val <= 15:
            advice_lines.append(f"当前 Form (TSB) 为 {form_val:+0.1f}（最佳训练区间 Optimal），极适宜进行节奏跑、间歇跑或常规有氧累积。")
        elif -30 <= form_val < -10:
            advice_lines.append(f"当前 Form (TSB) 为 {form_val:+0.1f}（疲劳累积 Overreaching），建议穿插轻松跑或主动恢复。")
        else:
            advice_lines.append(f"当前 Form (TSB) 为 {form_val:+0.1f}（重度疲劳 High Risk），过度训练风险高，应强制休息。")
    elif icu_client.is_configured:
        advice_lines.append("已连接 Intervals.icu。今日负荷尚未计算，建议触发 auto_sync_to_icu 自动同步最新数据。")
    else:
        advice_lines.append("未配置 Intervals.icu，仅基于佳明睡眠生成建议。建议配置 API Key 获取 CTL/ATL/TSB 负荷建模。")

    result["advice"] = " ".join(advice_lines)
    return _jd(result)


@mcp.tool()
def get_icu_fitness_curve(days: int = 14) -> str:
    """获取 Intervals.icu 的体能、疲劳、Form (TSB) 趋势曲线。

    Args:
        days: 回溯天数（默认14天）
    """
    if not icu_client.is_configured:
        return _jd({"error": "未配置 INTERVALS_API_KEY"})

    start = _days_ago(days)
    end = _today()
    w_list = icu_client.get_wellness(start, end)
    if not w_list:
        return _jd({"message": "未查询到负荷数据"})

    curve = []
    for item in w_list:
        ctl = item.get("ctl")
        atl = item.get("atl")
        tsb = (round(ctl - atl, 1)) if (ctl is not None and atl is not None) else None
        curve.append({
            "date": item.get("id"),
            "fitness_ctl": ctl,
            "fatigue_atl": atl,
            "form_tsb": tsb,
            "resting_hr": item.get("restingHR"),
            "hrv": item.get("hrv"),
            "ramp_rate": item.get("rampRate")
        })

    return _jd({"athlete_id": icu_client.athlete_id, "days": len(curve), "curve": curve})


@mcp.tool()
def get_activity_decoupling(activity_id: str) -> str:
    """获取单次运动的心率漂移与有氧解耦率分析 (Aerobic Decoupling)。

    有氧解耦率用来衡量在恒定配速/功率下，后半程心率是否显著漂移：
    - 解耦率 < 5%: 心率与配速高度匹配，表明拥有优秀的有氧耐力基础；
    - 解耦率 > 5%: 出现明显心率漂移，提示有氧耐力储备不足、脱水、体温过高或过度疲劳。

    Args:
        activity_id: Intervals.icu 中的活动ID（如果输入的是佳明活动ID，将自动尝试匹配）
    """
    if not icu_client.is_configured:
        return _jd({"error": "未配置 INTERVALS_API_KEY"})

    act = icu_client.get_activity(activity_id)
    if not act:
        # 尝试按名称匹配最近的活动
        recent_acts = icu_client.get_activities(_days_ago(14), _today()) or []
        for a in recent_acts:
            if str(a.get("id")) == str(activity_id) or activity_id in (a.get("name") or ""):
                act = a
                break

    if not act:
        return _jd({"error": f"在 Intervals.icu 未找到活动 {activity_id}"})

    decoupling = act.get("decoupling")
    icu_load = act.get("icu_training_load")
    ef = act.get("icu_efficiency_factor")

    analysis = {
        "id": act.get("id"),
        "name": act.get("name"),
        "start_time": act.get("start_date_local"),
        "type": act.get("type"),
        "duration_min": round((act.get("moving_time") or 0) / 60, 1),
        "distance_km": round((act.get("distance") or 0) / 1000, 2),
        "avg_hr": act.get("average_heartrate"),
        "training_load": icu_load,
        "efficiency_factor": ef,
        "aerobic_decoupling_pct": decoupling,
        "evaluation": ""
    }

    if decoupling is not None:
        if decoupling < 5.0:
            analysis["evaluation"] = f"解耦率为 {decoupling:.1f}% (<5%)：极佳！心率与动力输出高度一致，有氧基础非常扎实。"
        elif decoupling < 8.0:
            analysis["evaluation"] = f"解耦率为 {decoupling:.1f}% (5%~8%)：轻微心率漂移，属于正常长距离有氧消耗。"
        else:
            analysis["evaluation"] = f"解耦率为 {decoupling:.1f}% (>8%)：心率显著漂移！后半程心率攀升，提示脱水、糖原耗竭或耐力短板。"

    return _jd(analysis)


# ═══════════════════════════════════════════════════════════════════
# 佳明原生基础数据 Tools (保持 100% 完整与兼容)
# ═══════════════════════════════════════════════════════════════════


@mcp.tool()
def get_profile() -> str:
    """获取佳明用户资料（姓名、单位制等）"""
    profile = _api_get("/userprofile-service/socialProfile")
    settings = _api_get("/userprofile-service/userprofile/user-settings")
    return _jd({
        "profile": profile,
        "settings": {
            "measurementSystem": settings.get("userData", {}).get("measurementSystem"),
            "timeZone": settings.get("userData", {}).get("timeZone"),
        },
    })


@mcp.tool()
def get_devices() -> str:
    """获取已绑定的佳明设备列表"""
    return _jd(_api_get("/device-service/deviceregistration/devices"))


@mcp.tool()
def get_primary_device() -> str:
    """获取主训练设备信息"""
    return _jd(_api_get("/web-gateway/device-info/primary-training-device"))


@mcp.tool()
def get_activities(start: int = 0, limit: int = 20) -> str:
    """获取最近的运动记录列表

    Args:
        start: 起始索引（从0开始），默认0
        limit: 返回数量，默认20，最大50
    """
    limit = min(limit, 50)
    return _jd(_api_get(f"/activitylist-service/activities/search/activities?start={start}&limit={limit}"))


@mcp.tool()
def get_activities_by_date(start: str = "", end: str = "", activity_type: str = "") -> str:
    """按日期范围获取运动记录

    Args:
        start: 开始日期 YYYY-MM-DD，默认7天前
        end: 结束日期 YYYY-MM-DD，默认今天
        activity_type: 运动类型过滤，如 running, cycling, strength_training 等（可选）
    """
    start = start or _days_ago(7)
    end = end or _today()
    params = f"?startDate={start}&endDate={end}"
    if activity_type:
        params += f"&activityType={activity_type}"
    return _jd(_api_get(f"/activitylist-service/activities/search/activities{params}&start=0&limit=100"))


@mcp.tool()
def get_activity(activity_id: str) -> str:
    """获取单个运动的详细数据

    Args:
        activity_id: 运动ID（从 get_activities 获取）
    """
    return _jd(_api_get(f"/activity-service/activity/{activity_id}"))


@mcp.tool()
def get_activity_details(activity_id: str) -> str:
    """获取运动的详细数据（含分段、心率区间等）

    Args:
        activity_id: 运动ID
    """
    return _jd(_api_get(f"/activity-service/activity/{activity_id}/details"))


@mcp.tool()
def get_activity_splits(activity_id: str) -> str:
    """获取运动的分段数据（每公里配速等）

    Args:
        activity_id: 运动ID
    """
    return _jd(_api_get(f"/activity-service/activity/{activity_id}/splits"))


@mcp.tool()
def get_activity_hr_zones(activity_id: str) -> str:
    """获取运动的心率区间分布

    Args:
        activity_id: 运动ID
    """
    return _jd(_api_get(f"/activity-service/activity/{activity_id}/hrTimeInZones"))


@mcp.tool()
def get_activity_types() -> str:
    """获取支持的运动类型列表"""
    return _jd(_api_get("/activity-service/activity/activityTypes"))


@mcp.tool()
def get_last_activity() -> str:
    """获取最近一次运动"""
    activities = _api_get("/activitylist-service/activities/search/activities?start=0&limit=1")
    if isinstance(activities, list) and len(activities) > 0:
        return _jd(activities[0])
    return _jd({"message": "没有找到运动记录"})


@mcp.tool()
def get_training_status(date: str = "") -> str:
    """获取训练状态（训练负荷、恢复时间、VO2 Max 等）

    Args:
        date: 日期 YYYY-MM-DD，默认今天
    """
    date = date or _today()
    return _jd(_api_get(f"/metrics-service/metrics/trainingstatus/aggregated/{date}"))


@mcp.tool()
def get_training_readiness(date: str = "") -> str:
    """获取训练准备度

    Args:
        date: 日期 YYYY-MM-DD，默认今天
    """
    date = date or _today()
    return _jd(_api_get(f"/metrics-service/metrics/trainingreadiness/{date}"))


@mcp.tool()
def get_earned_badges() -> str:
    """获取已获得的徽章"""
    return _jd(_api_get("/badge-service/badge/earned"))


@mcp.tool()
def get_gear() -> str:
    """获取装备数据（跑鞋、自行车等）"""
    return _jd(_api_get("/gear-service/gear/filterGear", backend="gc-api"))


@mcp.tool()
def get_sleep(date: str = "") -> str:
    """获取某天的睡眠数据（深睡/浅睡/REM/醒来时长、睡眠得分、睡眠压力、心率、血氧等）

    Args:
        date: 日期 YYYY-MM-DD，默认昨天
    """
    date = date or _days_ago(1)
    return _jd(_api_get(f"/wellness-service/wellness/dailySleepData?date={date}"))


@mcp.tool()
def get_hrv(date: str = "") -> str:
    """获取某天的 HRV（心率变异性）数据

    Args:
        date: 日期 YYYY-MM-DD，默认昨天
    """
    date = date or _days_ago(1)
    return _jd(_api_get(f"/hrv-service/hrv/{date}"))


@mcp.tool()
def get_stress(date: str = "") -> str:
    """获取某天的压力数据（全天压力均值、峰值等）

    Args:
        date: 日期 YYYY-MM-DD，默认今天
    """
    date = date or _today()
    return _jd(_api_get(f"/wellness-service/wellness/dailyStress/{date}"))


@mcp.tool()
def get_spo2(date: str = "") -> str:
    """获取某天的血氧数据（SpO2 均值、最低值）

    Args:
        date: 日期 YYYY-MM-DD，默认今天
    """
    date = date or _today()
    return _jd(_api_get(f"/wellness-service/wellness/daily/spo2/{date}"))


@mcp.tool()
def get_respiration(date: str = "") -> str:
    """获取某天的呼吸数据（呼吸频率均值、最小、最大）

    Args:
        date: 日期 YYYY-MM-DD，默认今天
    """
    date = date or _today()
    return _jd(_api_get(f"/wellness-service/wellness/daily/respiration/{date}"))


# ═══════════════════════════════════════════════════════════════════
# 启动入口 (支持 stdio 与 sse 双传输通道)
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Garmin CN & Intervals.icu MCP Server")
    parser.add_argument("--sse", action="store_true", help="Run with SSE transport (HTTP)")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"), help="Host for SSE server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")), help="Port for SSE server")
    args, _ = parser.parse_known_args()

    transport = "stdio"
    if args.sse or os.environ.get("MCP_TRANSPORT") == "sse":
        transport = "sse"
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        if hasattr(mcp.settings, "transport_security") and mcp.settings.transport_security:
            mcp.settings.transport_security.enable_dns_rebinding_protection = False
            mcp.settings.transport_security.allowed_hosts = ["*"]
            mcp.settings.transport_security.allowed_origins = ["*"]

    mcp.run(transport=transport)
