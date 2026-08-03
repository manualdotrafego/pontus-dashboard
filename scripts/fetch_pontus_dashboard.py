#!/usr/bin/env python3
"""
Fetch dashboard data for NBP - Gui Pontus (act_1772556290384735).

Filters campaigns whose name contains "inlead".
Funnel events (Meta Pixel):
  PageView          → landing_page_view
  AddToCart         → offsite_conversion.fb_pixel_add_to_cart
  Contact           → offsite_conversion.fb_pixel_contact
  CompleteReg.      → offsite_conversion.fb_pixel_complete_registration
  Lead (final)      → offsite_conversion.fb_pixel_lead

Output: data_pontus.json (consumed by dashboard_pontus.html).
"""

import os, json, requests, time, re, html as html_mod
from datetime import datetime, date, timedelta, timezone
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*a, **k): pass

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

TOKEN  = os.getenv("META_ACCESS_TOKEN")
BASE   = "https://graph.facebook.com/v21.0"
ACCT   = {"id": "1772556290384735", "name": "NBP - Gui Pontus", "currency": "BRL"}
# Vazio = todas as campanhas da conta. Antes era "inlead", o que deixava de fora
# campanhas novas como "[LEAD - PONTUS] - [SPRINT DE CARTEIRA]".
FILTER = ""
OUT    = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

# Fetch window: from campaign start (or 30 days ago, whichever is later) to today
LOOKBACK_DAYS = 30
SINCE = (date.today() - timedelta(days=LOOKBACK_DAYS - 1)).strftime("%Y-%m-%d")
UNTIL = date.today().strftime("%Y-%m-%d")
TIME_RANGE = json.dumps({"since": SINCE, "until": UNTIL})

# ── Pixel mapping ──────────────────────────────────────────────────────────
PIXEL = {
    "page_view":     "landing_page_view",                                 # Meta LP view = PageView equivalent
    "add_to_cart":   "offsite_conversion.fb_pixel_add_to_cart",
    "contact":       "offsite_conversion.fb_pixel_contact",
    "complete_reg":  "offsite_conversion.fb_pixel_complete_registration",
    "lead":          "offsite_conversion.fb_pixel_lead",
}

# ── HTTP helpers ───────────────────────────────────────────────────────────

def get(path, params=None):
    p = {"access_token": TOKEN}
    if params:
        p.update(params)
    r = requests.get(f"{BASE}{path}", params=p, timeout=90)
    return r.json()


def get_all(path, params):
    out = []
    resp = get(path, params)
    if "error" in resp:
        print(f"  API error: {resp['error'].get('message','?')[:120]}")
        return out
    out.extend(resp.get("data", []))
    while resp.get("paging", {}).get("next"):
        try:
            r = requests.get(resp["paging"]["next"], timeout=90)
            resp = r.json()
            out.extend(resp.get("data", []))
        except Exception as e:
            print(f"  paging err: {e}")
            break
    return out


# ── Parsers ────────────────────────────────────────────────────────────────

def parse_actions(row):
    """Return funnel-event counts + cost-per for the 5 pixel events."""
    counts = {k: 0 for k in PIXEL}
    for a in row.get("actions", []) or []:
        t = a.get("action_type")
        v = int(float(a.get("value", 0) or 0))
        for key, target in PIXEL.items():
            if t == target:
                counts[key] += v

    costs = {f"cp_{k}": 0.0 for k in PIXEL}
    for c in row.get("cost_per_action_type", []) or []:
        t = c.get("action_type")
        v = float(c.get("value", 0) or 0)
        for key, target in PIXEL.items():
            if t == target:
                costs[f"cp_{key}"] = round(v, 2)

    spend = float(row.get("spend", 0) or 0)
    # Backfill missing cost_per
    for k in PIXEL:
        if counts[k] > 0 and costs[f"cp_{k}"] == 0:
            costs[f"cp_{k}"] = round(spend / counts[k], 2)

    return counts, costs


def video_pct(row, field):
    v = row.get(field) or []
    if not v:
        return 0
    try:
        return int(float(v[0].get("value", 0) or 0))
    except Exception:
        return 0


