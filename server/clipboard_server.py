#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-Platform Clipboard Server
Stores text clipboard content, serves a web UI for mobile access.
"""

import http.server
import socketserver
import json
import urllib.parse
import os
import sys
import time
import secrets
import threading
from datetime import datetime

# ===== Configuration =====
HOST = "0.0.0.0"
PORT = 8086
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "clipboard_data.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")
SHORTCUTS_DIR = os.path.join(BASE_DIR, "shortcuts")

# ===== Token Authentication =====
def load_or_create_token():
    """Load token from .env file, or generate one if not found."""
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("AUTH_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if token:
                            return token
        except Exception:
            pass
    # Generate new token
    token = secrets.token_urlsafe(32)
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(f"# CopyLite Authentication Token\n")
            f.write(f"# Include this token in all requests to access the clipboard service.\n")
            f.write(f"# Usage: http://your-server:8086?token={token}\n")
            f.write(f"# Or header: Authorization: Bearer {token}\n")
            f.write(f"AUTH_TOKEN={token}\n")
        print(f"[Auth] Generated new token: {token}")
    except Exception as e:
        print(f"[Auth] Warning: Could not save token to .env: {e}")
    return token

AUTH_TOKEN = load_or_create_token()

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
<title>CopyLite</title>
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
  /* Auth overlay */
  .auth-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: #0f172a; z-index: 999;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 20px;
  }
  .auth-overlay h2 { color: #38bdf8; margin-bottom: 8px; font-size: 1.3rem; }
  .auth-overlay p { color: #64748b; margin-bottom: 20px; font-size: 0.85rem; text-align: center; }
  .auth-input {
    width: 100%; max-width: 360px; padding: 12px; background: #1e293b;
    border: 1px solid #334155; border-radius: 8px; color: #e2e8f0;
    font-size: 1rem; outline: none; margin-bottom: 12px; font-family: monospace;
  }
  .auth-input:focus { border-color: #38bdf8; }
  .auth-btn {
    width: 100%; max-width: 360px; padding: 12px; background: #2563eb;
    color: white; border: none; border-radius: 8px; font-size: 1rem;
    font-weight: 600; cursor: pointer;
  }
  .auth-btn:hover { background: #1d4ed8; }
  .auth-error { color: #f87171; font-size: 0.85rem; margin-top: 10px; display: none; }
</style>
</head>
<body>

<!-- Auth Overlay -->
<div class="auth-overlay" id="authOverlay" style="display:none;">
  <h2>CopyLite</h2>
  <p>Enter your access token to continue</p>
  <input type="password" class="auth-input" id="tokenInput" placeholder="Paste your token here..." autocomplete="off">
  <button class="auth-btn" onclick="submitToken()">Verify & Enter</button>
  <div class="auth-error" id="authError">Invalid token, please try again.</div>
</div>

<div class="container" id="mainApp" style="display:none;">
  <h1>CopyLite</h1>
  <div class="status" id="status">Connecting...</div>

  <div class="card">
    <div class="card-title">Upload to Clipboard</div>
    <textarea id="uploadText" placeholder="Enter text to sync..."></textarea>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="uploadClipboard()">Upload</button>
      <button class="btn btn-secondary" onclick="pasteFromDevice()">Paste from Device</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Download from Clipboard</div>
    <textarea id="downloadText" readonly placeholder="Click button below to fetch content..."></textarea>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="downloadClipboard()">Download</button>
      <button class="btn btn-secondary" onclick="copyToDevice()">Copy to Device</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">History</div>
    <div id="historyList">
      <div class="empty">No history yet</div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const API_BASE = window.location.origin;
let authToken = '';

// --- Timeout-aware fetch ---
function fetchWithTimeout(url, options, timeoutMs) {
  timeoutMs = timeoutMs || 15000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, Object.assign({}, options || {}, {signal: controller.signal}))
    .finally(() => clearTimeout(timer));
}

// --- Token Management (localStorage persistence) ---
function getTokenFromURL() {
  const params = new URLSearchParams(window.location.search);
  return params.get('token') || '';
}

function saveToken(t) {
  try { localStorage.setItem('copylite_token', t); } catch(e) {}
}

function loadToken() {
  try { return localStorage.getItem('copylite_token') || ''; } catch(e) { return ''; }
}

function initAuth() {
  const urlToken = getTokenFromURL();
  if (urlToken) {
    authToken = urlToken;
    saveToken(urlToken);
    window.history.replaceState({}, '', window.location.pathname);
    verifyToken();
  } else {
    const saved = loadToken();
    if (saved) {
      authToken = saved;
      verifyToken();
    } else {
      document.getElementById('authOverlay').style.display = 'flex';
    }
  }
}

function submitToken() {
  const input = document.getElementById('tokenInput').value.trim();
  if (!input) return;
  document.getElementById('authError').style.display = 'none';
  authToken = input;
  saveToken(input);
  verifyToken();
}

async function verifyToken() {
  document.getElementById('status').textContent = 'Connecting...';
  document.getElementById('status').style.color = '#94a3b8';
  try {
    const res = await fetchWithTimeout(API_BASE + '/api/clipboard?token=' + encodeURIComponent(authToken));
    if (res.ok) {
      document.getElementById('authOverlay').style.display = 'none';
      document.getElementById('mainApp').style.display = 'block';
      fetchClipboard();
    } else if (res.status === 401) {
      showAuthError('Invalid token');
    } else {
      showAuthError('Server error (' + res.status + ')');
    }
  } catch(e) {
    if (e.name === 'AbortError') {
      showAuthError('Connection timed out, please retry');
    } else {
      showAuthError('Network error, please retry');
    }
  }
}

function showAuthError(msg) {
  document.getElementById('authOverlay').style.display = 'flex';
  const errEl = document.getElementById('authError');
  errEl.textContent = msg || 'Invalid token, please try again.';
  errEl.style.display = 'block';
  // Don't clear token on network errors - keep it for retry
  if (msg === 'Invalid token') {
    authToken = '';
    try { localStorage.removeItem('copylite_token'); } catch(e) {}
  }
}

// --- Authenticated Fetch with retry ---
function authFetch(url, options, retries) {
  retries = retries || 1;
  const sep = url.includes('?') ? '&' : '?';
  const authUrl = url + sep + 'token=' + encodeURIComponent(authToken);
  return fetchWithTimeout(authUrl, options).then(res => {
    if (res.status === 401) { showAuthError('Invalid token'); throw new Error('Unauthorized'); }
    return res;
  }).catch(err => {
    if (err.message === 'Unauthorized' || retries <= 0) throw err;
    return new Promise(r => setTimeout(r, 2000)).then(() => authFetch(url, options, retries - 1));
  });
}

// --- Clipboard Operations ---
function showToast(msg, color) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = color || '#22c55e';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

async function fetchClipboard() {
  try {
    const res = await authFetch(API_BASE + '/api/clipboard');
    const data = await res.json();
    if (data.content) {
      document.getElementById('downloadText').value = data.content;
    }
    document.getElementById('status').textContent = 'Connected | Updated: ' + (data.updated_at || '-');
    document.getElementById('status').style.color = '#64748b';
    renderHistory(data.history || []);
  } catch(e) {
    if (e.message !== 'Unauthorized') {
      const errMsg = e.name === 'AbortError' ? 'Request timeout' : (e.message || 'Unknown error');
      document.getElementById('status').textContent = 'Retrying... (' + errMsg + ')';
      document.getElementById('status').style.color = '#f59e0b';
    }
  }
}

async function uploadClipboard() {
  const text = document.getElementById('uploadText').value;
  if (!text.trim()) { showToast('Please enter text', '#ef4444'); return; }
  try {
    await authFetch(API_BASE + '/api/clipboard', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content: text})
    });
    showToast('Uploaded');
    fetchClipboard();
  } catch(e) { if (e.message !== 'Unauthorized') showToast('Upload failed', '#ef4444'); }
}

async function downloadClipboard() {
  try {
    const res = await authFetch(API_BASE + '/api/clipboard');
    const data = await res.json();
    document.getElementById('downloadText').value = data.content || '';
    showToast('Content fetched');
  } catch(e) { if (e.message !== 'Unauthorized') showToast('Download failed', '#ef4444'); }
}

async function pasteFromDevice() {
  if (navigator.clipboard && navigator.clipboard.readText) {
    try {
      const text = await navigator.clipboard.readText();
      document.getElementById('uploadText').value = text;
      showToast('Read from clipboard');
      return;
    } catch(e) {}
  }
  promptPaste();
}

function promptPaste() {
  const text = prompt('Paste your clipboard content below:');
  if (text !== null && text.trim()) {
    document.getElementById('uploadText').value = text;
    showToast('Content loaded');
  }
}

function copyToDevice() {
  const text = document.getElementById('downloadText').value;
  if (!text) { showToast('No content to copy', '#ef4444'); return; }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast('Copied to clipboard');
    }).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;top:40%;left:10%;width:80%;height:80px;z-index:9999;font-size:16px;padding:10px;border-radius:8px;border:2px solid #38bdf8;background:#0f172a;color:#e2e8f0;text-align:center';
  document.body.appendChild(ta);
  ta.select();
  ta.setSelectionRange(0, 99999);
  try {
    document.execCommand('copy');
    showToast('Copied');
  } catch(e) {
    showToast('Long-press to copy manually', '#f59e0b');
  }
  setTimeout(() => { document.body.removeChild(ta); }, 1500);
}

function renderHistory(history) {
  const el = document.getElementById('historyList');
  if (!history.length) { el.innerHTML = '<div class="empty">No history yet</div>'; return; }
  el.innerHTML = history.map((h, i) => `
    <div class="history-item" onclick="useHistory(${i})">
      <div class="history-time">${h.updated_at}</div>
      <div class="history-text">${escHtml(h.content.substring(0, 100))}${h.content.length > 100 ? '...' : ''}</div>
    </div>
  `).join('');
}

function useHistory(idx) {
  authFetch(API_BASE + '/api/clipboard').then(r => r.json()).then(data => {
    if (data.history && data.history[idx]) {
      document.getElementById('uploadText').value = data.history[idx].content;
      showToast('History loaded');
    }
  }).catch(() => {});
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Handle Enter key in token input
document.getElementById('tokenInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') submitToken();
});

// Init
initAuth();
setInterval(() => { if (authToken) fetchClipboard(); }, 10000);
</script>
</body>
</html>"""

