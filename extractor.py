"""
PDF bank statement extractor.

Column-aware: instead of guessing from text, every amount is assigned to the
"In", "Out" or "Balance" column by its x-position under the table header.
This gives each transaction a Direction, which the old regex parser lost
(it treated wages, refunds and transfers-in as spending).

Every statement is reconciled against the totals printed on the statement
itself (Payments In / Payments Out), and the running balance is checked
row-by-row where the bank prints it.

Public API (unchanged signature for app.py):
    process_pdf(file_object, file_name) -> (DataFrame | None, message)
    extract_statement(file_object) -> (DataFrame | None, meta dict)
"""
import re
import datetime as _dt

import pandas as pd
import pdfplumber

# ---------------------------------------------------------------------------
# Bank detection: score distinctive markers instead of "first word match".
# A CV that says "worked at HSBC" must not be parsed as an HSBC statement.
# ---------------------------------------------------------------------------
BANK_MARKERS = {
    "Revolut":    ["REVOLUT LTD", "REVOGB", "REVOLUT BANK", "REVPOINTS"],
    "Starling":   ["STARLINGBANK.COM", "STARLING BANK", "SRLGGB"],
    "HSBC":       ["HSBC", "HBUKGB", "HSBC UK"],
    "Santander":  ["SANTANDER", "ABBYGB"],
    "Nationwide": ["NATIONWIDE", "NAIAGB", "FLEXACCOUNT", "BUILDING SOCIETY"],
    "Barclays":   ["BARCLAYS", "BARCGB", "BARCLAYS BANK"],
    "Lloyds":     ["LLOYDS", "LOYDGB", "LLOYDS BANK"],
    "NatWest":    ["NATWEST", "NWBKGB", "NATIONAL WESTMINSTER"],
    "Monzo":      ["MONZO", "MONZGB", "MONZO BANK"],
    "Halifax":    ["HALIFAX", "HLFXGB"],
    "Chase":      ["CHASE", "CHASGB", "JPMORGAN CHASE"],
    "TSB":        ["TSB", "TSBSGB"],
}
# Signals that the document is a bank statement at all.
STATEMENT_SIGNALS = [r"SORT\s*CODE", r"\bIBAN\b", r"ACCOUNT\s*(NUMBER|NO)", r"\bBALANCE\b", r"STATEMENT"]

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

AMOUNT_RE = re.compile(r"^-?£?-?\(?[\d,]*\d\.\d{2}\)?$")
CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}\)?$")
DATE_TEXT_RE = re.compile(
    r"^(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<m>[A-Za-z]{3,4})\.?(?:\s+(?P<y>\d{4}|\d{2}))?(?=\s|$)")
DATE_SLASH_RE = re.compile(r"^(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{4}|\d{2})(?=\s|$)")
FULL_DATE_ANYWHERE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?\s+(20\d{2})\b")
SLASH_DATE_ANYWHERE = re.compile(r"\b(\d{2})/(\d{2})/(20\d{2})\b")

END_OF_TABLE = re.compile(r"carried\s*forward|reverted\s+from|pending\s+from|^start\s+date", re.I)
SKIP_ROW = re.compile(r"brought\s*forward|opening\s*balance|closing\s*balance|^balance\s+from\s+statement", re.I)
FOOTER_JUNK = re.compile(
    r"report lost|revolut ltd|revolut trading|get help|financial conduct|fscs|financial services comp|"
    r"registered (in|address)|authorised by|scan the qr|page \d+ of|interest will be|we charge interest|"
    r"continued on|sheet number|starling bank is|^©", re.I)

# Bank-specific behaviour.
#   wrap: where description overflow lines sit relative to the amount line.
#         "before" = HSBC style (amount is on the LAST line of a multi-line entry)
#         "after"  = Santander/Revolut style (amount on FIRST line, details follow)
BANK_CFG = {
    "HSBC":       {"wrap": "before"},
    "Santander":  {"wrap": "after"},
    "Revolut":    {"wrap": "after", "skip_cont": re.compile(r"^(revolut rate|card:)", re.I)},
    "Starling":   {"wrap": "after"},
    "Nationwide": {"wrap": "after"},
}


