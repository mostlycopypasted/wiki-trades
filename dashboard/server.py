#!/usr/bin/env python3
"""Trading Desk — local web dashboard over the wiki and the live TAT alert sheet.

    .venv/bin/python3 dashboard/server.py            # http://127.0.0.1:8787
    .venv/bin/python3 dashboard/server.py --port 9000

Read-only: nothing here writes to wiki/ or raw/. Binds to localhost by default.
"""
import argparse
import gzip
import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import wiki_data as W

STATIC = Path(__file__).resolve().parent / "static"


def safe_join(base, rel):
    """Resolve rel under base, refusing anything that escapes it."""
    target = (base / unquote(rel)).resolve()
    base = base.resolve()
    if target != base and base not in target.parents:
        return None
    return target


def api_meta(q):
    rows = W.SHEET.rows
    return {
        "now": W.now_sgt().isoformat(),
        "briefs": W.list_briefs(),
        "tat": W.list_tat_dates(),
        "dsig": W.list_dsig_dates(),
        "sheet": sheet_status(),
        "symbols": sorted({r["sym"] for r in rows} | {i["sym"] for b in W.list_briefs()[:1] for i in (W.parse_brief(b) or {}).get("watchlist", [])}),
    }


def sheet_status():
    s = W.SHEET
    return {"fetchedAt": s.fetched_at, "error": s.error, "loading": s.loading,
            "rows": len(s.rows), "tabs": s.tab_counts, "ttl": W.SHEET_TTL}


def api_signals(q):
    rows = W.SHEET.get(force=q.get("refresh") == "1")
    return {"status": sheet_status(), "rows": rows}


def api_brief(q):
    date = q.get("date") or (W.list_briefs() or [None])[0]
    return W.parse_brief(date) if date else None


def api_tat(q):
    date = q.get("date") or (W.list_tat_dates() or [None])[0]
    return W.parse_tat_report(date) if date else None


def api_tat_latest(q):
    """Setups from the most recent run of the most recent TAT report (no markdown)."""
    for date in W.list_tat_dates():
        rep = W.parse_tat_report(date)
        if rep and rep["runs"]:
            run = rep["runs"][-1]
            return {"date": date, "time": run["time"], "setups": run["setups"], "path": rep["path"]}
    return None


def api_dsig(q):
    date = q.get("date") or (W.list_dsig_dates() or [None])[0]
    return W.parse_daily_signals_report(date) if date else None


def api_doc(q):
    path = safe_join(W.WIKI, q.get("path", ""))
    if not path or path.suffix != ".md" or not path.exists():
        return None
    return {"path": str(path.relative_to(W.WIKI)), "md": W.read(path)}


def api_images(q):
    sym = (q.get("sym") or "").upper()
    idx = W.image_index()
    # captures of SGX/HKEX names were saved under a few spellings over time
    keys = [sym, sym + "SI", sym + "HK", "SGX_" + sym, "HKEX_" + sym]
    found = [img for k in keys for img in idx.get(k, [])]
    return sorted(found, key=lambda i: i["at"], reverse=True)[:40]


ROUTES = {
    "/api/meta": api_meta,
    "/api/signals": api_signals,
    "/api/brief": api_brief,
    "/api/strength-history": lambda q: W.strength_history(),
    "/api/calendar": lambda q: W.parse_calendar(),
    "/api/cb": lambda q: W.parse_cb_tally(),
    "/api/tat": api_tat,
    "/api/tat-latest": api_tat_latest,
    "/api/dsig": api_dsig,
    "/api/ahh": lambda q: W.all_ahh(),
    "/api/sentiment": lambda q: W.latest_sentiment(q.get("date")),
    "/api/images": api_images,
    "/api/journal": lambda q: W.all_journal(),
    "/api/doc": api_doc,
    "/api/my-watchlist": lambda q: W.my_watchlist_gallery(),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "TradingDesk/1.0"

    def log_message(self, fmt, *args):  # quieter console: only errors
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ROUTES:
                data = ROUTES[url.path](q)
                if data is None:
                    return self.send_json({"error": "not found"}, 404)
                return self.send_json(data)
            if url.path.startswith("/images/"):
                return self.send_file(safe_join(W.IMAGES, url.path[len("/images/"):]), cache=86400)
            if url.path in ("/", "/index.html"):
                return self.send_file(STATIC / "index.html")
            if url.path.startswith("/static/"):
                return self.send_file(safe_join(STATIC, url.path[len("/static/"):]))
            self.send_error(404)
        except BrokenPipeError:
            pass
        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": "%s: %s" % (type(e).__name__, e)}, 500)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        gz = "gzip" in self.headers.get("Accept-Encoding", "") and len(body) > 2048
        if gz:
            body = gzip.compress(body, compresslevel=5)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, cache=0):
        if not path or not path.is_file():
            return self.send_error(404)
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=%d" % cache if cache else "no-cache")
        self.end_headers()
        self.wfile.write(data)


def main():
    ap = argparse.ArgumentParser(description="Trading Desk dashboard server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    threading.Thread(target=W.SHEET.get, daemon=True).start()  # warm the alert-sheet cache
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("📊 Trading Desk on http://%s:%d  (Ctrl+C to stop)" % (args.host, args.port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
