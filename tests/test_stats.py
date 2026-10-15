# -*- coding: utf-8 -*-
"""stats 模块测试：记录、统计查询、旧数据清理"""
from datetime import date, timedelta

import stats


def setup_function():
    stats._stats = {"daily": {}}
    stats._stats_path = None


def test_record_success_fail():
    stats.init_stats(None)  # 不落盘
    stats.record_connect_success()
    stats.record_connect_fail()
    today = date.today().strftime("%Y-%m-%d")
    d = stats._stats["daily"][today]
    assert d["success"] == 1
    assert d["fail"] == 1


def test_get_stats_days():
    stats.init_stats(None)
    stats.record_connect_success()
    result = stats.get_stats(7)
    assert len(result) == 7
    # 升序：最后一条是今天
    assert result[-1]["date"] == date.today().strftime("%Y-%m-%d")
    assert result[-1]["success"] == 1
    assert result[-1]["rate"] == 100.0


def test_get_stats_rate_mixed():
    stats.init_stats(None)
    stats.record_connect_success()
    stats.record_connect_success()
    stats.record_connect_fail()
    result = stats.get_stats(1)
    assert result[0]["success"] == 2
    assert result[0]["fail"] == 1
    assert result[0]["rate"] == 66.7


def test_cleanup_old_data():
    old_key = (date.today() - timedelta(days=40)).strftime("%Y-%m-%d")
    stats._stats = {"daily": {old_key: {"success": 5, "fail": 0,
                                        "connect_time": 0,
                                        "last_connected_ts": 0}}}
    stats._cleanup()
    assert old_key not in stats._stats["daily"]


def test_online_time_settle():
    import time
    stats.init_stats(None)
    stats.record_connect_success()
    d = stats._today()
    d["last_connected_ts"] = int(time.time()) - 100
    stats._settle_now()
    assert d["connect_time"] >= 100


def test_load_from_file(tmp_path):
    import json
    p = str(tmp_path / "stats.json")
    today = date.today().strftime("%Y-%m-%d")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"daily": {today: {"success": 3, "fail": 1,
                                     "connect_time": 60,
                                     "last_connected_ts": 0}}}, f)
    stats.init_stats(p)
    result = stats.get_stats(1)
    assert result[0]["success"] == 3
