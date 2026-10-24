#!/usr/bin/env python3
"""يبني توقعات مباريات الدوري الإنجليزي القادمة ويصدرها إلى data.json.

- التاريخ: footballcsv (1992-93 → 2019-20) ثم openfootball (2020-21 → اليوم). كلاهما CC0.
- النموذج: مزيج Elo + هجوم/دفاع (بواسون) بنفس المعاملات المختارة في الاختبار الرجعي.
- محاكاة مونت كارلو للمواسم المتبقية لاحتمالات اللقب/دوري الأبطال/الهبوط.
"""
import json, math, os, random, re, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backtest as bt
import fd
import whatif as W

OF = os.environ.get("OF_DIR", os.path.join(HERE, "..", "openfootball", "england"))
OUT = os.environ.get("OUT_JSON", os.path.join(HERE, "..", "data.json"))
PATCH = os.path.join(HERE, "..", "data", "patch_results.json")
ODDS = os.environ.get("ODDS_JSON", os.path.join(HERE, "..", "data", "odds_history.json"))
LOG = os.environ.get("LOG_JSON", os.path.join(HERE, "..", "data", "predictions_log.json"))
# المواسم المتاحة في openfootball من 2020-21 فصاعداً؛ الأحدث هو الموسم الجاري
SEASONS_OF = sorted(d for d in os.listdir(OF) if re.fullmatch(r"\d{4}-\d{2}", d) and d >= "2020-21"
                    and os.path.exists(os.path.join(OF, d, "1-premierleague.txt")))
