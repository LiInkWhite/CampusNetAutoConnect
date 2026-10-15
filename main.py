# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""校园网自动连接工具 - 主入口（系统托盘 + 配置页 + 自动连接）"""
import os
import sys
import threading
import time
import webbrowser

import config as cfg_mod
import connector
import log as logger
import stats
import webserver
from notify import on_state_change_notify
from version import __version__

# 确保能 import 到 pystray 等第三方库（打包后由 PyInstaller 处理）
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except Exception:
    HAS_TRAY = False


def get_base_dir():
    """配置/数据文件目录：始终与 exe（或源码）同目录，便于用户查找修改"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_web_dir():
    """web 静态资源目录：打包后从 _MEIPASS 临时目录读取"""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", get_base_dir()), "web")
    return os.path.join(get_base_dir(), "web")


_base_icon_cache = None


def _make_base_icon():
    """基础图标（读取 icon.png 或绘制默认），进程内缓存避免反复读盘"""
    global _base_icon_cache
    if _base_icon_cache is not None:
        return _base_icon_cache.copy()
    try:
        if getattr(sys, "frozen", False):
            icon_path = os.path.join(getattr(sys, "_MEIPASS", ""), "icon.png")
        else:
            icon_path = os.path.join(get_base_dir(), "icon.png")
        if os.path.isfile(icon_path):
            img = Image.open(icon_path).convert("RGBA")
            _base_icon_cache = img
            return img.copy()
    except Exception:
        pass
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(59, 130, 246, 255))
    _base_icon_cache = img
    return img.copy()


def _make_icon_image():
    """托盘图标：根据连接状态着色（绿=已连/橙=连接中/灰=未连）"""
    base = _make_base_icon().convert("RGBA")
    state = connector.get_state().get("state", "disconnected")
    color = {
        "connected": (16, 185, 129, 255),    # 绿
        "connecting": (245, 158, 11, 255),   # 橙
        "disconnected": (156, 163, 175, 255),# 灰
        "error": (239, 68, 68, 255),         # 红
    }.get(state, (156, 163, 175, 255))

    # 在图标右下角叠加一个状态圆点
    size = base.size[0]
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    r = max(4, size // 6)
    margin = 1
    od.ellipse([size - 2 * r - margin, size - 2 * r - margin,
                size - margin, size - margin], fill=color)
    return Image.alpha_composite(base, overlay)


# 全局托盘图标引用
_icon = None
_icon_state_thread = None


def _on_connected():
    """连接成功回调：根据设置执行「退出」或「收起」"""
    app = cfg_mod.get_app()
    if app.get("exit_after_connect", False):
        _do_exit()
    elif app.get("minimize_after_connect", False):
        from notify import notify
        notify("校园网已连接", "程序已收起至托盘，后台继续守护网络")


def _do_exit():
    from notify import notify
    notify("校园网已连接", "已按设置自动退出程序")

    def _exit():
        time.sleep(2)
        connector.stop_connector()
        if _icon is not None:
            try:
                _icon.stop()
            except Exception:
                pass
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()


def _update_tray_icon():
    """后台线程：周期刷新托盘图标颜色"""
    global _icon
    while _icon is not None:
        try:
            _icon.icon = _make_icon_image()
        except Exception:
            pass
        time.sleep(5)


def main():
    base = get_base_dir()
    config_path = os.path.join(base, "config.yaml")
    app_path = os.path.join(base, "app.json")
    web_dir = get_web_dir()
    log_dir = os.path.join(base, "logs")

    silent = "--silent" in sys.argv  # 自启静默模式

    # 初始化日志
    logger.setup_logger(log_dir)

    # 加载配置
    try:
        cfg_mod.load_config(config_path)
    except Exception as e:
        logger.log_error("读取配置失败: %s" % e)
    try:
        cfg_mod.load_app(app_path)
    except Exception as e:
        logger.log_error("读取应用设置失败: %s" % e)

    # 确保 token 存在
    token = cfg_mod.ensure_token()
    try:
        cfg_mod.save_app(app_path)
    except Exception:
        pass

    # 初始化统计
    stats.init_stats(os.path.join(base, "stats.json"))

    logger.log_info("程序启动")

    # 启动后台连接线程
    connector.start_connector(on_state_change_notify, on_connected=_on_connected)

    # 启动配置页 Web 服务
    port = cfg_mod.get_app().get("web_port", 17777)
    try:
        webserver.start_web_server(config_path, app_path, web_dir, port)
    except OSError:
        import random
        port = random.randint(20000, 40000)
        try:
            webserver.start_web_server(config_path, app_path, web_dir, port)
        except OSError as e:
            logger.log_error("Web 服务启动失败: %s" % e)

    url = "http://127.0.0.1:%d/?token=%s" % (port, token)

    # 首次引导：账号为空且非静默模式，自动打开配置页
    if not silent and not cfg_mod.get_config().get("account"):
        webbrowser.open(url)

    # 命令行参数 --web 强制打开
    if "--web" in sys.argv:
        webbrowser.open(url)

    if not HAS_TRAY or "--no-tray" in sys.argv:
        # 无托盘模式：阻塞
        print("配置页: %s" % url)
        print("按 Ctrl+C 退出")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return

    # 系统托盘
    global _icon, _icon_state_thread
    icon = pystray.Icon(
        "campus_net",
        _make_icon_image(),
        "校园网自动连接 v" + __version__,
        menu=pystray.Menu(
            pystray.MenuItem("打开配置页", lambda: webbrowser.open(url),
                            default=True),
            pystray.MenuItem("立即连接",
                            lambda: connector.connect_once()),
            pystray.MenuItem(
                "开机自启",
                _toggle_auto_start,
                checked=lambda item: _auto_start_checked(item)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda icon, item: _quit(icon)),
        ),
    )
    _icon = icon
    _icon_state_thread = threading.Thread(target=_update_tray_icon, daemon=True)
    _icon_state_thread.start()
    icon.run()


def _auto_start_checked(item):
    import autostart
    return autostart.get_auto_start()


def _toggle_auto_start(icon, item):
    import autostart
    from notify import notify
    cur = autostart.get_auto_start()
    try:
        autostart.set_auto_start(not cur)
        cfg_mod.set_app({"auto_start": not cur})
        base = get_base_dir()
        cfg_mod.save_app(os.path.join(base, "app.json"))
        notify("开机自启", "已开启" if not cur else "已关闭")
    except Exception as e:
        notify("开机自启设置失败", str(e))


def _quit(icon):
    connector.stop_connector()
    stats.record_disconnect()
    icon.stop()


if __name__ == "__main__":
    main()
