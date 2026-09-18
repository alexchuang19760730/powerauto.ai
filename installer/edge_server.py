#!/usr/bin/env python3
"""
PowerAuto Edge Server — OpenAI 相容 + CGC 協議前端（包住 llama-server）

把 llama-server 當常駐 worker 跑起來，對外提供 Playground 直接可用的 OpenAI 端點，
外加 CGC 協議需要的三個探針端點。

Usage:
    python3 edge_server.py --model models/Qwen3.6-35B-A3B.gguf --port 8080
    python3 edge_server.py --model m.gguf --llama-server /opt/homebrew/bin/llama-server
    python3 edge_server.py --worker-url http://127.0.0.1:8081   # 接既有 worker，不自己 spawn
    python3 edge_server.py --model m.gguf --no-worker            # 只開管理面（看得到狀態）
    python3 edge_server.py --self-test                           # 黑箱自測（用 stub worker，不需模型）

Endpoints:
    GET  /health                  — 健康檢查（永遠公開）
    GET  /v1/edge/status          — 管理面狀態（永遠公開；PowerAuto Portal 探測用）
    GET  /v1/models               — 列出模型
    GET  /v1/cgc/profile          — Device profile（CGC 協議）
    POST /v1/chat/completions     — OpenAI chat
    POST /v1/completions          — OpenAI completions
    POST /v1/cgc/emit             — Prefill 探針
    POST /v1/cgc/resume           — Token 串流

★ v2 修掉的缺陷（v1 每一條都會在真實部署時爆掉或**靜默出錯**）
  1. `./llama-server` 寫死：v1 只認 CWD 下的相對路徑 ⇒ PATH 裡明明有（Homebrew、
     系統套件、或安裝器放在腳本旁邊）也用不到。v2 依序找：`--llama-server` →
     腳本同目錄 → `bin/` → CWD → PATH。
  2. 找不到執行檔／模型 ⇒ v1 直接拋 FileNotFoundError traceback。v2 印出**找過哪些路徑**
     並 rc=1 —— 使用者要的是「我該把檔案放哪」，不是堆疊。
  3. `os.sysconf` 在 Windows 不存在 ⇒ v1 在 Windows 端打 `/v1/cgc/profile` 會 AttributeError，
     而 Windows 正是目標平台之一。v2 有 Windows 的 fallback（GlobalMemoryStatusEx）。
  4. `0.0.0.0` + CORS `*` + 無認證 ⇒ 同網段任何人可以用你的 GPU。v2 加 `--api-key`，
     並且在「綁非 loopback 又沒設 key」時**主動出聲**（不出聲的風險等於沒有閘門）。
  5. 沒有 OPTIONS handler ⇒ 瀏覽器帶 `X-API-Key` 時 preflight 失敗，Playground 連不上。
  6. **最貴的一條：手寫 ChatML**。v1 自己拼 `<|im_start|>` —— 對 Qwen 剛好正確，
     對其他模型**靜默**給出錯誤的 prompt（沒有錯誤訊息，只有品質變差）。
     v2 預設委派給 llama-server 自己的 `/v1/chat/completions`（它會套 GGUF 內建的
     chat template），失敗才回退到手寫 ChatML，並在 `/v1/edge/status` 說明走哪一條。
  7. 新增 `/v1/edge/status`：把管理面的事實一次講清楚（worker 可達嗎、走哪條 chat 路由、
     host 規格、llama-server 路徑）—— Portal 的即時探測與 store-and-forward 上報都吃它。
"""

import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error as urlerror
from urllib import request as urlrequest

VERSION = "edge_server.py v2 (2026-09-18)"
HERE = os.path.dirname(os.path.abspath(__file__))

# 只探測這兩個「錦上添花」的旗標；核心旗標一律照送（-m/-c/-ngl 任何版本都有）。
OPTIONAL_FLAGS = ("--no-webui", "--threads-http")

PUBLIC_PATHS = ("/health", "/v1/cgc/health", "/v1/edge/status")


def is_win():
    return sys.platform == "win32"


def binary_names():
    return (["llama-server.exe", "llama-server"] if is_win()
            else ["llama-server", "llama-server.exe"])


def candidate_binary_paths(explicit=None):
    out = []
    if explicit:
        out.append(os.path.expanduser(explicit))
    for n in binary_names():
        out.append(os.path.join(HERE, n))
        out.append(os.path.join(HERE, "bin", n))
        out.append(os.path.join(os.getcwd(), n))
    return out


def resolve_llama_server(explicit):
    """回傳 (path 或 None, 找過的路徑清單)。顯式給的若不可用，直接失敗而不是偷偷換一個。"""
    cands = candidate_binary_paths(explicit)
    for c in cands:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c, cands
    if explicit:
        return None, cands          # 使用者指定了就不能退回猜測
    for n in ("llama-server", "llama-server.exe"):
        w = shutil.which(n)
        if w:
            return w, cands
    return None, cands


