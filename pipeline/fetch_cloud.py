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
import os, sys, csv, json, datetime as dt, urllib.parse, urllib.request, pathlib

HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://connectors.windsor.ai"
API_KEY = os.environ.get("WINDSOR_API_KEY", "").strip()
if not API_KEY:
    sys.exit("ERROR: WINDSOR_API_KEY env var is not set (add it as a GitHub repo secret).")

def windsor(connector, fields, **params):
    """Call the Windsor data API for one connector and return a list of row dicts."""
    q = {"api_key": API_KEY, "fields": ",".join(fields), "_renderer": "json"}
    q.update({k: v for k, v in params.items() if v is not None})
    url = f"{BASE}/{connector}?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if isinstance(payload, dict):
        if "error" in payload and payload["error"]:
            sys.exit(f"ERROR from Windsor ({connector}): {payload['error']}")
        rows = payload.get("data", payload.get("rows", []))
    else:
        rows = payload
    if not isinstance(rows, list):
        sys.exit(f"ERROR: unexpected Windsor response shape for {connector}: {type(rows)}")
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

def clean_money(v):
    return (v or "").replace("€", "").replace("EUR", "").replace(",", "").strip()

# ---------------- 1) GOOGLE SHEET -> orders_raw.csv ----------------
sheet_fields = ["date", "#_of_packages", "order_value_(incl._shipping)", "country"]
sheet = windsor("googlesheets", sheet_fields)
rows_out = ["date,packages,value,country"]
kept = 0
for row in sheet:
    date = (row.get("date") or "").strip()
    pk = (row.get("#_of_packages") or "").strip()
    val = clean_money(row.get("order_value_(incl._shipping)"))
    ctry = to_code(row.get("country"))
    if not date:
        continue
    if val == "" and ctry == "":      # skip empty future-date placeholder rows
        continue
    if pk in ("", "0") and val == "" and ctry == "":
        continue
    rows_out.append(f"{date},{pk},{val},{ctry}")
    kept += 1
(HERE / "orders_raw.csv").write_text("\n".join(rows_out) + "\n")
print(f"[sheet] wrote orders_raw.csv with {kept} order rows")

# ---------------- 2) WOOCOMMERCE orders -> wc_orders.json ----------------
TODAY = dt.date.today().isoformat()
order_fields = ["orders__id","orders__status","orders__date_created","orders__total",
                "orders__discount_total","orders__billing__country"]
wo = windsor("woocommerce", order_fields, date_from="2025-01-01", date_to=TODAY)
seen = {}
for r in wo:
    if (r.get("orders__status") or "").strip() != "completed":
        continue
    oid = str(r.get("orders__id"))
    seen[oid] = {           # dedupe by id (scalar fetch should already be 1 row/order)
        "id": oid,
        "date": r.get("orders__date_created"),
        "total": float(r.get("orders__total") or 0),
        "discount_total": float(r.get("orders__discount_total") or 0),
        "country": (r.get("orders__billing__country") or "").strip(),
    }
wc_orders = list(seen.values())
(HERE / "wc_orders.json").write_text(json.dumps(wc_orders, indent=1))
print(f"[woo] wrote wc_orders.json with {len(wc_orders)} completed orders")

# ---------------- 3) WOOCOMMERCE coupon lines -> wc_coupons.json ----------------
coupon_fields = ["orders__id","orders__status","orders__coupon_lines__code",
                 "orders__coupon_lines__discount"]
wc = windsor("woocommerce", coupon_fields, date_from="2025-01-01", date_to=TODAY)
coupons = []
for r in wc:
    if (r.get("orders__status") or "").strip() != "completed":
        continue
    code = r.get("orders__coupon_lines__code")
    if not code:
        continue
    coupons.append({
        "id": str(r.get("orders__id")),
        "code": code,
        "discount": float(r.get("orders__coupon_lines__discount") or 0),
    })
(HERE / "wc_coupons.json").write_text(json.dumps(coupons, indent=1))
print(f"[woo] wrote wc_coupons.json with {len(coupons)} coupon lines")
print("fetch_cloud done.")
