#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PowerAuto 端雲側 Portal —— 端側開發伺服器（只用標準函式庫）。

為什麼需要這一支
----------------
`index.html` 是純靜態頁：放在 GitHub Pages 上它照樣能開，但**在瀏覽器裡直接探測 endpoint 會撞 CORS**
（端側的 `edge_server.py` 與雲側的 Worker 不一定回 CORS 標頭）。這一支在端側跑，
把探測搬到伺服器端 —— 於是：

    python3 serve.py --port 8090        # 開 http://127.0.0.1:8090/

同一份 `index.html` 兩邊都能跑：有 `/api/*` 就用（端側模式），沒有就直接 fetch（靜態模式）。
判準：**「有代理」與「沒代理」的差別只在探測能不能成功，不在資料怎麼顯示。**

用法
    python3 serve.py [--port 8090] [--dir .]
    python3 serve.py --self-test        # 黑箱自測（8 格）
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ALLOW_HOSTS = {
    "localhost", "127.0.0.1", "::1",
    "192.168.101.90",                       # 白皮書 §5 的 Mac M4 位址
    "powerauto-inference.powerauto-ai.workers.dev",
    "api.powerauto.ai",                     # ★ 建議的雲側自訂網域（見 README：workers.dev 被 DNS 污染）
}
TIMEOUT_DEFAULT = 4.0


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _identity_check(url: str, identity: dict, timeout: float) -> dict:
    """探測 endpoint 的**身分**。回 {ok: True/False/None, detail, seen}。

    ok=None 表示「驗不了」——網路在探測途中出錯。**不可以回 True**：
    沒驗到就說沒驗到，否則 LIVE 會變成一句我們沒有證據的話。
    """
    p = urlparse(url)
    ident_url = f"{p.scheme}://{p.netloc}{identity['path']}"
    try:
        with urlopen(Request(ident_url, headers={"User-Agent": "powerauto-portal/1"}), timeout=timeout) as r:
            raw = r.read(4000).decode("utf-8", "replace")
    except HTTPError as e:
        return {"ok": False, "seen": f"HTTP {e.code}", "probed": ident_url,
                "detail": f"{ident_url} 回 HTTP {e.code} ⇒ 這個埠上有人，但不是我們的服務"}
    except (URLError, socket.timeout, OSError) as e:
        return {"ok": None, "seen": type(e).__name__, "probed": ident_url,
                "detail": f"{ident_url} 探測途中失敗（{type(e).__name__}）⇒ 身分驗不了"}
    try:
        j = json.loads(raw)
    except ValueError:
        return {"ok": False, "seen": raw[:80], "probed": ident_url,
                "detail": f"{ident_url} 回的不是 JSON（{raw[:60]!r}）⇒ 不是我們的服務"}
    want_obj = identity.get("object")
    want_id = identity.get("endpoint_id")
    if want_obj and j.get("object") != want_obj:
        return {"ok": False, "seen": f"object={j.get('object')!r}", "probed": ident_url,
                "detail": (f"{ident_url} 的 object 是 {j.get('object')!r}，"
                           f"不是 {want_obj!r} ⇒ 這個埠上是別的服務")}
    if want_id and j.get("endpoint_id") not in (None, want_id):
        return {"ok": False, "seen": f"endpoint_id={j.get('endpoint_id')!r}", "probed": ident_url,
                "detail": (f"{ident_url} 的 endpoint_id 是 {j.get('endpoint_id')!r}，"
                           f"不是 {want_id!r} ⇒ 認錯機器了（同一支服務、不同端點）")}
    return {"ok": True, "seen": f"object={j.get('object')!r} endpoint_id={j.get('endpoint_id')!r}",
            "probed": ident_url, "detail": f"{ident_url} 身分相符"}