def shape_metrics(row):
    """Build the metric dict (matches DevSpace data shape, adapted to Pontus funnel)."""
    spend       = float(row.get("spend", 0) or 0)
    impressions = int(row.get("impressions", 0) or 0)
    clicks      = int(row.get("clicks", 0) or 0)
    link_clicks = int(row.get("inline_link_clicks", 0) or 0)
    reach       = int(row.get("reach", 0) or 0)
    frequency   = float(row.get("frequency", 0) or 0)

    counts, costs = parse_actions(row)
    page_view    = counts["page_view"]
    add_to_cart  = counts["add_to_cart"]
    contact      = counts["contact"]
    complete_reg = counts["complete_reg"]
    leads        = counts["lead"]   # "leads" = final Lead pixel

    v25  = video_pct(row, "video_p25_watched_actions")
    v50  = video_pct(row, "video_p50_watched_actions")
    v75  = video_pct(row, "video_p75_watched_actions")
    v100 = video_pct(row, "video_p100_watched_actions")

    cpm = round(spend / impressions * 1000, 2) if impressions else 0
    cpc = round(spend / clicks, 2) if clicks else 0
    cpl = round(spend / leads, 2) if leads else 0

    # Funnel rates (always vs preceding step where it makes sense)
    connect_rate = round(page_view / link_clicks * 100, 1) if link_clicks else 0   # PV/LinkClick
    atc_rate     = round(add_to_cart / page_view * 100, 1) if page_view else 0      # ATC/PV
    contact_rate = round(contact / add_to_cart * 100, 1) if add_to_cart else 0      # Contact/ATC
    creg_rate    = round(complete_reg / contact * 100, 1) if contact else 0         # CReg/Contact
    lead_rate    = round(leads / complete_reg * 100, 1) if complete_reg else 0      # Lead/CReg
    lp_conv      = round(leads / page_view * 100, 1) if page_view else 0            # Lead/PV
    hook_rate    = round(v25 / impressions * 100, 1) if impressions else 0          # VP25/Impr (same as DevSpace)

    # Video rates (% of impressions)
    def vpct(x):
        return round(x / impressions * 100, 1) if impressions else 0

    return {
        "spend":        round(spend, 2),
        "impressions":  impressions,
        "clicks":       clicks,
        "link_clicks":  link_clicks,
        "reach":        reach,
        "frequency":    round(frequency, 2),
        "cpm":          cpm,
        "cpc":          cpc,
        "cpl":          cpl,

        # Funnel events
        "page_view":    page_view,
        "add_to_cart":  add_to_cart,
        "contact":      contact,
        "complete_reg": complete_reg,
        "leads":        leads,

        # Cost per funnel step
        "cp_page_view":    costs["cp_page_view"],
        "cp_add_to_cart":  costs["cp_add_to_cart"],
        "cp_contact":      costs["cp_contact"],
        "cp_complete_reg": costs["cp_complete_reg"],
        "cp_lead":         costs["cp_lead"],

        # Funnel rates
        "connect_rate": connect_rate,
        "atc_rate":     atc_rate,
        "contact_rate": contact_rate,
        "creg_rate":    creg_rate,
        "lead_rate":    lead_rate,
        "lp_conv":      lp_conv,
        "hook_rate":    hook_rate,

        # Video retention
        "vp25":  vpct(v25),
        "vp50":  vpct(v50),
        "vp75":  vpct(v75),
        "vp100": vpct(v100),
    }


def empty_metrics(date_str=None):
    z = {k: 0 for k in [
        "spend","impressions","clicks","link_clicks","reach","frequency",
        "cpm","cpc","cpl",
        "page_view","add_to_cart","contact","complete_reg","leads",
        "cp_page_view","cp_add_to_cart","cp_contact","cp_complete_reg","cp_lead",
        "connect_rate","atc_rate","contact_rate","creg_rate","lead_rate",
        "lp_conv","hook_rate",
        "vp25","vp50","vp75","vp100",
    ]}
    if date_str:
        z["date"] = date_str
    return z


# ── Destino do anúncio / versão da LP ──────────────────────────────────────

def extract_dest(creative):
    """Primeira URL de destino encontrada no criativo (link_data, video_data ou asset_feed)."""
    if not creative:
        return ""
    blob = json.dumps(creative, ensure_ascii=False)
    urls = re.findall(r'https?://[^"\\\s]+', blob)
    for u in urls:
        if "pontusfinance" in u or "inlead" in u:
            return u.split("?")[0]
    return urls[0].split("?")[0] if urls else ""


