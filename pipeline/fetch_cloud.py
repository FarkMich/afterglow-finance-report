#!/usr/bin/env python3
"""Cloud fetch step — pulls the Afterglow finance inputs from the Windsor.ai HTTP API.

Runs in GitHub Actions (no Claude / MCP available there), so it talks to Windsor over
plain HTTPS using the WINDSOR_API_KEY repo secret. Writes the three files that
parse_finance.py consumes:

  orders_raw.csv  : date,packages,value,country     (from the googlesheets connector)
  wc_orders.json  : [{id,date,total,discount_total,country}]  completed WooCommerce orders
  wc_coupons.json : [{id,code,discount}]            one row per coupon line (completed orders)

Notes:
  * Windsor expands country codes to full names ("Czech Republic") and keeps the euro
    sign / thousands commas — we normalise both so the output matches the existing pipeline.
  * For WooCommerce we request ONLY scalar order fields in one call (one row per order) and
    coupon-line fields in a SEPARATE call. Never request line_items + coupon_lines together
    (cartesian blow-up). Units come from the sheet, so line_items are not needed at all.
"""
import os, sys, csv, json, datetime as dt, urllib.parse, urllib.request, urllib.error, pathlib

HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://connectors.windsor.ai"
API_KEY = os.environ.get("WINDSOR_API_KEY", "").strip().strip('"').strip("'").strip()
# tolerate common paste mistakes: a leading "api_key=" prefix or a full URL
if "api_key=" in API_KEY:
    API_KEY = API_KEY.split("api_key=", 1)[1].split("&", 1)[0].strip()
if not API_KEY:
    sys.exit("ERROR: WINDSOR_API_KEY env var is not set (add it as a GitHub repo secret).")
print(f"[auth] using API key of length {len(API_KEY)} (first2={API_KEY[:2]}…)")

def windsor(connector, fields, **params):
    """Call the Windsor data API for one connector and return a list of row dicts.
    On any HTTP error, surface Windsor's response body (it explains the 400)."""
    q = {"api_key": API_KEY, "fields": ",".join(fields), "_renderer": "json"}
    q.update({k: v for k, v in params.items() if v is not None})
    qs = urllib.parse.urlencode(q)
    url = f"{BASE}/{connector}?{qs}"
    safe_url = url.replace(API_KEY, "***")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8")
        except Exception: pass
        raise RuntimeError(f"HTTP {e.code} from Windsor [{connector}] :: body={body[:800]} :: url={safe_url}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON from Windsor [{connector}] :: {raw[:400]} :: url={safe_url}")
    if isinstance(payload, dict):
        if payload.get("error"):
            raise RuntimeError(f"Windsor error [{connector}]: {payload['error']} :: url={safe_url}")
        rows = payload.get("data", payload.get("rows", []))
    else:
        rows = payload
    if not isinstance(rows, list):
        raise RuntimeError(f"Unexpected Windsor shape [{connector}]: {str(payload)[:300]}")
    print(f"[windsor] {connector}: {len(rows)} rows  (fields={len(fields)})")
    return rows

# country full-name -> ISO-2 code, to match the existing sheet/dashboard convention
COUNTRY = {
    "Czech Republic":"CZ","Czechia":"CZ","Slovakia":"SK","Netherlands":"NL","Germany":"DE",
    "Spain":"ES","Portugal":"PT","Italy":"IT","Belgium":"BE","Indonesia":"ID","Ireland":"IE",
    "Austria":"AT","France":"FR","Poland":"PL","Hungary":"HU","Romania":"RO","Bulgaria":"BG",
    "Croatia":"HR","Slovenia":"SI","Sweden":"SE","Denmark":"DK","Finland":"FI","Norway":"NO",
    "Switzerland":"CH","United Kingdom":"GB","Greece":"GR","Luxembourg":"LU","Estonia":"EE",
    "Latvia":"LV","Lithuania":"LT","United States":"US",
}
def to_code(name):
    name = (name or "").strip()
    return COUNTRY.get(name, name)  # leave unknown / "IE/DE" untouched

# WooCommerce sometimes marks a paid order "failed" (gateway callback failed though the
# payment actually cleared). These order IDs are confirmed-real sales and are counted as
# completed for orders, customers, discounts and coupons. Add IDs here when reconciled.
REINSTATE_FAILED = {"8106", "8014"}  # Mariia Petrenko (May 2026), Jasna Trgachevska (May 2026)
def is_real_order(r):
    s = (r.get("orders__status") or "").strip()
    # "processing" = paid but not yet fulfilled; counts as a real sale for orders/customers/CAC.
    return s in ("completed", "processing") or (s == "failed" and str(r.get("orders__id")) in REINSTATE_FAILED)

def clean_money(v):
    return (v or "").replace("€", "").replace("EUR", "").replace(",", "").strip()

TODAY = dt.date.today().isoformat()

