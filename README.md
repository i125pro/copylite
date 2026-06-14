# CopyLite - 跨平台剪贴板同步服务

轻量级跨平台剪贴板同步工具，基于 Python HTTP 服务器，支持 Windows、Android、iOS 和 Web 多端共享剪贴板文本。

## 架构

```
┌──────────┐                  ┌───────────────────┐                  ┌──────────┐
│ Windows  │◄── HTTP API ───►│   Termux Server   │◄── HTTP API ───►│ Android  │
│  EXE     │   上传/下载文本  │  Python HTTP      │   上传/下载文本  │  App     │
└──────────┘                  │  端口: 8086       │                  └──────────┘
                              │  守护进程+自启动   │
┌──────────┐                  │                   │
│  iOS     │── Shortcuts ───►│                   │
│  快捷指令 │   GET/POST API  │                   │
└──────────┘                  └───────────────────┘
                                       ▲
                                       │ Web UI
                                 浏览器直接访问
```

## 快速开始

### 1. 服务器端（Termux）

服务器已部署到 Termux，运行在 `http://192.168.0.24:8086`。

**启动/管理：**
```bash
# SSH 连接到 Termux（端口 8022）
ssh -p 8022 u0_a272@192.168.0.24

# 启动服务器（含唤醒锁+守护进程）
bash ~/clipboard-server/launcher.sh

# 查看状态
curl http://localhost:8086/api/health
cat ~/clipboard-server/server.log
cat ~/clipboard-server/watchdog.log
```

**自启动机制：** 已在 `~/.bashrc` 中配置自动启动（含 `pgrep` 防重复），打开 Termux 即自动运行。服务器内置 5 分钟定时守护，进程被杀后会自动重启。同时启用了 `termux-wake-lock` 防止 Android 后台杀进程。

**建议在手机端操作：** 进入手机设置 → 应用管理 → Termux → 电池 → 关闭"电池优化"/"后台限制"，以确保服务长期稳定运行。

### 2. Windows 客户端

**运行：** 双击 `windows/ClipboardSync.exe` 即可启动。

**悬浮窗：** 启动后在屏幕右下角显示一个小悬浮窗，包含"复制上传"和"下载粘贴"两个按钮。窗口可拖动，始终置顶，不在任务栏显示。仅支持运行一个实例。

**系统托盘：** 右下角托盘图标右键菜单：
- 显示窗口 — 恢复悬浮窗
- 配置服务器 — 修改服务器地址（默认 `http://192.168.0.24:8086`）
- 退出 — 关闭程序

**注意：** 关闭悬浮窗的 ✕ 按钮不会退出程序，而是最小化到托盘。需通过托盘菜单退出。

### 3. Android App

**安装：** 将 `android/ClipboardSync.apk` 传到手机安装（需允许"安装未知来源应用"）。

**使用步骤：**
1. 打开应用，点击右上角 ⚙ 进入设置页
2. 输入服务器地址（如 `http://192.168.0.24:8086`），点"测试连接"确认，保存
3. 返回主页：
   - **上传剪贴板：** 点击"从剪贴板读取"自动获取本机文本，或手动输入，点"上传到服务器"
   - **下载剪贴板：** 点击"从服务器下载"获取内容，点"复制到剪贴板"写入本机
4. 主页每 5 秒自动刷新服务器最新内容

**源码编译：** 解压 `android/ClipboardSync-Android.zip`，用 Android Studio 打开或命令行执行 `gradlew assembleDebug`，APK 输出在 `app/build/outputs/apk/debug/`。

### 4. iOS 快捷指令

iOS 端通过系统自带"快捷指令"App 实现一键操作，无需安装额外应用，不经过浏览器。

**创建"从服务器复制"快捷指令：**

1. 打开"快捷指令"App → 点 + 新建
2. 添加操作 **"获取URL的内容"**：
   - URL 填 `http://192.168.0.24:8086/api/clipboard`
   - 方法选 GET
3. 添加操作 **"从词典中获取值"**：
   - 获取 **值**，关键字填 `content`
4. 添加操作 **"拷贝至剪贴板"**
5. 添加操作 **"显示通知"**，内容填 `已复制`
6. 重命名为"从服务器复制"，完成

**创建"粘贴到服务器"快捷指令：**

1. 新建快捷指令
2. 添加操作 **"获取剪贴板"**
3. 添加操作 **"获取URL的内容"**：
   - URL 填 `http://192.168.0.24:8086/api/clipboard`
   - 方法选 POST
   - 请求体类型选 JSON，添加键 `content`，值选上一步的"剪贴板"变量
4. 添加操作 **"显示通知"**，内容填 `已粘贴到服务器`
5. 重命名为"粘贴到服务器"，完成

**添加到主屏幕：** 长按快捷指令 → "添加到主屏幕"，点击图标即可一键执行，无页面弹出。

### 5. Web UI（浏览器）

在任意设备浏览器访问 `http://192.168.0.24:8086` 即可使用 Web 界面，功能包括上传/下载剪贴板、查看历史记录。页面每 5 秒自动刷新。

## API 文档

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/clipboard` | GET | 获取当前剪贴板内容和历史记录 |
| `/api/clipboard` | POST | 上传文本到剪贴板（JSON body: `{"content": "文本"}`） |
| `/api/health` | GET | 健康检查，返回 `{"status":"ok"}` |
| `/copy` | GET | iOS 快捷指令页面（从服务器复制） |
| `/paste` | GET | iOS 快捷指令页面（粘贴到服务器） |

## 项目结构

```
copylite/
├── server/
│   └── clipboard_server.py    # Python 服务器（纯标准库，无外部依赖）
├── windows/
│   ├── clipboard_client.py    # Windows 客户端源码
│   └── ClipboardSync.exe     # Windows 可执行文件（可直接运行）
├── android/
│   ├── ClipboardSync.apk     # Android APK（可直接安装）
│   └── ClipboardSync-Android.zip  # Android 完整源码
├── shortcuts/
│   ├── copy-from-server.html  # iOS 备用网页版（从服务器复制）
│   └── paste-to-server.html   # iOS 备用网页版（粘贴到服务器）
└── README.md
```
