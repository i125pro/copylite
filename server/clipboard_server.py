#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-Platform Clipboard Server
Stores text clipboard content, serves a web UI for mobile access.
Designed to run on Termux (Android).
"""

import http.server
import json
import urllib.parse
import os
import sys
import time
import threading
from datetime import datetime

# ===== Configuration =====
HOST = "0.0.0.0"
PORT = 8086
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clipboard_data.json")

# ===== In-memory store =====
clipboard_store = {
    "content": "",
    "updated_at": "",
    "history": []  # last 20 entries
}
lock = threading.Lock()

def load_data():
    global clipboard_store
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                clipboard_store = json.load(f)
        except Exception:
            pass

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(clipboard_store, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to save data: {e}")

# ===== HTML Web UI =====
WEB_UI = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>剪贴板服务</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px;
  }
  .container {
    max-width: 480px;
    width: 100%;
  }
  h1 {
    text-align: center;
    font-size: 1.5rem;
    margin-bottom: 6px;
    color: #38bdf8;
  }
  .status {
    text-align: center;
    font-size: 0.8rem;
    color: #64748b;
    margin-bottom: 20px;
  }
  .card {
    background: #1e293b;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
    border: 1px solid #334155;
  }
  .card-title {
    font-size: 0.85rem;
    color: #94a3b8;
    margin-bottom: 10px;
    font-weight: 600;
  }
  textarea {
    width: 100%;
    min-height: 120px;
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 12px;
    font-size: 0.95rem;
    resize: vertical;
    outline: none;
    font-family: inherit;
  }
  textarea:focus { border-color: #38bdf8; }
  .btn-row {
    display: flex;
    gap: 10px;
    margin-top: 12px;
  }
  .btn {
    flex: 1;
    padding: 12px;
    border: none;
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }
  .btn-primary {
    background: #2563eb;
    color: white;
  }
  .btn-primary:hover { background: #1d4ed8; }
  .btn-primary:active { transform: scale(0.97); }
  .btn-secondary {
    background: #334155;
    color: #e2e8f0;
  }
  .btn-secondary:hover { background: #475569; }
  .btn-secondary:active { transform: scale(0.97); }
  .toast {
    position: fixed;
    bottom: 30px;
    left: 50%;
    transform: translateX(-50%) translateY(80px);
    background: #22c55e;
    color: white;
    padding: 10px 24px;
    border-radius: 20px;
    font-size: 0.9rem;
    font-weight: 600;
    opacity: 0;
    transition: all 0.3s;
    pointer-events: none;
    z-index: 100;
  }
  .toast.show {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
  }
  .history-item {
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
    font-size: 0.85rem;
    cursor: pointer;
    transition: border-color 0.2s;
    word-break: break-all;
    max-height: 60px;
    overflow: hidden;
    position: relative;
  }
  .history-item:hover { border-color: #38bdf8; }
  .history-time {
    font-size: 0.7rem;
    color: #64748b;
    margin-bottom: 4px;
  }
  .history-text {
    color: #cbd5e1;
  }
  .empty { text-align: center; color: #475569; padding: 20px; font-size: 0.9rem; }
</style>
</head>
<body>
<div class="container">
  <h1>📋 剪贴板服务</h1>
  <div class="status" id="status">连接中...</div>

  <div class="card">
    <div class="card-title">📤 上传到剪贴板</div>
    <textarea id="uploadText" placeholder="输入要同步的文本..."></textarea>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="uploadClipboard()">上传</button>
      <button class="btn btn-secondary" onclick="pasteFromDevice()">从设备粘贴</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">📥 从剪贴板下载</div>
    <textarea id="downloadText" readonly placeholder="点击下方按钮获取剪贴板内容..."></textarea>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="downloadClipboard()">下载</button>
      <button class="btn btn-secondary" onclick="copyToDevice()">复制到设备</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">📜 历史记录</div>
    <div id="historyList">
      <div class="empty">暂无历史记录</div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const API_BASE = window.location.origin;

function showToast(msg, color) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = color || '#22c55e';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

async function fetchClipboard() {
  try {
    const res = await fetch(API_BASE + '/api/clipboard');
    const data = await res.json();
    if (data.content) {
      document.getElementById('downloadText').value = data.content;
    }
    document.getElementById('status').textContent = '已连接 · 更新于 ' + (data.updated_at || '—');
    renderHistory(data.history || []);
  } catch(e) {
    document.getElementById('status').textContent = '连接失败';
    document.getElementById('status').style.color = '#f87171';
  }
}

async function uploadClipboard() {
  const text = document.getElementById('uploadText').value;
  if (!text.trim()) { showToast('请输入文本', '#ef4444'); return; }
  try {
    await fetch(API_BASE + '/api/clipboard', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content: text})
    });
    showToast('上传成功');
    fetchClipboard();
  } catch(e) { showToast('上传失败', '#ef4444'); }
}

async function downloadClipboard() {
  try {
    const res = await fetch(API_BASE + '/api/clipboard');
    const data = await res.json();
    document.getElementById('downloadText').value = data.content || '';
    showToast('已获取剪贴板内容');
  } catch(e) { showToast('下载失败', '#ef4444'); }
}

async function pasteFromDevice() {
  // Try modern API first (works on HTTPS/localhost)
  if (navigator.clipboard && navigator.clipboard.readText) {
    try {
      const text = await navigator.clipboard.readText();
      document.getElementById('uploadText').value = text;
      showToast('已从设备剪贴板读取');
      return;
    } catch(e) {}
  }
  // Fallback: create a hidden textarea, focus it, and trigger paste
  try {
    const ta = document.createElement('textarea');
    ta.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0';
    ta.setAttribute('readonly', '');
    document.body.appendChild(ta);
    ta.focus();
    const ok = document.execCommand('paste');
    const text = ta.value;
    document.body.removeChild(ta);
    if (ok && text) {
      document.getElementById('uploadText').value = text;
      showToast('已从设备剪贴板读取');
    } else {
      // Final fallback: prompt user
      promptPaste();
    }
  } catch(e) {
    promptPaste();
  }
}

function promptPaste() {
  const text = prompt('请在下方粘贴你的剪贴板内容（长按粘贴框）：');
  if (text !== null && text.trim()) {
    document.getElementById('uploadText').value = text;
    showToast('已从粘贴框读取');
  } else if (text !== null) {
    showToast('粘贴内容为空', '#f59e0b');
  }
}

function copyToDevice() {
  const text = document.getElementById('downloadText').value;
  if (!text) { showToast('没有内容可复制', '#ef4444'); return; }
  // Try modern API first
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast('已复制到设备剪贴板');
    }).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  // Reliable fallback: create a visible textarea, select, and execCommand
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;top:40%;left:10%;width:80%;height:80px;z-index:9999;font-size:16px;padding:10px;border-radius:8px;border:2px solid #38bdf8;background:#0f172a;color:#e2e8f0;text-align:center';
  document.body.appendChild(ta);
  ta.select();
  ta.setSelectionRange(0, 99999);
  try {
    document.execCommand('copy');
    showToast('已复制 ✓');
  } catch(e) {
    showToast('请长按文本框手动复制', '#f59e0b');
  }
  setTimeout(() => { document.body.removeChild(ta); }, 1500);
}

function renderHistory(history) {
  const el = document.getElementById('historyList');
  if (!history.length) { el.innerHTML = '<div class="empty">暂无历史记录</div>'; return; }
  el.innerHTML = history.map((h, i) => `
    <div class="history-item" onclick="useHistory(${i})">
      <div class="history-time">${h.updated_at}</div>
      <div class="history-text">${escHtml(h.content.substring(0, 100))}${h.content.length > 100 ? '...' : ''}</div>
    </div>
  `).join('');
}

function useHistory(idx) {
  try {
    const res = fetch(API_BASE + '/api/clipboard');
    res.then(r => r.json()).then(data => {
      if (data.history && data.history[idx]) {
        document.getElementById('uploadText').value = data.history[idx].content;
        showToast('已填入历史内容');
      }
    });
  } catch(e) {}
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Auto-refresh every 5s
fetchClipboard();
setInterval(fetchClipboard, 5000);
</script>
</body>
</html>"""

# ===== HTTP Handler =====
class ClipboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {args[0]}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(WEB_UI.encode("utf-8"))

        elif parsed.path == "/api/clipboard":
            with lock:
                resp = json.dumps(clipboard_store, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(resp.encode("utf-8"))

        elif parsed.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/clipboard":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                content = data.get("content", "")
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with lock:
                    entry = {"content": content, "updated_at": now}
                    clipboard_store["content"] = content
                    clipboard_store["updated_at"] = now
                    clipboard_store["history"].insert(0, entry)
                    clipboard_store["history"] = clipboard_store["history"][:20]
                    save_data()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "updated_at": now}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

# ===== Main =====
if __name__ == "__main__":
    load_data()
    server = http.server.HTTPServer((HOST, PORT), ClipboardHandler)
    print(f"[Clipboard Server] Running on http://{HOST}:{PORT}")
    print(f"[Clipboard Server] Web UI: http://localhost:{PORT}")
    print(f"[Clipboard Server] API: GET/POST /api/clipboard")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Clipboard Server] Shutting down...")
        server.shutdown()
