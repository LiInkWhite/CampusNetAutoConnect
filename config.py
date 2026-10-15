# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""配置管理：Schema 驱动（字段定义、校验、转换的唯一来源）

- config.yaml：认证相关字段（与参考项目格式兼容）
- app.json：程序自身设置（端口/开关/token 等）

所有字段的定义、默认值、类型约束集中在本文件的 SCHEMA 中，
Web 接口的读取与保存均由 Schema 派生，新增字段只改这里。
"""
import json
import os
import secrets
import threading

import yaml

# ---------------------------------------------------------------------------
# Schema：字段唯一定义处
# type: str / int / bool；choices: 可选值；min/max: 数值范围
# ---------------------------------------------------------------------------
CONFIG_SCHEMA: dict = {
    "account":      {"type": "str", "default": "", "label": "账号"},
    "password":     {"type": "str", "default": ""},
    "operator":     {"type": "str", "default": "cmcc",
                     "choices": ["telecom", "cmcc", "unicom"]},
    "callback":     {"type": "str", "default": "dr1003"},
    "login_method": {"type": "str", "default": "1"},
    "ipv4":         {"type": "str", "default": ""},
    "ipv6":         {"type": "str", "default": ""},
    "mac":          {"type": "str", "default": "000000000000"},
    "inlet_ip":     {"type": "str", "default": "192.168.40.2"},
    "ua":           {"type": "str",
                     "default": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/106.0.0.0 Safari/537.36"},
    "max_attempts": {"type": "int", "default": 12, "min": 1, "max": 100},
    "attempt_delay": {"type": "int", "default": 5, "min": 1, "max": 3600},
    "only_once":    {"type": "bool", "default": False},
}

# 客户端可设置的应用字段（token 不可由客户端设置，单独处理）
APP_SCHEMA = {
    "auto_start":            {"type": "bool", "default": False},
    "web_port":              {"type": "int", "default": 17777,
                              "min": 1024, "max": 65535},
    "notify_on_up":          {"type": "bool", "default": True},
    "notify_on_down":        {"type": "bool", "default": True},
    "exit_after_connect":    {"type": "bool", "default": False},
    "minimize_after_connect": {"type": "bool", "default": False},
}

DEFAULT_CONFIG: dict = {k: spec["default"]
                        for k, spec in CONFIG_SCHEMA.items()}
DEFAULT_APP: dict = {k: spec["default"] for k, spec in APP_SCHEMA.items()}
DEFAULT_APP["token"] = ""  # 内部字段，非客户端可写

_lock = threading.RLock()
_config = dict(DEFAULT_CONFIG)
_app = dict(DEFAULT_APP)


# ---------------------------------------------------------------------------
# 原子写盘：写临时文件 + os.replace，避免写一半断电导致配置损坏
# ---------------------------------------------------------------------------
def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Schema 校验：把任意 payload（如 HTTP JSON）转换为合法配置值
# 返回 (values, errors)；未出现的字段不处理，未知字段忽略
# ---------------------------------------------------------------------------
def validate_payload(schema, payload):
    values, errors = {}, []
    for key, spec in schema.items():
        if key not in payload:
            continue
        v = payload[key]
        t = spec["type"]
        try:
            if t == "int":
                if isinstance(v, bool):
                    raise ValueError("应为整数")
                if isinstance(v, str):
                    v = v.strip()
                if v is None or v == "":
                    values[key] = spec["default"]
                    continue
                v = int(v)
                if "min" in spec and v < spec["min"]:
                    errors.append("%s 不能小于 %s" % (key, spec["min"]))
                    continue
                if "max" in spec and v > spec["max"]:
                    errors.append("%s 不能大于 %s" % (key, spec["max"]))
                    continue
                values[key] = v
            elif t == "bool":
                if isinstance(v, str):
                    values[key] = v.strip().lower() in ("1", "true", "yes", "on")
                else:
                    values[key] = bool(v)
            else:  # str
                v = "" if v is None else str(v).strip()
                if "choices" in spec and v and v not in spec["choices"]:
                    errors.append("%s 的值无效（可选：%s）"
                                  % (key, "/".join(spec["choices"])))
                    continue
                values[key] = v
        except (ValueError, TypeError):
            errors.append("%s: 无法解析为 %s 类型" % (key, t))
    return values, errors


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------
def load_config(path):
    """读取 config.yaml，不存在则用默认值"""
    global _config
    with _lock:
        _config = dict(DEFAULT_CONFIG)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for k in DEFAULT_CONFIG:
                    if k in data:
                        _config[k] = data[k]
            except Exception as e:
                raise RuntimeError("读取配置文件失败: %s" % e) from e
        return dict(_config)


def save_config(path):
    """写回 config.yaml（仅认证相关字段）"""
    with _lock:
        try:
            text = "# 以下为校园网认证配置信息\n" + yaml.safe_dump(
                _config, allow_unicode=True, default_flow_style=False)
            atomic_write(path, text)
        except Exception as e:
            raise RuntimeError("保存配置文件失败: %s" % e) from e


def load_app(path):
    global _app
    with _lock:
        _app = dict(DEFAULT_APP)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                for k in DEFAULT_APP:
                    if k in data:
                        _app[k] = data[k]
            except Exception as e:
                raise RuntimeError("读取应用设置失败: %s" % e) from e
        return dict(_app)


def save_app(path):
    with _lock:
        try:
            atomic_write(path, json.dumps(_app, ensure_ascii=False, indent=2))
        except Exception as e:
            raise RuntimeError("保存应用设置失败: %s" % e) from e


def get_config():
    with _lock:
        return dict(_config)


def set_config(d):
    global _config
    with _lock:
        for k, v in d.items():
            if k in DEFAULT_CONFIG:
                _config[k] = v


def get_app():
    with _lock:
        return dict(_app)


def set_app(d):
    global _app
    with _lock:
        for k, v in d.items():
            if k in DEFAULT_APP:
                _app[k] = v


def ensure_token():
    """确保 token 存在（首次运行生成随机 token），返回 token"""
    global _app
    with _lock:
        if not _app.get("token"):
            _app["token"] = secrets.token_urlsafe(16)
        return _app["token"]