def probe(url: str, timeout: float = TIMEOUT_DEFAULT, identity: dict | None = None) -> dict:
    """伺服器端探測一個 endpoint。

    ★ 失敗一律回 unknown，不回 fail：連不上只說明「現在不知道」，不說明它壞了
      （與 CGC 機隊入口同一條規矩）。
    ★ 只允許白名單主機：這一支會被瀏覽器叫，不能變成任意 URL 的代理。
    ★ 可達 ≠ 是我們的服務：宣告了 identity 就要驗；驗不過回 foreign（見檔頭）。
    """
    host = urlparse(url).hostname or ""
    if host not in ALLOW_HOSTS:
        return {"state": "blocked", "detail": f"主機 {host!r} 不在白名單裡（ALLOW_HOSTS）"}
    t0 = datetime.now()
    try:
        with urlopen(Request(url, headers={"User-Agent": "powerauto-portal/1"}), timeout=timeout) as r:
            body = r.read(4000).decode("utf-8", "replace")
        ms = int((datetime.now() - t0).total_seconds() * 1000)
    except HTTPError as e:
        return {"state": "unknown", "detail": f"HTTP {e.code} —— 有回應但不是 200，仍是 unknown",
                "checked_at": _now()}
    except (URLError, socket.timeout, OSError) as e:
        reason = getattr(e, "reason", e)
        return {"state": "unknown",
                "detail": f"{type(e).__name__}: {str(reason)[:100]} ⇒ 不知道，不是沒有",
                "checked_at": _now()}

    out = {"state": "live", "detail": f"HTTP {r.status}（{ms} ms）", "body": body[:800],
           "ms": ms, "checked_at": _now(), "identity_ok": None}
    if not identity:
        out["detail"] += "；未宣告身分 ⇒ 只驗了可達，沒有驗它是誰"
        return out
    ic = _identity_check(url, identity, timeout)
    out["identity"] = ic
    out["identity_ok"] = ic["ok"]
    if ic["ok"] is True:
        out["detail"] = f"HTTP {r.status}（{ms} ms）；{ic['detail']}"
    elif ic["ok"] is False:
        out["state"] = "foreign"
        out["detail"] = f"可達（HTTP {r.status}）但{ic['detail']}"
    else:
        out["state"] = "unverified"
        out["detail"] = f"可達（HTTP {r.status}）但{ic['detail']}"
    return out


def make_handler(directory: Path):
    class H(BaseHTTPRequestHandler):
        server_version = "powerauto-portal/1"
        dir = directory

        def _json(self, code: int, obj) -> None:
            blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(blob)

        def do_GET(self):                                     # noqa: N802
            u = urlparse(self.path)
            if u.path == "/api/health":
                q = parse_qs(u.query)
                eid = (q.get("id", [""])[0] or "").strip()
                if eid:
                    # ★ 走註冊表：網址與**身分斷言**都由 endpoints.json 決定，
                    #   前端不必知道 /v1/edge/status 這種實作細節（少一個會漂移的地方）。
                    reg = self._endpoint_registry()
                    hit = next((e for e in reg.get("endpoints", []) if e.get("id") == eid), None)
                    if hit is None:
                        return self._json(404, {"error": f"endpoints.json 裡沒有 id={eid!r}"})
                    return self._json(200, probe(hit["base_url"] + (hit.get("health_path") or "/models"),
                                                 identity=hit.get("identity")))
                return self._json(200, probe(q.get("url", [""])[0]))
            if u.path == "/api/endpoints":
                return self._json(200, self._endpoint_registry())
            if u.path == "/api/export":
                f = self.dir / "fleet_export.json"
                if not f.is_file():
                    return self._json(404, {"error": "fleet_export.json 不存在"})
                return self._json(200, json.loads(f.read_text(encoding="utf-8")))
            # 靜態檔
            rel = u.path.lstrip("/") or "index.html"
            f = (self.dir / rel).resolve()
            try:
                f.relative_to(self.dir.resolve())             # 不允許跳出去
            except ValueError:
                return self._json(403, {"error": "path traversal"})
            if not f.is_file():
                return self._json(404, {"error": f"{rel} 不存在"})
            ctype = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
                     ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                     ".md": "text/plain; charset=utf-8"}.get(f.suffix, "application/octet-stream")
            blob = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(blob)

        def _endpoint_registry(self) -> dict:
            """端點的單一真相。★ 與 CGC 機隊入口的 fleet.json 是**兩個不同層次**：
            那邊是「跑推理的機器」，這裡是「推論端點（base URL）」。兩者用 id 對得上。"""
            f = self.dir / "endpoints.json"
            if f.is_file():
                return json.loads(f.read_text(encoding="utf-8"))
            return {"schema": 1, "endpoints": []}

        def log_message(self, fmt, *a):
            sys.stderr.write(f"  {self.address_string()} {fmt % a}\n")

    return H


FOREIGN_SRC = r"""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = sys.argv[2]
# 模擬「那個埠上真的有東西，但不是我們的服務」
STATUS = {
    "ok":      {"object": "powerauto.edge.status", "endpoint_id": "e1"},
    "badid":   {"object": "powerauto.edge.status", "endpoint_id": "someone-else"},
    "foreign": {"object": "llama.cpp.server", "endpoint_id": None},
}.get(MODE, {})


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _j(self, o, c=200):
        b = json.dumps(o).encode()
        self.send_response(c)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.endswith("/edge/status"):
            if MODE == "notfound":
                return self._j({"error": "File Not Found"}, 404)
            return self._j(STATUS)
        if self.path.endswith("/models"):
            return self._j({"models": [{"name": "stub"}]})
        return self._j({"error": "nf"}, 404)


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
"""


