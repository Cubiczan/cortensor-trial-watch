"""Deterministic recurring-charge analysis (no model needed)."""
import csv, io, re
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median

DATE_FMTS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y", "%Y/%m/%d", "%b %d, %Y", "%d %b %Y")


def parse_date(s):
    s = s.strip()
    for f in DATE_FMTS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognized date: {s!r}")


def parse_amount(s):
    s = s.strip().replace(",", "").replace("$", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    v = float(s)
    return -v if neg else v


def merchant_key(desc):
    d = desc.upper()
    d = re.sub(r"\d{3,}|#\S+|\*", " ", d)
    d = re.sub(r"\b(POS|ACH|DEBIT|PURCHASE|RECURRING|PAYMENT|CARD|ONLINE|WWW|COM|INC|LLC)\b", " ", d)
    d = re.sub(r"[^A-Z ]", " ", d)
    words = [w for w in d.split() if len(w) > 1]
    return " ".join(words[:3]) or desc.strip().upper()


def load_rows(text):
    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    cols = {c.lower().strip(): c for c in reader.fieldnames}
    pick = lambda *names: next((cols[n] for n in names if n in cols), None)
    dc = pick("date", "transaction date", "posted date", "posting date")
    nc = pick("description", "merchant", "name", "payee", "memo")
    ac = pick("amount", "value")
    debit, credit = pick("debit", "withdrawal"), pick("credit", "deposit")
    if not dc or not nc or not (ac or debit):
        raise ValueError("Need columns: date, description, amount (or debit/credit)")
    rows = []
    for r in reader:
        try:
            if ac:
                amt = parse_amount(r[ac])
            else:
                amt = (parse_amount(r[credit]) if credit and r.get(credit) else 0) - (
                    parse_amount(r[debit]) if r.get(debit) else 0)
            rows.append({"date": parse_date(r[dc]), "desc": r[nc].strip(), "amount": amt})
        except (ValueError, KeyError):
            continue
    if not rows:
        raise ValueError("No parsable transactions found")
    # Normalise sign: if most rows are positive, treat positives as spend.
    if sum(1 for r in rows if r["amount"] > 0) > len(rows) * 0.8:
        for r in rows:
            r["amount"] = -r["amount"]
    return rows


def cadence(days):
    for name, target, tol in (("weekly", 7, 2), ("monthly", 30, 4), ("quarterly", 91, 8), ("yearly", 365, 15)):
        if abs(days - target) <= tol:
            return name, target
    return None, None


def _consistent(amts):
    """Subscriptions bill a fixed amount, possibly stepping up (trial->paid, price hike)."""
    distinct = {round(a, 0) for a in amts}
    if len(distinct) <= 2:
        return True
    med = median(amts)
    return sum(1 for a in amts if abs(a - med) <= 0.1 * med) >= 0.75 * len(amts)


def analyze(rows, cash_on_hand=None):
    rows.sort(key=lambda r: r["date"])
    end = rows[-1]["date"]
    groups = defaultdict(list)
    for r in rows:
        if r["amount"] < 0:
            groups[merchant_key(r["desc"])].append(r)
    recurring = []
    for key, txs in groups.items():
        if len(txs) < 2:
            continue
        gaps = [(b["date"] - a["date"]).days for a, b in zip(txs, txs[1:])]
        name, period = cadence(median(gaps))
        if not name:
            continue
        amts = [-t["amount"] for t in txs]
        if not _consistent(amts):
            continue  # variable discretionary spend (fuel, rides), not a subscription
        last = txs[-1]
        monthly = amts[-1] * 30 / period  # forward-looking: what it will cost next cycle
        flags = []
        if len(amts) >= 2 and amts[-1] > amts[0] * 1.15:
            flags.append(f"price up {amts[0]:.2f} -> {amts[-1]:.2f}")
        if amts[0] < 2 and amts[-1] >= 5:
            flags.append("looks like a trial that converted to paid")
        nxt = last["date"] + timedelta(days=period)
        recurring.append({
            "merchant": key.title(), "cadence": name, "charges": len(txs),
            "last_amount": round(amts[-1], 2), "monthly_cost": round(monthly, 2),
            "annual_cost": round(monthly * 12, 2), "last_charge": last["date"].isoformat(),
            "next_expected": nxt.isoformat(), "flags": flags,
            "stale": (end - last["date"]).days > period + 7,
        })
    recurring.sort(key=lambda x: -x["monthly_cost"])
    span_days = max((end - rows[0]["date"]).days, 1)
    spend = -sum(r["amount"] for r in rows if r["amount"] < 0)
    income = sum(r["amount"] for r in rows if r["amount"] > 0)
    burn = (spend - income) * 30 / span_days
    upcoming = [r for r in recurring if not r["stale"] and
                date.fromisoformat(r["next_expected"]) <= end + timedelta(days=14)]
    out = {
        "period": {"from": rows[0]["date"].isoformat(), "to": end.isoformat(), "transactions": len(rows)},
        "totals": {"spend": round(spend, 2), "income": round(income, 2),
                   "net_monthly_burn": round(burn, 2)},
        "recurring": recurring,
        "subscription_monthly_total": round(sum(r["monthly_cost"] for r in recurring if not r["stale"]), 2),
        "upcoming_14d": [{"merchant": u["merchant"], "date": u["next_expected"], "amount": u["last_amount"]} for u in upcoming],
    }
    if cash_on_hand is not None and burn > 0:
        out["runway_months"] = round(cash_on_hand / burn, 1)
    return out


