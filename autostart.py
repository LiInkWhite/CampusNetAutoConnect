# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""Windows 开机自启（注册表 Run 键，当前用户级，无需管理员）

非 Windows 平台（如 CI 上的 Linux）优雅降级：查询返回 False，设置抛出明确错误。
"""
import os
import sys

try:
    import winreg
except ImportError:  # 非 Windows 平台
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CampusNetAutoConnect"


def _supported():
    return winreg is not None


def set_auto_start(enable):
    """设置/取消开机自启，返回命令行；非 Windows 抛出明确错误"""
    if not _supported():
        raise RuntimeError("开机自启仅支持 Windows 系统")
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                         winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
    try:
        if not enable:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
            return ""
        cmd = _build_cmd()
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
        return cmd
    finally:
        winreg.CloseKey(key)


def _build_cmd():
    """构造自启命令行（带 --silent 静默启动）"""
    if getattr(sys, "frozen", False):
        # 打包成 exe 后直接运行自身，静默模式
        return '"%s" --silent' % sys.executable
    # 源码模式：用 pythonw.exe 无窗口运行 main.py
    base = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(base, "main.py")
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    return '"%s" "%s" --silent' % (pyw, main_py)


def get_auto_start():
    """查询当前是否已开启自启（非 Windows 恒为 False）"""
    if not _supported():
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                             winreg.KEY_QUERY_VALUE)
        try:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False
