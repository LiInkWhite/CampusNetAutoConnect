# -*- coding: utf-8 -*-
"""connector 模块测试：状态机迁移、回调触发、退避、最大尝试次数"""

import connector
from connector import State


class FakeSession:
    def get(self, *a, **kw):
        raise AssertionError("不应发起真实网络请求")


def setup_function():
    connector._reset_state()
    connector._stop.clear()


def teardown_function():
    connector._stop.set()
    connector._reset_state()


def _cfg(**kw):
    base = {"account": "u", "password": "p", "inlet_ip": "1.2.3.4",
            "operator": "cmcc", "attempt_delay": 1, "max_attempts": 3,
            "only_once": False}
    base.update(kw)
    return base


def test_transition_to_connected_fires_callbacks(monkeypatch):
    events = []
    connector._on_state_change_cb = lambda o, n: events.append((o, n))
    connector._on_connected_cb = lambda: events.append("connected_cb")
    connector._transition(State.CONNECTED, "登录成功", connect_time="t")
    assert connector.get_state()["state"] == "connected"
    assert ("disconnected", "connected") in events
    assert "connected_cb" in events


def test_transition_same_state_no_callback():
    calls = []
    connector._transition(State.DISCONNECTED, "x")  # 初始即 disconnected
    connector._on_state_change_cb = lambda o, n: calls.append(1)
    connector._transition(State.DISCONNECTED, "y")  # 无迁移
    assert calls == []


def test_connect_once_already_online(monkeypatch):
    monkeypatch.setattr(connector, "get_config", lambda: _cfg())
    monkeypatch.setattr(connector, "_probe_online", lambda cfg, s: True)
    result = connector.connect_once(FakeSession())
    assert result == "网络已连接"
    assert connector.get_state()["state"] == "connected"


def test_connect_once_login_success(monkeypatch):
    # 探测第一次 False（未在线），登录后第二次 True（已连上）
    seq = {"n": 0}

    def fake_probe(cfg, s):
        seq["n"] += 1
        return seq["n"] > 1

    monkeypatch.setattr(connector, "get_config", lambda: _cfg())
    monkeypatch.setattr(connector, "_probe_online", fake_probe)
    monkeypatch.setattr(connector, "_do_login",
                        lambda cfg, s: (True, ""))
    result = connector.connect_once(FakeSession())
    assert result == "登录成功"
    assert connector.get_state()["state"] == "connected"


def test_connect_once_no_account(monkeypatch):
    monkeypatch.setattr(connector, "get_config", lambda: _cfg(account=""))
    result = connector.connect_once()
    assert "未配置" in result


def test_connect_once_login_fail_records(monkeypatch):
    monkeypatch.setattr(connector, "get_config", lambda: _cfg())
    monkeypatch.setattr(connector, "_probe_online", lambda cfg, s: False)
    monkeypatch.setattr(connector, "_do_login",
                        lambda cfg, s: (False, "账号或密码错误"))
    connected_cb = []
    connector._on_connected_cb = lambda: connected_cb.append(1)
    result = connector.connect_once(FakeSession())
    assert "登录失败" in result
    assert connector.get_state()["state"] == "disconnected"
    assert connected_cb == []  # 失败不触发连接成功回调


def test_login_lock_prevents_concurrent(monkeypatch):
    monkeypatch.setattr(connector, "get_config", lambda: _cfg())
    assert connector._login_lock.acquire(blocking=False)
    try:
        # 模拟后台循环持有锁时，手动连接应立即返回"进行中"
        result = connector.connect_once(FakeSession())
        assert "进行中" in result
    finally:
        connector._login_lock.release()


def test_backoff_delay():
    assert connector._backoff_delay(5, 1) == 5
    assert connector._backoff_delay(5, 3) == 5
    assert connector._backoff_delay(5, 4) == 10
    assert connector._backoff_delay(5, 7) == 20
    assert connector._backoff_delay(5, 100) == 20  # min(5*4, 60)
    assert connector._backoff_delay(30, 100) == 60  # 上限 60


def test_run_loop_respects_max_attempts(monkeypatch):
    """达到 max_attempts 后不再发起登录，仅监测"""
    monkeypatch.setattr(connector, "get_config", lambda: _cfg(max_attempts=2))
    # 跳过循环间的真实等待，加速测试
    monkeypatch.setattr(connector._stop, "wait", lambda *_: None)
    login_calls = []
    probe_calls = []

    def fake_login(cfg, s):
        login_calls.append(1)
        return False, "账号或密码错误"

    def fake_probe(cfg, s):
        probe_calls.append(1)
        # 每轮循环共 3 次探活（循环 1 次 + 登录前后各 1 次），
        # 第 3 轮（第 7 次探活）时通知循环退出
        if len(probe_calls) >= 7:
            connector._stop.set()
        return False

    monkeypatch.setattr(connector, "_probe_online", fake_probe)
    monkeypatch.setattr(connector, "_do_login", fake_login)
    connector._run_loop()
    # max_attempts=2：只发起 2 次登录，第 3 轮起仅探测
    assert len(login_calls) == 2
    assert "已达最大尝试次数" in connector.get_state()["last_result"]


def test_run_loop_config_change_resets_attempts(monkeypatch):
    """修改密码等关键配置后，重试计数重置"""
    cfg = _cfg(max_attempts=1, only_once=True)
    monkeypatch.setattr(connector, "get_config", lambda: cfg)
    login_calls = []

    def fake_login(cfgd, s):
        login_calls.append(1)
        return False, "账号或密码错误"

    monkeypatch.setattr(connector, "_probe_online",
                        lambda cfgd, s: False)
    monkeypatch.setattr(connector, "_do_login", fake_login)
    # 第 1 轮：登录失败（only_once 每次调用跑一轮）
    connector._run_loop()
    assert len(login_calls) == 1
    # 第 2 轮：已达上限，不登录
    connector._run_loop()
    assert len(login_calls) == 1
    # 修改密码 → 重置计数 → 再次登录
    cfg["password"] = "newpass"
    connector._run_loop()
    assert len(login_calls) == 2


def test_run_loop_unconfigured(monkeypatch):
    def fail_probe(cfg, s):
        raise AssertionError("未配置时不应探测")

    monkeypatch.setattr(connector, "get_config",
                        lambda: _cfg(account="", password="",
                                     only_once=True))
    monkeypatch.setattr(connector, "_probe_online", fail_probe)
    connector._run_loop()
    assert "未配置" in connector.get_state()["last_result"]
