"""فحص لمرة واحدة: ماذا تتيح باقة API-Football المجانية؟ لا يطبع المفتاح أبداً."""
import json, os, sys, urllib.request, urllib.parse

KEY = os.environ.get("API_FOOTBALL_KEY", "")
BASE = "https://v3.football.api-sports.io"
out = []


def call(path, **params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode())
            rem = r.headers.get("x-ratelimit-requests-remaining")
            return body, rem
    except Exception as e:
        return {"exception": str(e)[:200]}, None


def log(s):
    print(s)
    out.append(s)


if not KEY:
    log("لا يوجد مفتاح في السر API_FOOTBALL_KEY")
    sys.exit(1)

b, rem = call("/status")
r = b.get("response") or {}
if isinstance(r, dict):
    log(f"[status] plan={r.get('subscription',{}).get('plan')} active={r.get('subscription',{}).get('active')} requests={r.get('requests')}")
log(f"[status] errors={b.get('errors')} exc={b.get('exception')}")

b, _ = call("/leagues", id=39)
for L in (b.get("response") or [])[:1]:
    for s in L.get("seasons", [])[-3:]:
        cov = s.get("coverage", {})
        log(f"[leagues] season={s['year']} current={s['current']} fixtures_events={cov.get('fixtures',{}).get('events')} standings={cov.get('standings')}")
log(f"[leagues] errors={b.get('errors')} exc={b.get('exception')}")

for season in (2026, 2025):
    b, rem = call("/fixtures", league=39, season=season, next=3)
    res = b.get("response") or []
    log(f"[next season={season}] count={len(res)} errors={b.get('errors')} exc={b.get('exception')}")
    for f in res[:3]:
        log(f"   {f['fixture']['date']} {f['teams']['home']['name']} v {f['teams']['away']['name']} status={f['fixture']['status']['short']}")

b, rem = call("/fixtures", league=39, season=2026, last=3)
res = b.get("response") or []
log(f"[last season=2026] count={len(res)} errors={b.get('errors')}")
fid = None
for f in res[:3]:
    g = f.get("goals", {})
    log(f"   {f['teams']['home']['name']} {g.get('home')}-{g.get('away')} {f['teams']['away']['name']} status={f['fixture']['status']['short']}")
    fid = fid or f['fixture']['id']

b, rem = call("/fixtures", live="all")
res = b.get("response") or []
pl = [f for f in res if f.get("league", {}).get("id") == 39]
log(f"[live=all] total_live={len(res)} premier_league_live={len(pl)} errors={b.get('errors')} exc={b.get('exception')}")
for f in pl:
    g = f.get("goals", {})
    log(f"   LIVE {f['teams']['home']['name']} {g.get('home')}-{g.get('away')} {f['teams']['away']['name']} min={f['fixture']['status']['elapsed']} events_in_payload={len(f.get('events') or [])}")
if res and not pl:
    f = res[0]
    log(f"   (مثال مباراة جارية من دوري آخر) events_in_payload={len(f.get('events') or [])} keys={sorted(f.keys())}")

if fid:
    b, rem = call("/fixtures/events", fixture=fid)
    log(f"[events fixture] count={len(b.get('response') or [])} errors={b.get('errors')}")

b, rem = call("/status")
r = b.get("response") or {}
if isinstance(r, dict):
    log(f"[status after] requests={r.get('requests')}")

open("probe_result.txt", "w", encoding="utf-8").write("\n".join(out))
