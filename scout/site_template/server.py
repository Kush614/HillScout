"""Hill Scout site server: static files plus POST /api/request.

Requests go to Postgres when DATABASE_URL is set (table site_requests), otherwise they are
appended to $REQUESTS_FILE. A person reviews each one; nothing is emailed or built automatically.
"""
import json
import os
import re
import secrets
import ssl
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("REQUESTS_FILE", "/data/requests.jsonl"))
FIELDS = {"name": 120, "email": 200, "company": 160, "kind": 40, "deadline": 20, "notes": 2000,
          "task": 20, "target": 200, "file": 300, "source_ref": 500, "source_url": 500, "source_license": 200}
KINDS = {"private_hill", "private_competition", "eval_pack"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_last = {}
_import_last = {}
_import_slots = threading.BoundedSemaphore(2)
DB_URL = os.environ.get("DATABASE_URL", "")
_db_lock = threading.Lock()
_db = None
SCHEMA = """CREATE TABLE IF NOT EXISTS site_requests (
  id TEXT PRIMARY KEY, received TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'awaiting human review', kind TEXT, email TEXT, name TEXT,
  payload JSONB NOT NULL)"""


def _connect():
    import pg8000.native
    from urllib.parse import parse_qs, unquote, urlparse
    u = urlparse(DB_URL)
    q = parse_qs(u.query)
    mode = (q.get("sslmode") or ["prefer"])[0]
    ctx = None
    if mode in ("require", "verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        if mode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
    con = pg8000.native.Connection(user=unquote(u.username or ""), password=unquote(u.password or ""),
                                   host=u.hostname, port=u.port or 5432, database=u.path.lstrip("/"),
                                   ssl_context=ctx, timeout=10)
    con.run(SCHEMA)
    return con


def save(rec):
    """Store one request. Raises OSError if it could not be stored anywhere durable."""
    global _db
    if DB_URL:
        with _db_lock:
            for attempt in (1, 2):
                try:
                    if _db is None:
                        _db = _connect()
                    _db.run("INSERT INTO site_requests (id, kind, email, name, payload) VALUES (:i, :k, :e, :n, CAST(:p AS JSONB))",
                            i=rec["id"], k=rec["kind"], e=rec["email"], n=rec["name"], p=json.dumps(rec))
                    return "database"
                except Exception as exc:  # noqa: BLE001 - reconnect once, then report
                    _db = None
                    if attempt == 2:
                        print(f"request store failed: {type(exc).__name__}", flush=True)
                        raise OSError("database unavailable") from exc
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return "file"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.path.endswith(".json"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ip(self):
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

    def do_GET(self):
        if self.path.startswith("/api/import"):
            return self._import()
        if self.path.split("?")[0] in ("/server.py", "/importer.py", "/Dockerfile") or self.path.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        return super().do_GET()

    def _import(self):
        from urllib.parse import parse_qs, urlparse
        import importer
        q = parse_qs(urlparse(self.path).query)
        ref = (q.get("ref") or [""])[0][:600]
        file = (q.get("file") or [""])[0][:300]
        ip = self._ip()
        if time.time() - _import_last.get(ip, 0) < 3:
            return self._json(429, {"error": "one import every few seconds, please"})
        _import_last[ip] = time.time()
        if not _import_slots.acquire(timeout=20):
            return self._json(503, {"error": "the importer is busy; try again in a moment"})
        try:
            return self._json(200, importer.fetch(ref, file))
        except importer.ImportError_ as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            print(f"import failed: {type(exc).__name__}: {exc}", flush=True)
            return self._json(500, {"error": "the import failed unexpectedly; try another link"})
        finally:
            _import_slots.release()

    def do_POST(self):
        if self.path != "/api/request":
            return self._json(404, {"error": "not found"})
        ip = self._ip()
        if time.time() - _last.get(ip, 0) < 10:
            return self._json(429, {"error": "please wait a few seconds before sending again"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 20000:
                return self._json(413, {"error": "request too large"})
            raw = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "invalid JSON"})
        rec = {k: str(raw.get(k, ""))[:lim].strip() for k, lim in FIELDS.items()}
        if not rec["name"] or not EMAIL.match(rec["email"]):
            return self._json(400, {"error": "name and a valid email are required"})
        if rec["kind"] not in KINDS:
            rec["kind"] = "private_hill"
        rec["rows"] = int(raw.get("rows") or 0)
        for k in ("columns", "checks"):
            if isinstance(raw.get(k), list):
                rec[k] = [str(x)[:200] for x in raw[k][:200]]
        rec["id"] = "req_" + secrets.token_hex(4)
        rec["received"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rec["status"] = "awaiting human review"
        try:
            save(rec)
        except OSError:
            return self._json(503, {"error": "requests are paused while we set up storage, so nothing was saved",
                                    "paused": True})
        _last[ip] = time.time()
        return self._json(200, {"id": rec["id"], "status": rec["status"]})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    where = "postgres (DATABASE_URL)" if DB_URL else str(OUT)
    if DB_URL:
        try:
            _db = _connect()
            print("database ready: table site_requests", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"database not reachable at start ({type(exc).__name__}); will retry per request", flush=True)
    print(f"serving {ROOT} on 0.0.0.0:{port}; requests -> {where}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
