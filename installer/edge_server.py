#!/usr/bin/env python3
"""
PowerAuto Edge Server — OpenAI-Compatible Wrapper for llama-server

Starts llama-server as a persistent worker and exposes OpenAI-compatible
endpoints that the PowerAuto Playground can connect to.

Usage:
    python edge_server.py --model models/Qwen3.6-35B-A3B.gguf --port 8080

Endpoints:
    GET  /v1/models              — List available models
    POST /v1/chat/completions    — OpenAI chat completions
    POST /v1/completions         — OpenAI completions
    GET  /health                 — Health check
    GET  /v1/cgc/profile         — Device profile (CGC protocol)
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest
from urllib import error as urlerror


class Config:
    def __init__(self):
        self.model = ""
        self.host = "0.0.0.0"
        self.port = 8080
        self.worker_host = "127.0.0.1"
        self.worker_port = 8081
        self.ngl = 99
        self.threads = max(1, (os.cpu_count() or 8) // 2)
        self.ctx = 8192
        self.no_mmap = False
        self.extra_args = []


CFG = Config()
WORKER_PROC = None
WORKER_LOG = None
WORKER_LOCK = threading.Lock()


def build_worker_cmd():
    cmd = [
        "llama-server.exe" if sys.platform == "win32" else "./llama-server",
        "-m", CFG.model,
        "-ngl", str(CFG.ngl),
        "-t", str(CFG.threads),
        "-c", str(CFG.ctx),
        "--host", CFG.worker_host,
        "--port", str(CFG.worker_port),
        "--no-webui",
        "--threads-http", "2",
    ]
    if CFG.no_mmap:
        cmd.append("--no-mmap")
    cmd.extend(CFG.extra_args)
    return cmd


def start_worker():
    global WORKER_PROC, WORKER_LOG
    with WORKER_LOCK:
        if WORKER_PROC and WORKER_PROC.poll() is None:
            return True

        log_path = f"edge_worker_{CFG.worker_port}.log"
        WORKER_LOG = open(log_path, "ab", buffering=0)
        cmd = build_worker_cmd()
        print(f"[Edge] Starting worker: {' '.join(cmd)}")
        WORKER_PROC = subprocess.Popen(
            cmd, stdout=WORKER_LOG, stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )

    # Wait for worker to be ready
    deadline = time.time() + 120
    while time.time() < deadline:
        if WORKER_PROC.poll() is not None:
            print(f"[Edge] Worker exited with rc={WORKER_PROC.returncode}")
            return False
        try:
            req = urlrequest.urlopen(f"http://{CFG.worker_host}:{CFG.worker_port}/health", timeout=2)
            data = json.loads(req.read())
            if data.get("status") in ("ok", "healthy", None):
                print(f"[Edge] Worker ready on port {CFG.worker_port}")
                return True
        except Exception:
            pass
        time.sleep(1)

    print("[Edge] Worker start timeout")
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


def worker_url(path):
    return f"http://{CFG.worker_host}:{CFG.worker_port}{path}"


def worker_request(path, body=None, stream=False):
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if stream:
        headers["Accept"] = "text/event-stream"
    req = urlrequest.Request(worker_url(path), data=data, headers=headers, method="POST")
    return urlrequest.urlopen(req, timeout=600)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Suppress default logging

    def do_GET(self):
        if self.path == "/health" or self.path == "/v1/cgc/health":
            try:
                req = urlrequest.urlopen(worker_url("/health"), timeout=3)
                data = json.loads(req.read())
                self._json({"status": "ok", "model": CFG.model, "worker": data})
            except Exception:
                self._json({"status": "error", "model": CFG.model}, 503)

        elif self.path == "/v1/models":
            model_id = os.path.basename(CFG.model).replace(".gguf", "")
            self._json({
                "object": "list",
                "data": [{
                    "id": model_id,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "powerauto",
                }]
            })

        elif self.path == "/v1/cgc/profile":
            import platform
            self._json({
                "profile": {
                    "total_ram_gb": round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024**3), 1),
                    "gpu_type": "NVIDIA CUDA" if CFG.ngl > 0 else "CPU",
                    "cpu_cores": os.cpu_count(),
                    "cpu_arch": platform.machine(),
                },
                "model": CFG.model,
                "ngl": CFG.ngl,
                "worker_mode": "persistent",
            })

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "bad json"}, 400)
            return

        if self.path == "/v1/chat/completions":
            self._handle_chat_completions(body)
        elif self.path == "/v1/completions":
            self._handle_completions(body)
        elif self.path == "/v1/cgc/emit":
            self._handle_emit(body)
        elif self.path == "/v1/cgc/resume":
            self._handle_resume(body)
        else:
            self._json({"error": "not found"}, 404)

    def _handle_chat_completions(self, body):
        # Convert messages to prompt
        messages = body.get("messages", [])
        prompt = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"

        stream = body.get("stream", False)
        payload = {
            "prompt": prompt,
            "n_predict": body.get("max_tokens", 512),
            "stream": stream,
            "cache_prompt": True,
            "timings_per_token": True,
        }
        # Sampling params
        for src, dst in [("temperature", "temperature"), ("top_p", "top_p"),
                         ("top_k", "top_k"), ("min_p", "min_p"),
                         ("stop", "stop")]:
            if src in body:
                payload[dst] = body[src]

        model_id = os.path.basename(CFG.model).replace(".gguf", "")

        if stream:
            self._sse_chat(payload, model_id)
        else:
            self._sync_chat(payload, model_id, body.get("max_tokens", 512))

    def _sync_chat(self, payload, model_id, max_tokens):
        try:
            req = worker_request("/completion", payload)
            obj = json.loads(req.read().decode())
            content = obj.get("content", "")
            timings = obj.get("timings", {})

            response = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_id,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": timings.get("prompt_n", 0),
                    "completion_tokens": timings.get("predicted_n", 0),
                    "total_tokens": timings.get("prompt_n", 0) + timings.get("predicted_n", 0),
                },
            }
            # Add CGC summary
            if timings:
                response["cgc_summary"] = {
                    "decode_tps": timings.get("predicted_per_second", 0),
                    "prompt_tps": timings.get("prompt_per_second", 0),
                }
            self._json(response)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _sse_chat(self, payload, model_id):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            req = worker_request("/completion", payload, stream=True)
            full_content = ""
            for raw in req:
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    continue
                obj = json.loads(data)
                text = obj.get("content", "")
                if text:
                    full_content += text
                    chunk = {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_id,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": None,
                        }],
                    }
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()

            # Final chunk
            final = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_id,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_completions(self, body):
        payload = {
            "prompt": body.get("prompt", ""),
            "n_predict": body.get("max_tokens", 128),
            "stream": False,
            "cache_prompt": True,
        }
        for src in ["temperature", "top_p", "top_k", "min_p", "stop"]:
            if src in body:
                payload[src] = body[src]

        try:
            req = worker_request("/completion", payload)
            obj = json.loads(req.read().decode())
            model_id = os.path.basename(CFG.model).replace(".gguf", "")
            self._json({
                "id": f"cmpl-{uuid.uuid4().hex[:12]}",
                "object": "text_completion",
                "created": int(time.time()),
                "model": model_id,
                "choices": [{
                    "text": obj.get("content", ""),
                    "index": 0,
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": obj.get("timings", {}).get("prompt_n", 0),
                    "completion_tokens": obj.get("timings", {}).get("predicted_n", 0),
                },
            })
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _handle_emit(self, body):
        payload = {
            "prompt": body.get("prompt", ""),
            "n_predict": 1,
            "stream": False,
            "cache_prompt": True,
            "timings_per_token": True,
        }
        try:
            req = worker_request("/completion", payload)
            obj = json.loads(req.read().decode())
            timings = obj.get("timings", {})
            self._json({
                "ok": True,
                "emit": {
                    "prompt_tps": timings.get("prompt_per_second", 0),
                    "load_ms": timings.get("load_ms", 0),
                    "n_decoded": timings.get("predicted_n", 0),
                    "decode_tps": timings.get("predicted_per_second", 0),
                }
            })
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def _handle_resume(self, body):
        payload = {
            "prompt": body.get("prompt", ""),
            "n_predict": body.get("max_tokens", 32),
            "stream": True,
            "cache_prompt": True,
        }
        if "seed" in body:
            payload["seed"] = body["seed"]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            req = worker_request("/completion", payload, stream=True)
            n_decoded = 0
            t0 = time.time()
            for raw in req:
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    continue
                obj = json.loads(data)
                text = obj.get("content", "")
                if text:
                    n_decoded += 1
                    self.wfile.write(f"data: {json.dumps({'event': 'token', 't': text})}\n\n".encode())
                    self.wfile.flush()

            decode_s = time.time() - t0
            self.wfile.write(f"data: {json.dumps({'event': 'summary', 'n_decoded': n_decoded, 'decode_tps': round(n_decoded / decode_s, 1) if decode_s > 0 else 0})}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(blob)


def main():
    ap = argparse.ArgumentParser(description="PowerAuto Edge Server")
    ap.add_argument("--model", required=True, help="GGUF model path")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--ngl", type=int, default=99)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--ctx", type=int, default=8192)
    ap.add_argument("--no-mmap", action="store_true")
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--worker-port", type=int, default=8081)
    args = ap.parse_args()

    CFG.model = os.path.abspath(args.model)
    CFG.host = args.host
    CFG.port = args.port
    CFG.ngl = args.ngl
    CFG.ctx = args.ctx
    CFG.no_mmap = args.no_mmap
    CFG.extra_args = args.extra or []
    CFG.worker_port = args.worker_port
    if args.threads:
        CFG.threads = args.threads

    # Check files
    for f in [CFG.model]:
        if not os.path.exists(f):
            print(f"[ERROR] Not found: {f}")
            sys.exit(1)

    # Handle signals
    signal.signal(signal.SIGINT, lambda *_: (stop_worker(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (stop_worker(), sys.exit(0)))

    # Start worker
    print(f"[Edge] Model: {CFG.model}")
    print(f"[Edge] Starting llama-server worker on port {CFG.worker_port}...")
    if not start_worker():
        print("[Edge] Failed to start worker")
        sys.exit(1)

    # Start edge server
    srv = ThreadingHTTPServer((CFG.host, CFG.port), Handler)
    print(f"[Edge] Edge server listening on http://{CFG.host}:{CFG.port}")
    print(f"[Edge] Playground: https://powerauto.ai/playground/")
    print(f"[Edge] API: http://localhost:{CFG.port}/v1/chat/completions")
    print()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_worker()


if __name__ == "__main__":
    main()
