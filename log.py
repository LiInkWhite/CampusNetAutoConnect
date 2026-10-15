# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""日志模块：滚动日志文件 + 内存环形缓冲（供配置页查询）"""
import logging
import os
from collections import deque
from logging.handlers import RotatingFileHandler

# 内存中保留最近 500 条日志供网页查询
_MAX_MEM = 500
_mem_logs: deque = deque(maxlen=_MAX_MEM)

_logger = None


class MemHandler(logging.Handler):
    """把日志同时写入内存环形缓冲"""

    def emit(self, record):
        try:
            _mem_logs.append({
                "time": record.asctime,
                "level": record.levelname,
                "msg": record.getMessage(),
            })
        except Exception:
            pass


def setup_logger(log_dir):
    """初始化日志，返回 logger"""
    global _logger
    if _logger is not None:
        return _logger

    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "campusnet.log")

    logger = logging.getLogger("campusnet")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    # 滚动文件：单文件 1MB，保留 5 个备份
    fh = RotatingFileHandler(log_file, maxBytes=1 * 1024 * 1024,
                             backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 内存缓冲
    mh = MemHandler()
    mh.setFormatter(fmt)
    logger.addHandler(mh)

    _logger = logger
    return logger


def get_logger():
    global _logger
    if _logger is None:
        _logger = logging.getLogger("campusnet")
        _logger.setLevel(logging.INFO)
    return _logger


def log_info(msg):
    get_logger().info(msg)


def log_error(msg):
    get_logger().error(msg)


def log_warn(msg):
    get_logger().warning(msg)


def get_recent_logs(n=200):
    """返回最近 n 条日志（新→旧）"""
    logs = list(_mem_logs)
    return list(reversed(logs))[-n:][::-1]