def lp_version(url):
    """Rotula a versão da landing page a partir da URL de destino."""
    if not url:
        return "—"
    m = re.search(r"/lp-v(\d+)", url)
    if m:
        return f"V{m.group(1)}"
    if "/lp/" in url or url.rstrip("/").endswith("/lp"):
        return "LP antiga"
    if "inlead" in url:
        return "Inlead direto"
    return "Outro"


# ── Aggregator ─────────────────────────────────────────────────────────────

SUMS  = ["spend","impressions","clicks","link_clicks","reach",
         "page_view","add_to_cart","contact","complete_reg","leads"]
VAVG  = ["vp25","vp50","vp75","vp100","frequency"]   # weighted by impressions


def aggregate(rows):
    """Aggregate a list of metric dicts (sums for counts, weighted avgs for rates)."""
    out = {k: 0 for k in SUMS}
    for r in rows:
        for k in SUMS:
            out[k] += r.get(k, 0)

    impr = out["impressions"]
    spend = out["spend"]
    leads = out["leads"]
    pv    = out["page_view"]
    atc   = out["add_to_cart"]
    contact = out["contact"]
    creg  = out["complete_reg"]
    lc    = out["link_clicks"]
    clk   = out["clicks"]

    # Weighted avgs for video/freq
    for k in VAVG:
        s = sum((r.get(k, 0) or 0) * (r.get("impressions", 0) or 0) for r in rows)
        out[k] = round(s / impr, 2) if impr else 0

    out["spend"]   = round(spend, 2)
    out["cpm"]     = round(spend / impr * 1000, 2) if impr else 0
    out["cpc"]     = round(spend / clk, 2) if clk else 0
    out["cpl"]     = round(spend / leads, 2) if leads else 0

    out["cp_page_view"]    = round(spend / pv, 2)      if pv else 0
    out["cp_add_to_cart"]  = round(spend / atc, 2)     if atc else 0
    out["cp_contact"]      = round(spend / contact, 2) if contact else 0
    out["cp_complete_reg"] = round(spend / creg, 2)    if creg else 0
    out["cp_lead"]         = round(spend / leads, 2)   if leads else 0

    out["connect_rate"] = round(pv / lc * 100, 1) if lc else 0
    out["atc_rate"]     = round(atc / pv * 100, 1) if pv else 0
    out["contact_rate"] = round(contact / atc * 100, 1) if atc else 0
    out["creg_rate"]    = round(creg / contact * 100, 1) if contact else 0
    out["lead_rate"]    = round(leads / creg * 100, 1) if creg else 0
    out["lp_conv"]      = round(leads / pv * 100, 1) if pv else 0
    out["hook_rate"]    = out.get("vp25", 0)
    return out


# ── Main fetch ─────────────────────────────────────────────────────────────