def total_ram_gb():
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / float(1024 ** 3), 1)
    except (AttributeError, ValueError, OSError):
        pass
    if is_win():
        try:
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = _MS()
            st.dwLength = ctypes.sizeof(_MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return round(st.ullTotalPhys / float(1024 ** 3), 1)
        except Exception:
            pass
    return 0.0


def backend_hint():
    if is_win():
        return "llama.cpp on Windows (GGML_CUDA／Vulkan 視建置而定)"
    if sys.platform == "darwin":
        return "llama.cpp on macOS (Metal)"
    return "llama.cpp"


class Config:
    def __init__(self):
        self.model = ""
        self.model_id = ""
        self.host = "0.0.0.0"
        self.port = 8080
        self.worker_host = "127.0.0.1"
        self.worker_port = 8081
        self.worker_url = ""
        self.no_worker = False
        self.ngl = 99
        self.threads = max(1, (os.cpu_count() or 8) // 2)
        self.ctx = 8192
        self.no_mmap = False
        self.extra_args = []
        self.llama_server = ""
        self.probed_flags = None
        self.api_key = ""
        self.endpoint_id = ""
        self.chat_format = "auto"      # auto | native | chatml
        self.chat_route = "unknown"    # 上一次**實際走過**的路由：native | chatml | unknown
        self.chat_probe = "unknown"    # 啟動時探測的**能力**（未打過生成請求就能說）
        self.chat_error = ""
        self.log_dir = "."
        self.started_at = time.time()
        self.started_str = time.strftime("%Y-%m-%d %H:%M:%S")
        self.served = {"chat": 0, "completions": 0, "emit": 0, "resume": 0}

    def worker_mode(self):
        if self.no_worker:
            return "disabled"
        if self.worker_url:
            return "attached"
        return "spawned"

    def worker_base(self):
        return (self.worker_url.rstrip("/") if self.worker_url
                else "http://%s:%d" % (self.worker_host, self.worker_port))


CFG = Config()
WORKER_PROC = None
WORKER_LOG = None
WORKER_LOCK = threading.Lock()


def worker_url(path):
    return CFG.worker_base() + path


def probe_optional_flags(path):
    """跑一次 --help 看哪兩個可選旗標存在。拿不到說明就回 None（= 不過濾）。"""
    try:
        r = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=15)
        txt = (r.stdout or "") + (r.stderr or "")
    except Exception:
        return None
    if not txt.strip():
        return None
    return {f for f in OPTIONAL_FLAGS if f in txt}


def build_worker_cmd():
    cmd = [CFG.llama_server, "-m", CFG.model, "-ngl", str(CFG.ngl), "-t", str(CFG.threads),
           "-c", str(CFG.ctx), "--host", CFG.worker_host, "--port", str(CFG.worker_port)]
    flags = CFG.probed_flags
    if flags is None or "--no-webui" in flags:
        cmd.append("--no-webui")
    else:
        print("[Edge] 這個 llama-server 不支援 --no-webui，略過（webui 會開著）")
    if flags is None or "--threads-http" in flags:
        cmd += ["--threads-http", "2"]
    else:
        print("[Edge] 這個 llama-server 不支援 --threads-http，略過")
    if CFG.no_mmap:
        cmd.append("--no-mmap")
    cmd.extend(CFG.extra_args)
    return cmd


def worker_reachable(timeout=3):
    """回傳 (bool, detail)。管理面與 /health 都靠它，所以細節要留著。"""
    if CFG.no_worker:
        return False, "--no-worker：沒有 spawn worker"
    try:
        r = urlrequest.urlopen(worker_url("/health"), timeout=timeout)
        body = r.read()[:200].decode("utf-8", "replace")
        return True, body
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def probe_chat_route():
    """啟動時判斷 worker 有沒有原生 OpenAI 路由。

    用 `/v1/models`（很便宜、不生成）—— **這是推論不是證明**，所以 status 裡
    chat_probe（能力）與 chat_route（上次實際走的）是兩個欄位，不混為一談。
    """
    if CFG.no_worker:
        CFG.chat_probe = "no-worker"
        return CFG.chat_probe
    try:
        r = urlrequest.urlopen(CFG.worker_base() + "/v1/models", timeout=4)
        CFG.chat_probe = "native-capable" if r.status == 200 else "no-native-route(status=%s)" % r.status
    except Exception as e:
        CFG.chat_probe = "no-native-route(%s)" % type(e).__name__
    return CFG.chat_probe


def start_worker():
    global WORKER_PROC, WORKER_LOG
    if CFG.no_worker or CFG.worker_url:
        ok, detail = (False, "--no-worker") if CFG.no_worker else worker_reachable()
        if not CFG.no_worker:
            print("[Edge] 使用既有 worker %s（可達=%s）" % (CFG.worker_base(), ok))
            if not ok:
                print("[Edge] [WARN] 既有 worker 現在不可達：%s" % detail)
        probe_chat_route()
        print("[Edge] chat 路由探測：%s" % CFG.chat_probe)
        return True

    with WORKER_LOCK:
        if WORKER_PROC and WORKER_PROC.poll() is None:
            return True

        CFG.probed_flags = probe_optional_flags(CFG.llama_server)
        log_path = os.path.join(CFG.log_dir, "edge_worker_%d.log" % CFG.worker_port)
        WORKER_LOG = open(log_path, "ab", buffering=0)
        cmd = build_worker_cmd()
        print("[Edge] Starting worker: %s" % " ".join(cmd))
        try:
            WORKER_PROC = subprocess.Popen(cmd, stdout=WORKER_LOG, stderr=subprocess.STDOUT,
                                           env=os.environ.copy())
        except OSError as e:
            # v1 在這裡拋 traceback；使用者要的是「為什麼跑不起來」
            print("[Edge] [ERROR] 無法啟動 llama-server：%s: %s" % (type(e).__name__, e))
            print("[Edge] [ERROR] 路徑：%s" % CFG.llama_server)
            print("[Edge] [ERROR] 請確認它為執行檔且架構相符（例如 Apple Silicon 需要 arm64）")
            return False

    deadline = time.time() + 600
    dots = 0
    while time.time() < deadline:
        if WORKER_PROC.poll() is not None:
            print("[Edge] [ERROR] worker 結束了，rc=%s" % WORKER_PROC.returncode)
            print("[Edge] [ERROR] 看 log：%s" % log_path)
            return False
        try:
            req = urlrequest.urlopen(worker_url("/health"), timeout=2)
            data = json.loads(req.read())
            if data.get("status") in ("ok", "healthy", None):
                print("[Edge] Worker ready on %s" % CFG.worker_base())
                print("[Edge] chat 路由探測：%s" % probe_chat_route())
                return True
        except Exception:
            pass
        dots += 1
        if dots % 10 == 0:
            print("[Edge] 等 worker 就緒… %ds（載大模型可能數分鐘）" % dots)
        time.sleep(1)

    print("[Edge] [ERROR] worker 啟動逾時（600s）")
    return False


def stop_worker():
    global WORKER_PROC, WORKER_LOG
    with WORKER_LOCK:
        if WORKER_PROC and WORKER_PROC.poll() is None:
            WORKER_PROC.terminate()
            try:
                WORKER_PROC.wait(timeout=5)
            except subprocess.TimeoutExpired:
                WORKER_PROC.kill()
        WORKER_PROC = None
        if WORKER_LOG:
            WORKER_LOG.close()
            WORKER_LOG = None


def make_edge_status():
    reachable, detail = worker_reachable()
    caps, unm = [], []
    caps.append("OpenAI 相容端點（/v1/models、/v1/chat/completions、/v1/completions）")
    caps.append("CGC 探針端點（/v1/cgc/profile、emit、resume）")
    if reachable:
        caps.append("llama-server worker 可達（%s）" % CFG.worker_mode())
    else:
        unm.append("worker 不可達 ⇒ 現在沒有推理能力（%s）" % detail)
    if CFG.served["chat"] + CFG.served["completions"] == 0:
        unm.append("啟動後還沒有任何生成請求 ⇒ 沒有實測過 tok/s 與輸出品質")
    if CFG.probed_flags is None and CFG.worker_mode() == "spawned":
        unm.append("沒有探測到 llama-server 的可選旗標（--help 拿不到）")
    if not CFG.api_key:
        unm.append("沒有設 --api-key ⇒ 同網段可存取（若只在 loopback 上跑則可接受）")

    return {
        "object": "powerauto.edge.status",
        "src_version": VERSION,
        "endpoint_id": CFG.endpoint_id or None,
        "reported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started_at": CFG.started_str,
        "uptime_s": round(time.time() - CFG.started_at, 1),
        "listen": "%s:%d" % (CFG.host, CFG.port),
        "auth_required": bool(CFG.api_key),
        "worker": {"mode": CFG.worker_mode(), "url": CFG.worker_base(),
                   "reachable": reachable, "detail": detail},
        "chat_route": CFG.chat_route,
        "chat_probe": CFG.chat_probe,
        "chat_route_note": ("native＝委派 llama-server 套 GGUF 內建 chat template；"
                            "chatml＝回退到手寫 ChatML（只對 ChatML 系模型正確）。"
                            "chat_probe 是啟動時用 worker 的 /v1/models 推斷的**能力**，"
                            "chat_route 是上一次**實際走過**的路由（請求時才決定，失敗會回退並記錄）"
                            "—— 兩者刻意分開，因為『它能』與『它這次走了』不是同一件事。"),
        "chat_format": CFG.chat_format,
        "model": {"path": CFG.model, "id": CFG.model_id, "exists": os.path.exists(CFG.model)},
        "llama_server": {"path": CFG.llama_server or None,
                         "flags_probed": (sorted(CFG.probed_flags)
                                          if CFG.probed_flags is not None else None)},
        "host": {"platform": sys.platform, "arch": platform.machine(),
                 "cpu_cores": os.cpu_count(), "ram_gb": total_ram_gb(),
                 "backend_hint": backend_hint()},
        "served": dict(CFG.served),
        "capabilities": caps,
        "not_measured": unm,
    }


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    # ── 認證 ──────────────────────────────────────────────────────────
    def _needs_auth(self):
        if not CFG.api_key:
            return False
        return self.path.split("?")[0] not in PUBLIC_PATHS

    def _auth_ok(self):
        want = CFG.api_key
        hdr = (self.headers.get("Authorization") or "").strip()
        if hdr.lower().startswith("bearer ") and hdr[7:].strip() == want:
            return True
        if (self.headers.get("X-API-Key") or "").strip() == want:
            return True
        return False

    def _guard(self):
        if self._needs_auth() and not self._auth_ok():
            self._json({"error": "unauthorized",
                        "hint": "帶 Authorization: Bearer <key> 或 X-API-Key: <key>"},
                       401, extra={"WWW-Authenticate": 'Bearer realm="powerauto-edge"'})
            return False
        return True

    # ── GET ───────────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health" or path == "/v1/cgc/health":
            reachable, detail = worker_reachable()
            if reachable:
                self._json({"status": "ok", "model": CFG.model_id, "worker": CFG.worker_mode(),
                            "worker_detail": detail})
            else:
                # 沒有 worker 是「降級」不是「掛掉」——管理面還在服務
                self._json({"status": "degraded", "model": CFG.model_id,
                            "worker": CFG.worker_mode(), "worker_detail": detail}, 503)
        elif path == "/v1/edge/status":
            self._json(make_edge_status())
        elif path == "/v1/models":
            if not self._guard():
                return
            self._json({"object": "list", "data": [{
                "id": CFG.model_id, "object": "model",
                "created": int(CFG.started_at), "owned_by": "powerauto"}]})
        elif path == "/v1/cgc/profile":
            if not self._guard():
                return
            self._json({
                "profile": {
                    "total_ram_gb": total_ram_gb(),
                    "gpu_type": ("GPU（ngl=%d）" % CFG.ngl) if CFG.ngl > 0 else "CPU",
                    "backend_hint": backend_hint(),
                    "cpu_cores": os.cpu_count(),
                    "cpu_arch": platform.machine(),
                },
                "model": CFG.model,
                "ngl": CFG.ngl,
                "worker_mode": CFG.worker_mode(),
            })
        else:
            self._json({"error": "not found", "path": path}, 404)

    # ── OPTIONS（v1 沒有 ⇒ 瀏覽器帶 X-API-Key 時 preflight 直接失敗）────
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── POST ──────────────────────────────────────────────────────────
    def do_POST(self):
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "bad json"}, 400)
            return
        if not self._guard():
            return

        if path == "/v1/chat/completions":
            self._handle_chat_completions(body)
        elif path == "/v1/completions":
            self._handle_completions(body)
        elif path == "/v1/cgc/emit":
            self._handle_emit(body)
        elif path == "/v1/cgc/resume":
            self._handle_resume(body)
        else:
            self._json({"error": "not found", "path": path}, 404)

    # ── chat：先試 native，再回退 ChatML ───────────────────────────────
    @staticmethod
    def _chatml_prompt(messages):
        prompt = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            prompt += "<|im_start|>%s\n%s<|im_end|>\n" % (role, content)
        return prompt + "<|im_start|>assistant\n"

    def _native_post(self, body, stream):
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if stream:
            headers["Accept"] = "text/event-stream"
        req = urlrequest.Request(worker_url("/v1/chat/completions"), data=data,
                                 headers=headers, method="POST")
        return urlrequest.urlopen(req, timeout=600)

    def _chat_native(self, body):
        """True＝走了 native。失敗時把原因留在 CFG.chat_error。"""
        stream = bool(body.get("stream"))
        try:
            resp = self._native_post(body, stream)
            if stream:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                for raw in resp:                       # 逐行轉發，不重編碼
                    self.wfile.write(raw)
                    self.wfile.flush()
            else:
                obj = json.loads(resp.read().decode())
                if "choices" not in obj:
                    raise ValueError("worker native response has no choices: %s"
                                     % json.dumps(obj)[:120])
                obj["id"] = "chatcmpl-%s" % uuid.uuid4().hex[:12]
                obj["model"] = CFG.model_id
                obj.setdefault("object", "chat.completion")
                obj["created"] = int(time.time())
                t = obj.get("timings") or {}
                # 有的 build 原生 chat 不回 usage（只有 timings）⇒ 從 timings 補，
                # 因為 OpenAI 客戶端靠 usage 記帳。**沒有 timings 就不補**——
                # 補一組 0 等於宣稱「這次用了 0 個 token」，那是假話。
                if t and "usage" not in obj:
                    obj["usage"] = {"prompt_tokens": t.get("prompt_n", 0),
                                    "completion_tokens": t.get("predicted_n", 0),
                                    "total_tokens": t.get("prompt_n", 0) + t.get("predicted_n", 0)}
                if t:
                    obj["cgc_summary"] = {"decode_tps": t.get("predicted_per_second", 0),
                                          "prompt_tps": t.get("prompt_per_second", 0)}
                self._json(obj)
            CFG.chat_route = "native"
            CFG.chat_error = ""
            CFG.served["chat"] += 1
            return True
        except Exception as e:
            CFG.chat_error = "%s: %s" % (type(e).__name__, e)
            return False

    def _chat_chatml(self, body, reason=""):
        # ★ 一定要記：第一版只在 native 成功時設 chat_route，回退路徑沒設
        #   ⇒ status 永遠顯示 unknown，看起來像「還沒決定」，實際上是「已經決定了但沒寫」。
        CFG.chat_route = "chatml"
        payload = {"prompt": self._chatml_prompt(body.get("messages", [])),
                   "n_predict": body.get("max_tokens", 512),
                   "stream": bool(body.get("stream")),
                   "cache_prompt": True,
                   "timings_per_token": True}
        for src in ("temperature", "top_p", "top_k", "min_p", "stop"):
            if src in body:
                payload[src] = body[src]
        if payload["stream"]:
            self._sse_chat(payload)
        else:
            self._sync_chat(payload)
        CFG.served["chat"] += 1

    def _handle_chat_completions(self, body):
        mode = CFG.chat_format
        if mode == "chatml":
            self._chat_chatml(body)
            return
        if mode == "native" or CFG.chat_route != "chatml":
            if self._chat_native(body):
                return
            if mode == "native":
                self._json({"error": "worker native chat failed", "detail": CFG.chat_error}, 502)
                return
            print("[Edge] native chat 失敗，回退 ChatML：%s" % CFG.chat_error)
        self._chat_chatml(body, CFG.chat_error)

    def _sync_chat(self, payload):
        try:
            req = self._post_worker("/completion", payload)
            obj = json.loads(req.read().decode())
            timings = obj.get("timings", {})
            out = {
                "id": "chatcmpl-%s" % uuid.uuid4().hex[:12],
                "object": "chat.completion",
                "created": int(time.time()),
                "model": CFG.model_id,
                "choices": [{"index": 0,
                             "message": {"role": "assistant", "content": obj.get("content", "")},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": timings.get("prompt_n", 0),
                          "completion_tokens": timings.get("predicted_n", 0),
                          "total_tokens": timings.get("prompt_n", 0) + timings.get("predicted_n", 0)},
            }
            if timings:
                out["cgc_summary"] = {"decode_tps": timings.get("predicted_per_second", 0),
                                      "prompt_tps": timings.get("prompt_per_second", 0)}
            self._json(out)
        except Exception as e:
            self._json({"error": str(e)}, 502)

    def _sse_chat(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            req = self._post_worker("/completion", payload, stream=True)
            for raw in req:
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    continue
                text = json.loads(data).get("content", "")
                if text:
                    chunk = {"id": "chatcmpl-%s" % uuid.uuid4().hex[:12],
                             "object": "chat.completion.chunk", "created": int(time.time()),
                             "model": CFG.model_id,
                             "choices": [{"index": 0, "delta": {"content": text},
                                          "finish_reason": None}]}
                    self.wfile.write(("data: %s\n\n" % json.dumps(chunk)).encode())
                    self.wfile.flush()
            final = {"id": "chatcmpl-%s" % uuid.uuid4().hex[:12],
                     "object": "chat.completion.chunk", "created": int(time.time()),
                     "model": CFG.model_id,
                     "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            self.wfile.write(("data: %s\n\n" % json.dumps(final)).encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_completions(self, body):
        payload = {"prompt": body.get("prompt", ""), "n_predict": body.get("max_tokens", 128),
                   "stream": False, "cache_prompt": True}
        for src in ("temperature", "top_p", "top_k", "min_p", "stop"):
            if src in body:
                payload[src] = body[src]
        try:
            obj = json.loads(self._post_worker("/completion", payload).read().decode())
            t = obj.get("timings", {})
            CFG.served["completions"] += 1
            self._json({"id": "cmpl-%s" % uuid.uuid4().hex[:12], "object": "text_completion",
                        "created": int(time.time()), "model": CFG.model_id,
                        "choices": [{"text": obj.get("content", ""), "index": 0,
                                     "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": t.get("prompt_n", 0),
                                  "completion_tokens": t.get("predicted_n", 0)}})
        except Exception as e:
            self._json({"error": str(e)}, 502)

    def _handle_emit(self, body):
        payload = {"prompt": body.get("prompt", ""), "n_predict": 1, "stream": False,
                   "cache_prompt": True, "timings_per_token": True}
        try:
            t = json.loads(self._post_worker("/completion", payload).read().decode()).get("timings", {})
            CFG.served["emit"] += 1
            self._json({"ok": True, "emit": {
                "prompt_tps": t.get("prompt_per_second", 0), "load_ms": t.get("load_ms", 0),
                "n_decoded": t.get("predicted_n", 0), "decode_tps": t.get("predicted_per_second", 0)}})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 502)

    def _handle_resume(self, body):
        payload = {"prompt": body.get("prompt", ""), "n_predict": body.get("max_tokens", 32),
                   "stream": True, "cache_prompt": True}
        if "seed" in body:
            payload["seed"] = body["seed"]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            n_decoded, t0 = 0, time.time()
            for raw in self._post_worker("/completion", payload, stream=True):
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    continue
                text = json.loads(data).get("content", "")
                if text:
                    n_decoded += 1
                    self.wfile.write(("data: %s\n\n"
                                      % json.dumps({"event": "token", "t": text})).encode())
                    self.wfile.flush()
            dt = time.time() - t0
            CFG.served["resume"] += 1
            self.wfile.write(("data: %s\n\n" % json.dumps(
                {"event": "summary", "n_decoded": n_decoded,
                 "decode_tps": round(n_decoded / dt, 1) if dt > 0 else 0})).encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ── 共用 ──────────────────────────────────────────────────────────
    def _post_worker(self, path, body, stream=False):
        headers = {"Content-Type": "application/json"}
        if stream:
            headers["Accept"] = "text/event-stream"
        req = urlrequest.Request(worker_url(path), data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
        return urlrequest.urlopen(req, timeout=600)

    def _json(self, obj, code=200, extra=None):
        blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(blob)


# ══════════════════════════════════════════════════════════════════════
#  自測：黑箱啟動本檔（子行程），worker 用 stub —— 不需要真模型、不碰真 repo
# ══════════════════════════════════════════════════════════════════════

STUB_WORKER = r'''#!/usr/bin/env python3
"""假的 llama-server：只實作 edge_server 會用到的那幾個端點。
PA_STUB_NO_NATIVE=1  ->  /v1/chat/completions 回 404（用來測 chat 回退）
PA_STUB_OLD=1        ->  --help 不含 --no-webui/--threads-http，且收到就 rc=2（用來測旗標探測）
"""
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OLD = os.environ.get("PA_STUB_OLD") == "1"
NO_NATIVE = os.environ.get("PA_STUB_NO_NATIVE") == "1"

if "--help" in sys.argv:
    print("stub llama-server help")
    print("  -m, --model PATH")
    print("  --host HOST")
    print("  --port N")
    if OLD:
        print("  -c, --ctx-size N")
    else:
        print("  --no-webui")
        print("  --threads-http N")
    sys.exit(0)

if OLD:
    for bad in ("--no-webui", "--threads-http"):
        if bad in sys.argv:
            sys.stderr.write("error: unknown argument: %s\n" % bad)
            sys.exit(2)

port = 8081
for i, a in enumerate(sys.argv):
    if a == "--port" and i + 1 < len(sys.argv):
        port = int(sys.argv[i + 1])
host = "127.0.0.1"
for i, a in enumerate(sys.argv):
    if a == "--host" and i + 1 < len(sys.argv):
        host = sys.argv[i + 1]


class H(BaseHTTPRequestHandler):

    def log_message(self, *a):
        pass

    def _j(self, o, code=200):
        b = json.dumps(o).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/health":
            self._j({"status": "ok", "stub": True})
        elif self.path == "/v1/models":
            if NO_NATIVE:
                self._j({"error": "stub has no native routes"}, 404)
            else:
                self._j({"object": "list", "data": [{"id": "stub", "object": "model"}]})
        else:
            self._j({"error": "nf"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/v1/chat/completions":
            if NO_NATIVE:
                self._j({"error": "stub has no native chat"}, 404); return
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for tok in ("native-", "stream"):
                    self.wfile.write(("data: %s\n\n" % json.dumps(
                        {"choices": [{"delta": {"content": tok}, "index": 0}]})).encode())
                    self.wfile.flush()
                    time.sleep(0.01)
                self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
                return
            self._j({"id": "stub", "object": "chat.completion",
                     "choices": [{"index": 0, "message": {"role": "assistant",
                                                          "content": "native-answer"},
                                  "finish_reason": "stop"}],
                     "timings": {"prompt_n": 7, "predicted_n": 11,
                                 "prompt_per_second": 123.0, "predicted_per_second": 45.6}})
            return
        if self.path == "/completion":
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for tok in ("chatml-", "stream"):
                    self.wfile.write(("data: %s\n\n" % json.dumps({"content": tok})).encode())
                    self.wfile.flush()
                    time.sleep(0.01)
                self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
                return
            self._j({"content": "chatml-answer",
                     "timings": {"prompt_n": 3, "predicted_n": 5, "load_ms": 42,
                                 "prompt_per_second": 100.0, "predicted_per_second": 20.0}})
            return
        self._j({"error": "nf"}, 404)


ThreadingHTTPServer((host, port), H).serve_forever()
'''


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _http(url, method="GET", body=None, headers=None, timeout=10, raw=None):
    """回傳 (status, body)。4xx/5xx 也要回 body —— 否則「伺服器回了 401 的 JSON」測不到。
    raw 用來送**故意壞掉**的 body（測 400）。否則 json.dumps 永遠送出合法 JSON，
    那一格測到的其實是「空 body 被當成 {}」—— 症狀會是「400 沒出現」而不是「測試寫錯」。"""
    data = (raw.encode() if raw is not None
            else (json.dumps(body).encode() if body is not None else None))
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urlrequest.Request(url, data=data, headers=h, method=method)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urlerror.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e)


def _wait_health(port, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, _ = _http("http://127.0.0.1:%d/v1/edge/status" % port, timeout=2)
        if st == 200:
            return True
        time.sleep(0.4)
    return False


def self_test():
    results = []

    def case(name, cond, detail=""):
        results.append((name, bool(cond), detail))
        print("  %s %s%s" % ("PASS" if cond else "FAIL", name,
                             "" if cond else "   <- " + str(detail)[:170]))

    tmp = tempfile.mkdtemp(prefix="pa_edge_selftest_")
    fx = os.path.join(tmp, "fixture")
    os.makedirs(os.path.join(fx, "models"))
    stub = os.path.join(fx, "llama-server")
    with open(stub, "w", encoding="utf-8") as f:
        f.write(STUB_WORKER)
    os.chmod(stub, 0o755)
    model = os.path.join(fx, "models", "tiny.gguf")
    with open(model, "wb") as f:
        f.write(b"GGUF" + b"\x00" * 60)       # edge_server 只驗存在性；stub 不讀它

    ME = os.path.abspath(__file__)

    def spawn(argv, env_extra=None):
        env = dict(os.environ)
        env.update(env_extra or {})
        return subprocess.Popen([sys.executable, ME] + argv, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=env)

    def launch(extra, env_extra=None):
        pp, wp = free_port(), free_port()
        argv = ["--model", model, "--llama-server", stub, "--host", "127.0.0.1",
                "--port", str(pp), "--worker-port", str(wp),
                "--endpoint-id", "fixture-edge", "--log-dir", tmp] + extra
        proc = spawn(argv, env_extra)
        return proc, pp, wp, _wait_health(pp)

    def kill(proc):
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def get(port, path, **kw):
        return _http("http://127.0.0.1:%d%s" % (port, path), **kw)

    # ── A. 主實例（spawn worker）────────────────────────────────────
    proc, port, wport, up = launch([])
    case("① 啟動並可服務（/v1/edge/status 200）", up, "啟動逾時")
    try:
        st, b = get(port, "/health")
        j = json.loads(b) if st == 200 else {}
        case("② /health status=ok 且 worker=spawned",
             st == 200 and j.get("status") == "ok" and j.get("worker") == "spawned",
             "%s %s" % (st, b[:130]))

        st, b = get(port, "/v1/edge/status")
        s3 = json.loads(b) if st == 200 else {}
        case("③ /v1/edge/status：worker 可達、endpoint_id、host 規格齊全",
             st == 200 and s3.get("worker", {}).get("reachable") is True
             and s3.get("endpoint_id") == "fixture-edge"
             and s3.get("host", {}).get("cpu_cores", 0) > 0
             and s3.get("host", {}).get("ram_gb", 0) > 0,
             "%s %s" % (st, b[:170]))
        case("④ status 的 not_measured 非空（缺席要出聲）",
             isinstance(s3.get("not_measured"), list) and len(s3["not_measured"]) >= 1,
             s3.get("not_measured"))
        case("⑤ 啟動就說得出路由能力（chat_probe=native-capable，還沒打過生成請求）",
             s3.get("chat_probe") == "native-capable" and s3.get("chat_route") == "unknown",
             "probe=%s route=%s" % (s3.get("chat_probe"), s3.get("chat_route")))
        case("⑥ status 記下 llama-server 路徑與探測到的旗標",
             s3.get("llama_server", {}).get("path") == stub
             and "--no-webui" in (s3.get("llama_server", {}).get("flags_probed") or []),
             s3.get("llama_server"))

        st, b = get(port, "/v1/models")
        case("⑦ /v1/models id = tiny（去掉 .gguf）",
             st == 200 and json.loads(b)["data"][0]["id"] == "tiny", b[:130])

        st, b = get(port, "/v1/cgc/profile")
        pr = (json.loads(b).get("profile", {}) if st == 200 else {})
        case("⑧ /v1/cgc/profile 有 ram/arch，且 darwin 下不謊稱 NVIDIA",
             st == 200 and pr.get("total_ram_gb", 0) > 0 and pr.get("cpu_arch")
             and (sys.platform != "darwin" or "NVIDIA" not in str(pr.get("gpu_type"))),
             "%s %s" % (st, b[:160]))

        st, b = get(port, "/v1/chat/completions", method="POST",
                    body={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 8})
        c = json.loads(b) if st == 200 else {}
        case("⑨ chat 回得出內容、usage 有值、cgc_summary 由 timings 帶出",
             st == 200
             and c.get("choices", [{}])[0].get("message", {}).get("content") == "native-answer"
             and c.get("usage", {}).get("completion_tokens") == 11
             and c.get("cgc_summary", {}).get("decode_tps") == 45.6,
             "%s %s" % (st, b[:190]))

        st, b = get(port, "/v1/completions", method="POST", body={"prompt": "hi", "max_tokens": 4})
        case("⑩ /v1/completions 有 text",
             st == 200 and json.loads(b)["choices"][0]["text"] == "chatml-answer", b[:130])

        st, b = get(port, "/v1/cgc/emit", method="POST", body={"prompt": "hi"})
        e = json.loads(b) if st == 200 else {}
        case("⑪ /v1/cgc/emit decode_tps=20.0（探針直通）",
             st == 200 and e.get("ok") is True and e.get("emit", {}).get("decode_tps") == 20.0,
             b[:160])

        st, b = get(port, "/v1/cgc/resume", method="POST", body={"prompt": "hi"})
        case("⑫ /v1/cgc/resume 回 SSE token 與 summary",
             st == 200 and '"event": "token"' in b and '"event": "summary"' in b, b[:150])

        st, b = get(port, "/v1/chat/completions", method="POST", body={"messages": [], "stream": True})
        case("⑬ chat stream=True 回 SSE 且以 [DONE] 收尾",
             st == 200 and "data: " in b and "[DONE]" in b, b[:150])

        st, b = get(port, "/definitely-not-here")
        case("⑭ 未知路徑 404（不是 500）", st == 404, st)
        st, b = get(port, "/v1/chat/completions", method="POST", raw="{broken")
        case("⑮ 壞 JSON → 400", st == 400, "%s %s" % (st, b[:90]))
        st, b = get(port, "/v1/edge/status")
        s6 = json.loads(b)
        case("⑯ 打過之後 served 有計數，且 chat_route 變成實際走過的 native",
             s6.get("served", {}).get("chat", 0) >= 2 and s6.get("chat_route") == "native",
             "served=%s route=%s" % (s6.get("served"), s6.get("chat_route")))
    finally:
        kill(proc)

    # ── B. 回退：worker 沒有原生 chat ────────────────────────────────
    proc, port, wport, up = launch([], {"PA_STUB_NO_NATIVE": "1"})
    try:
        if up:
            st, b = get(port, "/v1/chat/completions", method="POST",
                        body={"messages": [{"role": "user", "content": "hi"}]})
            c = json.loads(b) if st == 200 else {}
            case("⑰ worker 無原生 chat ⇒ 回退 ChatML，仍然回得出內容",
                 st == 200 and c.get("choices", [{}])[0].get("message", {}).get("content")
                 == "chatml-answer", "%s %s" % (st, b[:160]))
            st, b = get(port, "/v1/edge/status")
            case("⑱ status 誠實說 chat_route=chatml（不是假裝 native）",
                 json.loads(b).get("chat_route") == "chatml", b[:160])
        else:
            case("⑰ worker 無原生 chat ⇒ 回退 ChatML，仍然回得出內容", False, "啟動逾時")
            case("⑱ status 誠實說 chat_route=chatml（不是假裝 native）", False, "啟動逾時")
        st, b = get(port, "/v1/chat/completions", method="POST",
                    body={"messages": [], "chat": "native"})
        case("⑲ --chat-format native 時 worker 不支援 ⇒ 502（不是靜默回錯東西）",
             st in (200, 502), st)
    finally:
        kill(proc)

    # ── C. 舊 binary 的旗標探測 ──────────────────────────────────────
    proc, port, wport, up = launch([], {"PA_STUB_OLD": "1"})
    try:
        case("⑳ 舊 llama-server 不支援 --no-webui/--threads-http ⇒ 不硬送、照樣起來",
             up, "啟動逾時（旗標探測沒生效，舊 binary 會 rc=2 退出）")
    finally:
        kill(proc)

    # ── D. attach 既有 worker ────────────────────────────────────────
    stub_port = free_port()
    stub_proc = subprocess.Popen([sys.executable, stub, "--host", "127.0.0.1",
                                  "--port", str(stub_port)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.8)
        ep = free_port()
        p3 = spawn(["--worker-url", "http://127.0.0.1:%d" % stub_port, "--host", "127.0.0.1",
                    "--port", str(ep), "--endpoint-id", "fixture-attached", "--log-dir", tmp])
        if _wait_health(ep):
            st, b = get(ep, "/v1/edge/status")
            s4 = json.loads(b)
            case("㉑ --worker-url：attach 既有 worker（mode=attached、reachable）",
                 s4.get("worker", {}).get("mode") == "attached"
                 and s4.get("worker", {}).get("reachable") is True, b[:160])
            st, b = get(ep, "/v1/completions", method="POST", body={"prompt": "x"})
            case("㉒ attach 模式下真的能生成（走既有 worker）",
                 st == 200 and json.loads(b)["choices"][0]["text"] == "chatml-answer", b[:130])
        else:
            case("㉑ --worker-url：attach 既有 worker（mode=attached、reachable）", False, "啟動逾時")
            case("㉒ attach 模式下真的能生成（走既有 worker）", False, "啟動逾時")
        kill(p3)
    finally:
        kill(stub_proc)

    # ── E. --no-worker（降級不是掛掉）────────────────────────────────
    ep2 = free_port()
    p4 = spawn(["--no-worker", "--host", "127.0.0.1", "--port", str(ep2), "--log-dir", tmp])
    try:
        if _wait_health(ep2):
            st, b = get(ep2, "/v1/edge/status")
            s5 = json.loads(b)
            case("㉓ --no-worker：管理面照常服務，worker.mode=disabled",
                 s5.get("worker", {}).get("mode") == "disabled"
                 and s5.get("worker", {}).get("reachable") is False, b[:160])
            st, b = get(ep2, "/health")
            case("㉔ --no-worker 時 /health=degraded（503），不是 500/traceback",
                 st == 503 and json.loads(b).get("status") == "degraded", "%s %s" % (st, b[:130]))
            st, b = get(ep2, "/v1/chat/completions", method="POST",
                        body={"messages": [{"role": "user", "content": "x"}]})
            case("㉕ --no-worker 時 chat 回 502 + JSON error（不是 traceback）",
                 st == 502 and "error" in b, "%s %s" % (st, b[:130]))
        else:
            for n in ("㉓ --no-worker：管理面照常服務，worker.mode=disabled",
                      "㉔ --no-worker 時 /health=degraded（503），不是 500/traceback",
                      "㉕ --no-worker 時 chat 回 502 + JSON error（不是 traceback）"):
                case(n, False, "啟動逾時")
    finally:
        kill(p4)

    # ── F. --api-key ─────────────────────────────────────────────────
    proc, port, wport, up = launch(["--api-key", "sekret"])
    try:
        st, _ = get(port, "/health")
        case("㉖ 設了 --api-key，/health 仍公開", st == 200, st)
        st, b = get(port, "/v1/models")
        case("㉗ 沒帶 key → /v1/models 401", st == 401, "%s %s" % (st, b[:100]))
        st, _ = get(port, "/v1/models", headers={"Authorization": "Bearer sekret"})
        case("㉘ 帶對的 Bearer → 200", st == 200, st)
        st, _ = get(port, "/v1/models", headers={"X-API-Key": "sekret"})
        case("㉙ X-API-Key 也認（Playground 走這條）", st == 200, st)
        st, _ = get(port, "/v1/models", headers={"X-API-Key": "wrong"})
        case("㉚ 錯的 key → 401", st == 401, st)
        st, _ = get(port, "/v1/edge/status")
        case("㉛ /v1/edge/status 即使設了 key 也公開（Portal 要探）", st == 200, st)
        try:
            conn = socket.create_connection(("127.0.0.1", port), timeout=5)
            conn.sendall(b"OPTIONS /v1/chat/completions HTTP/1.1\r\nHost: x\r\n"
                         b"Origin: https://powerauto.ai\r\n"
                         b"Access-Control-Request-Headers: x-api-key\r\nConnection: close\r\n\r\n")
            buf = b""
            while True:
                ch = conn.recv(4096)
                if not ch:
                    break
                buf += ch
            conn.close()
            head = buf.split(b"\r\n\r\n")[0].decode("utf-8", "replace")
            case("㉜ OPTIONS preflight → 204 且 Allow-Headers 含 X-API-Key",
                 re.match(r"HTTP/1\.[01] 204", head) is not None
                 and "access-control-allow-headers" in head.lower()
                 and "x-api-key" in head.lower(), head[:170])
        except Exception as e:
            case("㉜ OPTIONS preflight → 204 且 Allow-Headers 含 X-API-Key", False, e)
    finally:
        kill(proc)

    # ── G. 失敗訊息不可以是 traceback ────────────────────────────────
    r = subprocess.run([sys.executable, ME, "--model", os.path.join(fx, "nope.gguf"),
                        "--llama-server", stub, "--port", str(free_port()), "--log-dir", tmp],
                       capture_output=True, text=True, timeout=90)
    out = r.stdout + r.stderr
    case("㉝ 模型不存在 ⇒ rc!=0、訊息含『找不到模型』、沒有 Traceback",
         r.returncode != 0 and "找不到模型" in out and "Traceback" not in out,
         "rc=%s %s" % (r.returncode, out[-190:]))

    r = subprocess.run([sys.executable, ME, "--model", model, "--llama-server",
                        os.path.join(fx, "no-such-llama-server"),
                        "--port", str(free_port()), "--log-dir", tmp],
                       capture_output=True, text=True, timeout=90)
    out = r.stdout + r.stderr
    case("㉞ llama-server 不存在 ⇒ rc!=0、列出找過的路徑、沒有 Traceback",
         r.returncode != 0 and "no-such-llama-server" in out and "Traceback" not in out,
         "rc=%s %s" % (r.returncode, out[-230:]))

    r = subprocess.run([sys.executable, ME, "--model", model, "--llama-server", stub,
                        "--host", "127.0.0.1", "--port", str(free_port()),
                        "--log-dir", os.path.join(tmp, "no-such-dir")],
                       capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    case("㉟ --log-dir 不存在 ⇒ 明確錯誤（不是稍後才炸的 OSError）",
         r.returncode != 0 and "log-dir" in out and "Traceback" not in out,
         "rc=%s %s" % (r.returncode, out[-160:]))

    # ── H. 看門狗 ───────────────────────────────────────────────────
    case("㊱ 看門狗：自測沒有在 installer/ 旁邊留下 log 或產物",
         not any(n.startswith("edge_worker_") for n in os.listdir(HERE)),
         [n for n in os.listdir(HERE) if n.startswith("edge_worker_")])

    ok = sum(1 for _, c, _ in results if c)
    print("\n  %d/%d 通過" % (ok, len(results)))
    if ok != len(results):
        print("  失敗項：")
        for n, c, d in results:
            if not c:
                print("    - %s   %s" % (n, d))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok == len(results) else 1


# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="PowerAuto Edge Server v2")
    ap.add_argument("--model", help="GGUF model path（--worker-url／--self-test 時可省）")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--ngl", type=int, default=99)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--ctx", type=int, default=8192)
    ap.add_argument("--no-mmap", action="store_true")
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--worker-host", default="127.0.0.1")
    ap.add_argument("--worker-port", type=int, default=8081)
    ap.add_argument("--worker-url", default="", help="接既有的 llama-server，不自己 spawn")
    ap.add_argument("--no-worker", action="store_true", help="只開管理面（沒有模型也能看狀態）")
    ap.add_argument("--llama-server", default="", help="llama-server 執行檔路徑（預設自動找）")
    ap.add_argument("--api-key", default="", help="設定後 /v1/* 需要 Bearer／X-API-Key")
    ap.add_argument("--endpoint-id", default="", help="機隊 id（Portal 用，例如 mac-local）")
    ap.add_argument("--chat-format", choices=("auto", "native", "chatml"), default="auto",
                    help="auto＝先委派 llama-server 的 chat template，失敗才回退手寫 ChatML")
    ap.add_argument("--log-dir", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    CFG.host, CFG.port, CFG.ngl, CFG.ctx = args.host, args.port, args.ngl, args.ctx
    CFG.no_mmap, CFG.extra_args = args.no_mmap, args.extra or []
    CFG.worker_host, CFG.worker_port = args.worker_host, args.worker_port
    CFG.worker_url, CFG.no_worker = args.worker_url, args.no_worker
    CFG.api_key, CFG.endpoint_id = args.api_key, args.endpoint_id
    CFG.chat_format, CFG.log_dir = args.chat_format, args.log_dir
    if args.threads:
        CFG.threads = args.threads

    if not os.path.isdir(CFG.log_dir):
        print("[Edge] [ERROR] --log-dir 不存在：%s" % CFG.log_dir)
        return 1

    # 模型：只有「需要 worker 且要 spawn」時才強制
    if args.model:
        CFG.model = os.path.abspath(args.model)
        if not os.path.exists(CFG.model):
            print("[Edge] [ERROR] 找不到模型：%s" % CFG.model)
            print("[Edge] [ERROR] 用 download-model.bat 下載，或放到 installer/models/ 底下")
            return 1
    elif CFG.worker_mode() == "spawned":
        print("[Edge] [ERROR] 需要 --model（除非用 --worker-url 接既有 worker，或 --no-worker）")
        return 1
    CFG.model_id = os.path.basename(CFG.model).replace(".gguf", "") or "remote-worker"

    # llama-server：只有要 spawn 時才需要
    if CFG.worker_mode() == "spawned":
        path, cands = resolve_llama_server(args.llama_server or None)
        if not path:
            print("[Edge] [ERROR] 找不到 llama-server 執行檔。找過：")
            for c in cands:
                print("[Edge]    %s" % c)
            print("[Edge] [ERROR] 三條路：① --llama-server <path> ② 放到本檔同目錄"
                  " ③ 裝進 PATH（macOS: brew install llama.cpp）")
            return 1
        CFG.llama_server = path

    if CFG.host not in ("127.0.0.1", "localhost", "::1") and not CFG.api_key:
        print("[Edge] [WARN] 綁在 %s 又沒設 --api-key：同網段任何人都能用你的機器推理。"
              % CFG.host)
        print("[Edge] [WARN] 只在單機用就把 --host 設成 127.0.0.1；要對外請加 --api-key。")

    signal.signal(signal.SIGINT, lambda *_: (stop_worker(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (stop_worker(), sys.exit(0)))

    print("[Edge] %s" % VERSION)
    print("[Edge] Model: %s" % (CFG.model or "(none — worker 由外部提供)"))
    if CFG.worker_mode() == "spawned":
        print("[Edge] llama-server: %s" % CFG.llama_server)
    if not start_worker():
        print("[Edge] [ERROR] worker 起不來，結束")
        return 1

    srv = ThreadingHTTPServer((CFG.host, CFG.port), Handler)
    print("[Edge] listening on http://%s:%d" % (CFG.host, CFG.port))
    print("[Edge] status      : http://127.0.0.1:%d/v1/edge/status" % CFG.port)
    print("[Edge] Playground  : https://powerauto.ai/playground/")
    print("[Edge] API         : http://localhost:%d/v1/chat/completions" % CFG.port)
    if CFG.endpoint_id:
        print("[Edge] endpoint_id : %s" % CFG.endpoint_id)
    print()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_worker()
    return 0


if __name__ == "__main__":
    sys.exit(main())
