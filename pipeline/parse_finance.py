#!/usr/bin/env python3
"""Parse the order log + WooCommerce coupon overlay -> finance_data.json.

HYBRID source of truth (decided Jun 2026):
  * Core metrics (orders, revenue, AOV, units, pack mix, countries, KPI targets)
    come from orders_raw.csv, which the daily task overwrites from the shared
    Google Sheet. The sheet is authoritative because it also captures offline /
    wholesale orders that never pass through WooCommerce checkout.
  * Coupon metrics (coupon orders, redemptions, discount given, coupon revenue,
    top codes) come from WooCommerce via Windsor.ai, written next to this script as
    wc_orders.json + wc_coupons.json by the daily fetch step. WooCommerce is the
    only place coupon usage is recorded.

orders_raw.csv : date,packages,value,country   (date MM-DD-YYYY; blank value -> skipped)
wc_orders.json : [{id, date(ISO), total, discount_total, country}]  completed orders
wc_coupons.json: [{id, code, discount}]                              one row per coupon line

Money rounded to 2 decimals. Never invents numbers.
"""
import csv, json, datetime as dt, pathlib, collections
HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "orders_raw.csv"

# ============ CORE METRICS FROM THE ORDER LOG (SHEET) ============
orders=[]; blanks=0
with open(SRC, newline="") as f:
    rd=csv.reader(f); next(rd, None)
    for row in rd:
        if not row or not row[0].strip(): continue
        d=row[0].strip(); pk=(row[1] if len(row)>1 else "").strip()
        val=(row[2] if len(row)>2 else "").strip(); ctry=(row[3] if len(row)>3 else "").strip()
        try: date=dt.datetime.strptime(d,"%m-%d-%Y").date()
        except ValueError: continue
        v=val.replace("€","").replace("EUR","").replace(",","").strip()
        if v=="":
            blanks+=1; continue
        orders.append((date, int(pk) if pk.isdigit() else 0, float(v), ctry))

def agg(key):
    b={}
    for date,pk,rev,ctry in orders:
        e=b.setdefault(key(date),{"orders":0,"rev":0.0,"units":0})
        e["orders"]+=1; e["rev"]+=rev; e["units"]+=pk
    return b
m=agg(lambda d:(d.year,d.month))
w=agg(lambda d:d-dt.timedelta(days=d.weekday()))

# ============ COUPON OVERLAY FROM WOOCOMMERCE ============
def load_opt(name):
    p=HERE/name
    return json.loads(p.read_text()) if p.exists() else []

wc_orders=load_opt("wc_orders.json")
wc_coupons=load_opt("wc_coupons.json")
ord_by_id={o["id"]:o for o in wc_orders}
coup_by_order=collections.defaultdict(list)
for c in wc_coupons:
    coup_by_order[c["id"]].append(c)

# coupon orders = WooCommerce orders carrying >=1 coupon line
cm=collections.defaultdict(lambda:{"cOrders":0,"cDisc":0.0,"cRev":0.0})  # by (year,month)
cw=collections.defaultdict(lambda:{"cOrders":0,"cDisc":0.0,"cRev":0.0})  # by week start
c_orders=c_apps=0; c_disc=c_rev=0.0
by_code=collections.defaultdict(lambda:{"uses":0,"discount":0.0,"revenue":0.0})
for oid,lines in coup_by_order.items():
    o=ord_by_id.get(oid)
    if not o: continue
    try: date=dt.datetime.fromisoformat(o["date"]).date()
    except (ValueError,KeyError): continue
    rev=float(o.get("total") or 0); disc=float(o.get("discount_total") or 0)
    c_orders+=1; c_apps+=len(lines); c_disc+=disc; c_rev+=rev
    km=(date.year,date.month); cm[km]["cOrders"]+=1; cm[km]["cDisc"]+=disc; cm[km]["cRev"]+=rev
    kw=date-dt.timedelta(days=date.weekday()); cw[kw]["cOrders"]+=1; cw[kw]["cDisc"]+=disc; cw[kw]["cRev"]+=rev
    seen=set()
    for cl in lines:
        code=cl.get("code") or "?"
        by_code[code]["uses"]+=1
        by_code[code]["discount"]+=float(cl.get("discount") or 0)
        if code not in seen:
            by_code[code]["revenue"]+=rev; seen.add(code)
topCoupons=sorted(
    ({"code":k,"uses":v["uses"],"discount":round(v["discount"],2),"revenue":round(v["revenue"],2)}
     for k,v in by_code.items()), key=lambda x:(-x["uses"],-x["revenue"]))
wc_total_discount=round(sum(float(o.get("discount_total") or 0) for o in wc_orders),2)

