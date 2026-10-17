"""Broker statement logs (AXI, Fusion) -> normalised trades + performance stats for the Performance tab.

Read-only: pulls each account's `Statement Logs` tab with the service account, keeps the last good copy in
memory and in cache/statements.json (so the tab still renders when Google is unreachable), and never writes
to the sheets or to wiki/. All times are converted to SGT, like the rest of the desk.
"""
import datetime as dt
import json
import re
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import wiki_data as W

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "cache" / "statements.json"
TTL = 900
NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
SA_CANDIDATES = [W.ROOT / "service_account.json", Path.home() / "tradingview-mcp" / "service_account.json",
                 Path.home() / "service_account.json"]
# names wiki_data.asset_class() doesn't know (broker-specific CFD names)
CLASS_OVERRIDE = {"USOIL": "Energy", "UKOIL": "Energy", "COPPER": "Metal", "USDINDEX": "Index", "US500": "Index",
                  "USTEC": "Index", "US100": "Index"}


def _num(v):
    """'$5,000.00' / '-$0.13' / '(12.5)' / '-22.73' / '' -> float."""
    s = str(v or "").strip().replace(",", "").replace("$", "").replace("SGD", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        x = float(s)
    except ValueError:
        return 0.0
    return -x if neg else x


def _sgt(d):
    return d.astimezone(W.SGT).strftime("%Y-%m-%d %H:%M:%S")


def _axi_time(s):
    """MT4 server time = New York time + 7h (GMT+2 winter / GMT+3 summer)."""
    s = (s or "").strip()
    if not s:
        return None
    naive = dt.datetime.strptime(s, "%Y.%m.%d %H:%M:%S") - dt.timedelta(hours=7)
    return _sgt(naive.replace(tzinfo=NY))


def _utc_time(s):
    s = (s or "").strip()
    if not s:
        return None
    return _sgt(dt.datetime.strptime(s, "%d/%m/%Y %H:%M:%S").replace(tzinfo=UTC))


def _sym(s):
    return re.sub(r"\.[a-z]+$", "", (s or "").strip(), flags=re.I).replace("-", "").upper()


def _hours(a, b):
    if not a or not b:
        return None
    f = "%Y-%m-%d %H:%M:%S"
    return (dt.datetime.strptime(b, f) - dt.datetime.strptime(a, f)).total_seconds() / 3600


def _flow_kind(note, amount):
    n = (note or "").lower()
    if "truncation" in n:
        return "adjustment"
    if "dividend" in n:
        return "dividend"
    if "promo" in n:
        return "promo"
    if "transfer" in n:
        return "transfer"
    return "deposit" if amount >= 0 else "withdrawal"


def parse_axi(rows):
    trades, flows = [], []
    for r in rows[1:]:
        r = (r + [""] * 14)[:14]
        ticket, opened, typ, size, item, price, _sl, _tp, closed, cprice, comm, swap, pl, note = r
        typ = typ.strip().lower()
        if typ == "balance":
            amt = _num(pl)
            flows.append({"account": "axi", "time": _axi_time(opened), "amount": amt,
                          "kind": _flow_kind(note, amt), "note": note.strip()})
        elif typ in ("buy", "sell"):
            o, c = _axi_time(opened), _axi_time(closed)
            gross, comm, swap = _num(pl), _num(comm), _num(swap)
            trades.append({"account": "axi", "id": ticket.strip(), "symbol": _sym(item),
                           "side": "long" if typ == "buy" else "short", "size": _num(size),
                           "open": o, "close": c, "entry": _num(price), "exit": _num(cprice),
                           "gross": gross, "commission": comm, "swap": swap,
                           "net": round(gross + comm + swap, 2), "hold": _hours(o, c), "balance": None})
    notes = []
    if any(f["kind"] == "adjustment" for f in flows):
        notes.append("“Data Truncation” balance rows are AXI carrying forward history this log already itemises, "
                     "so they are left out of the balance (counting them would double it).")
    return trades, flows, notes


def parse_fusion(rows):
    trades, seen, dups = [], set(), 0
    for r in rows[1:]:
        r = (r + [""] * 15)[:15]
        did, sym, odir, _cdir, opened, closed, entry, cprice, qty, swap, comm, _conv, gross, net, bal = r
        if not did.strip() or not sym.strip():
            continue
        if did.strip() in seen:   # the log has pasted-twice deals; a deal ID is unique
            dups += 1
            continue
        seen.add(did.strip())
        o, c = _utc_time(opened), _utc_time(closed)
        trades.append({"account": "fusion", "id": did.strip(), "symbol": _sym(sym),
                       "side": "long" if odir.strip().upper() == "BUY" else "short", "size": _num(qty),
                       "open": o, "close": c, "entry": _num(entry), "exit": _num(cprice),
                       "gross": _num(gross), "commission": _num(comm), "swap": _num(swap), "net": _num(net),
                       "hold": _hours(o, c), "balance": _num(bal) if bal.strip() else None})
    # The log has no deposit/withdrawal rows: back them out of the Balance column. The opening balance comes
    # from the first deal; any later jump the deal's own net doesn't explain is a cash movement.
    trades.sort(key=lambda t: (t["close"] or "", t["id"]))
    flows, prev = [], None
    for t in trades:
        if t["balance"] is None:
            continue
        gap = round(t["balance"] - t["net"] - (prev if prev is not None else 0), 2)
        if prev is None or abs(gap) >= 0.05:
            flows.append({"account": "fusion", "time": t["close"], "amount": gap,
                          "kind": "opening" if prev is None else "inferred",
                          "note": "Opening balance (from the first deal)" if prev is None
                          else "Balance change not explained by a deal (deposit, withdrawal or adjustment)"})
        prev = t["balance"]
    notes = []
    if dups:
        notes.append("%d duplicated deal rows in the log were counted once (the sheet's Stats tab counts them twice)." % dups)
    inferred = [f for f in flows if f["kind"] == "inferred"]
    if inferred:
        notes.append("%d balance changes (net %+.2f) aren't explained by a deal, so they're treated as cash movements."
                     % (len(inferred), sum(f["amount"] for f in inferred)))
    return trades, flows, notes


ACCOUNTS = {
    "axi": {"label": "AXI", "key": "188-yOG1NRKNIt9Tdf30D-GvL_rGYuDNi2TdWHoDNcXU", "gid": 201, "parse": parse_axi},
    "fusion": {"label": "Fusion", "key": "1mX_2qAY6vYTXm63XvGawFrrmVU4DnNj3HZVehQv3fOs", "gid": 201,
               "parse": parse_fusion},
}


class StatementCache:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = {}            # account -> {"trades": [...], "flows": [...]}
        self.fetched_at = None
        self.error = None
        self.loading = False
        self.source = None        # "live" | "snapshot"
        self._load_snapshot()

    def _load_snapshot(self):
        try:
            snap = json.loads(SNAPSHOT.read_text())
            self.data, self.fetched_at, self.source = snap["data"], snap["fetchedAt"], "snapshot"
        except (OSError, ValueError, KeyError):
            pass

    def get(self, force=False):
        stale = self.source != "live" or (time.time() - (self.fetched_at or 0)) > TTL
        if (force or stale) and not self.loading:
            if not self.data or force:
                self._refresh()
            else:
                threading.Thread(target=self._refresh, daemon=True).start()
        return self.data

    def _refresh(self):
        with self.lock:
            if self.loading:
                return
            self.loading = True
        try:
            import gspread
            sa = next((p for p in SA_CANDIDATES if p.exists()), None)
            if not sa:
                raise FileNotFoundError("service_account.json not found")
            gc = gspread.service_account(filename=str(sa))
            data = {}
            for acc, cfg in ACCOUNTS.items():
                rows = gc.open_by_key(cfg["key"]).get_worksheet_by_id(cfg["gid"]).get_all_values()
                trades, flows, notes = cfg["parse"](rows)
                data[acc] = {"trades": trades, "flows": flows, "notes": notes}
            self.data, self.error, self.source = data, None, "live"
            self.fetched_at = time.time()
            try:
                SNAPSHOT.parent.mkdir(exist_ok=True)
                tmp = SNAPSHOT.with_suffix(".tmp")
                tmp.write_text(json.dumps({"fetchedAt": self.fetched_at, "data": data}))
                tmp.replace(SNAPSHOT)
            except OSError:
                pass
        except Exception as e:  # keep serving the last good copy
            self.error = "%s: %s" % (type(e).__name__, e)
            self.fetched_at = self.fetched_at or 0
            if self.source == "snapshot" or not self.data:
                self.fetched_at = max(self.fetched_at, time.time() - TTL + 60)  # retry in a minute
                self.source = self.source or "none"
        finally:
            self.loading = False


CACHE = StatementCache()


# ---------------------------------------------------------------- stats

DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _bucket(trades):
    wins = [t["net"] for t in trades if t["net"] > 0]
    losses = [t["net"] for t in trades if t["net"] < 0]
    n = len(trades)
    net = sum(t["net"] for t in trades)
    return {"deals": n, "wins": len(wins), "losses": len(losses), "be": n - len(wins) - len(losses),
            "winRate": len(wins) / n if n else 0, "avg": net / n if n else 0, "net": round(net, 2)}


def _drawdown(series):
    """Max peak-to-trough on a value series -> (dd $, dd % of peak, peak, trough)."""
    peak, best, best_pct = None, 0.0, 0.0
    for v in series:
        peak = v if peak is None else max(peak, v)
        best = max(best, peak - v)
        if peak > 0:
            best_pct = max(best_pct, (peak - v) / peak)
    return round(best, 2), best_pct


def compute(all_trades, flows, since=None):
    """Stats over trades closed on/after `since`; balances are replayed over the full history so the
    window starts from the real balance, not zero."""
    all_trades = sorted([t for t in all_trades if t["close"]], key=lambda t: t["close"])
    trades = [t for t in all_trades if not since or t["close"] >= since]
    n = len(trades)
    b = _bucket(trades)
    gains = sum(t["net"] for t in trades if t["net"] > 0)
    losses = sum(t["net"] for t in trades if t["net"] < 0)
    holds = [t for t in trades if t["hold"] is not None]

    def avg_hold(lst):
        return sum(t["hold"] for t in lst) / len(lst) if lst else 0

    by_sym = {}
    for t in trades:
        by_sym.setdefault(t["symbol"], []).append(t)
    symbols = sorted(({"symbol": s, "cls": CLASS_OVERRIDE.get(s) or W.asset_class(s), **_bucket(lst)}
                      for s, lst in by_sym.items()), key=lambda r: (-r["deals"], r["net"]))
    classes = {}
    for t in trades:
        classes.setdefault(CLASS_OVERRIDE.get(t["symbol"]) or W.asset_class(t["symbol"]), []).append(t)

    def day(t):
        return dt.datetime.strptime(t["close"], "%Y-%m-%d %H:%M:%S")

    dow = [{"day": d, **_bucket([t for t in trades if day(t).weekday() == i])} for i, d in enumerate(DOW)]
    hours = [{"hour": hr, **_bucket([t for t in trades if day(t).hour == hr])} for hr in range(24)]
    months = {}
    for t in trades:
        months.setdefault(t["close"][:7], []).append(t)
    monthly = [{"month": m, **_bucket(lst)} for m, lst in sorted(months.items())]

    # balance: cash flows + realised net in time order (what the broker balance did)
    events = [(f["time"] or "", f["amount"], "flow") for f in flows if f["kind"] != "adjustment"] + \
             [(t["close"], t["net"], "trade") for t in all_trades]
    events.sort(key=lambda e: (e[0], e[2] == "trade"))
    first = trades[0]["close"] if trades else "~"
    bal, balances, start = 0.0, [], None
    for when, amt, kind in events:
        if kind == "trade" and when >= first and start is None:
            start = bal       # balance just before the window's first trade
        bal += amt
        if kind == "trade" and when >= first:
            balances.append(bal)
    # trading-only equity: starting capital + cumulative net (no deposits/transfers/truncation jumps)
    start = start or 0.0
    cum, equity = 0.0, []
    for t in trades:
        cum += t["net"]
        equity.append({"t": t["close"], "cum": round(cum, 2), "eq": round(start + cum, 2)})
    dd_bal, dd_bal_pct = _drawdown(balances)
    dd_eq, dd_eq_pct = _drawdown([start + e["cum"] for e in equity])

    streak = 0
    for t in reversed(trades):
        sgn = 1 if t["net"] > 0 else -1 if t["net"] < 0 else 0
        if sgn == 0 or (streak and (streak > 0) != (sgn > 0)):
            break
        streak += sgn
    best = max(trades, key=lambda t: t["net"]) if trades else None
    worst = min(trades, key=lambda t: t["net"]) if trades else None
    longs = [t for t in trades if t["side"] == "long"]
    shorts = [t for t in trades if t["side"] == "short"]
    return {
        "trades": n, "net": round(sum(t["net"] for t in trades), 2),
        "gross": round(sum(t["gross"] for t in trades), 2), "swap": round(sum(t["swap"] for t in trades), 2),
        "commission": round(sum(t["commission"] for t in trades), 2),
        "avgCommission": sum(t["commission"] for t in trades) / n if n else 0,
        "wins": b["wins"], "losses": b["losses"], "be": b["be"], "winRate": b["winRate"],
        "long": _bucket(longs), "short": _bucket(shorts),
        "avgWin": gains / b["wins"] if b["wins"] else 0, "avgLoss": losses / b["losses"] if b["losses"] else 0,
        "totalGains": round(gains, 2), "totalLosses": round(losses, 2),
        "profitFactor": gains / abs(losses) if losses else None,
        "wlRatio": b["wins"] / b["losses"] if b["losses"] else None,
        "expectancy": b["avg"],
        "largestGain": best["net"] if best else 0, "largestLoss": worst["net"] if worst else 0,
        "bestSymbol": best["symbol"] if best else None, "worstSymbol": worst["symbol"] if worst else None,
        "streak": streak,
        "balance": {"peak": round(max(balances), 2) if balances else None,
                    "trough": round(min(balances), 2) if balances else None,
                    "last": round(balances[-1], 2) if balances else None, "dd": dd_bal, "ddPct": dd_bal_pct},
        "equityDD": {"start": round(start, 2), "dd": dd_eq, "ddPct": dd_eq_pct},
        "hold": {"all": avg_hold(holds), "win": avg_hold([t for t in holds if t["net"] > 0]),
                 "loss": avg_hold([t for t in holds if t["net"] < 0]),
                 "max": max((t["hold"] for t in holds), default=0)},
        "dow": dow, "hours": hours, "monthly": monthly, "symbols": symbols,
        "classes": sorted(({"cls": c, **_bucket(lst)} for c, lst in classes.items()), key=lambda r: -r["deals"]),
        "equity": equity,
    }


def performance(account="all", since=None, refresh=False):
    data = CACHE.get(force=refresh)
    accs = [a for a in ACCOUNTS if account in ("all", a)]
    trades = [t for a in accs for t in data.get(a, {}).get("trades", [])]
    flows = [f for a in accs for f in data.get(a, {}).get("flows", [])]
    stats = compute(trades, flows, since)
    if since:
        trades = [t for t in trades if (t["close"] or "") >= since]
    recent = sorted(trades, key=lambda t: t["close"] or "", reverse=True)[:500]
    accounts = {a: {"label": ACCOUNTS[a]["label"], "trades": len(data.get(a, {}).get("trades", [])),
                    "first": min((t["close"] for t in data.get(a, {}).get("trades", []) if t["close"]), default=None),
                    "last": max((t["close"] for t in data.get(a, {}).get("trades", []) if t["close"]), default=None),
                    "flows": data.get(a, {}).get("flows", []), "notes": data.get(a, {}).get("notes", [])}
                for a in ACCOUNTS}
    return {"status": {"fetchedAt": CACHE.fetched_at, "error": CACHE.error, "source": CACHE.source,
                       "loading": CACHE.loading, "ttl": TTL},
            "account": account, "since": since, "accounts": accounts, "stats": stats, "list": recent}
