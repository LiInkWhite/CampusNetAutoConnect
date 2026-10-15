# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""核心连接逻辑：Dr.COM EPortal 探活 + 认证 + 自动重连循环

状态机（统一迁移入口 _transition，日志/统计/通知/回调集中挂载）：
  disconnected --探测在线--> connected
  disconnected --发起登录--> connecting --成功--> connected
  connecting --失败--> disconnected（指数退避重试，达 max_attempts 次后暂停登录）
"""
import threading
from datetime import datetime
from enum import Enum

import requests

import log as logger
import stats
from config import get_config


class State(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


# 状态显示字符串（对外保持与前端兼容的小写字符串）
S_DISCONNECTED = State.DISCONNECTED.value
S_CONNECTING = State.CONNECTING.value
S_CONNECTED = State.CONNECTED.value

_state = {
    "state": S_DISCONNECTED,
    "last_check": "",
    "last_result": "尚未开始检测",
    "connect_time": "",
}
_state_lock = threading.Lock()
_stop = threading.Event()
# 登录互斥锁：防止手动"立即连接"与后台循环并发重复登录
_login_lock = threading.Lock()
# 重试计数与配置签名（跨循环持久，配置变更时重置）
_attempt = 0
_last_sig = None

# 回调（由 start_connector 注入，_transition 统一触发）
_on_state_change_cb = None
_on_connected_cb = None


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _reset_state():
    """重置内部状态与回调（测试用）"""
    global _on_state_change_cb, _on_connected_cb, _attempt, _last_sig
    with _state_lock:
        _state.update(state=S_DISCONNECTED, last_check="",
                      last_result="尚未开始检测", connect_time="")
    _attempt = 0
    _last_sig = None
    _on_state_change_cb = None
    _on_connected_cb = None


def get_state():
    with _state_lock:
        return dict(_state)


def _get(key):
    with _state_lock:
        return _state.get(key, "")


# ---------------------------------------------------------------------------
# 统一状态迁移：日志、统计、通知、退出回调全部集中在此
# ---------------------------------------------------------------------------
def _transition(new_state, result, connect_time=None):
    old = _get("state")
    with _state_lock:
        _state.update(state=new_state.value, last_result=result,
                      last_check=_now())
        if connect_time is not None:
            _state["connect_time"] = connect_time
    if old == new_state.value:
        return

    # 日志与统计
    if new_state == State.CONNECTED:
        logger.log_info("连接成功：%s" % result)
        stats.record_connect_success()
    elif new_state == State.DISCONNECTED and old == S_CONNECTED:
        logger.log_warn("网络断开：%s" % result)
        stats.record_disconnect()
    elif new_state == State.DISCONNECTED:
        logger.log_warn("连接失败：%s" % result)
        stats.record_connect_fail()

    # 回调
    if _on_state_change_cb:
        try:
            _on_state_change_cb(old, new_state.value)
        except Exception as e:
            logger.log_error("状态回调异常: %s" % e)
    if _on_connected_cb and new_state == State.CONNECTED:
        try:
            _on_connected_cb()
        except Exception as e:
            logger.log_error("连接回调异常: %s" % e)


# ---------------------------------------------------------------------------
# 探活与登录
# ---------------------------------------------------------------------------
def _probe_online(cfg, session):
    """探测是否已在线。返回 True 表示已登录校园网。"""
    if not cfg.get("inlet_ip"):
        return False
    url = "http://%s/" % cfg["inlet_ip"]
    try:
        r = session.get(url, timeout=5,
                        headers={"User-Agent": cfg.get("ua", "")})
        if r.status_code < 200 or r.status_code >= 300:
            return False
        return "Dr.COMWebLoginID_0.htm" not in r.text
    except Exception:
        return False


def _parse_login_error(text):
    """解析 Dr.COM 登录失败原因，返回友好中文描述"""
    t = text.lower()
    if ("账号或密码" in text or "密码错误" in text
            or ("password" in t and "wrong" in t)):
        return "账号或密码错误"
    if "欠费" in text or "arrearage" in t or "余额不足" in text:
        return "账号欠费，请充值"
    if "已在线" in text or "already online" in t or "already_online" in t:
        return "该账号已在线"
    if "运营商" in text or "operator" in t or "isp" in t:
        return "运营商选择不匹配"
    if "账号不存在" in text or "user not exist" in t or "no such" in t:
        return "账号不存在"
    if "停机" in text or "suspend" in t:
        return "账号已停机"
    if "失败" in text or "failed" in t or "error" in t:
        return "认证失败"
    return ""


def _do_login(cfg, session):
    """发起登录，返回 (成功, 错误信息)"""
    login_url = "http://%s:801/eportal/portal/login" % cfg["inlet_ip"]
    params = {
        "callback": cfg.get("callback", "dr1003"),
        "login_method": cfg.get("login_method", "1"),
        "user_account": ",0,%s@%s" % (cfg.get("account", ""),
                                      cfg.get("operator", "cmcc")),
        "user_password": cfg.get("password", ""),
        "wlan_user_ip": cfg.get("ipv4", ""),
        "wlan_user_ipv6": cfg.get("ipv6", ""),
        "wlan_user_mac": cfg.get("mac", ""),
    }
    try:
        r = session.get(login_url, params=params, timeout=5,
                        headers={"User-Agent": cfg.get("ua", "")})
        text = r.text
        tl = text.lower()
        if "failed" in tl or "error" in tl or "登录失败" in text or "失败" in text:
            reason = _parse_login_error(text)
            if not reason:
                reason = "认证返回错误: %s" % text[:200]
            return False, reason
        return True, ""
    except Exception as e:
        return False, "登录请求失败: %s" % e


# ---------------------------------------------------------------------------
# 重试退避：前 3 次基础间隔，4-6 次翻倍，7 次以上 4 倍，上限 60s
# ---------------------------------------------------------------------------
def _backoff_delay(base, attempt):
    if attempt <= 3:
        return base
    if attempt <= 6:
        return min(base * 2, 60)
    return min(base * 4, 60)


# ---------------------------------------------------------------------------
# 登录执行（探活 + 登录 + 验证 + 状态迁移），手动与后台共用同一路径
# ---------------------------------------------------------------------------
def _execute_attempt(cfg, session):
    """执行一次完整登录尝试（调用方需持有 _login_lock）"""
    if _probe_online(cfg, session):
        ct = _get("connect_time") or _now()
        _transition(State.CONNECTED, "网络已连接", connect_time=ct)
        return "网络已连接"

    ok, err = _do_login(cfg, session)
    verify = _probe_online(cfg, session)
    if ok and verify:
        _transition(State.CONNECTED, "登录成功，网络已连接",
                    connect_time=_now())
        return "登录成功"
    if not ok:
        return "登录失败: " + err
    return "登录请求已发送，请稍后查看状态"


def connect_once(session=None):
    """立即执行一次探测+登录（网页按钮/托盘菜单调用），返回结果描述"""
    cfg = get_config()
    if not cfg.get("account") or not cfg.get("password"):
        return "未配置账号/密码"

    if not _login_lock.acquire(blocking=False):
        return "已有连接任务进行中，请稍候"
    try:
        if session is None:
            session = requests.Session()
        result = _execute_attempt(cfg, session)
        if "登录失败" in result or "登录请求已发送" in result:
            _transition(State.DISCONNECTED, result)
        return result
    finally:
        _login_lock.release()


# ---------------------------------------------------------------------------
# 后台循环
# ---------------------------------------------------------------------------
def _run_loop(on_state_change=None, on_connected=None):
    """后台循环：持续探测，断网自动登录（带指数退避与次数上限）"""
    global _on_state_change_cb, _on_connected_cb, _attempt, _last_sig
    _on_state_change_cb = on_state_change
    _on_connected_cb = on_connected

    session = requests.Session()

    while not _stop.is_set():
        cfg = get_config()
        base = int(cfg.get("attempt_delay", 5) or 5)
        if base < 1:
            base = 5
        max_attempts = int(cfg.get("max_attempts", 12) or 12)
        if max_attempts < 1:
            max_attempts = 1

        # 认证关键配置变化时重置重试计数（改完密码立即重试）
        sig = (cfg.get("account"), cfg.get("password"),
               cfg.get("inlet_ip"), cfg.get("operator"))
        if sig != _last_sig:
            _attempt = 0
            _last_sig = sig

        if not cfg.get("account") or not cfg.get("password"):
            _transition(State.DISCONNECTED, "未配置账号/密码，请在配置页填写")
        elif _probe_online(cfg, session):
            _attempt = 0
            ct = _get("connect_time") or _now()
            _transition(State.CONNECTED, "网络已连接", connect_time=ct)
        elif _attempt >= max_attempts:
            # 达到重试上限：不再发起登录，仅持续监测（配置变更后自动恢复）
            _transition(State.DISCONNECTED,
                        "已达最大尝试次数(%d)，暂停登录；将持续监测网络，"
                        "修改配置后将自动重试" % max_attempts)
        else:
            _attempt += 1
            _transition(State.CONNECTING,
                        "正在尝试登录 (第 %d/%d 次)" % (_attempt, max_attempts))
            with _login_lock:
                result = _execute_attempt(cfg, session)
            if "登录失败" in result:
                _transition(State.DISCONNECTED, result)
            elif "登录请求已发送" in result:
                _transition(State.DISCONNECTED, result)

        if cfg.get("only_once"):
            return

        wait = _backoff_delay(base, _attempt) if _attempt > 0 else base
        _stop.wait(wait)


def start_connector(on_state_change=None, on_connected=None):
    """启动后台连接线程"""
    t = threading.Thread(target=_run_loop,
                         args=(on_state_change, on_connected),
                         daemon=True)
    t.start()
    return t


def stop_connector():
    _stop.set()
