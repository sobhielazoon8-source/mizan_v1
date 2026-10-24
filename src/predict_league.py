#!/usr/bin/env python3
"""توقعات الدوريات الأوروبية (إسباني/ألماني/إيطالي/فرنسي) بنفس نموذج الدوري الإنجليزي.

الاستعمال: python3 -I src/predict_league.py es [de it fr]
المصدر: openfootball (CC0) عبر متغير OF_ROOT (مجلد يحوي espana وdeutschland وitaly وfrance)،
ونتائج أسرع اختيارياً من football-data.org عند وجود FOOTBALL_DATA_TOKEN.
"""
import json, math, os, random, sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backtest as bt
import fd
import whatif as W
import leagues as L
import league_names as N
import scorers as S

ROOT = os.environ.get("OF_ROOT", os.path.join(HERE, "..", "openfootball"))
DATA = os.environ.get("DATA_DIR", os.path.join(HERE, "..", "data"))
OUTDIR = os.environ.get("OUT_DIR", os.path.join(HERE, ".."))
PE = dict(k=15, home=80, draw=0.55, shrink=0.15)
PP = dict(lr=0.02, home=0.3, shrink=0.1)
# معاملات مضبوطة لكل دوري (tools/tune_leagues.py): تُعتمد فقط حيث تحسّن logloss على آخر 3 مواسم مجمّدة بما لا يقل عن 0.005
# دون خفض الدقة. إسبانيا وفرنسا لم تبلغا العتبة فبقيتا على المعاملات العامة. أيام الراحة جُرّبت ولم تغيّر شيئاً فلم تُعتمد.
TUNED = {
    "de": dict(pe=dict(k=10, home=65, draw=0.55, shrink=0.1), pp=dict(lr=0.015, home=0.2, shrink=0.05), w=0.4),
    "it": dict(pe=dict(k=20, home=50, draw=0.65, shrink=0.1), pp=dict(lr=0.03, home=0.2, shrink=0.05), w=0.5),
}
TODAY = datetime.now(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
HORIZON = TODAY + timedelta(days=160)
FD_CODES = {"es": "PD", "de": "BL1", "it": "SA", "fr": "FL1"}


def draw_flag(p):
    return bool(abs(p[0] - p[2]) < 0.12 and p[1] >= 0.25)


def outcome_of(hg, ag):
    return 0 if hg > ag else (1 if hg == ag else 2)


def pois_draw(lam):
    L_ = math.exp(-lam); k = 0; p = 1.0
    while True:
        p *= random.random()
        if p <= L_:
            return k
        k += 1


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


def kickoff_iso(date, time, tz):
    if not time:
        return None
    local = datetime(date.year, date.month, date.day, time[0], time[1], tzinfo=ZoneInfo(tz))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def fetch_fd(code):
    tok = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not tok:
        return []
    try:
        import urllib.request
        j = fd.get(f"https://api.football-data.org/v4/competitions/{FD_CODES[code]}/matches?status=FINISHED", tok, 30)
        out = []
        for m in j.get("matches", []):
            ft = (m.get("score") or {}).get("fullTime") or {}
            if ft.get("home") is None or ft.get("away") is None:
                continue
            try:
                out.append((N.canon(code, m["homeTeam"]["name"]), N.canon(code, m["awayTeam"]["name"]), ft["home"], ft["away"]))
            except KeyError:
                continue
        print(f"[{code}] نتائج من football-data.org: {len(out)}")
        return out
    except Exception as e:
        print(f"[{code}] تعذّر football-data.org:", type(e).__name__, str(e)[:100])
        return []


def load(code):
    root = os.path.join(ROOT, L.LEAGUES[code]["repo"])
    data = L.load_league(code, root)
    for s, rows in data.items():
        for r in rows:
            r["home"], r["away"] = N.canon(code, r["home"]), N.canon(code, r["away"])
        teams = {r["home"] for r in rows} | {r["away"] for r in rows}
        n = L.expected_teams(code, s)
        assert len(teams) == n, (code, s, len(teams))
        cur = s == max(data)
        done = sum(1 for r in rows if r["hg"] is not None)
        if not cur and not (code == "fr" and s == "2019-20"):
            assert done == n * (n - 1), (code, s, done)
    cur_s = max(data)
    hist, cur_played, upcoming = [], [], []
    for s in sorted(data):
        for r in data[s]:
            if r["hg"] is None:
                if s == cur_s:
                    upcoming.append(r)
                continue
            hist.append({k: r[k] for k in ("season", "date", "home", "away", "hg", "ag")})
            if s == cur_s:
                cur_played.append(r)
    # نتائج أسرع من football-data.org تُطبَّق على المباريات غير المسجلة في المصدر
    applied = 0
    for h, a, hg, ag in fetch_fd(code):
        hit = [r for r in upcoming if r["home"] == h and r["away"] == a]
        if len(hit) == 1:
            r = hit[0]; r["hg"], r["ag"] = hg, ag
            upcoming.remove(r); cur_played.append(r)
            hist.append({k: r[k] for k in ("season", "date", "home", "away", "hg", "ag")})
            applied += 1
    print(f"[{code}] نتائج مكمَّلة من football-data.org: {applied}")
    hist.sort(key=lambda x: (x["date"], x["home"]))
    return hist, cur_played, upcoming, cur_s, data


def new_model(code=None):
    t = TUNED.get(code)
    pe, pp, w = (t["pe"], t["pp"], t["w"]) if t else (PE, PP, 0.5)
    elo = bt.Elo(**pe)
    poi = bt.PoissonDC(pp["lr"], pp["home"], 0.2, pp["shrink"])
    return elo, poi, bt.Blend(elo, poi, w)


def backtest(hist, cur_s, code=None):
    """اختبار زمني على المواسم المكتملة: أول موسمين تسخين، والباقي يُقاس. ثم آخر 3 مواسم منفصلة."""
    seasons = sorted({r["season"] for r in hist if r["season"] != cur_s})
    rows = [r for r in hist if r["season"] != cur_s]
    start = seasons[2]
    _, _, mdl = new_model(code)
    preds, outs = bt.run(mdl, rows, start)
    m = bt.metrics(preds, outs)
    base = sum(1 for o in outs if o == 0) / len(outs)
    _, _, mdl2 = new_model(code)
    r_start = seasons[-3]
    p2, o2 = bt.run(mdl2, rows, r_start)
    m2 = bt.metrics(p2, o2)
    base2 = sum(1 for o in o2 if o == 0) / len(o2)
    return dict(matches=m["n"], acc=round(m["accuracy"], 4), base_acc=round(base, 4), logloss=round(m["logloss"], 4),
                seasons=f"{start}→{seasons[-1]}",
                recent=dict(matches=m2["n"], acc=round(m2["accuracy"], 4), base_acc=round(base2, 4),
                            logloss=round(m2["logloss"], 4), seasons=f"{r_start}→{seasons[-1]}"))


def update_log_and_score(code, fixtures, cur_played, now, base_freq):
    path = os.path.join(DATA, f"predictions_log_{code}.json")
    log = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    today = now.strftime("%Y-%m-%d")
    added = 0
    horizon = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    for f in fixtures:
        key = f"{f['home']}|{f['away']}"
        ko = f.get("kickoff")
        if ko:
            ok = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ") < ko <= (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%MZ")
        else:
            ok = (f["date"] > today or (f["date"] == today and now.hour < 10)) and f["date"] <= horizon
        if not ok:
            continue
        shown = f["modal"]["s"] if f["draw_flag"] else f["pick"]["s"]
        new = dict(date=f["date"], md=f["md"], home=f["home"], away=f["away"], ph=f["ph"], pd=f["pd"], pa=f["pa"],
                   shown=shown, flag=f["draw_flag"], logged_at=now.strftime("%Y-%m-%dT%H:%MZ"))
        old = log.get(key)
        if old is None or any(old[k] != new[k] for k in ("ph", "pd", "pa", "shown", "flag", "date", "md")):
            log[key] = new; added += 1
    if added or not os.path.exists(path):
        os.makedirs(DATA, exist_ok=True)
        json.dump(log, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    res = {(m["home"], m["away"]): m for m in cur_played}
    scored, pending = [], 0
    for e in log.values():
        m = res.get((e["home"], e["away"]))
        if m is None:
            if e["date"] >= (now - timedelta(days=7)).strftime("%Y-%m-%d"):
                pending += 1
            continue
        o = outcome_of(m["hg"], m["ag"]); probs = [e["ph"], e["pd"], e["pa"]]
        scored.append(dict(date=e["date"], md=e["md"], home=e["home"], away=e["away"], shown=e["shown"], flag=e["flag"],
                           hg=m["hg"], ag=m["ag"], outcome=o, hit=max(range(3), key=lambda k: probs[k]) == o,
                           exact=e["shown"] == f"{m['hg']}-{m['ag']}", logloss=-math.log(max(probs[o], 1e-9))))
    scored.sort(key=lambda x: (x["date"], x["home"]), reverse=True)
    n = len(scored)
    rec = dict(since=min((e["date"] for e in log.values()), default=None), logged=len(log), pending=pending, n=n,
               hits=sum(1 for x in scored if x["hit"]), exact=sum(1 for x in scored if x["exact"]),
               draws=sum(1 for x in scored if x["outcome"] == 1),
               flagged=sum(1 for x in scored if x["flag"]), flagged_draws=sum(1 for x in scored if x["flag"] and x["outcome"] == 1),
               home_wins=sum(1 for x in scored if x["outcome"] == 0),
               logloss=round(sum(x["logloss"] for x in scored) / n, 4) if n else None,
               base_logloss=round(sum(-math.log(base_freq[x["outcome"]]) for x in scored) / n, 4) if n else None,
               recent=scored[:30])
    print(f"[{code}] السجل الحي: محفوظ {len(log)} | جديد {added} | مُقيَّم {n} | بانتظار {pending}")
    return rec


def run_league(code):
    cfg = L.LEAGUES[code]
    hist, cur_played, upcoming, cur_s, season_rows = load(code)
    print(f"[{code}] مباريات التاريخ {len(hist)} | الموسم الجاري {cur_s} | قادمة {len(upcoming)}")
    bt_info = backtest(hist, cur_s, code)
    print(f"[{code}] اختبار رجعي: {bt_info['acc']:.3f} مقابل المضيف دائماً {bt_info['base_acc']:.3f} على {bt_info['matches']} | "
          f"حديث {bt_info['recent']['acc']:.3f} مقابل {bt_info['recent']['base_acc']:.3f} على {bt_info['recent']['matches']}")
    freq = Counter(outcome_of(r["hg"], r["ag"]) for r in hist)
    tot = sum(freq.values())
    base_freq = [freq[0] / tot, freq[1] / tot, freq[2] / tot]

    elo, poi, mdl = new_model(code)
    prev = None
    pre = {}   # احتمالات ما قبل المباراة لمباريات الموسم الجاري (كاشف المفاجآت)
    for m in hist:
        if prev is not None and m["season"] != prev:
            mdl.new_season()
        prev = m["season"]
        if m["season"] == cur_s:
            pre[(m["date"].strftime("%Y-%m-%d"), m["home"], m["away"])] = mdl.predict(m)
        mdl.update(m)

    n_teams = L.expected_teams(code, cur_s)
    teams = sorted({m["home"] for m in cur_played} | {m["home"] for m in upcoming} | {m["away"] for m in upcoming})
    assert len(teams) == n_teams, teams
    tb = table(cur_played, teams)
    strength = {t: elo.r.get(t, elo.newteam) for t in teams}
    att = {t: poi.att.get(t, 0.0) for t in teams}
    dfn = {t: poi.dfn.get(t, 0.0) for t in teams}

    def predict(m):
        p = mdl.predict(m); lh, la = poi.lams(m)
        P = [[bt.pois(i, lh) * bt.pois(j, la) for j in range(8)] for i in range(8)]
        tot_ = sum(sum(r) for r in P)
        cells = sorted(((P[i][j] / tot_, i, j) for i in range(8) for j in range(8)), reverse=True)
        top = [dict(s=f"{i}-{j}", p=round(c, 4)) for c, i, j in cells[:5]]
        over25 = sum(P[i][j] for i in range(8) for j in range(8) if i + j >= 3) / tot_
        btts = sum(P[i][j] for i in range(1, 8) for j in range(1, 8)) / tot_
        cs_h = sum(P[i][0] for i in range(8)) / tot_
        cs_a = sum(P[0][j] for j in range(8)) / tot_
        fav = max(range(3), key=lambda k: p[k])
        ok = lambda i, j: (i > j) if fav == 0 else ((i == j) if fav == 1 else (i < j))
        c2 = next((c, i, j) for c, i, j in cells if ok(i, j))
        pick = dict(s=f"{c2[1]}-{c2[2]}", p=round(c2[0], 4))
        modal = dict(s=f"{cells[0][1]}-{cells[0][2]}", p=round(cells[0][0], 4))
        return p, lh, la, top, over25, btts, cs_h, cs_a, pick, modal

    fixtures = []
    for m in upcoming:
        if m["date"] > HORIZON:
            continue
        p, lh, la, top, o25, bb, ch, ca, pick, modal = predict(m)
        diff = elo.rating(m["home"]) + elo.home - elo.rating(m["away"])
        _eh, _ph = elo.home, poi.home
        elo.home, poi.home = 0.0, 0.0
        pn = mdl.predict(m); lhn, lan = poi.lams(m)
        elo.home, poi.home = _eh, _ph
        fixtures.append(dict(
            md=m["md"] or 0, date=m["date"].strftime("%Y-%m-%d"), kickoff=kickoff_iso(m["date"], m.get("time"), cfg["tz"]),
            home=m["home"], away=m["away"], ph=round(p[0], 4), pd=round(p[1], 4), pa=round(p[2], 4), pick=pick, modal=modal,
            draw_flag=draw_flag(p), xg_h=round(lh, 2), xg_a=round(la, 2), top=top,
            over25=round(o25, 4), btts=round(bb, 4), cs_h=round(ch, 4), cs_a=round(ca, 4),
            elo_h=round(elo.rating(m["home"])), elo_a=round(elo.rating(m["away"])), elo_diff=round(diff),
            nh_ph=round(pn[0], 4), nh_pd=round(pn[1], 4), nh_pa=round(pn[2], 4), nh_xg_h=round(lhn, 2), nh_xg_a=round(lan, 2)))
    NOW = datetime.now(timezone.utc)
    record = update_log_and_score(code, fixtures, cur_played, NOW, base_freq)

    forms = {t: [] for t in teams}
    for m in sorted(cur_played, key=lambda x: x["date"]):
        for me, op, gf, ga, ven in ((m["home"], m["away"], m["hg"], m["ag"], "H"), (m["away"], m["home"], m["ag"], m["hg"], "A")):
            forms[me].append(dict(r="W" if gf > ga else ("D" if gf == ga else "L"), s=f"{gf}-{ga}", op=op, v=ven))

    random.seed(2026)
    rest = []
    for m in upcoming:
        p = mdl.predict(m); lh, la = poi.lams(m)
        rest.append((m["home"], m["away"], p, lh, la))
    NSIM = 10000
    rel_n = cfg["rel"]
    wi = W.WhatIf(rest, teams, (1, 4, n_teams - rel_n), TODAY, fixtures)
    cnt = {t: dict(title=0, top4=0, rel=0, pos_sum=0, pts_sum=0) for t in teams}
    base = {t: (tb[t]["pts"], tb[t]["gf"] - tb[t]["ga"], tb[t]["gf"]) for t in teams}
    for _ in range(NSIM):
        pts = {t: base[t][0] for t in teams}; gd = {t: base[t][1] for t in teams}; gf = {t: base[t][2] for t in teams}
        q = {t: random.gauss(0, 0.2) for t in teams}
        outs = []
        for h, a, p, lh, la in rest:
            dlt = q[h] - q[a]
            w0, w1, w2 = p[0] * math.exp(dlt), p[1], p[2] * math.exp(-dlt)
            r = random.random() * (w0 + w1 + w2)
            o = 0 if r < w0 else (1 if r < w0 + w1 else 2)
            outs.append(o)
            for _try in range(30):
                x = pois_draw(lh); y = pois_draw(la)
                if (x > y and o == 0) or (x == y and o == 1) or (x < y and o == 2):
                    break
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
            if i >= n_teams - rel_n: c["rel"] += 1
    print(f"[{code}] ماذا لو: مباريات مغطاة", wi.attach(fixtures))
    teams_out = []
    for t in teams:
        c = cnt[t]
        teams_out.append(dict(name=t, elo=round(strength[t]), att=round(att[t], 3), dfn=round(dfn[t], 3),
                              **{k: tb[t][k] for k in ("p", "w", "d", "l", "gf", "ga", "pts")},
                              form=forms[t][-5:], title=round(c["title"] / NSIM, 4), top4=round(c["top4"] / NSIM, 4),
                              rel=round(c["rel"] / NSIM, 4), exp_pos=round(c["pos_sum"] / NSIM, 1), exp_pts=round(c["pts_sum"] / NSIM, 1)))
    teams_out.sort(key=lambda x: (-x["pts"], -(x["gf"] - x["ga"]), -x["gf"]))

    cur_md = min(tb[t]["p"] for t in teams)
    opath = os.path.join(DATA, f"odds_history_{code}.json")
    try:
        odds_hist = json.load(open(opath, encoding="utf-8"))
    except (OSError, ValueError):
        odds_hist = {}
    prev_keys = sorted(int(k) for k in odds_hist if int(k) < cur_md)
    prev_s = odds_hist[str(prev_keys[-1])] if prev_keys else {}
    for t in teams_out:
        pv = prev_s.get(t["name"])
        t["prev_title"], t["prev_top4"], t["prev_rel"] = (pv if pv else (None, None, None))
    odds_hist[str(cur_md)] = {t["name"]: [t["title"], t["top4"], t["rel"]] for t in teams_out}
    os.makedirs(DATA, exist_ok=True)
    json.dump(odds_hist, open(opath, "w", encoding="utf-8"), ensure_ascii=False, sort_keys=True)

    results = [dict(date=m["date"].strftime("%Y-%m-%d"), md=m.get("md"), home=m["home"], away=m["away"], hg=m["hg"], ag=m["ag"])
               for m in sorted(cur_played, key=lambda x: x["date"])]
    # مسجّلو الأهداف (متوفرون فقط لمباريات حرّر لها المتطوعون التفاصيل): نُرفق ما تحقق منه العدّ
    g_cur, n_cur, ok_cur = S.attach([r for r in season_rows[cur_s]], canon=lambda n: n)
    for r in results:
        g = g_cur.get((r["date"], r["home"], r["away"]))
        if g:
            r["g"] = g
    scorers_live = S.fetch_fd_scorers(FD_CODES[code], [t["name"] for t in teams_out]) if code in FD_CODES else None
    prev_s = sorted(season_rows)[-2] if len(season_rows) > 1 else None
    scorers = dict(season=cur_s, matches=n_cur, with_details=ok_cur,
                   top=S.top_scorers(season_rows[cur_s], g_cur))
    if prev_s:
        g_prev, n_prev, ok_prev = S.attach(season_rows[prev_s])
        scorers_prev = dict(season=prev_s, matches=n_prev, with_details=ok_prev, top=S.top_scorers(season_rows[prev_s], g_prev))
    else:
        scorers_prev = None
    out = dict(league=code, league_ar=cfg["ar"], rel_n=rel_n, generated=TODAY.strftime("%Y-%m-%d"),
               updated_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
               last_result_date=max((m["date"] for m in cur_played), default=TODAY).strftime("%Y-%m-%d"),
               record=record, played_md=cur_md, through=str(HORIZON.date()), season=cur_s,
               model="Elo + هجوم/دفاع (بواسون)", backtest=bt_info, teams=teams_out, fixtures=fixtures, results=results,
               scorers=scorers, scorers_prev=scorers_prev, scorers_live=scorers_live,
               names_ar=N.AR[code], upsets=W.upset_list(pre, results))
    json.dump(out, open(os.path.join(OUTDIR, f"data_{code}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[{code}] تم. اللقب:", sorted(((t["title"], t["name"]) for t in teams_out), reverse=True)[:3],
          "| مجموع اللقب", round(sum(t["title"] for t in teams_out), 3))


if __name__ == "__main__":
    codes = sys.argv[1:] or list(L.LEAGUES)
    for c in codes:
        run_league(c)