def _norm(word):
    return word.lower().strip("£:()").strip()


def _to_float(token):
    t = token.replace("£", "").replace(",", "").strip()
    neg = t.startswith("-") or t.endswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("-()")
    val = float(t)
    return -val if neg else val


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
def _page_lines(page):
    """Group words into visual lines (sorted top->bottom, left->right)."""
    words = page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)
    words.sort(key=lambda w: (round(w["top"]), w["x0"]))
    lines, current, cur_top = [], [], None
    for w in words:
        if cur_top is None or abs(w["top"] - cur_top) <= 3:
            current.append(w)
            cur_top = w["top"] if cur_top is None else cur_top
        else:
            lines.append(sorted(current, key=lambda x: x["x0"]))
            current, cur_top = [w], w["top"]
    if current:
        lines.append(sorted(current, key=lambda x: x["x0"]))
    return lines


def _find_columns(lines, idx):
    """If lines[idx] is a transaction table header, return {'in':cx,'out':cx,'balance':cx} column centres."""
    words = lines[idx]
    norms = [_norm(w["text"]) for w in words]
    
    # Check date column (matches 'Date', 'Transaction Date', 'Posted Date', etc.)
    has_date = any(any(k in n for k in ("date", "trans", "posted", "time")) for n in norms)
    if not has_date:
        return None

    cols = {}
    in_aliases = ("in", "credit", "credits", "deposit", "deposits", "received")
    out_aliases = ("out", "debit", "debits", "withdrawal", "withdrawals", "paid")
    
    for w, n in zip(words, norms):
        if n in in_aliases and "in" not in cols:
            cols["in"] = [w["x0"], w["x1"]]
        elif n in out_aliases and "out" not in cols:
            cols["out"] = [w["x0"], w["x1"]]
        elif n in ("balance", "bal") and "balance" not in cols:
            cols["balance"] = [w["x0"], w["x1"]]

    # Merge compound header phrases (e.g. "Paid In", "Money In", "Paid Out", "Money Out")
    for i, (w, n) in enumerate(zip(words, norms)):
        if n in ("paid", "money", "total") and i + 1 < len(words):
            next_n = norms[i + 1]
            if next_n in in_aliases and "in" in cols:
                cols["in"][0] = w["x0"]
            elif next_n in out_aliases and "out" in cols:
                cols["out"][0] = w["x0"]

    if "in" not in cols or "out" not in cols:
        return None

    if "balance" not in cols and idx + 1 < len(lines):
        for w in lines[idx + 1]:
            if _norm(w["text"]) in ("balance", "bal") and w["x0"] > max(cols["in"][1], cols["out"][1]):
                cols["balance"] = [w["x0"], w["x1"]]

    if "balance" not in cols:
        return None  # Tables without balance column are typically auxiliary/pending summaries

    return {k: (v[0] + v[1]) / 2 for k, v in cols.items()}


def _classify_amounts(words, cols):
    """Split a line into (desc_words, {'in':x,'out':y,'balance':z})."""
    amounts, desc = {}, []
    for i, w in enumerate(words):
        txt = w["text"]
        nxt = words[i + 1]["text"] if i + 1 < len(words) else ""
        if AMOUNT_RE.match(txt) and not (CURRENCY_CODE_RE.match(nxt) and nxt not in ("GBP", "EUR", "USD")):
            centre = (w["x0"] + w["x1"]) / 2
            col, dist = min(((c, abs(centre - x)) for c, x in cols.items()), key=lambda t: t[1])
            if dist < 45 and col not in amounts:
                amounts[col] = _to_float(txt)
                continue
        desc.append(w)
    return desc, amounts


def _parse_leading_date(text):
    """Return (day, month, year|None, matched_length) for a date at the start of text."""
    m = DATE_SLASH_RE.match(text)
    if m:
        y = int(m["y"]); y = y + 2000 if y < 100 else y
        return int(m["d"]), int(m["m"]), y, m.end()
    m = DATE_TEXT_RE.match(text)
    if m and m["m"][:3].lower() in MONTHS:
        y = m["y"]
        y = (int(y) + 2000 if len(y) == 2 else int(y)) if y else None
        return int(m["d"]), MONTHS[m["m"][:3].lower()], y, m.end()
    return None


