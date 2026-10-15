# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""校园网自动连接工具

功能：
1. 自动连接校园网（Dr.COM EPortal 认证）
2. 系统托盘常驻，断网自动重连
3. 本地网页配置页，可视化修改账号/密码/运营商/开机自启等设置
4. 可选开机自启（当前用户注册表 Run 键，无需管理员）
5. 断网/重连成功时 Windows 弹窗提醒

运行方式：
- 源码运行：python main.py（或双击 启动.bat）
- 打包成 exe：pyinstaller -F -w --add-data "web;web" main.py

命令行参数：
- --web       启动后立即打开配置页
- --no-tray   不显示系统托盘（调试用）
"""
import main

if __name__ == "__main__":
    main.main()
