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

# ============ UNIT ECONOMICS (cost per package + discount per order) ============
# Cost per package = total marketing spend / packages(units), per month and overall, since Jan 2026.
# Marketing spend = Meta ad spend (meta_spend.json, pulled from Windsor) + influencer overlay.
meta_raw=load_opt("meta_spend.json")            # [{"month":"2026-01","spend":123.45}, ...]
meta_by_month={r["month"]:float(r.get("spend") or 0) for r in meta_raw if r.get("month")}
meta_available=any(v>0 for v in meta_by_month.values())
# Influencer spend paid directly (not captured by any ad platform), EUR per month.
INFLUENCER={"2026-03":500.0,"2026-04":500.0,"2026-05":500.0,"2026-06":500.0}

# Customers = distinct billing emails on completed WooCommerce orders (deduped), per month.
# Internal / test addresses are excluded so they don't inflate the customer count.
CUST_EXCLUDE_DOMAINS={"webgate.digital"}
CUST_EXCLUDE_EMAILS={"misko.farkas@gmail.com"}
def _keep_email(e):
    e=(e or "").strip().lower()
    if not e or e in CUST_EXCLUDE_EMAILS: return False
    return e.split("@")[-1] not in CUST_EXCLUDE_DOMAINS
cust_by_month=collections.defaultdict(set)
for o in wc_orders:
    d=str(o.get("date") or ""); e=o.get("email")
    if d[:4]<"2026" or not _keep_email(e): continue
    cust_by_month[d[:7]].add(e.strip().lower())

# every month since Jan 2026 that has customers, plus any month carrying spend
all_keys=sorted(k for k in (set(cust_by_month)|set(meta_by_month)|set(INFLUENCER)) if k>="2026-01")
# CAC = marketing spend / unique customers. Shown two ways: excl. and incl. influencer cost.
cac_months=[]; tot_meta=0.0; tot_infl=0.0; all_customers=set()
for k in all_keys:
    y,mo=int(k[:4]),int(k[5:7])
    custset=cust_by_month.get(k,set()); nc=len(custset)
    meta=round(meta_by_month.get(k,0.0),2); infl=INFLUENCER.get(k,0.0)
    spend=round(meta+infl,2)
    cac_months.append({"label":dt.date(y,mo,1).strftime("%b %Y"),"customers":nc,
                       "metaSpend":meta,"influencer":round(infl,2),"totalSpend":spend,
                       "cacExInfluencer":round(meta/nc,2) if nc else None,
                       "cacInclInfluencer":round(spend/nc,2) if nc else None})
    tot_meta+=meta; tot_infl+=infl; all_customers|=custset
tot_spend=round(tot_meta+tot_infl,2); tot_cust=len(all_customers)
wc_order_count=len(wc_orders)
# discount as % of gross (gross = net total + discount), aggregate across orders
wc_net_total=sum(float(o.get("total") or 0) for o in wc_orders)
wc_gross_all=wc_net_total+wc_total_discount
unitEcon={
    "sinceLabel":"Jan 2026",
    "metaSpendAvailable":meta_available,
    "cac":cac_months,
    "overall":{"customers":tot_cust,"metaSpend":round(tot_meta,2),"influencer":round(tot_infl,2),
               "totalSpend":tot_spend,
               "cacExInfluencer":round(tot_meta/tot_cust,2) if tot_cust else None,
               "cacInclInfluencer":round(tot_spend/tot_cust,2) if tot_cust else None},
    # Avg discount across ALL completed WooCommerce orders (offline/wholesale carry none).
    "avgDiscountPerOrder":round(wc_total_discount/wc_order_count,2) if wc_order_count else 0,
    "discountPctPerOrder":round(wc_total_discount/wc_gross_all*100,2) if wc_gross_all else 0,
    "wcOrders":wc_order_count,
    "totalDiscount":wc_total_discount,
    # Avg discount narrowed to orders that actually used a coupon.
    "avgDiscountPerCouponOrder":round(c_disc/c_orders,2) if c_orders else 0,
    "discountPctPerCouponOrder":round(c_disc/(c_rev+c_disc)*100,2) if (c_rev+c_disc) else 0,
    "couponOrders":c_orders,
    "source":"sheet(packages)+woocommerce(discounts)",
}

# ============ PACK MIX ============
# Every order is attributed to 1/3/10 pack-equivalents (Afterglow only sells
# 1/3/10-packs): multiples of 10 count as that many 10-packs, other multiples
# of 3 as that many 3-packs, and any other size splits greedily into 10s, then
# 3s, then singles. e.g. 13 = 10+3, 25 = 10+10+3+1+1, 76 = 7x10+2x3, 24 = 8x3,
# 5 = 3+1+1, 2 = 1+1. This also covers the pre-Oct 2025 non-standard sizes that
# used to sit in "others"; others is kept for schema compatibility and is 0.
THIS_YEAR=dt.date.today().year
def pack_mix(rows):
    ones=threes=tens=0
    for date,pk,rev,ctry in rows:
        n=pk
        if n<=0: continue
        if n%10==0: tens+=n//10
        elif n%3==0: threes+=n//3
        elif n==1: ones+=1
        else:
            t=n//10; r=n-10*t
            th=r//3; r2=r-3*th
            tens+=t; threes+=th; ones+=r2
    return {"ones":ones,"threes":threes,"tens":tens,"others":0}
packMix=pack_mix(orders)
packMixYtd=pack_mix([o for o in orders if o[0].year==THIS_YEAR])

# ============ YTD TOTALS (current calendar year) ============
ytd=[o for o in orders if o[0].year==THIS_YEAR]
ytd_rev=sum(o[2] for o in ytd); ytd_ord=len(ytd); ytd_units=sum(o[1] for o in ytd)
totalsYtd={"year":THIS_YEAR,"orders":ytd_ord,"revenue":round(ytd_rev,2),"units":ytd_units,
           "aov":round(ytd_rev/ytd_ord,2) if ytd_ord else 0}

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
targets_raw=[("Jun",217,2554),("Jul",147,1732.56),("Aug",162,1905.81),("Sep",178,2096.39),
             ("Oct",196,2306.03),("Nov",216,2536.64),("Dec",237,2790.30)]
kpis=[]
for nm,to,tr in targets_raw:
    e=m.get((2026,mn[nm]),{"orders":0,"rev":0.0,"units":0})
    kpis.append({"month":nm+" 2026","tPieces":to,"tRev":round(float(tr),2),
                 "aPieces":e["units"],"aRev":round(e["rev"],2)})

data={"monthly":monthly,"weekly":weekly,
      "totals":{"orders":tot_ord,"revenue":round(tot_rev,2),"units":tot_units,
                "aov":round(tot_rev/tot_ord,2) if tot_ord else 0},
      "totalsYtd":totalsYtd,
      "packMix":packMix,"packMixYtd":packMixYtd,"countryOrders":countryOrders,"kpis":kpis,
      "coupons":coupons,"unitEcon":unitEcon,"blanksExcluded":blanks,"source":"sheet+woocommerce_coupons"}
(HERE/"finance_data.json").write_text(json.dumps(data,indent=1))
print(f"[orders/sheet] orders={tot_ord} revenue={round(tot_rev,2)} units={tot_units} blanks={blanks} "
      f"months={len(monthly)} weeks={len(weekly)} packMix={packMix}")
print(f"[coupons/woo]  orders={c_orders} apps={c_apps} discountGiven={round(c_disc,2)} "
      f"couponRevenue={round(c_rev,2)} topCoupon={topCoupons[0] if topCoupons else None}")