def _statement_end_date(full_text):
    """Latest full date on page 1: used to infer the year for 'dd Mon' style dates."""
    found = []
    for d, mon, y in FULL_DATE_ANYWHERE.findall(full_text):
        if mon[:3].lower() in MONTHS:
            try:
                found.append(_dt.date(int(y), MONTHS[mon[:3].lower()], int(d)))
            except ValueError:
                pass
    for d, mo, y in SLASH_DATE_ANYWHERE.findall(full_text):
        try:
            found.append(_dt.date(int(y), int(mo), int(d)))
        except ValueError:
            pass
    return max(found) if found else None


def _summary_totals(text):
    """Pull the bank's own printed totals from page 1 for reconciliation across any bank."""
    t = re.sub(r"[ \t]+", " ", text)
    out = {}
    m = re.search(r"(?:payments|total money|money|paid|credits?|deposits?)\s*in:?\s*£?(-?[\d,]+\.\d{2})", t, re.I)
    if m: out["in"] = abs(_to_float(m.group(1)))
    m = re.search(r"(?:payments|total money|money|paid|debits?|withdrawals?)\s*out:?\s*-?£?(-?[\d,]+\.\d{2})", t, re.I)
    if m: out["out"] = abs(_to_float(m.group(1)))
    m = re.search(r"^Total\s+£([\d,]+\.\d{2})\s+£([\d,]+\.\d{2})\s+£([\d,]+\.\d{2})\s+£([\d,]+\.\d{2})", t, re.M)
    if m:  # Revolut: Opening, Money out, Money in, Closing
        out.update(opening=_to_float(m.group(1)), out=_to_float(m.group(2)),
                   **{"in": _to_float(m.group(3))}, closing=_to_float(m.group(4)))
    return out


def detect_bank(first_page_text):
    """Detects bank name or accepts verified statement with 3+ banking signals."""
    up = first_page_text.upper()
    signals = sum(1 for s in STATEMENT_SIGNALS if re.search(s, up))
    if signals < 2:
        return None

    # Focus bank identification on the institution header area (before transaction table)
    table_split = re.split(r'\bDATE\b.*?\b(?:DEBIT|CREDIT|MONEY|PAID|WITHDRAWAL|DEPOSIT|BALANCE)\b', up, flags=re.DOTALL)
    header_area = table_split[0] if table_split else up[:500]

    scores = {}
    for b, keys in BANK_MARKERS.items():
        h_score = sum(3 for k in keys if re.search(r'\b' + re.escape(k) + r'\b', header_area))
        scores[b] = h_score

    best_bank, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score >= 3:
        return best_bank
    if signals >= 3:
        return "Bank Statement"
    return None


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------
def _parse(pdf, bank):
    cfg = BANK_CFG.get(bank, {"wrap": "after"})
    wrap, skip_cont = cfg["wrap"], cfg.get("skip_cont")
    first_text = pdf.pages[0].extract_text() or ""
    end_date = _statement_end_date(first_text)

    txns, balance_checks = [], {"ok": 0, "broken": 0}
    running = None             # running balance, for row-by-row validation
    cols, current_date = None, None
    buffer, last_txn, last_top = "", None, None

    for page in pdf.pages:
        lines = _page_lines(page)
        in_table = False
        for i, words in enumerate(lines):
            text = " ".join(w["text"] for w in words)
            top = words[0]["top"]

            header = _find_columns(lines, i)
            if header:
                cols, in_table, buffer, last_top = header, True, "", top
                last_txn = None
                continue
            if not in_table or cols is None:
                continue
            if END_OF_TABLE.search(text):
                in_table = False
                continue
            if FOOTER_JUNK.search(text):
                continue

            d = _parse_leading_date(text)
            if d:
                day, month, year, _ = d
                if year is None and end_date:
                    year = end_date.year - (1 if month > end_date.month else 0)
                try:
                    current_date = _dt.date(year or _dt.date.today().year, month, day)
                except ValueError:
                    pass
                # Drop the words that made up the date from the line.
                consumed = len(text[: d[3]].split())
                words = words[consumed:]
                buffer = ""

            desc_words, amts = _classify_amounts(words, cols)
            desc = " ".join(w["text"] for w in desc_words).strip(" .")

            if SKIP_ROW.search(text):
                if "balance" in amts:
                    running = amts["balance"]
                continue

            money_in, money_out = amts.get("in"), amts.get("out")
            if (money_in or money_out) and current_date:
                full_desc = f"{buffer} {desc}".strip() if wrap == "before" else desc
                amount = money_in if money_in else money_out
                txn = {"Date": current_date, "Description": full_desc,
                       "Amount": abs(amount), "Direction": "In" if money_in else "Out", "Bank": bank}
                txns.append(txn)
                if running is not None:
                    running = round(running + (money_in or 0) - (money_out or 0), 2)
                if "balance" in amts:
                    if running is not None:
                        balance_checks["ok" if abs(running - amts["balance"]) < 0.01 else "broken"] += 1
                    running = amts["balance"]
                buffer, last_txn, last_top = "", txn, top
            elif desc:
                if wrap == "before":
                    if last_top is not None and top - last_top > 40:
                        buffer = ""
                    buffer = f"{buffer} {desc}".strip()
                    last_top = top
                elif last_txn is not None and last_top is not None and top - last_top < 30:
                    if not (skip_cont and skip_cont.search(desc)) and len(desc) < 120:
                        last_txn["Description"] += " | " + desc
                    last_top = top
            if "balance" in amts and not (money_in or money_out):
                running = amts["balance"]

    return txns, balance_checks, _summary_totals(first_text)


