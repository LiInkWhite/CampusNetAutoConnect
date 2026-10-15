# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""统计模块：记录连接成功/失败事件，供统计面板查询"""
import json
import os
import threading
import time
from datetime import date

from config import atomic_write

_lock = threading.RLock()

# 统计数据文件结构：
# {
#   "daily": {
#     "2026-10-13": {
#       "success": 3,          # 成功次数
#       "fail": 1,             # 失败次数
#       "connect_time": 3600,  # 累计在线秒数
#       "last_connected_ts": 0 # 最近一次连上的时间戳（用于计算在线时长）
#     }, ...
#   }
# }
_stats: dict = {"daily": {}}
_stats_path = None


def _today_key():
    return date.today().strftime("%Y-%m-%d")


def init_stats(path):
    """初始化统计（path 为 None 时不持久化，仅内存）"""
    global _stats_path, _stats
    _stats_path = path
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data.get("daily"), dict):
                    _stats = data
        except Exception:
            _stats = {"daily": {}}
    # 清理超过 30 天的旧数据
    _cleanup()


def _cleanup():
    """只保留最近 30 天"""
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    keys = list(_stats["daily"].keys())
    for k in keys:
        if k < cutoff:
            del _stats["daily"][k]


def _save():
    if not _stats_path:
        return
    try:
        atomic_write(_stats_path,
                     json.dumps(_stats, ensure_ascii=False, indent=2))
    except Exception:
        pass


def _today():
    key = _today_key()
    with _lock:
        if key not in _stats["daily"]:
            _stats["daily"][key] = {
                "success": 0, "fail": 0, "connect_time": 0,
                "last_connected_ts": 0,
            }
        return _stats["daily"][key]


def record_connect_success():
    """连接成功：成功次数 +1，记录连上时间戳"""
    with _lock:
        d = _today()
        d["success"] += 1
        d["last_connected_ts"] = int(time.time())
        _save()


def record_connect_fail():
    """连接失败：失败次数 +1"""
    with _lock:
        d = _today()
        d["fail"] += 1
        _save()


def _flush_online_time():
    """把当前在线时长累加到当天（断开时调用）"""
    with _lock:
        d = _today()
        ts = d.get("last_connected_ts", 0)
        if ts:
            elapsed = int(time.time()) - ts
            if elapsed > 0:
                d["connect_time"] += elapsed
            d["last_connected_ts"] = 0
        _save()


def record_disconnect():
    """断开连接：结算在线时长"""
    _flush_online_time()


def get_stats(days=7):
    """返回最近 days 天的统计，用于面板展示"""
    from datetime import timedelta
    result = []
    today = date.today()
    with _lock:
        # 结算当前在线时长（实时显示）
        _settle_now()
        for i in range(days - 1, -1, -1):
            key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            d = _stats["daily"].get(key, {
                "success": 0, "fail": 0, "connect_time": 0,
            })
            total = d.get("success", 0) + d.get("fail", 0)
            result.append({
                "date": key,
                "success": d.get("success", 0),
                "fail": d.get("fail", 0),
                "connect_time": d.get("connect_time", 0),
                "rate": round(d.get("success", 0) * 100.0 / total, 1)
                        if total else 100.0,
            })
    return result


def _settle_now():
    """实时结算当天在线时长（不落盘，仅用于展示）"""
    d = _today()
    ts = d.get("last_connected_ts", 0)
    if ts:
        elapsed = int(time.time()) - ts
        d["connect_time"] = d.get("connect_time", 0) + elapsed
        d["last_connected_ts"] = int(time.time())