# ============ MONTHLY / WEEKLY (core + coupon overlay) ============
def fill_months(b):
    ks=sorted(b); out=[]; y,mo=ks[0]; ey,em=ks[-1]
    while (y,mo)<=(ey,em):
        e=b.get((y,mo),{"orders":0,"rev":0.0,"units":0})
        c=cm.get((y,mo),{"cOrders":0,"cDisc":0.0,"cRev":0.0})
        out.append({"label":dt.date(y,mo,1).strftime("%b %Y"),"orders":e["orders"],
                    "revenue":round(e["rev"],2),"units":e["units"],
                    "aov":round(e["rev"]/e["orders"],2) if e["orders"] else 0,
                    "couponOrders":c["cOrders"],"couponDiscount":round(c["cDisc"],2),
                    "couponRevenue":round(c["cRev"],2)})
        mo+=1
        if mo>12: mo=1; y+=1
    return out
def fill_weeks(b):
    ks=sorted(b); out=[]; cur=ks[0]; end=ks[-1]
    while cur<=end:
        e=b.get(cur,{"orders":0,"rev":0.0,"units":0})
        c=cw.get(cur,{"cOrders":0,"cDisc":0.0,"cRev":0.0})
        out.append({"label":cur.strftime("%d %b %y"),"weekStart":cur.isoformat(),
                    "orders":e["orders"],"revenue":round(e["rev"],2),"units":e["units"],
                    "aov":round(e["rev"]/e["orders"],2) if e["orders"] else 0,
                    "couponOrders":c["cOrders"],"couponDiscount":round(c["cDisc"],2),
                    "couponRevenue":round(c["cRev"],2)})
        cur+=dt.timedelta(days=7)
    return out
monthly=fill_months(m); weekly=fill_weeks(w)
tot_rev=sum(o[2] for o in orders); tot_ord=len(orders); tot_units=sum(o[1] for o in orders)

# ============ PACK MIX ============
OCT=dt.date(2025,10,1); ones=threes=tens=others=0
for date,pk,rev,ctry in orders:
    n=pk
    if date>=OCT:
        if n%10==0: tens+=n//10
        elif n%3==0: threes+=n//3
        elif n==1: ones+=1
        else: others+=1
    else:
        if n==1: ones+=1
        elif n==3: threes+=1
        elif n==10: tens+=1
        else: others+=1
packMix={"ones":ones,"threes":threes,"tens":tens,"others":others}

# ============ COUNTRIES ============
cc={}
for date,pk,rev,ctry in orders:
    e=cc.setdefault(ctry,{"orders":0,"rev":0.0}); e["orders"]+=1; e["rev"]+=rev
countryOrders={k:{"orders":v["orders"],"revenue":round(v["rev"],2)} for k,v in cc.items()}

# ============ COUPON SUMMARY BLOCK ============
coupons={
    "orders":c_orders,
    "applications":c_apps,
    "discountGiven":round(c_disc,2),
    "revenue":round(c_rev,2),
    "pctOrders":round(c_orders/tot_ord*100,2) if tot_ord else 0,
    "pctRevenue":round(c_rev/tot_rev*100,2) if tot_rev else 0,
    "savingsRate":round(c_disc/(c_rev+c_disc)*100,2) if (c_rev+c_disc) else 0,
    "topCoupons":topCoupons,
    "totalDiscountAllOrders":wc_total_discount,
    "source":"woocommerce",
}

# ============ KPI MONTHLY TARGETS ============
mn={"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
targets_raw=[("Jun",217,2554),("Jul",250,2937),("Aug",287,3378),("Sep",331,3885),
             ("Oct",380,4468),("Nov",437,5138),("Dec",503,5909)]
kpis=[]
for nm,to,tr in targets_raw:
    e=m.get((2026,mn[nm]),{"orders":0,"rev":0.0,"units":0})
    kpis.append({"month":nm+" 2026","tPieces":to,"tRev":round(float(tr),2),
                 "aPieces":e["units"],"aRev":round(e["rev"],2)})

data={"monthly":monthly,"weekly":weekly,
      "totals":{"orders":tot_ord,"revenue":round(tot_rev,2),"units":tot_units,
                "aov":round(tot_rev/tot_ord,2) if tot_ord else 0},
      "packMix":packMix,"countryOrders":countryOrders,"kpis":kpis,
      "coupons":coupons,"blanksExcluded":blanks,"source":"sheet+woocommerce_coupons"}
(HERE/"finance_data.json").write_text(json.dumps(data,indent=1))
print(f"[orders/sheet] orders={tot_ord} revenue={round(tot_rev,2)} units={tot_units} blanks={blanks} "
      f"months={len(monthly)} weeks={len(weekly)} packMix={packMix}")
print(f"[coupons/woo]  orders={c_orders} apps={c_apps} discountGiven={round(c_disc,2)} "
      f"couponRevenue={round(c_rev,2)} topCoupon={topCoupons[0] if topCoupons else None}")
