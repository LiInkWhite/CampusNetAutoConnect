# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""Windows 系统弹窗通知（优先 winotify，失败则降级为 PowerShell Toast）"""
import subprocess

try:
    from winotify import Notification, audio  # noqa: F401
    HAS_WINOTIFY = True
except Exception:
    HAS_WINOTIFY = False


def notify(title, body):
    """弹一条 Windows 通知，失败静默（不影响主流程）"""
    if HAS_WINOTIFY:
        try:
            toast = Notification(app_id="校园网自动连接", title=title,
                                 msg=body, duration="short")
            toast.show()
            return
        except Exception:
            pass
    _notify_powershell(title, body)


def _notify_powershell(title, body):
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null\n"
        "[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] | Out-Null\n"
        "$t = '%s'\n$b = '%s'\n"
        "$tmpl = '<toast><visual><binding template=\"ToastText02\">"
        "<text id=\"1\">' + $t + '</text><text id=\"2\">' + $b + "
        "'</text></binding></visual></toast>'\n"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        "$xml.LoadXml($tmpl)\n"
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml\n"
        "[Windows.UI.Notifications.ToastNotificationManager]"
        "::CreateToastNotifier('CampusNet').Show($toast)\n"
    ) % (title.replace("'", "''"), body.replace("'", "''"))
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-Command", script],
            creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass


def on_state_change_notify(old, new):
    """连接器状态变化时的通知回调"""
    from config import get_app
    app = get_app()
    if new == "connected":
        if old != "connected" and app.get("notify_on_up", True):
            notify("校园网已连接", "自动连接成功，网络已恢复")
    elif new == "disconnected":
        if old == "connected" and app.get("notify_on_down", True):
            notify("校园网已断开", "正在尝试自动重连…")