# ===== HTTP Handler =====
class ClipboardHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {args[0]}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Connection", "close")

    def _check_auth(self):
        """Check token authentication. Returns True if authorized."""
        # Check query parameter
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        token_param = params.get("token", [""])[0]
        if token_param == AUTH_TOKEN:
            return True

        # Check Authorization header (Bearer token)
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:] == AUTH_TOKEN:
            return True

        # Check POST body for token field
        if self.command == "POST":
            content_type = self.headers.get("Content-Type", "")
            if "application/json" in content_type:
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8")
                    data = json.loads(body)
                    if data.get("token") == AUTH_TOKEN:
                        # Re-store body for handler to read
                        self._post_body = body
                        return True
                except Exception:
                    pass

        return False

    def _send_unauthorized(self):
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Unauthorized. Provide a valid token via ?token=, Authorization: Bearer header, or token field in POST body."}).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Health check - no auth required
        if parsed.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return

        # Web UI - no auth required (frontend JS handles token auth via overlay)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(WEB_UI.encode("utf-8"))
            return

        # All other endpoints require auth
        if not self._check_auth():
            self._send_unauthorized()
            return

        if parsed.path == "/api/clipboard":
            with lock:
                resp = json.dumps(clipboard_store, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(resp.encode("utf-8"))

        elif parsed.path in ("/copy", "/paste"):
            filename = "copy-from-server.html" if parsed.path == "/copy" else "paste-to-server.html"
            filepath = os.path.join(SHORTCUTS_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._cors()
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            except FileNotFoundError:
                self.send_response(404)
                self._cors()
                self.end_headers()
                self.wfile.write(b"Shortcut file not found")

        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/clipboard":
            if not self._check_auth():
                self._send_unauthorized()
                return

            # Read body (may have been read during auth check)
            if hasattr(self, '_post_body'):
                body = self._post_body
                del self._post_body
            else:
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

    class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = ThreadedHTTPServer((HOST, PORT), ClipboardHandler)
    print(f"[CopyLite] Running on http://{HOST}:{PORT}")
    print(f"[CopyLite] Web UI: http://localhost:{PORT}")
    print(f"[CopyLite] API: GET/POST /api/clipboard")
    print(f"[CopyLite] Token auth enabled. Access with: http://your-server:{PORT}/?token=<your-token>")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[CopyLite] Shutting down...")
        server.shutdown()
