#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clipboard Sync - Windows Tray Client
运行后只在右下角系统托盘显示图标，不显示任务栏。
右键托盘图标：显示窗口 / 配置服务器 / 退出
"""

import tkinter as tk
import json
import threading
import sys
import os
import time
import ctypes
import urllib.request
import urllib.error
import ctypes.wintypes

# ===== 单实例限制：只允许运行一个实例 =====
MUTEX_NAME = "Global\\ClipboardSync_SingleInstance_Mutex_v2"
_kernel32 = ctypes.windll.kernel32
_mutex = _kernel32.CreateMutexW(None, True, MUTEX_NAME)
if _kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    ctypes.windll.user32.MessageBoxW(
        0, "剪贴板同步已在运行中！", "提示", 0x40
    )
    sys.exit(0)

# ===== Configuration =====
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "clipboard_config.json")
DEFAULT_SERVER = "http://192.168.0.24:8086"


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"server_url": DEFAULT_SERVER}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


config = load_config()

# ===== DPI Awareness =====
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# ===== API Functions =====
def api_get(server_url):
    req = urllib.request.Request(f"{server_url}/api/clipboard")
    req.add_header("User-Agent", "ClipboardClient/2.0")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post(server_url, content):
    data = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(f"{server_url}/api/clipboard", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "ClipboardClient/2.0")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_health(server_url):
    req = urllib.request.Request(f"{server_url}/api/health")
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))


class ClipboardApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("剪贴板同步")
        self.server_url = config.get("server_url", DEFAULT_SERVER)
        self.last_content = ""
        self.running = True
        self.tray_icon = None
        self.tray_thread = None

        # Drag state
        self._drag_x = 0
        self._drag_y = 0

        self._build_window()
        self._build_ui()
        self._setup_tray()
        self._start_background_tasks()

    # ==================== Window ====================
    def _build_window(self):
        """无边框悬浮窗，不在任务栏显示"""
        self.root.overrideredirect(True)       # 去掉标题栏 → 任务栏不显示
        self.root.attributes("-topmost", True)  # 始终置顶
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg="#1a1a2e")

        w, h = 290, 155
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = sw - w - 16
        y = sh - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.resizable(False, False)

        # 启动时隐藏，只显示托盘图标
        self.root.withdraw()

    # ==================== UI ====================
    def _build_ui(self):
        outer = tk.Frame(self.root, bg="#1a1a2e", padx=8, pady=6)
        outer.pack(fill=tk.BOTH, expand=True)

        # 拖拽绑定到整个外层
        outer.bind("<Button-1>", self._drag_start)
        outer.bind("<B1-Motion>", self._drag_move)

        # --- 标题行 ---
        top = tk.Frame(outer, bg="#1a1a2e")
        top.pack(fill=tk.X)
        top.bind("<Button-1>", self._drag_start)
        top.bind("<B1-Motion>", self._drag_move)

        tk.Label(top, text="📋 剪贴板同步", font=("Microsoft YaHei", 10, "bold"),
                 bg="#1a1a2e", fg="#38bdf8").pack(side=tk.LEFT)
        tk.Label(top, text="  ", bg="#1a1a2e").pack(side=tk.LEFT)

        self.status_dot = tk.Label(top, text="●", font=("Arial", 8),
                                   bg="#1a1a2e", fg="#ef4444")
        self.status_dot.pack(side=tk.RIGHT, padx=(0, 2))

        self.status_lbl = tk.Label(top, text="…", font=("Microsoft YaHei", 7),
                                   bg="#1a1a2e", fg="#64748b")
        self.status_lbl.pack(side=tk.RIGHT)

        # 关闭按钮 ×
        close_btn = tk.Label(top, text="✕", font=("Arial", 10),
                             bg="#1a1a2e", fg="#64748b", cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=(0, 6))
        close_btn.bind("<Button-1>", lambda e: self._hide_window())

        # 分隔线
        tk.Frame(outer, bg="#334155", height=1).pack(fill=tk.X, pady=4)

        # 文本预览
        self.preview = tk.Text(outer, height=2, bg="#0f172a", fg="#e2e8f0",
                               font=("Microsoft YaHei", 8), borderwidth=0,
                               highlightthickness=1, highlightcolor="#334155",
                               highlightbackground="#334155", wrap=tk.WORD,
                               padx=6, pady=4)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(2, 4))

        # 按钮行
        bf = tk.Frame(outer, bg="#1a1a2e")
        bf.pack(fill=tk.X)

        self.btn_up = tk.Button(bf, text="⬆ 复制上传",
                                font=("Microsoft YaHei", 8, "bold"),
                                bg="#2563eb", fg="white", activebackground="#1d4ed8",
                                activeforeground="white", borderwidth=0,
                                padx=8, pady=3, cursor="hand2",
                                command=self._upload)
        self.btn_up.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3))

        self.btn_dn = tk.Button(bf, text="⬇ 下载粘贴",
                                font=("Microsoft YaHei", 8, "bold"),
                                bg="#334155", fg="#e2e8f0", activebackground="#475569",
                                activeforeground="white", borderwidth=0,
                                padx=8, pady=3, cursor="hand2",
                                command=self._download)
        self.btn_dn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0))

    # ==================== Drag ====================
    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event):
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    # ==================== Tray ====================
    def _setup_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([12, 8, 52, 56], radius=6,
                                   fill="#2563eb", outline="#38bdf8", width=2)
            draw.rectangle([22, 4, 42, 16], fill="#38bdf8")
            draw.rectangle([26, 20, 48, 22], fill="white")
            draw.rectangle([26, 28, 48, 30], fill="white")
            draw.rectangle([26, 36, 42, 38], fill="white")

            menu = pystray.Menu(
                pystray.MenuItem("显示窗口", self._on_show, default=True),
                pystray.MenuItem("配置服务器", self._on_config),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._on_quit),
            )
            self.tray_icon = pystray.Icon("clip", img, "剪贴板同步", menu)
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()
        except ImportError:
            print("[WARN] pystray/PIL not installed, tray disabled")

    # --- Tray callbacks (called from pystray thread) ---
    def _on_show(self, icon=None, item=None):
        self.root.after(0, self._show_window)

    def _on_config(self, icon=None, item=None):
        self.root.after(0, self._show_window)
        self.root.after(100, self._open_settings)

    def _on_quit(self, icon=None, item=None):
        self.running = False
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        # Release mutex
        try:
            _kernel32.ReleaseMutex(_mutex)
            _kernel32.CloseHandle(_mutex)
        except Exception:
            pass
        self.root.after(0, self.root.destroy)

    # ==================== Show / Hide ====================
    def _show_window(self):
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()

    def _hide_window(self):
        self.root.withdraw()

    # ==================== Settings Dialog ====================
    def _open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.configure(bg="#1a1a2e")
        dlg.attributes("-topmost", True)

        dw, dh = 340, 110
        sx = self.root.winfo_x() + (self.root.winfo_width() - dw) // 2
        sy = self.root.winfo_y() + self.root.winfo_height() + 4
        dlg.geometry(f"{dw}x{dh}+{sx}+{sy}")

        tk.Label(dlg, text="服务器地址:", font=("Microsoft YaHei", 9),
                 bg="#1a1a2e", fg="#e2e8f0").pack(anchor=tk.W, padx=14, pady=(12, 4))

        url_var = tk.StringVar(value=self.server_url)
        entry = tk.Entry(dlg, textvariable=url_var, font=("Consolas", 10),
                         bg="#0f172a", fg="#e2e8f0", insertbackground="white",
                         borderwidth=1, relief=tk.SOLID)
        entry.pack(fill=tk.X, padx=14, pady=(0, 8))

        bf = tk.Frame(dlg, bg="#1a1a2e")
        bf.pack(fill=tk.X, padx=14)

        def save():
            u = url_var.get().strip().rstrip("/")
            if u:
                self.server_url = u
                config["server_url"] = u
                save_config(config)
                self._check_conn()
            dlg.destroy()

        tk.Button(bf, text="保存", font=("Microsoft YaHei", 9, "bold"),
                  bg="#2563eb", fg="white", borderwidth=0, padx=14, pady=3,
                  command=save).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        tk.Button(bf, text="取消", font=("Microsoft YaHei", 9),
                  bg="#334155", fg="#e2e8f0", borderwidth=0, padx=14, pady=3,
                  command=dlg.destroy).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))

    # ==================== Clipboard Operations ====================
    def _upload(self):
        try:
            text = self.root.clipboard_get()
            if not text:
                self._flash("剪贴板为空", "#f59e0b")
                return
            api_post(self.server_url, text)
            self.last_content = text
            self._set_preview(text)
            self._flash("已上传 ✓", "#22c55e")
        except Exception as e:
            self._flash("上传失败", "#ef4444")

    def _download(self):
        try:
            data = api_get(self.server_url)
            text = data.get("content", "")
            if text:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.last_content = text
                self._set_preview(text)
                self._flash("已复制 ✓", "#22c55e")
            else:
                self._flash("服务器为空", "#f59e0b")
        except Exception:
            self._flash("下载失败", "#ef4444")

    # ==================== Helpers ====================
    def _set_preview(self, text):
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text[:200])

    def _flash(self, msg, color):
        self.status_lbl.config(text=msg, fg=color)
        self.root.after(2500, lambda: self.status_lbl.config(text="", fg="#64748b"))

    def _check_conn(self):
        def check():
            ok = False
            try:
                api_health(self.server_url)
                ok = True
            except Exception:
                pass
            if ok:
                self.root.after(0, lambda: (
                    self.status_dot.config(fg="#22c55e"),
                    self.status_lbl.config(text="已连接", fg="#22c55e")
                ))
            else:
                self.root.after(0, lambda: (
                    self.status_dot.config(fg="#ef4444"),
                    self.status_lbl.config(text="未连接", fg="#ef4444")
                ))
        threading.Thread(target=check, daemon=True).start()

    # ==================== Background Tasks ====================
    def _start_background_tasks(self):
        self._check_conn()

        def loop():
            while self.running:
                try:
                    data = api_get(self.server_url)
                    c = data.get("content", "")
                    if c and c != self.last_content:
                        self.last_content = c
                        self.root.after(0, lambda t=c: self._set_preview(t))
                        self.root.after(0, lambda: self.status_dot.config(fg="#22c55e"))
                except Exception:
                    self.root.after(0, lambda: self.status_dot.config(fg="#ef4444"))
                time.sleep(5)

        threading.Thread(target=loop, daemon=True).start()

    # ==================== Run ====================
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ClipboardApp()
    app.run()