def main():
    print(f"=== NBP - Gui Pontus dashboard build ===")
    print(f"Account: act_{ACCT['id']}")
    print(f"Filter:  campaign name contains '{FILTER}'")
    print(f"Window:  {SINCE} → {UNTIL}\n")

    # 1. Campaigns
    camps_raw = get_all(f"/act_{ACCT['id']}/campaigns", {
        "fields": "id,name,effective_status,objective,start_time",
        "limit": 200,
    })
    matched = [c for c in camps_raw if FILTER in c.get("name", "").lower()]
    print(f"Total campaigns: {len(camps_raw)}  ·  match '{FILTER}': {len(matched)}")
    for c in matched:
        print(f"  [{c.get('effective_status','?')}] {c['id']} | {c['name']}")
    if not matched:
        raise SystemExit("No campaigns match filter — abort.")
    camp_ids = [c["id"] for c in matched]

    INSIGHT_FIELDS = ("date_start,campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
                      "spend,impressions,clicks,inline_link_clicks,reach,frequency,cpm,ctr,"
                      "actions,cost_per_action_type,"
                      "video_p25_watched_actions,video_p50_watched_actions,"
                      "video_p75_watched_actions,video_p100_watched_actions")

    flt = json.dumps([{"field": "campaign.id", "operator": "IN", "value": camp_ids}])

    # 2. Daily insights at AD level (lets us build daily / camp / ad rollups in one pass)
    print(f"\nFetching daily ad-level insights...")
    ad_daily = get_all(f"/act_{ACCT['id']}/insights", {
        "fields":         INSIGHT_FIELDS,
        "level":          "ad",
        "time_range":     TIME_RANGE,
        "time_increment": "1",
        "filtering":      flt,
        "limit":          500,
    })
    print(f"  {len(ad_daily)} ad-day rows")

    # 3. Ad creative meta (thumbnails + status + preview + destino/LP)
    print(f"Fetching ad meta + thumbnails...")
    ads_meta = get_all(f"/act_{ACCT['id']}/ads", {
        "fields":    ("id,name,effective_status,"
                      "creative{thumbnail_url,video_id,object_story_spec,asset_feed_spec}"),
        "filtering": flt,
        "limit":     200,
    })
    thumb_map  = {}
    status_map = {}
    video_map  = {}
    dest_map   = {}   # ad_id -> URL de destino
    lp_map     = {}   # ad_id -> versão da LP ("V1", "V2", "V3", "LP antiga", "—")
    for a in ads_meta:
        cr = a.get("creative", {}) or {}
        thumb_map[a["id"]]  = cr.get("thumbnail_url", "")
        status_map[a["id"]] = a.get("effective_status", "PAUSED")
        video_map[a["id"]]  = cr.get("video_id", "")
        dest_map[a["id"]]   = extract_dest(cr)
        lp_map[a["id"]]     = lp_version(dest_map[a["id"]])

    # 4. Preview URLs (only for active ads)
    preview_map = {}
    actives = [a["id"] for a in ads_meta if status_map.get(a["id"]) == "ACTIVE"]
    print(f"Fetching previews for {len(actives)} active ads...")
    for ad_id in actives:
        prev = get(f"/{ad_id}/previews", {"ad_format": "MOBILE_FEED_STANDARD"})
        for p in prev.get("data", []) or []:
            m = re.search(r'src="([^"]+)"', p.get("body", "") or "")
            if m:
                preview_map[ad_id] = html_mod.unescape(m.group(1))
                break
        time.sleep(0.08)

    # 5. Build per-ad-day metric records
    by_ad_day  = {}        # ad_id -> [day_metric, ...]
    ad_meta    = {}        # ad_id -> {name, campaign_id, campaign_name, adset_id, adset_name}
    by_camp_day = {}       # (camp_id, date) -> list of metric dicts
    by_day_all  = {}       # date -> list of metric dicts (all matched campaigns)

    for row in ad_daily:
        ad_id   = row.get("ad_id")
        camp_id = row.get("campaign_id")
        d       = row.get("date_start")
        if not (ad_id and camp_id and d):
            continue
        m = shape_metrics(row)
        m["date"] = d
        by_ad_day.setdefault(ad_id, []).append(m)
        if ad_id not in ad_meta:
            ad_meta[ad_id] = {
                "name":          row.get("ad_name") or ad_id,
                "campaign_id":   camp_id,
                "campaign_name": row.get("campaign_name") or "",
                "adset_id":      row.get("adset_id") or "",
                "adset_name":    row.get("adset_name") or "",
            }
        by_camp_day.setdefault((camp_id, d), []).append(m)
        by_day_all.setdefault(d, []).append(m)

    # 6. Aggregate per ad
    ads_out = []
    for ad_id, days in by_ad_day.items():
        agg = aggregate(days)
        meta = ad_meta[ad_id]
        ads_out.append({
            **agg,
            "id":            ad_id,
            "name":          meta["name"],
            "campaign_id":   meta["campaign_id"],
            "campaign_name": meta["campaign_name"],
            "adset_id":      meta["adset_id"],
            "adset_name":    meta["adset_name"],
            "ad_on":         status_map.get(ad_id) == "ACTIVE",
            "thumbnail":     thumb_map.get(ad_id, ""),
            "video_id":      video_map.get(ad_id, ""),
            "preview_url":   preview_map.get(ad_id, ""),
        })
    ads_out.sort(key=lambda x: x.get("spend", 0), reverse=True)

    # 7. Aggregate per campaign + per-day timeline per campaign
    camps_out = []
    for c in matched:
        cid = c["id"]
        # all ad-day rows belonging to this campaign
        rows = [m for ad_id, days in by_ad_day.items() for m in days
                if ad_meta.get(ad_id, {}).get("campaign_id") == cid]
        if not rows:
            continue
        agg = aggregate(rows)
        # Build daily timeline for this campaign
        daily = []
        days = sorted({r["date"] for r in rows})
        for d in days:
            day_rows = [r for r in rows if r["date"] == d]
            d_agg = aggregate(day_rows)
            d_agg["date"] = d
            daily.append(d_agg)
        camps_out.append({
            **agg,
            "id":     cid,
            "name":   c["name"],
            "status": c.get("effective_status", "PAUSED"),
            "daily":  daily,
        })
    camps_out.sort(key=lambda x: x.get("spend", 0), reverse=True)

    # 7b. Aggregate per adset (com a versão da LP de destino)
    adsets_meta = get_all(f"/act_{ACCT['id']}/adsets", {
        "fields":    "id,name,effective_status,daily_budget,optimization_goal",
        "filtering": flt,
        "limit":     200,
    })
    as_status = {a["id"]: a.get("effective_status", "PAUSED") for a in adsets_meta}
    as_budget = {a["id"]: a.get("daily_budget") for a in adsets_meta}

    adsets_out = []
    for asid in {m.get("adset_id") for m in ad_meta.values() if m.get("adset_id")}:
        ad_ids = [aid for aid, m in ad_meta.items() if m.get("adset_id") == asid]
        rows   = [m for aid in ad_ids for m in by_ad_day.get(aid, [])]
        if not rows:
            continue
        agg  = aggregate(rows)
        meta = next(m for m in ad_meta.values() if m.get("adset_id") == asid)

        # versão da LP: a dos anúncios do conjunto (se divergirem, marca "misto")
        versoes = {lp_map.get(aid) for aid in ad_ids if lp_map.get(aid) and lp_map.get(aid) != "—"}
        lp = versoes.pop() if len(versoes) == 1 else ("misto" if versoes else "—")
        destino = next((dest_map.get(aid) for aid in ad_ids if dest_map.get(aid)), "")

        daily = []
        for d in sorted({r["date"] for r in rows}):
            d_agg = aggregate([r for r in rows if r["date"] == d])
            d_agg["date"] = d
            daily.append(d_agg)

        adsets_out.append({
            **agg,
            "id":            asid,
            "name":          meta.get("adset_name") or asid,
            "campaign_id":   meta.get("campaign_id", ""),
            "campaign_name": meta.get("campaign_name", ""),
            "status":        as_status.get(asid, "PAUSED"),
            "daily_budget":  (int(as_budget[asid]) / 100) if as_budget.get(asid) else None,
            "lp":            lp,
            "destino":       destino,
            "ads_count":     len(ad_ids),
            "daily":         daily,
        })
    adsets_out.sort(key=lambda x: (x["lp"], -x.get("spend", 0)))

    # 8. Daily timeline (aggregate of all matched campaigns)
    daily_out = []
    for d in sorted(by_day_all.keys()):
        d_agg = aggregate(by_day_all[d])
        d_agg["date"] = d
        daily_out.append(d_agg)

    # 9. Summary (entire window, all matched campaigns)
    summary = aggregate([m for ms in by_day_all.values() for m in ms]) if by_day_all else empty_metrics()

    # Determine effective date range (first day with spend → today)
    days_with_spend = [d["date"] for d in daily_out if d.get("spend", 0) > 0]
    eff_since = days_with_spend[0] if days_with_spend else SINCE
    eff_until = UNTIL

    out = {
        "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "account":      {"id": f"act_{ACCT['id']}", "name": ACCT["name"], "currency": ACCT["currency"]},
        "date_range":   {"since": eff_since, "until": eff_until},
        "camp_filter":  FILTER,
        "summary":      summary,
        "daily":        daily_out,
        "campaigns":    camps_out,
        "adsets":       adsets_out,
        "ads":          ads_out,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Wrote {OUT}")
    print(f"   Range: {eff_since} → {eff_until}")
    print(f"   Spend: R$ {summary['spend']:.2f}  ·  Leads: {summary['leads']}  ·  CPL: R$ {summary['cpl']:.2f}")
    print(f"   PageView: {summary['page_view']}  ATC: {summary['add_to_cart']}  Contact: {summary['contact']}  CReg: {summary['complete_reg']}  Lead: {summary['leads']}")
    print(f"   Campaigns: {len(camps_out)}  ·  Ads: {len(ads_out)}")


if __name__ == "__main__":
    main()