def extract_statement(file_object):
    """Returns (df, meta). df is None on failure; meta['error'] explains why."""
    meta = {}
    try:
        with pdfplumber.open(file_object) as pdf:
            if len(pdf.pages) == 0:
                return None, {"error": "PDF is empty or locked."}
            if len(pdf.pages) > 50:
                return None, {"error": "PDF exceeds 50 pages maximum safety limit."}
            first_text = pdf.pages[0].extract_text() or ""
            if not first_text.strip():
                return None, {"error": "No readable text (scanned image?)."}
            bank = detect_bank(first_text)
            if not bank:
                return None, {"error": "Not recognised as a supported bank statement "
                                       "(HSBC, Santander, Starling, Nationwide, Revolut)."}
            txns, checks, summary = _parse(pdf, bank)
    except Exception as e:
        return None, {"error": f"Invalid or unreadable PDF document ({e})"}

    meta.update(bank=bank, balance_checks=checks, summary=summary)
    if not txns:
        meta["error"] = f"Recognised {bank}, but found no transactions."
        return None, meta

    df = pd.DataFrame(txns)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date", kind="stable").reset_index(drop=True)
    df["Date"] = df["Date"].dt.strftime("%d %b %Y")

    total_in = round(df.loc[df.Direction == "In", "Amount"].sum(), 2)
    total_out = round(df.loc[df.Direction == "Out", "Amount"].sum(), 2)
    meta.update(n=len(df), total_in=total_in, total_out=total_out)
    checks_ok = []
    if "in" in summary:
        checks_ok.append(abs(summary["in"] - total_in) < 0.01)
    if "out" in summary:
        checks_ok.append(abs(summary["out"] - total_out) < 0.01)
    meta["reconciled"] = bool(checks_ok) and all(checks_ok)
    meta["reconcile_available"] = bool(checks_ok)
    return df, meta


def process_pdf(file_object, file_name):
    try:
        df, meta = extract_statement(file_object)
    except Exception as e:  # corrupt PDFs etc.
        return None, f"🚨 {file_name}: could not read PDF ({e})"
    if df is None:
        return None, f"❌ {file_name}: {meta.get('error')}"
    msg = (f"✅ {file_name}: {meta['bank']}: {meta['n']} transactions "
           f"(in £{meta['total_in']:,.2f} / out £{meta['total_out']:,.2f})")
    if meta["reconciled"]:
        msg += ". Matches the statement's own totals ✔"
    elif meta["reconcile_available"]:
        s = meta["summary"]
        msg += (f". ⚠️ Statement says in £{s.get('in', 0):,.2f} / out £{s.get('out', 0):,.2f}, "
                f"so some rows may be missing")
    return df, msg