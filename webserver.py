# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""本地配置页 HTTP 服务（多线程，Schema 校验，token 鉴权）"""
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import autostart
import config as cfg_mod
import connector
import log as logger
import stats
from version import __version__

_MAX_LOGS = 1000
_MAX_STATS_DAYS = 30


class Handler(BaseHTTPRequestHandler):
    server_version = "CampusNet/" + __version__

    def log_message(self, *args):
        pass  # 静默

    # ------------------------------------------------------------------
    # 鉴权：fail-closed —— token 缺失或为空一律拒绝
    # ------------------------------------------------------------------
    def _token_ok(self):
        expected = cfg_mod.get_app().get("token", "")
        if not expected:
            return False
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        got = qs.get("token", [""])[0]
        if not got:
            got = self.headers.get("X-Auth-Token", "")
        if not got:
            return False
        return secrets.compare_digest(got.encode("utf-8"),
                                      expected.encode("utf-8"))

    def _send_json(self, code, msg, data=None):
        body = json.dumps({"code": code, "msg": msg, "data": data},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            return {}
        if length <= 0 or length > 1024 * 1024:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _clamp_int(raw, default, lo, hi):
        try:
            v = int(raw)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, v))

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path

        if path.startswith("/api/"):
            if not self._token_ok():
                self._send_json(403, "鉴权失败", None)
                return

        if path == "/api/config":
            cfg = cfg_mod.get_config()
            app = cfg_mod.get_app()
            # 由 Schema 派生返回值，与字段定义保持单一来源
            data = dict(cfg)
            data.update({k: app[k] for k in cfg_mod.APP_SCHEMA})
            data["auto_start_reg"] = autostart.get_auto_start()
            self._send_json(0, "ok", data)
        elif path == "/api/status":
            self._send_json(0, "ok", connector.get_state())
        elif path == "/api/connect":
            msg = connector.connect_once()
            self._send_json(0, msg, connector.get_state())
        elif path == "/api/logs":
            qs = parse_qs(urlparse(self.path).query)
            n = self._clamp_int(qs.get("n", ["200"])[0], 200, 1, _MAX_LOGS)
            self._send_json(0, "ok", logger.get_recent_logs(n))
        elif path == "/api/stats":
            qs = parse_qs(urlparse(self.path).query)
            days = self._clamp_int(qs.get("days", ["7"])[0], 7, 1,
                                   _MAX_STATS_DAYS)
            self._send_json(0, "ok", stats.get_stats(days))
        else:
            self._serve_static(path)

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/api/") and not self._token_ok():
            self._send_json(403, "鉴权失败", None)
            return
        if path == "/api/config/save":
            self._save_config()
        else:
            self._send_json(1, "未知接口", None)

    def _save_config(self):
        body = self._read_body()
        if not body:
            self._send_json(1, "参数解析失败", None)
            return

        # Schema 统一校验与类型转换（非法输入返回明确错误而非崩溃）
        cfg_vals, cfg_errs = cfg_mod.validate_payload(
            cfg_mod.CONFIG_SCHEMA, body)
        app_vals, app_errs = cfg_mod.validate_payload(
            cfg_mod.APP_SCHEMA, body)
        if cfg_errs or app_errs:
            self._send_json(1, "；".join(cfg_errs + app_errs), None)
            return

        old_port = cfg_mod.get_app().get("web_port")
        cfg_mod.set_config(cfg_vals)
        cfg_mod.set_app(app_vals)

        try:
            cfg_mod.save_config(self.server.config_path)
            cfg_mod.save_app(self.server.app_path)
        except Exception as e:
            self._send_json(1, str(e), None)
            return

        if "auto_start" in app_vals:
            try:
                autostart.set_auto_start(bool(app_vals["auto_start"]))
            except Exception as e:
                self._send_json(1, "设置开机自启失败: %s" % e, None)
                return

        msg = "保存成功"
        if app_vals.get("web_port") not in (None, old_port):
            msg += "（端口修改将在重启程序后生效）"
        self._send_json(0, msg, None)

    # ------------------------------------------------------------------
    # 静态文件（带目录穿越防护）
    # ------------------------------------------------------------------
    def _serve_static(self, path):
        web_dir = os.path.normpath(self.server.web_dir)
        if path == "/" or path == "":
            path = "/index.html"
        rel = path.lstrip("/")
        file_path = os.path.normpath(os.path.join(web_dir, rel))
        # 前缀比较必须带路径分隔符，防止 web-evil 之类的同级目录绕过
        if file_path != web_dir and not file_path.startswith(web_dir + os.sep):
            self.send_error(403)
            return
        if not os.path.isfile(file_path):
            self.send_error(404)
            return
        ext = os.path.splitext(file_path)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except Exception:
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def start_web_server(config_path, app_path, web_dir, port):
    """启动 HTTP 服务（多线程），返回 server 对象"""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.config_path = config_path
    server.server_app_path = app_path  # 兼容别名
    server.app_path = app_path
    server.web_dir = web_dir
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