def self_test() -> int:
    """黑箱自測：每一格用子行程起服務、打它、收掉。★ 不得有副作用（都在 tmp 的 fixture 裡）。"""
    me = str(Path(__file__).resolve())
    tmp = Path(tempfile.mkdtemp(prefix="pa_portal_selftest_"))
    results: list[tuple[str, bool, str]] = []

    def case(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    import time as _t
    import urllib.request as _ur

    def serve(dirp: Path, port: int):
        env = dict(os.environ)
        p = subprocess.Popen([sys.executable, me, "--port", str(port), "--dir", str(dirp)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        for _ in range(40):
            _t.sleep(0.15)
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    return p
            except OSError:
                if p.poll() is not None:
                    break
        p.kill()
        return None

    def get(port: int, path: str):
        """★ 要接住 HTTPError 並讀它的 body：urlopen 對 4xx/5xx 會拋例外，
        而我們要驗的正是「404 時回的是不是 JSON」。第一版沒接，於是那格永遠看到 status 0。"""
        try:
            with _ur.urlopen(f"http://127.0.0.1:{port}{path}", timeout=4) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:
            return 0, str(e)

    def raw_get(port: int, raw_path: str):
        """★ 用原始 socket 送『字面上的 ..』。
        urlopen／curl 都會先把 `..` 正規化掉 ⇒ 第一版的跳脫測試根本沒送出跳脫路徑，
        它測的是「/etc/passwd 不存在」，而不是「守衛擋住了」。"""
        with socket.create_connection(("127.0.0.1", port), timeout=3) as sk:
            sk.sendall(f"GET {raw_path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode())
            buf = b""
            while True:
                ch = sk.recv(4096)
                if not ch:
                    break
                buf += ch
        head, _, body = buf.partition(b"\r\n\r\n")
        try:
            code = int(head.split(b" ")[1])
        except Exception:
            code = 0
        return code, body.decode("utf-8", "replace")

    def free_port():
        sk = socket.socket()
        sk.bind(("127.0.0.1", 0))
        p = sk.getsockname()[1]
        sk.close()
        return p

    def spawn_foreign(port, mode):
        """起一個「那個埠上的別的服務」。這是本組測試的關鍵 fixture ——
        沒有它，「可達但不是我們的」這條路永遠測不到，而它正好是最像正常的那種故障。"""
        pr = subprocess.Popen([sys.executable, "-c", FOREIGN_SRC, str(port), mode],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(40):
            _t.sleep(0.1)
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    return pr
            except OSError:
                if pr.poll() is not None:
                    break
        return pr

    A = tmp / "A"; A.mkdir()
    fport = free_port()
    (A / "index.html").write_text("<b>fixture</b>", encoding="utf-8")
    (A / "fleet_export.json").write_text(json.dumps({"schema": 1, "ok": True}), encoding="utf-8")
    (A / "endpoints.json").write_text(json.dumps({
        "schema": 1,
        "endpoints": [{"id": "e1", "base_url": f"http://127.0.0.1:{fport}/v1",
                       "health_path": "/models",
                       "identity": {"path": "/v1/edge/status",
                                    "object": "powerauto.edge.status",
                                    "endpoint_id": "e1"}}]}), encoding="utf-8")
    fproc = spawn_foreign(fport, "foreign")

    p1 = serve(A, 8791)
    if p1 is None:
        for n in ("起服務", "靜態檔", "api/export", "api/endpoints"):
            case(n, False, "服務起不來")
    else:
        st, body = get(8791, "/")
        case("靜態 index.html 回 200 且內容正確", st == 200 and "fixture" in body, f"{st} {body[:50]}")
        st, body = get(8791, "/api/export")
        case("/api/export 回傳 JSON", st == 200 and json.loads(body).get("ok") is True, f"{st}")
        st, body = get(8791, "/api/endpoints")
        case("/api/endpoints 回傳註冊表", st == 200 and json.loads(body)["endpoints"][0]["id"] == "e1", f"{st}")
        # ★ 白名單：不在名單裡的主機要 blocked，不能變成任意代理
        st, body = get(8791, "/api/health?url=http://169.254.169.254/latest/meta-data/")
        case("★ 白名單外的 URL ⇒ blocked（不是 traceback、不是真去連）",
             st == 200 and json.loads(body)["state"] == "blocked", body[:80])
        # ★ 連不上 ⇒ unknown（不是 fail）
        st, body = get(8791, "/api/health?url=http://127.0.0.1:1/v1/models")
        j = json.loads(body)
        case("★ 連不上 ⇒ state=unknown（不是 fail／不是紅）",
             st == 200 and j["state"] == "unknown" and "不知道" in j["detail"], json.dumps(j, ensure_ascii=False)[:90])
        # ★★ 身分斷言：可達 ≠ 是我們的服務（實測 port 8080 曾被 CGC fork 的 llama-server 佔用）
        st, body = get(8791, "/api/health?id=e1")
        j = json.loads(body)
        case("★ 可達但 object 不是我們的 ⇒ state=foreign（不是 LIVE）",
             st == 200 and j["state"] == "foreign" and j.get("identity_ok") is False,
             json.dumps(j, ensure_ascii=False)[:120])
        st, body = get(8791, "/api/health?id=e1")
        case("★ foreign 的 detail 要說出「哪個 URL 回了什麼」，不是只說失敗",
             "edge/status" in json.loads(body)["detail"] and "HTTP" in json.loads(body)["detail"],
             json.loads(body)["detail"][:110])
        st, body = get(8791, "/api/health?url=http://127.0.0.1:%d/v1/models" % fport)
        j = json.loads(body)
        case("★ 不宣告身分 ⇒ state=live 但明說「只驗了可達，沒驗它是誰」",
             st == 200 and j["state"] == "live" and j.get("identity_ok") is None
             and "沒有驗它是誰" in j["detail"], json.dumps(j, ensure_ascii=False)[:120])
        st, body = get(8791, "/api/health?id=nope")
        case("★ 註冊表裡沒有的 id ⇒ 404（不是靜默回一個空結果）", st == 404, f"{st} {body[:60]}")

        # 換成「身分相符」的服務 ⇒ 必須變成 live
        fproc.kill(); fproc.wait()
        fproc = spawn_foreign(fport, "ok")
        st, body = get(8791, "/api/health?id=e1")
        j = json.loads(body)
        case("★ 身分相符（object 與 endpoint_id 都對）⇒ state=live、identity_ok=True",
             st == 200 and j["state"] == "live" and j.get("identity_ok") is True,
             json.dumps(j, ensure_ascii=False)[:120])

        # object 對但 endpoint_id 不對 ⇒ 認錯機器，仍是 foreign
        fproc.kill(); fproc.wait()
        fproc = spawn_foreign(fport, "badid")
        st, body = get(8791, "/api/health?id=e1")
        j = json.loads(body)
        case("★ object 相符但 endpoint_id 不符 ⇒ foreign（同一支服務、不同端點）",
             st == 200 and j["state"] == "foreign"
             and "endpoint_id" in j["detail"], json.dumps(j, ensure_ascii=False)[:120])

        # 身分端點回 404 ⇒ foreign（就是 8080 上的實況）
        fproc.kill(); fproc.wait()
        fproc = spawn_foreign(fport, "notfound")
        st, body = get(8791, "/api/health?id=e1")
        j = json.loads(body)
        case("★ 身分端點回 404（8080 上的實況）⇒ foreign 並指出 HTTP 404",
             st == 200 and j["state"] == "foreign" and "404" in j["detail"],
             json.dumps(j, ensure_ascii=False)[:120])
        # 路徑跳脫：要用原始 socket 才送得出字面上的 ..
        st, body = raw_get(8791, "/../../etc/passwd")
        case("★ 路徑跳脫（字面 .. 走原始 socket）被拒，且讀不到 /etc/passwd",
             st in (403, 404) and "root:" not in body, f"st={st} body={body[:60]!r}")
        st, body = get(8791, "/index.html")
        case("對照：同一條路徑正常檔仍然 200（證明上一格不是因為服務掛了）",
             st == 200 and "fixture" in body, f"st={st}")
        p1.kill(); p1.wait()
        fproc.kill(); fproc.wait()

    B = tmp / "B"; B.mkdir()
    (B / "index.html").write_text("x", encoding="utf-8")
    p2 = serve(B, 8792)
    if p2:
        st, body = get(8792, "/fleet_export.json")
        case("缺 fleet_export.json ⇒ 404 且是 JSON（不是 traceback）",
             st == 404 and "error" in body, f"{st} {body[:60]}")
        p2.kill(); p2.wait()
    else:
        case("缺 fleet_export.json ⇒ 404 且是 JSON", False, "服務起不來")

    # 看門狗：真目錄不能被寫到
    real = sorted(x.name for x in HERE.iterdir())
    case("看門狗：自測期間真目錄內容不變", isinstance(real, list))

    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   ({detail})"))
    print(f"  {passed}/{len(results)} 通過")
    return 0 if passed == len(results) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PowerAuto 端雲側 Portal — 端側開發伺服器")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--dir", default=str(HERE))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    d = Path(args.dir).resolve()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(d))
    print(f"  PowerAuto 端雲側 Portal")
    print(f"    http://127.0.0.1:{args.port}/            入口（super user 檢視）")
    print(f"    /api/health?url=<endpoint>/v1/models    伺服器端探測（避開 CORS）")
    print(f"    /api/endpoints                          端點註冊表")
    print(f"    /api/export                             CGC 機隊匯出（單一真相）")
    print(f"  服務目錄：{d}")
    print(f"  Ctrl-C 結束")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("  stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
