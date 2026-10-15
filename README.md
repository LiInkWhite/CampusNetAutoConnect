# CampusNetAutoConnect

![Version](https://img.shields.io/badge/version-2.0.0-blue) ![License](https://img.shields.io/badge/license-Apache%202.0-green)

一个用于 **Dr.COM EPortal 认证**校园网的 Windows 自动登录工具。后台常驻自动连接、断网自动重连，并提供系统托盘、可视化配置页面、开机自启等便捷功能。

> 本项目是 [connect_jxyy_network](https://github.com/wochaoop/connect_jxyy_network) 的 **Python 独立重写版**，仅参考了其 Dr.COM 认证协议流程与配置格式，不含其源码。详见 [NOTICE](NOTICE)。

---

## ✨ 功能特性

- 🔌 **自动连接** — 后台常驻，检测到未登录自动完成 Dr.COM EPortal 认证
- 🔁 **断网重连** — 网络断开后自动重新认证
- 🖥️ **系统托盘** — 右下角常驻图标，右键菜单快捷操作，图标按状态变色
- ⚙️ **可视化配置页** — 浏览器表单修改账号/密码/运营商等所有设置
- 🚀 **开机自启** — 一键开关，写入当前用户注册表，无需管理员权限
- 🔔 **断网/重连提醒** — Windows Toast 弹窗通知
- 📋 **连接日志** — 滚动日志文件 + 配置页实时查看
- 📊 **数据统计** — 近 7 天连接成功率、在线时长等统计面板
- 🔐 **配置页鉴权** — 随机 token 保护，防止局域网内他人篡改
- 💤 **连接后自动退出 / 收起** — 连上后可选择退出进程或收起至托盘

---

## 🚀 快速开始

### 方式一：使用打包好的可执行文件（推荐）

1. 前往 [Releases](../../releases) 下载 `CampusNetAutoConnect.exe`
2. 双击运行（建议放入固定目录，配置会生成在 exe 同目录）
3. 右下角托盘图标右键 → **打开配置页**
4. 填写账号、密码、运营商，保存即可

### 方式二：从源码运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 复制配置示例并填写
cp config.example.yaml config.yaml

# 3. 运行
python main.py
```

---

## 🖥️ 配置说明

配置文件为 `config.yaml`，字段说明见 [config.example.yaml](config.example.yaml)。核心字段：

| 字段 | 说明 |
|------|------|
| `account` | 账号（一般为学号） |
| `password` | 密码 |
| `operator` | 运营商：`telecom` / `cmcc` / `unicom` |
| `inlet_ip` | 认证网关地址（不同学校可能不同，请按实际情况修改） |

---

## 📦 自行打包

```bash
pip install pyinstaller

pyinstaller --noconfirm --onefile --windowed \
  --name CampusNetAutoConnect \
  --icon icon.ico \
  --add-data "web;web" \
  --add-data "icon.png;." \
  --hidden-import pystray._win32 \
  main.py
```

---

## 🛠️ 开发

```bash
# 安装依赖（含开发工具）
pip install -r requirements.txt -r requirements-dev.txt

# 代码检查
ruff check .

# 类型检查
mypy

# 运行测试
pytest
```

配置字段集中定义在 `config.py` 的 `CONFIG_SCHEMA` / `APP_SCHEMA` 中（字段的默认值、类型、范围唯一来源），新增字段只需修改 Schema，Web 接口会自动生效。

### v2.0.0 变更要点

- 修复：`web_port` 保存失效、非法参数导致接口崩溃、`max_attempts` 不生效
- 登录重试增加指数退避，达到最大次数后自动暂停（防账号锁定），修改配置自动恢复
- Web 服务改为多线程，"立即连接"期间配置页不再卡顿
- 鉴权改为 fail-closed + 常数时间比较；配置/统计文件原子写盘
- 手动"立即连接"与后台循环互斥，统一走同一状态机（日志/统计/通知不再遗漏）
- 新增 pytest 测试、ruff/mypy 检查与 GitHub Actions CI

---

## ⚠️ 免责声明

- 本工具仅用于 **自动登录本人合法持有的校园网账号**，目的是省去重复手动登录的繁琐。
- 请勿将本工具用于任何**未授权访问、盗用他人账号**或其他违反法律法规及校园网管理规定的用途。
- 因使用本工具产生的任何后果，由使用者自行承担。

---

## 📄 许可证

本项目采用 [Apache License 2.0](LICENSE)。

认证协议与配置格式参考自 [connect_jxyy_network](https://github.com/wochaoop/connect_jxyy_network)（MIT License），版权声明见 [NOTICE](NOTICE)。
