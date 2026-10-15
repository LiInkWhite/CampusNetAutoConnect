# -*- coding: utf-8 -*-
"""webserver 模块测试：鉴权、目录穿越防护、Schema 校验、保存流程"""
import http.client
import json

import pytest

import config
import log as logger
import stats
import webserver

TOKEN = "test-token-abc123"


@pytest.fixture
def server(tmp_path, monkeypatch):
    """启动隔离的真实 HTTP 服务（随机端口）"""
    cfg_path = str(tmp_path / "config.yaml")
    app_path = str(tmp_path / "app.json")
    config.load_config(cfg_path)
    config.load_app(app_path)
    config._app["token"] = TOKEN
    logger.setup_logger(str(tmp_path / "logs"))
    stats.init_stats(str(tmp_path / "stats.json"))
    # 注册表操作打桩（CI 的 Linux 环境无 winreg）
    monkeypatch.setattr(webserver.autostart, "set_auto_start",
                        lambda enable: "")
    monkeypatch.setattr(webserver.autostart, "get_auto_start",
                        lambda: False)
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    srv = webserver.start_web_server(cfg_path, app_path, str(web_dir), 0)
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def _api_json(port, path, token=TOKEN):
    sep = "&" if "?" in path else "?"
    status, data = _request(port, "GET", path + sep + "token=" + token)
    return status, json.loads(data.decode("utf-8"))


# ------------------------------------------------------------------
# 鉴权
# ------------------------------------------------------------------
def test_api_without_token_rejected(server):
    port = server
    status, body = _request(port, "GET", "/api/config")
    j = json.loads(body.decode("utf-8"))
    assert j["code"] == 403


def test_api_wrong_token_rejected(server):
    port = server
    status, body = _request(port, "GET", "/api/config?token=wrong")
    j = json.loads(body.decode("utf-8"))
    assert j["code"] == 403


def test_api_correct_token_ok(server):
    status, j = _api_json(server, "/api/config")
    assert j["code"] == 0
    assert "account" in j["data"]
    assert "web_port" in j["data"]


def test_api_header_token_ok(server):
    port = server
    status, body = _request(port, "GET", "/api/config",
                            headers={"X-Auth-Token": TOKEN})
    j = json.loads(body.decode("utf-8"))
    assert j["code"] == 0


# ------------------------------------------------------------------
# 静态文件与目录穿越
# ------------------------------------------------------------------
def test_static_index_served(server):
    status, body = _request(server, "GET", "/")
    assert status == 200
    assert b"ok" in body


def test_static_traversal_blocked(server):
    # 尝试读取 web 目录之外的同前缀文件（目录穿越攻击）
    status, _ = _request(server, "GET", "/../config.yaml")
    assert status == 403


def test_static_404(server):
    status, _ = _request(server, "GET", "/notexist.html")
    assert status == 404


# ------------------------------------------------------------------
# 保存接口：Schema 校验
# ------------------------------------------------------------------
def _save(server, payload):
    body = json.dumps(payload).encode("utf-8")
    status, data = _request(
        server, "POST", "/api/config/save?token=" + TOKEN, body=body,
        headers={"Content-Type": "application/json"})
    return json.loads(data.decode("utf-8"))


def test_save_invalid_int_returns_error(server):
    j = _save(server, {"max_attempts": "abc"})
    assert j["code"] == 1
    assert "max_attempts" in j["msg"]


def test_save_out_of_range_returns_error(server):
    j = _save(server, {"web_port": 80, "attempt_delay": 99999})
    assert j["code"] == 1
    assert "web_port" in j["msg"]
    assert "attempt_delay" in j["msg"]


def test_save_invalid_operator_returns_error(server):
    j = _save(server, {"operator": "unknown"})
    assert j["code"] == 1
    assert "operator" in j["msg"]


def test_save_valid_including_port(server):
    j = _save(server, {"account": "u1", "password": "p1",
                       "web_port": 28000, "max_attempts": 20})
    assert j["code"] == 0
    assert "重启" in j["msg"]  # 端口变更提示
    app = config.get_app()
    assert app["web_port"] == 28000
    assert config.get_config()["max_attempts"] == 20


def test_save_token_not_overwritable(server):
    """客户端提交的 token 字段不能覆盖服务端鉴权 token"""
    _save(server, {"token": "evil-token"})
    assert config.get_app()["token"] == TOKEN


def test_logs_param_clamped(server):
    status, j = _api_json(server, "/api/logs?n=999999")
    assert j["code"] == 0  # 超大 n 被钳制，不报错
    status, j = _api_json(server, "/api/logs?n=abc")
    assert j["code"] == 0  # 非法 n 回退默认值