CUR = SEASONS_OF[-1]
PE = dict(k=15, home=80, draw=0.55, shrink=0.15)
PP = dict(lr=0.02, home=0.3, shrink=0.1)
TODAY = datetime.now(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
HORIZON = TODAY + timedelta(days=160)   # نحو خمسة أشهر قادمة

MATCH_RE = re.compile(r"^\s+(?:\d{1,2}:\d{2}\s+)?(?P<h>.+?)\s+v\s+(?P<a>.+?)(?:\s{2,}|\s+)(?P<s>\d+-\d+)?(?:\s*\(\d+-\d+\))?\s*$")
DATE_RE = re.compile(r"^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(?P<mon>[A-Z][a-z]{2})\s+(?P<d>\d{1,2})(?:\s+(?P<y>\d{4}))?\s*$")
MD_RE = re.compile(r"Matchday\s+(\d+)")
# صيغة المواسم 2020-21 إلى 2023-24 و2025-26: النتيجة بين الفريقين دون كلمة v
MID_RE = re.compile(r"^\s*(?:(?P<h1>\d{1,2}):(?P<m1>\d{2})\s+)?(?P<home>[A-Za-z][^\d()]*?)\s{2,}(?P<hg>\d+)-(?P<ag>\d+)(?:\s*\(\d+-\d+\))?\s{2,}(?P<away>[A-Za-z][^\d()]*?)\s*$")
MONTHS = {m: i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}


def parse_of(season):
    y0 = int(season[:4])
    out, date, md, cur_time = [], None, None, None
    goal_depth = 0
    with open(f"{OF}/{season}/1-premierleague.txt", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            # أسطر المسجّلين تلي سطر المباراة وقد تمتد على عدة أسطر (لا تؤثر على قراءة المباريات)
            if goal_depth > 0 and (re.match(r"^\s+\d{1,2}:\d{2}\s", line) or DATE_RE.match(line)):
                goal_depth = 0
            if out and (goal_depth > 0 or line.lstrip().startswith("(")):
                out[-1]["goals_raw"] = (out[-1].get("goals_raw", "") + " " + line.strip()).strip()
                goal_depth = out[-1]["goals_raw"].count("(") - out[-1]["goals_raw"].count(")")
                continue
            m = MD_RE.search(line)
            if m and line.lstrip().startswith("▪"):
                md = int(m.group(1)); continue
            d = DATE_RE.match(line)
            if d:
                mon = MONTHS[d.group("mon")]
                year = int(d.group("y")) if d.group("y") else (y0 if mon >= 7 else y0 + 1)
                date = datetime(year, mon, int(d.group("d"))); cur_time = None; continue
            mid = MID_RE.match(line) if (date and " v " not in line) else None
            if mid:
                if mid.group("h1"):
                    cur_time = (int(mid.group("h1")), int(mid.group("m1")))
                out.append(dict(season=season, date=date, home=mid.group("home").strip(), away=mid.group("away").strip(),
                                hg=int(mid.group("hg")), ag=int(mid.group("ag")), md=md, time=cur_time))
                continue
            if " v " in line and date:
                tm = re.match(r"^\s+(\d{1,2}):(\d{2})\s+", line)
                if tm:
                    cur_time = (int(tm.group(1)), int(tm.group(2)))   # المباريات التالية في اليوم نفسه تشترك في الوقت إن لم يُذكر
                # فصل الفريقين والنتيجة بدقة: نبحث عن النتيجة في نهاية السطر
                body = re.sub(r"^\s+\d{1,2}:\d{2}\s+", "", line).strip()
                sc = re.search(r"\s(\d+)-(\d+)(?:\s*\(\d+-\d+\))?\s*$", body)
                hg = ag = None
                if sc:
                    hg, ag = int(sc.group(1)), int(sc.group(2)); body = body[:sc.start()].rstrip()
                parts = re.split(r"\s+v\s+", body)
                if len(parts) != 2:
                    raise ValueError(f"سطر غير مفهوم: {line!r}")
                out.append(dict(season=season, date=date, home=parts[0].strip(), away=parts[1].strip(),
                                hg=hg, ag=ag, md=md, time=cur_time))
    return out


def canon_names(rows_by_season, old):
    """يوحّد أسماء الفرق المختصرة (مثل Liverpool) مع الأسماء الكاملة المعتمدة (Liverpool FC)."""
    known = {r["home"] for r in old} | {r["away"] for r in old}
    for rows in rows_by_season.values():
        for r in rows:
            if r["hg"] is None or " FC" in r["home"] or r["home"].startswith("AFC "):
                known.add(r["home"]); known.add(r["away"])
    def fix(n):
        if n in known: return n
        for c in (n + " FC", n + " AFC", "AFC " + n):
            if c in known: return c
        return n
    return fix


def fetch_fd_results():
    """نتائج المباريات المنتهية للدوري الممتاز من football-data.org بصيغة [مضيف، 'هـ-ض', ضيف]."""
    tok = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not tok:
        return []
    try:
        import urllib.request
        j = fd.get("https://api.football-data.org/v4/competitions/PL/matches?status=FINISHED", tok, 30)
        out = []
        for m in j.get("matches", []):
            ft = (m.get("score") or {}).get("fullTime") or {}
            if ft.get("home") is None or ft.get("away") is None:
                continue
            out.append([m["homeTeam"]["name"], f"{ft['home']}-{ft['away']}", m["awayTeam"]["name"]])
        print("نتائج من football-data.org:", len(out))
        return out
    except Exception as e:
        print("تعذّر football-data.org:", type(e).__name__, str(e)[:120])
        return []


def load_all():
    old = [r for r in bt.load() if r["season"] <= "2019-20"]
    hist = list(old)
    upcoming, cur_played = [], []
    parsed = {s: parse_of(s) for s in SEASONS_OF}
    for s_, rows_ in parsed.items():
        # حارس ضد التجاهل الصامت: كل موسم مكتمل يجب أن يحوي 380 مباراة منتهية
        if s_ != CUR:
            done_ = sum(1 for r in rows_ if r["hg"] is not None)
            assert done_ == 380, f"الموسم {s_}: {done_} مباراة مقروءة بدل 380 (تغيّرت صيغة الملف؟)"
    fix = canon_names({s: rows for s, rows in parsed.items() if s in ("2024-25", CUR)}, old)
    global PARSED, FIX
    PARSED, FIX = parsed, fix
    for s in SEASONS_OF:
        for r in parsed[s]:
            r["home"], r["away"] = fix(r["home"]), fix(r["away"])
            if r["hg"] is None:
                if s == CUR: upcoming.append(r)
                continue
            r2 = {k: r[k] for k in ("season", "date", "home", "away", "hg", "ag")}
            hist.append(r2)
            if s == CUR: cur_played.append(r)
    # نتائج الجولتين 6 و7 غير موجودة بعد في openfootball (آخر تحديث للمستودع 15 أكتوبر): تُكمَّل من patch_results.json
    patch = json.load(open(PATCH, encoding="utf-8")) if os.path.exists(PATCH) else []
    # نتائج أسرع من football-data.org (اختيارية: تُستعمل فقط إن وُجد المفتاح، وأي خطأ لا يوقف البناء)
    patch = list(patch) + fetch_fd_results()

    def full(short, names):
        c = [n for n in names if n == short or n.startswith(short + " ")]
        assert len(c) == 1, (short, c)
        return c[0]
    names = {r["home"] for r in upcoming} | {r["away"] for r in upcoming}
    applied = 0
    for h, sc, a in patch:
        try:
            hf, af = full(h, names), full(a, names)
        except AssertionError:
            continue   # الفريقان لم يعودا ضمن المباريات غير المسجلة
        hit = [r for r in upcoming if r["home"] == hf and r["away"] == af]
        if not hit:
            continue   # المصدر سجّل النتيجة بنفسه
        assert len(hit) == 1, (h, a, hit)
        r = hit[0]; r["hg"], r["ag"] = map(int, sc.split("-"))
        upcoming.remove(r); cur_played.append(r)
        hist.append({k: r[k] for k in ("season", "date", "home", "away", "hg", "ag")})
        applied += 1
    print("نتائج مكمَّلة من الويب:", applied)
    hist.sort(key=lambda x: (x["date"], x["home"]))
    return hist, cur_played, upcoming


def kickoff_iso(date, time):
    """وقت الانطلاق بتوقيت UTC بصيغة ISO. أوقات المصدر بتوقيت لندن المحلي (يشمل التوقيت الصيفي)."""
    if not time:
        return None
    local = datetime(date.year, date.month, date.day, time[0], time[1], tzinfo=ZoneInfo("Europe/London"))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def draw_flag(p):
    """«مرشحة للتعادل»: فرصتا الفوز متقاربتان (فارق أقل من 12 نقطة مئوية) وفرصة التعادل 25% فأكثر.
    اختُبرت القاعدة تاريخياً: 20% من المباريات تقع تحتها، وينتهي 29.8% منها بتعادل (مقابل 24.6% عموماً)."""
    return bool(abs(p[0] - p[2]) < 0.12 and p[1] >= 0.25)


def shown_score(f):
    """النتيجة التي تعرضها الصفحة: الأرجح منفردةً للمباريات المرشحة للتعادل، وإلا الأرجح المتسقة مع الفائز."""
    return f["modal"]["s"] if f["draw_flag"] else f["pick"]["s"]


def outcome_of(hg, ag):
    return 0 if hg > ag else (1 if hg == ag else 2)


def update_log_and_score(fixtures, cur_played, now):
    """يحفظ توقعات المباريات المستقبلية قبل انطلاقها (لا تُعدَّل بعد حفظها)، ثم يقيّم ما انتهى منها.
    شرط الحفظ: قبل موعد الانطلاق بساعة على الأقل (وإن غاب الموعد: يوم المباراة بعد اليوم الحالي)،
    فلا تُسجَّل توقعات بعد بدء المباراة."""
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
    today = now.strftime("%Y-%m-%d")
    added = 0
    horizon = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    for f in fixtures:
        key = f"{f['home']}|{f['away']}"            # كل زوج يلتقي مرة واحدة على أرض المضيف في الموسم
        ko = f.get("kickoff")
        if ko:   # الشرط الدقيق: قبل الانطلاق بساعة على الأقل، وخلال الأيام السبعة القادمة
            ok = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ") < ko <= (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%MZ")
        else:
            ok = (f["date"] > today or (f["date"] == today and now.hour < 10)) and f["date"] <= horizon
        if not ok:
            continue                                  # بعيدة جداً، أو بدأت: لا نكتب فوق التوقع المحفوظ
        new = dict(date=f["date"], md=f["md"], home=f["home"], away=f["away"],
                        ph=f["ph"], pd=f["pd"], pa=f["pa"], shown=shown_score(f), flag=f["draw_flag"],
                        logged_at=now.strftime("%Y-%m-%dT%H:%MZ"))
        old = log.get(key)
        if old is None or any(old[k] != new[k] for k in ("ph", "pd", "pa", "shown", "flag", "date", "md")):
            log[key] = new                            # آخر توقع قبل المباراة هو المعتمد في السجل
            added += 1
    if added or not os.path.exists(LOG):
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    res = {(m["home"], m["away"]): m for m in cur_played}
    scored, pending = [], 0
    for key, e in log.items():
        m = res.get((e["home"], e["away"]))
        if m is None:
            if e["date"] >= (now - timedelta(days=7)).strftime("%Y-%m-%d"):
                pending += 1
            continue
        o = outcome_of(m["hg"], m["ag"])
        probs = [e["ph"], e["pd"], e["pa"]]
        scored.append(dict(date=e["date"], md=e["md"], home=e["home"], away=e["away"],
                           ph=e["ph"], pd=e["pd"], pa=e["pa"], shown=e["shown"], flag=e["flag"],
                           hg=m["hg"], ag=m["ag"], outcome=o,
                           hit=max(range(3), key=lambda k: probs[k]) == o,
                           exact=e["shown"] == f"{m['hg']}-{m['ag']}",
                           logloss=-math.log(max(probs[o], 1e-9))))
    scored.sort(key=lambda x: (x["date"], x["home"]), reverse=True)
    n = len(scored)
    base_freq = [0.465, 0.246, 0.288]       # النسب التاريخية لفوز المضيف/تعادل/فوز الضيف
    rec = dict(
        since=min((e["date"] for e in log.values()), default=None), logged=len(log), pending=pending, n=n,
        hits=sum(1 for x in scored if x["hit"]), exact=sum(1 for x in scored if x["exact"]),
        draws=sum(1 for x in scored if x["outcome"] == 1),
        flagged=sum(1 for x in scored if x["flag"]), flagged_draws=sum(1 for x in scored if x["flag"] and x["outcome"] == 1),
        home_wins=sum(1 for x in scored if x["outcome"] == 0),
        logloss=round(sum(x["logloss"] for x in scored) / n, 4) if n else None,
        base_logloss=round(sum(-math.log(base_freq[x["outcome"]]) for x in scored) / n, 4) if n else None,
        recent=scored[:30])
    print(f"السجل الحي: محفوظ {len(log)} | جديد/محدَّث {added} | مُقيَّم {n} | بانتظار {pending}")
    return rec


def table(played, teams):
    t = {x: dict(p=0, w=0, d=0, l=0, gf=0, ga=0, pts=0) for x in teams}
    for m in played:
        h, a = t[m["home"]], t[m["away"]]
        h["p"] += 1; a["p"] += 1
        h["gf"] += m["hg"]; h["ga"] += m["ag"]; a["gf"] += m["ag"]; a["ga"] += m["hg"]
        if m["hg"] > m["ag"]: h["w"] += 1; h["pts"] += 3; a["l"] += 1
        elif m["hg"] < m["ag"]: a["w"] += 1; a["pts"] += 3; h["l"] += 1
        else: h["d"] += 1; a["d"] += 1; h["pts"] += 1; a["pts"] += 1
    return t


def main():
    hist, cur_played, upcoming = load_all()
    seasons = sorted({r["season"] for r in hist})
    print("مباريات التاريخ:", len(hist), "| مواسم:", len(seasons), seasons[0], "→", seasons[-1])

    elo = bt.Elo(**PE)
    poi = bt.PoissonDC(PP["lr"], PP["home"], 0.2, PP["shrink"])
    mdl = bt.Blend(elo, poi, 0.5)

    # تشغيل زمني كامل (هو نفسه الذي اختُبر رجعياً) ثم التقاط الحالة الراهنة
    prev = None
    pre = {}   # احتمالات ما قبل المباراة (تشغيل زمني متدرّج) لمباريات الموسم الجاري، لكاشف المفاجآت
    for m in hist:
        if prev is not None and m["season"] != prev:
            mdl.new_season()
        prev = m["season"]
        if m["season"] == CUR:
            pre[(m["date"].strftime("%Y-%m-%d"), m["home"], m["away"])] = mdl.predict(m)
        mdl.update(m)
    # بدء موسم 2026-27: لم يُنفَّذ new_season بعد لأن آخر مباراة في التاريخ هي من 2026-27 نفسه؛
    # ملاحظة: المواسم تُفصل داخل الحلقة، لذا حالة الدوري الحالية سليمة.

    teams = sorted({m["home"] for m in cur_played} | {m["home"] for m in upcoming} | {m["away"] for m in upcoming})
    assert len(teams) == 20, teams
    unknown = [t for t in teams if t not in elo.r]
    print("فرق بلا تاريخ:", unknown)

    tb = table(cur_played, teams)
    played_n = {t: tb[t]["p"] for t in teams}
    print("الجولات الملعوبة لكل فريق:", sorted(set(played_n.values())))

    # قوة الفرق
    strength = {t: elo.r[t] for t in teams}
    # قدرات الهجوم والدفاع (بتصحيح الميزة بحيث المتوسط 0)
    att = {t: poi.att.get(t, 0.0) for t in teams}
    dfn = {t: poi.dfn.get(t, 0.0) for t in teams}

    def predict(m):
        p = mdl.predict(m)
        lh, la = poi.lams(m)
        # شبكة النتائج المحتملة بتعديل بسيط ليتوافق مجموع الاحتمالات مع المزيج
        P = [[bt.pois(i, lh) * bt.pois(j, la) for j in range(8)] for i in range(8)]
        tot = sum(sum(r) for r in P)
        cells = sorted(((P[i][j] / tot, i, j) for i in range(8) for j in range(8)), reverse=True)
        top = [dict(s=f"{i}-{j}", p=round(c, 4)) for c, i, j in cells[:5]]
        over25 = sum(P[i][j] for i in range(8) for j in range(8) if i + j >= 3) / tot
        btts = sum(P[i][j] for i in range(1, 8) for j in range(1, 8)) / tot
        cs_h = sum(P[i][0] for i in range(8)) / tot
        cs_a = sum(P[0][j] for j in range(8)) / tot
        fav = max(range(3), key=lambda k: p[k])
        ok = lambda i, j: (i > j) if fav == 0 else ((i == j) if fav == 1 else (i < j))
        c2 = next((c, i, j) for c, i, j in cells if ok(i, j))
        pick = dict(s=f"{c2[1]}-{c2[2]}", p=round(c2[0], 4))
        modal = dict(s=f"{cells[0][1]}-{cells[0][2]}", p=round(cells[0][0], 4))
        return p, lh, la, top, over25, btts, cs_h, cs_a, pick, modal

    fixtures = []
    for m in upcoming:
        if m["date"] > HORIZON: continue
        p, lh, la, top, o25, bt_, ch, ca, pick, modal = predict(m)
        diff = elo.rating(m["home"]) + PE["home"] - elo.rating(m["away"])
        # نفس النموذج تماماً لكن بلا أفضلية الأرض (ملعب محايد) لزر «بلا أفضلية الأرض» في التطبيق
        _eh, _ph = elo.home, poi.home
        elo.home, poi.home = 0.0, 0.0
        pn = mdl.predict(m)
        lhn, lan = poi.lams(m)
        elo.home, poi.home = _eh, _ph
        fixtures.append(dict(
            md=m["md"], date=m["date"].strftime("%Y-%m-%d"), kickoff=kickoff_iso(m["date"], m.get("time")), home=m["home"], away=m["away"],
            ph=round(p[0], 4), pd=round(p[1], 4), pa=round(p[2], 4), pick=pick, modal=modal,
            draw_flag=draw_flag(p),
            xg_h=round(lh, 2), xg_a=round(la, 2), top=top,
            over25=round(o25, 4), btts=round(bt_, 4), cs_h=round(ch, 4), cs_a=round(ca, 4),
            elo_h=round(elo.rating(m["home"])), elo_a=round(elo.rating(m["away"])), elo_diff=round(diff),
            nh_ph=round(pn[0], 4), nh_pd=round(pn[1], 4), nh_pa=round(pn[2], 4), nh_xg_h=round(lhn, 2), nh_xg_a=round(lan, 2),
        ))
    print("مباريات قادمة حتى", HORIZON.date(), ":", len(fixtures))
    NOW = datetime.now(timezone.utc)
    record = update_log_and_score(fixtures, cur_played, NOW)

    # آخر 5 نتائج لكل فريق (النتيجة + الخصم)
    forms = {t: [] for t in teams}
    for m in sorted(cur_played, key=lambda x: x["date"]):
        for me, op, gf, ga, ven in ((m["home"], m["away"], m["hg"], m["ag"], "H"), (m["away"], m["home"], m["ag"], m["hg"], "A")):
            forms[me].append(dict(r="W" if gf > ga else ("D" if gf == ga else "L"), s=f"{gf}-{ga}", op=op, v=ven))

    # محاكاة الموسم المتبقي كاملاً (يشمل ما بعد مارس لأجل الجدول النهائي)
    random.seed(2026)
    rest = []
    for m in upcoming:
        p = mdl.predict(m); lh, la = poi.lams(m)
        rest.append((m["home"], m["away"], p, lh, la))
    N = 10000
    wi = W.WhatIf(rest, teams, (1, 4, 17), TODAY, fixtures)
    cnt = {t: dict(title=0, top4=0, rel=0, pos_sum=0, pts_sum=0) for t in teams}
    base = {t: (tb[t]["pts"], tb[t]["gf"] - tb[t]["ga"], tb[t]["gf"]) for t in teams}
    for _ in range(N):
        pts = {t: base[t][0] for t in teams}
        gd = {t: base[t][1] for t in teams}
        gf = {t: base[t][2] for t in teams}
        # عدم يقين قوة الفريق: انحراف عشوائي ثابت لكل فريق طوال هذه المحاكاة (≈ ±35 نقطة Elo)
        q = {t: random.gauss(0, 0.2) for t in teams}
        outs = []
        for h, a, p, lh, la in rest:
            dlt = q[h] - q[a]
            w0, w1, w2 = p[0] * math.exp(dlt), p[1], p[2] * math.exp(-dlt)
            z = w0 + w1 + w2
            r = random.random() * z
            if r < w0:
                o = 0
            elif r < w0 + w1:
                o = 1
            else:
                o = 2
            outs.append(o)
            # أهداف متسقة مع النتيجة: عيّن من بواسون مشروطاً بالنتيجة
            for _try in range(30):
                x = _pois_draw(lh); y = _pois_draw(la)
                if (x > y and o == 0) or (x == y and o == 1) or (x < y and o == 2): break
            else:
                x, y = (1, 0) if o == 0 else ((0, 0) if o == 1 else (0, 1))
            gd[h] += x - y; gd[a] += y - x; gf[h] += x; gf[a] += y
            pts[h] += 3 if o == 0 else (1 if o == 1 else 0)
            pts[a] += 3 if o == 2 else (1 if o == 1 else 0)
        order = sorted(teams, key=lambda t: (pts[t], gd[t], gf[t], random.random()), reverse=True)
        wi.record(outs, order)
        for i, t in enumerate(order):
            c = cnt[t]; c["pos_sum"] += i + 1; c["pts_sum"] += pts[t]
            if i == 0: c["title"] += 1
            if i < 4: c["top4"] += 1
            if i >= 17: c["rel"] += 1
    print("ماذا لو: مباريات مغطاة", wi.attach(fixtures))
    teams_out = []
    for t in teams:
        c = cnt[t]
        teams_out.append(dict(
            name=t, elo=round(strength[t]), att=round(att[t], 3), dfn=round(dfn[t], 3),
            **{k: tb[t][k] for k in ("p", "w", "d", "l", "gf", "ga", "pts")},
            form=forms[t][-5:], title=round(c["title"] / N, 4), top4=round(c["top4"] / N, 4),
            rel=round(c["rel"] / N, 4), exp_pos=round(c["pos_sum"] / N, 1), exp_pts=round(c["pts_sum"] / N, 1)))
    teams_out.sort(key=lambda x: (-x["pts"], -(x["gf"] - x["ga"]), -x["gf"]))

    # لقطة احتمالات نهاية الموسم لكل جولة، لعرض أسهم التغيّر (▲▼) بعد كل جولة
    cur_md = min(tb[t]["p"] for t in teams)
    try:
        odds_hist = json.load(open(ODDS, encoding="utf-8"))
    except (OSError, ValueError):
        odds_hist = {}
    prev_keys = sorted((int(k) for k in odds_hist if int(k) < cur_md))
    prev = odds_hist[str(prev_keys[-1])] if prev_keys else {}
    for t in teams_out:
        pv = prev.get(t["name"])
        t["prev_title"], t["prev_top4"], t["prev_rel"] = (pv if pv else (None, None, None))
    odds_hist[str(cur_md)] = {t["name"]: [t["title"], t["top4"], t["rel"]] for t in teams_out}
    os.makedirs(os.path.dirname(ODDS), exist_ok=True)
    json.dump(odds_hist, open(ODDS, "w", encoding="utf-8"), ensure_ascii=False, sort_keys=True)
    results = [dict(date=m["date"].strftime("%Y-%m-%d"), md=m.get("md"), home=m["home"], away=m["away"], hg=m["hg"], ag=m["ag"])
               for m in sorted(cur_played, key=lambda x: x["date"])]
    # مسجّلو الأهداف: نُرفق ما تحقق منه العدّ (عدد أهداف كل جانب = النتيجة) ولا ننشر غيره
    scorers = scorers_prev = scorers_live = None
    try:
        import scorers as S
        scorers_live = S.fetch_fd_scorers("PL", [t["name"] for t in teams_out])
        def sc_block(season):
            rows = PARSED[season]
            for r in rows:
                r["home"], r["away"] = FIX(r["home"]), FIX(r["away"])
            g, n, ok = S.attach(rows)
            return g, dict(season=season, matches=n, with_details=ok, top=S.top_scorers(rows, g))
        g_cur, scorers = sc_block(CUR)
        for r in results:
            g = g_cur.get((r["date"], r["home"], r["away"]))
            if g:
                r["g"] = g
        prev_season = sorted(PARSED)[-2]
        _, scorers_prev = sc_block(prev_season)
    except Exception as e:   # المسجلون إضافة؛ أي خلل فيها لا يوقف نشر التوقعات
        print("تعذّر استخراج المسجلين:", type(e).__name__, str(e)[:120])

    out = dict(generated=TODAY.strftime("%Y-%m-%d"), updated_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
               last_result_date=max(m["date"] for m in cur_played).strftime("%Y-%m-%d"), record=record, played_md=min(tb[t]["p"] for t in teams), through=str(HORIZON.date()), season=CUR, model="Elo + هجوم/دفاع (بواسون)",
               backtest=dict(matches=5700, acc=0.545, base_acc=0.465, logloss=0.965, recent=dict(matches=2280, acc=0.525, base_acc=0.431, logloss=0.988, seasons="2020-21→2025-26")), teams=teams_out, fixtures=fixtures, results=results, scorers=scorers, scorers_prev=scorers_prev, scorers_live=scorers_live, upsets=W.upset_list(pre, results))
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("تم. أفضل 5 بالقوة:", sorted(((round(v), k) for k, v in strength.items()), reverse=True)[:5])
    print("احتمال اللقب:", sorted(((t["title"], t["name"]) for t in teams_out), reverse=True)[:5])
    print("مجموع احتمالات اللقب:", round(sum(t["title"] for t in teams_out), 3))


def _pois_draw(lam):
    L = math.exp(-lam); k = 0; p = 1.0
    while True:
        p *= random.random()
        if p <= L: return k
        k += 1


if __name__ == "__main__":
    main()
