# -*- coding: utf-8 -*-
"""pytest 共享夹具"""
import os
import sys

import pytest

# 保证能 import 项目根目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_base(tmp_path):
    """提供隔离的临时工作目录"""
    return tmp_path