# ---------------- GUARD HELPERS ----------------
# Windsor occasionally returns an empty or partial slice on an otherwise-successful
# (non-error) call. Writing that straight to disk is what wipes CAC / YTD. These helpers
# let each fetcher compare the fresh pull against what is already on disk and refuse to
# overwrite good data with a shrunk / blank / email-less response (same idea as fetch_meta).
def _prev_csv_data(name):
    """Return the current CSV's data rows (header dropped), or None if the file is absent."""
    p = HERE / name
    if not p.exists():
        return None
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    return lines[1:] if lines else []

def _prev_json(name):
    """Return the current JSON list, or None if the file is absent/unreadable."""
    p = HERE / name
    if not p.exists():
        return None
    try:
        v = json.loads(p.read_text())
        return v if isinstance(v, list) else None
    except (json.JSONDecodeError, ValueError):
        return None

# ---------------- 1) GOOGLE SHEET -> orders_raw.csv ----------------
def fetch_sheet():
    sheet_fields = ["date", "#_of_packages", "order_value_(incl._shipping)", "country"]
    sheet = windsor("googlesheets", sheet_fields, date_preset="last_2years")
    rows_out = ["date,packages,value,country"]; kept = 0
    for row in sheet:
        date = (row.get("date") or "").strip()
        pk = (row.get("#_of_packages") or "").strip()
        val = clean_money(row.get("order_value_(incl._shipping)"))
        ctry = to_code(row.get("country"))
        if not date:
            continue
        if val == "" and ctry == "":      # skip empty future-date placeholder rows
            continue
        rows_out.append(f"{date},{pk},{val},{ctry}")
        kept += 1
    # GUARD: never overwrite orders_raw.csv with an empty or shrunk sheet. A blank/partial
    # Windsor slice here wipes YTD and every historical month. Keep the last good file instead.
    prev_rows = _prev_csv_data("orders_raw.csv")
    prev_n = len(prev_rows) if prev_rows is not None else 0
    if kept == 0:
        print(f"[sheet] GUARD: Windsor returned 0 usable rows; keeping existing orders_raw.csv ({prev_n} rows)")
        return
    if prev_rows is not None and kept < prev_n:
        print(f"[sheet] GUARD: candidate has fewer rows ({kept}) than current ({prev_n}); "
              f"refusing to shrink - keeping existing orders_raw.csv")
        return
    (HERE / "orders_raw.csv").write_text("\n".join(rows_out) + "\n")
    print(f"[sheet] wrote orders_raw.csv with {kept} order rows (was {prev_n})")

# ---------------- 1b) META ADS spend -> meta_spend.json ----------------
def fetch_meta():
    # Monthly Meta (Facebook/Instagram Ads) spend since 2026-01-01, aggregated from daily rows.
    rows = windsor("facebook", ["date", "spend"], date_from="2026-01-01", date_to=TODAY)
    by_month = {}
    for r in rows:
        d = (r.get("date") or "").strip()
        if len(d) < 7:
            continue
        key = d[:7]  # YYYY-MM
        try:
            by_month[key] = by_month.get(key, 0.0) + float(r.get("spend") or 0)
        except (TypeError, ValueError):
            continue
    # MERGE, never clobber. Windsor's facebook connector intermittently returns an
    # empty or partial slice even on a successful (non-error) call; the old code wrote
    # that straight over meta_spend.json, wiping historical CAC data. Instead we load the
    # existing file and only overwrite a month when the fresh pull reports real (>0) spend
    # for it, and we refuse to shrink the file. A transient empty Meta response is now a
    # no-op rather than data loss.
    prev = {}
    p = HERE / "meta_spend.json"
    if p.exists():
        try:
            prev = {r["month"]: float(r.get("spend") or 0)
                    for r in json.loads(p.read_text()) if r.get("month")}
        except (json.JSONDecodeError, TypeError, KeyError):
            prev = {}
    merged = dict(prev)
    updated = 0
    for k, v in by_month.items():
        v = round(v, 2)
        if v > 0 and v != prev.get(k):   # only real spend updates an existing/new month
            merged[k] = v
            updated += 1
    if not merged:
        print("[meta] fresh pull and existing file both empty - leaving meta_spend.json untouched")
        return
    if len(merged) < len(prev):
        print(f"[meta] refusing to shrink meta_spend.json "
              f"({len(prev)} -> {len(merged)} months); keeping previous file")
        return
    out = [{"month": k, "spend": merged[k]} for k in sorted(merged)]
    p.write_text(json.dumps(out, indent=1))
    print(f"[meta] wrote meta_spend.json with {len(out)} month rows "
          f"({updated} updated from fresh pull, total spend {round(sum(x['spend'] for x in out), 2)})")

