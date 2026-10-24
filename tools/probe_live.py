"""يراقب مباريات الدوري الإنجليزي الجارية (live=39) كل دقيقتين ويسجّل تغيّر النتيجة. لا يطبع المفتاح."""
import json, os, sys, time, urllib.request, datetime

KEY = os.environ.get("API_FOOTBALL_KEY", "")
URL = "https://v3.football.api-sports.io/fixtures?live=39"
DURATION = int(os.environ.get("PROBE_MINUTES", "100"))
EVERY = 120
out, last, lineup_done = [], {}, set()


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")


def log(s):
    print(s, flush=True)
    out.append(s)


if not KEY:
    log("لا يوجد مفتاح")
    sys.exit(1)

end = time.time() + DURATION * 60
polls = 0
while time.time() < end:
    polls += 1
    try:
        req = urllib.request.Request(URL, headers={"x-apisports-key": KEY})
        with urllib.request.urlopen(req, timeout=30) as r:
            b = json.loads(r.read().decode())
            rem = r.headers.get("x-ratelimit-requests-remaining")
    except Exception as e:
        log(f"{now()} خطأ: {str(e)[:120]}")
        time.sleep(EVERY)
        continue
    if b.get("errors"):
        log(f"{now()} errors={b['errors']}")
    res = b.get("response") or []
    if polls == 1:
        log(f"{now()} أول استعلام: مباريات الدوري الجارية={len(res)} المتبقي اليوم={rem}")
    for f in res:
        fid = f["fixture"]["id"]
        g = f.get("goals", {})
        st = (g.get("home"), g.get("away"), f["fixture"]["status"]["short"])
        if fid not in lineup_done:
            lineup_done.add(fid)
            try:
                rq = urllib.request.Request(f"https://v3.football.api-sports.io/fixtures/lineups?fixture={fid}", headers={"x-apisports-key": KEY})
                with urllib.request.urlopen(rq, timeout=30) as r2:
                    lb = json.loads(r2.read().decode())
                lr = lb.get("response") or []
                info = [(x.get("team", {}).get("name"), x.get("formation"), len(x.get("startXI") or []), (x.get("startXI") or [{}])[0].get("player", {}).get("grid")) for x in lr]
                log(f"{now()} تشكيلة fixture={fid}: errors={lb.get('errors')} {info}")
            except Exception as e:
                log(f"{now()} تشكيلة خطأ: {str(e)[:120]}")
        if last.get(fid) != st:
            log(f"{now()} {f['teams']['home']['name']} {g.get('home')}-{g.get('away')} {f['teams']['away']['name']} دقيقة={f['fixture']['status']['elapsed']} حالة={st[2]} أحداث_في_الرد={len(f.get('events') or [])}")
            last[fid] = st
    time.sleep(EVERY)
log(f"{now()} انتهى بعد {polls} استعلاماً، المتبقي اليوم={rem}")
open("probe_live_result.txt", "w", encoding="utf-8").write("\n".join(out))
