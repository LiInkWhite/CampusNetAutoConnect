# -*- coding: utf-8 -*-
"""config 模块测试：Schema 校验、加载保存、原子写盘"""
import os

import config


def test_defaults_when_file_missing(tmp_path):
    cfg = config.load_config(str(tmp_path / "config.yaml"))
    assert cfg["operator"] == "cmcc"
    assert cfg["inlet_ip"] == "192.168.40.2"
    assert cfg["max_attempts"] == 12


def test_load_existing_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("account: '123'\noperator: telecom\n", encoding="utf-8")
    cfg = config.load_config(str(p))
    assert cfg["account"] == "123"
    assert cfg["operator"] == "telecom"
    # 未写的字段用默认值
    assert cfg["max_attempts"] == 12


def test_validate_payload_int_coercion():
    vals, errs = config.validate_payload(
        config.CONFIG_SCHEMA, {"max_attempts": "20", "attempt_delay": 10})
    assert errs == []
    assert vals["max_attempts"] == 20
    assert vals["attempt_delay"] == 10


def test_validate_payload_int_invalid():
    vals, errs = config.validate_payload(
        config.CONFIG_SCHEMA, {"max_attempts": "abc"})
    assert vals == {}
    assert len(errs) == 1
    assert "max_attempts" in errs[0]


def test_validate_payload_int_out_of_range():
    _, errs = config.validate_payload(
        config.CONFIG_SCHEMA, {"max_attempts": 999, "attempt_delay": 0})
    assert len(errs) == 2


def test_validate_payload_bool_from_string():
    vals, _ = config.validate_payload(
        config.CONFIG_SCHEMA, {"only_once": "true"})
    assert vals["only_once"] is True


def test_validate_payload_choices():
    _, errs = config.validate_payload(
        config.CONFIG_SCHEMA, {"operator": "unknown_isp"})
    assert len(errs) == 1
    vals, errs = config.validate_payload(
        config.CONFIG_SCHEMA, {"operator": "telecom"})
    assert errs == []
    assert vals["operator"] == "telecom"


def test_validate_payload_empty_int_uses_default():
    vals, errs = config.validate_payload(
        config.CONFIG_SCHEMA, {"max_attempts": ""})
    assert errs == []
    assert vals["max_attempts"] == 12


def test_validate_payload_ignores_unknown_and_token():
    vals, errs = config.validate_payload(
        config.APP_SCHEMA, {"token": "hacked", "unknown": 1, "web_port": 8080})
    assert errs == []
    assert "token" not in vals
    assert "unknown" not in vals
    assert vals["web_port"] == 8080


def test_save_and_reload_roundtrip(tmp_path):
    cfg_path = str(tmp_path / "config.yaml")
    app_path = str(tmp_path / "app.json")
    config.load_config(cfg_path)
    config.load_app(app_path)
    config.set_config({"account": "u1", "password": "p1"})
    config.set_app({"web_port": 28000, "notify_on_up": False})
    config.save_config(cfg_path)
    config.save_app(app_path)
    # 重新加载
    cfg = config.load_config(cfg_path)
    app = config.load_app(app_path)
    assert cfg["account"] == "u1"
    assert app["web_port"] == 28000
    assert app["notify_on_up"] is False


def test_atomic_write_no_tmp_leftover(tmp_path):
    p = str(tmp_path / "f.txt")
    config.atomic_write(p, "hello")
    assert open(p, encoding="utf-8").read() == "hello"
    assert not os.path.exists(p + ".tmp")


def test_ensure_token_generates_once():
    config._app["token"] = ""
    t1 = config.ensure_token()
    assert t1
    t2 = config.ensure_token()
    assert t1 == t2  # 已存在则不重新生成