# ---------------- 2) WOOCOMMERCE orders -> wc_orders.json ----------------
def fetch_orders():
    order_fields = ["orders__id","orders__status","orders__date_created","orders__total",
                    "orders__discount_total","orders__billing__country","orders__billing__email"]
    wo = windsor("woocommerce", order_fields, date_from="2025-01-01", date_to=TODAY)
    seen = {}
    for r in wo:
        if not is_real_order(r):
            continue
        oid = str(r.get("orders__id"))
        seen[oid] = {
            "id": oid, "date": r.get("orders__date_created"),
            "total": float(r.get("orders__total") or 0),
            "discount_total": float(r.get("orders__discount_total") or 0),
            "country": (r.get("orders__billing__country") or "").strip(),
            "email": (r.get("orders__billing__email") or "").strip(),
        }
    new = list(seen.values())
    prev = _prev_json("wc_orders.json")
    prev_n = len(prev) if prev is not None else 0
    # GUARD 1: empty pull -> keep the previous file (transient Windsor blank).
    if not new:
        print(f"[woo] GUARD: 0 real orders returned; keeping existing wc_orders.json ({prev_n})")
        return
    # GUARD 2: every kept order MUST carry an email. parse_finance counts unique customers by
    # billing email for CAC; a single missing email means Windsor dropped the field, which
    # silently zeroes every customer count and blanks the CAC tab. Refuse the write.
    missing = [o["id"] for o in new if not o["email"]]
    if missing:
        print(f"[woo] GUARD: {len(missing)} orders missing email (e.g. {missing[:5]}); "
              f"Windsor dropped billing__email - keeping existing wc_orders.json ({prev_n})")
        return
    # GUARD 3: WooCommerce orders only ever grow; a smaller count is a partial pull.
    if prev_n and len(new) < prev_n:
        print(f"[woo] GUARD: candidate {len(new)} < current {prev_n} orders; "
              f"refusing to shrink - keeping existing wc_orders.json")
        return
    (HERE / "wc_orders.json").write_text(json.dumps(new, indent=1))
    print(f"[woo] wrote wc_orders.json with {len(new)} real orders (was {prev_n}; all have email)")

# ---------------- 3) WOOCOMMERCE coupon lines -> wc_coupons.json ----------------
def fetch_coupons():
    coupon_fields = ["orders__id","orders__status","orders__coupon_lines__code",
                     "orders__coupon_lines__discount"]
    wc = windsor("woocommerce", coupon_fields, date_from="2025-01-01", date_to=TODAY)
    coupons = []
    for r in wc:
        if not is_real_order(r):
            continue
        code = r.get("orders__coupon_lines__code")
        if not code:
            continue
        coupons.append({"id": str(r.get("orders__id")), "code": code,
                        "discount": float(r.get("orders__coupon_lines__discount") or 0)})
    prev = _prev_json("wc_coupons.json")
    prev_n = len(prev) if prev is not None else 0
    # GUARD: don't clobber a populated coupon file with an empty pull.
    if not coupons and prev_n:
        print(f"[woo] GUARD: 0 coupon lines returned but existing file has {prev_n}; "
              f"keeping existing wc_coupons.json")
        return
    (HERE / "wc_coupons.json").write_text(json.dumps(coupons, indent=1))
    print(f"[woo] wrote wc_coupons.json with {len(coupons)} coupon lines (was {prev_n})")

# attempt the core sources so one run surfaces every issue, then fail if any errored
errors = []
for name, fn in [("googlesheets", fetch_sheet), ("woocommerce/orders", fetch_orders),
                 ("woocommerce/coupons", fetch_coupons)]:
    try:
        fn()
    except Exception as e:
        print(f"!! FAILED [{name}]: {e}")
        errors.append(name)
# Meta spend is supplementary (feeds cost-per-package); never let it block the dashboard.
try:
    fetch_meta()
except Exception as e:
    print(f"!! WARN [facebook/meta]: {e} (keeping previous meta_spend.json)")
if errors:
    sys.exit(f"fetch_cloud failed for: {', '.join(errors)}")

# ---------------- FINAL INVARIANT CHECK (defense in depth) ----------------
# Even if a guard is bypassed, never let the pipeline proceed with data that would publish
# a dashboard missing CAC or YTD. Fail loudly so the daily job keeps the last good site
# instead of committing a broken one.
def _final_sanity():
    problems = []
    yr = str(dt.date.today().year)
    csv_rows = _prev_csv_data("orders_raw.csv") or []
    if not csv_rows:
        problems.append("orders_raw.csv is empty")
    elif not any(row.split(",", 1)[0].endswith(yr) for row in csv_rows):  # date is MM-DD-YYYY
        problems.append(f"orders_raw.csv has no {yr} rows - YTD would be blank")
    wo = _prev_json("wc_orders.json") or []
    if not wo:
        problems.append("wc_orders.json is empty - CAC would be blank")
    else:
        no_email = [o.get("id") for o in wo if not (o.get("email") or "").strip()]
        if no_email:
            problems.append(f"{len(no_email)} wc_orders rows missing email - CAC would be blank")
    return problems

_problems = _final_sanity()
if _problems:
    sys.exit("fetch_cloud sanity check FAILED (not publishing): " + "; ".join(_problems))
print("fetch_cloud done.")
