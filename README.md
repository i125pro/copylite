# 跨平台剪贴板服务 - 使用指南

## 架构概览

```
┌─────────────┐     HTTP API     ┌──────────────────┐     HTTP API     ┌─────────────┐
│  Windows    │◄────────────────►│  Termux Server   │◄────────────────►│  Android    │
│  EXE 悬浮窗 │   上传/下载文本   │  192.168.0.24    │   上传/下载文本   │  App        │
└─────────────┘                  │  端口: 8086      │                  └─────────────┘
                                 └──────────────────┘
```

---

## 1. 服务器端 (已部署)

### 服务器信息
- **地址**: `http://192.168.0.24:8086`
- **Web UI**: `http://192.168.0.24:8086`
- **API**: `GET/POST /api/clipboard`
- **Health**: `GET /api/health`
- **状态**: ✅ 已运行

### 管理命令 (通过SSH)
```bash
# SSH 连接
ssh -p 8022 u0_a272@192.168.0.24  # 密码: 123

# 启动服务器
bash ~/clipboard-server/start.sh

# 停止服务器
bash ~/clipboard-server/stop.sh

# 查看日志
cat ~/clipboard-server/server.log
```

### 自启动配置
已配置 Termux:Boot 自启动脚本: `~/.termux/boot/clipboard-server.sh`
需要在手机上安装 **Termux:Boot** 应用才能自动启动。
手动安装 Termux:Boot: 从 F-Droid 下载 https://f-droid.org/packages/com.termux.boot/

---

## 2. Windows 客户端

### 使用方法
1. 双击运行 `ClipboardSync.exe`
2. 悬浮窗会显示在屏幕右下角
3. **复制上传**: 复制文字到剪贴板后点击"⬆ 复制上传"
4. **下载粘贴**: 点击"⬇ 下载粘贴"获取服务器上的文本
5. 窗口可拖动，始终置顶

### 系统托盘
- 右键托盘图标:
  - **显示窗口**: 恢复悬浮窗
  - **配置服务器**: 修改服务器地址
  - **退出**: 关闭程序

### 首次配置
- 默认服务器地址: `http://192.168.0.24:8086`
- 右键托盘图标 → 配置服务器 → 输入新的服务器地址 → 保存

---

## 3. Android App

### 编译方法
1. 用 Android Studio 打开 `ClipboardSync-Android.zip` 解压后的项目
2. 等待 Gradle 同步完成
3. 点击 Build → Build Bundle(s) / APK(s) → Build APK(s)
4. APK 输出位置: `app/build/outputs/apk/debug/app-debug.apk`

### 或使用命令行编译
```bash
# 确保已安装 Android SDK
export ANDROID_HOME=/path/to/android/sdk

# 编译 debug APK
cd android
./gradlew assembleDebug

# APK 位置
ls app/build/outputs/apk/debug/app-debug.apk
```

### 使用方法
1. 安装 APK 后打开应用
2. 点击右上角 ⚙ 按钮配置服务器地址
3. 主页面:
   - **上传区域**: 输入文本或从剪贴板读取，点击"上传"
   - **下载区域**: 点击"下载"获取服务器内容，点击"复制到剪贴板"
4. 每5秒自动刷新服务器内容

---

## API 文档

### 获取剪贴板内容
```
GET /api/clipboard
响应: {"content": "文本内容", "updated_at": "2026-06-14 22:00:00", "history": [...]}
```

### 上传剪贴板内容
```
POST /api/clipboard
请求体: {"content": "要上传的文本"}
响应: {"status": "ok", "updated_at": "2026-06-14 22:00:00"}
```

### 健康检查
```
GET /api/health
响应: {"status": "ok"}
```

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `ClipboardSync.exe` | Windows 悬浮窗客户端 (可直接运行) |
| `clipboard_server.py` | Python 剪贴板服务器代码 (已部署到Termux) |
| `ClipboardSync-Android.zip` | Android App 完整源码项目 |
