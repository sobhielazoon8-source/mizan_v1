#!/usr/bin/env python3
"""توقعات دوري أبطال أوروبا. نموذج منفصل: تقييم Elo + هجوم/دفاع (بواسون) يُبنى من نتائج دوري الأبطال نفسه فقط (2011-12 فصاعداً)،
فلا نخلط تقييمات الدوريات المحلية غير المتجانسة. النتائج الحديثة والمباريات القادمة من football-data.org (المستوى المجاني) عبر FOOTBALL_DATA_TOKEN،
والتاريخ من openfootball/champions-league (CC0) عبر CL_ROOT.
الاستعمال: CL_ROOT=<مجلد> python3 -I src/predict_cl.py"""
import json, math, os, random, re, sys
from collections import Counter
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backtest as bt
import cl_names as CN
import league_names as N
import leagues as L
import predict_league as PL
import scorers as S

CL_ROOT = os.environ.get("CL_ROOT", os.path.join(HERE, "..", "openfootball", "champions-league"))
# معاملات دوري الأبطال (تُضبط بـ tools/tune_cl.py؛ القيم هنا نتيجة ذلك الضبط)
# مضبوطة على المواسم 2013-14→2021-22 ومجمّدة ثم قيست على 2022-23→2024-25: logloss من 0.947 إلى 0.925 والدقة من 56.0% إلى 58.8%
PE_CL = dict(k=30, home=60, draw=0.55, shrink=0.15)
PP_CL = dict(lr=0.045, home=0.2, shrink=0.1)
W_CL = 0.3
LINE = re.compile(r"^\s*(?:\d{1,2}:\d{2}\s+)?(?P<h>.+?\([A-Z]{3}\))\s+v\s+(?P<a>.+?\([A-Z]{3}\))(?:\s+(?P<s>.*))?$")
TIME = re.compile(r"^\s+(\d{1,2}):(\d{2})\s")


def parse_score(s):
    """نتيجة الـ90 دقيقة: للمباريات الممتدة تكون في القوس الأخير «(90د, شوط أول)»."""
    if not s:
        return None
    m = re.match(r"^(\d+)-(\d+)", s)
    if not m:
        return None
    if "a.e.t." in s or "pen." in s:
        p = re.search(r"\((\d+)-(\d+),\s*\d+-\d+\)", s)
        return (int(p.group(1)), int(p.group(2))) if p else None
    return int(m.group(1)), int(m.group(2))


def parse_cl(path, season, known):
    y0 = int(season[:4])
    out, date, md, stage = [], None, 0, "league"
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.lstrip().startswith("▪"):
            head = line.lstrip("▪ ").strip()
            stage = "league" if head.startswith("League") else ("group" if head.startswith("Group") else "ko")
            mm = re.search(r"Matchday\s+(\d+)", head)
            md = int(mm.group(1)) if mm else 0
            continue
        d = L.DATE_RE.match(line)
        if d:
            mon = L.MONTHS[d.group("mon")]
            year = int(d.group("y")) if d.group("y") else (y0 if mon >= 7 else y0 + 1)
            date = datetime(year, mon, int(d.group("d")))
            continue
        m = LINE.match(line)
        if not m or not date:
            continue
        sc = parse_score(m.group("s"))
        out.append(dict(season=season, date=date, home=CN.canon(m.group("h"), known), away=CN.canon(m.group("a"), known),
                        hg=sc[0] if sc else None, ag=sc[1] if sc else None, md=md, stage=stage, time=None))
    return out


def fetch_fd_cl(known):
    """مباريات الموسم الجاري من football-data.org: (منتهية، قادمة، وسم الموسم) أو None عند أي خلل."""
    tok = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not tok:
        return None
    try:
        import urllib.request
        req = urllib.request.Request("https://api.football-data.org/v4/competitions/CL/matches", headers={"X-Auth-Token": tok})
        j = json.load(urllib.request.urlopen(req, timeout=40))
        played, upcoming, season = [], [], None
        for m in j.get("matches", []):
            h, a = (m.get("homeTeam") or {}).get("name"), (m.get("awayTeam") or {}).get("name")
            if not h or not a:
                continue   # مباريات الأدوار الإقصائية قبل القرعة
            sd = (m.get("season") or {}).get("startDate")
            if sd and not season:
                y = int(sd[:4]); season = f"{y}-{(y + 1) % 100:02d}"
            stg = "league" if m.get("stage") == "LEAGUE_STAGE" else ("group" if m.get("stage") == "GROUP_STAGE" else "ko")
            when = datetime.strptime(m["utcDate"], "%Y-%m-%dT%H:%M:%SZ")
            row = dict(date=when.replace(hour=0, minute=0, second=0), kick=when.strftime("%Y-%m-%dT%H:%MZ"),
                       home=CN.canon(h, known), away=CN.canon(a, known), md=m.get("matchday") or 0, stage=stg, time=None)
            sc = m.get("score") or {}
            ft = sc.get("regularTime") or sc.get("fullTime") or {}
            if m.get("status") == "FINISHED" and ft.get("home") is not None and ft.get("away") is not None:
                row["hg"], row["ag"] = int(ft["home"]), int(ft["away"])
                played.append(row)
            elif m.get("status") in ("SCHEDULED", "TIMED"):
                row["hg"] = row["ag"] = None
                upcoming.append(row)
        print(f"[cl] football-data.org: منتهية {len(played)} | قادمة {len(upcoming)} | الموسم {season}")
        return played, upcoming, season
    except Exception as e:
        print("[cl] تعذّر football-data.org:", type(e).__name__, str(e)[:120])
        return None


def new_model():
    elo = bt.Elo(**PE_CL)
    poi = bt.PoissonDC(PP_CL["lr"], PP_CL["home"], 0.2, PP_CL["shrink"])
    return elo, poi, bt.Blend(elo, poi, W_CL)


def backtest(hist, cur_s):
    rows = [r for r in hist if r["season"] != cur_s]
    seasons = sorted({r["season"] for r in rows})
    start = seasons[2]
    _, _, mdl = new_model()
    preds, outs = bt.run(mdl, rows, start)
    m = bt.metrics(preds, outs)
    base = sum(1 for o in outs if o == 0) / len(outs)
    _, _, mdl2 = new_model()
    r_start = seasons[-3]
    p2, o2 = bt.run(mdl2, rows, r_start)
    m2 = bt.metrics(p2, o2)
    base2 = sum(1 for o in o2 if o == 0) / len(o2)
    return dict(matches=m["n"], acc=round(m["accuracy"], 4), base_acc=round(base, 4), logloss=round(m["logloss"], 4),
                seasons=f"{start}→{seasons[-1]}",
                recent=dict(matches=m2["n"], acc=round(m2["accuracy"], 4), base_acc=round(base2, 4),
                            logloss=round(m2["logloss"], 4), seasons=f"{r_start}→{seasons[-1]}"))


def main():
    known = [x for c in ("es", "de", "it", "fr") for x in N.AR[c]]
    try:
        known += [t["name"] for t in json.load(open(os.path.join(HERE, "..", "data.json"), encoding="utf-8"))["teams"]]
    except Exception:
        pass
    seasons = sorted(d for d in os.listdir(CL_ROOT) if re.fullmatch(r"\d{4}-\d{2}", d) and os.path.exists(os.path.join(CL_ROOT, d, "cl.txt")))
    data = {s: parse_cl(os.path.join(CL_ROOT, s, "cl.txt"), s, known) for s in seasons}
    fd = fetch_fd_cl(known)
    cur_s = fd[2] if (fd and fd[2]) else seasons[-1]
    rows_cur = [dict(r) for r in data.get(cur_s, [])]
    # دمج openfootball وfootball-data للموسم الجاري: الأولوية لنتيجة مسجّلة
    seen = {(r["home"], r["away"], r["stage"]): r for r in rows_cur}
    if fd:
        for r in fd[0] + fd[1]:
            k = (r["home"], r["away"], r["stage"])
            if k in seen:
                old = seen[k]
                if old["hg"] is None and r["hg"] is not None:
                    old["hg"], old["ag"] = r["hg"], r["ag"]
                if r.get("kick"):
                    old["kick"] = r["kick"]
                old["md"] = old["md"] or r["md"]
            else:
                rows_cur.append(r); seen[k] = r
    cur_played = [r for r in rows_cur if r["hg"] is not None]
    upcoming = [r for r in rows_cur if r["hg"] is None]
    if not cur_played and not upcoming:
        print("[cl] لا بيانات للموسم الجاري: لا ملف يُكتب")
        return
    last_played = max((r["date"] for r in cur_played), default=None)
    if not upcoming and not os.environ.get("CL_FORCE") and (last_played is None or (PL.TODAY - last_played).days > 40):
        print(f"[cl] لا مباريات قادمة وآخر مباراة {last_played}: بيانات الموسم {cur_s} قديمة، لا ملف يُكتب")
        return
    hist = []
    for s in seasons:
        if s != cur_s:
            hist += [r for r in data[s] if r["hg"] is not None]
    for r in rows_cur:
        r["season"] = cur_s
    hist += cur_played
    hist.sort(key=lambda x: (x["date"], x["home"]))
    hist = [{k: r[k] for k in ("season", "date", "home", "away", "hg", "ag")} for r in hist]
    print(f"[cl] مباريات التاريخ {len(hist)} | الموسم الجاري {cur_s} | منتهية {len(cur_played)} | قادمة {len(upcoming)}")

    bt_info = backtest(hist, cur_s)
    print(f"[cl] اختبار رجعي: {bt_info['acc']:.3f} مقابل المضيف دائماً {bt_info['base_acc']:.3f} على {bt_info['matches']} | "
          f"حديث {bt_info['recent']['acc']:.3f} مقابل {bt_info['recent']['base_acc']:.3f} على {bt_info['recent']['matches']}")
    freq = Counter(PL.outcome_of(r["hg"], r["ag"]) for r in hist)
    tot = sum(freq.values())
    base_freq = [freq[0] / tot, freq[1] / tot, freq[2] / tot]

    elo, poi, mdl = new_model()
    prev = None
    for m in hist:
        if prev is not None and m["season"] != prev:
            mdl.new_season()
        prev = m["season"]
        mdl.update(m)

    league_rows = [r for r in rows_cur if r["stage"] == "league"]
    teams = sorted({r["home"] for r in league_rows} | {r["away"] for r in league_rows})
    n_league_matches = len(league_rows)
    if len(teams) != 36 or n_league_matches != 144:
        print(f"[cl] صيغة مرحلة الدوري غير مكتملة ({len(teams)} فريقاً، {n_league_matches} مباراة): لا ملف يُكتب")
        return
    all_names = sorted({r["home"] for r in rows_cur} | {r["away"] for r in rows_cur})
    lp = [r for r in cur_played if r["stage"] == "league"]
    tb = PL.table(lp, teams)
    strength = {t: elo.r.get(t, elo.newteam) for t in all_names}
    att = {t: poi.att.get(t, 0.0) for t in all_names}
    dfn = {t: poi.dfn.get(t, 0.0) for t in all_names}

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
    for m in sorted(upcoming, key=lambda x: (x["date"], x["home"])):
        if m["date"] > PL.HORIZON:
            continue
        p, lh, la, top, o25, bb, ch, ca, pick, modal = predict(m)
        diff = elo.rating(m["home"]) + PE_CL["home"] - elo.rating(m["away"])
        _eh, _ph = elo.home, poi.home
        elo.home, poi.home = 0.0, 0.0
        pn = mdl.predict(m); lhn, lan = poi.lams(m)
        elo.home, poi.home = _eh, _ph
        fixtures.append(dict(
            md=m["md"] or 0, date=m["date"].strftime("%Y-%m-%d"), kickoff=m.get("kick"),
            home=m["home"], away=m["away"], ph=round(p[0], 4), pd=round(p[1], 4), pa=round(p[2], 4), pick=pick, modal=modal,
            draw_flag=PL.draw_flag(p), xg_h=round(lh, 2), xg_a=round(la, 2), top=top,
            over25=round(o25, 4), btts=round(bb, 4), cs_h=round(ch, 4), cs_a=round(ca, 4),
            elo_h=round(elo.rating(m["home"])), elo_a=round(elo.rating(m["away"])), elo_diff=round(diff),
            nh_ph=round(pn[0], 4), nh_pd=round(pn[1], 4), nh_pa=round(pn[2], 4), nh_xg_h=round(lhn, 2), nh_xg_a=round(lan, 2)))
    NOW = datetime.now(timezone.utc)
    record = PL.update_log_and_score("cl", fixtures, cur_played, NOW, base_freq)

    forms = {t: [] for t in all_names}
    for m in sorted(cur_played, key=lambda x: x["date"]):
        for me, op, gf, ga, ven in ((m["home"], m["away"], m["hg"], m["ag"], "H"), (m["away"], m["home"], m["ag"], m["hg"], "A")):
            forms[me].append(dict(r="W" if gf > ga else ("D" if gf == ga else "L"), s=f"{gf}-{ga}", op=op, v=ven))

    # محاكاة ما تبقى من مرحلة الدوري (36 فريقاً): 1-8 مباشرة، 9-24 ملحق، 25-36 خروج
    random.seed(2026)
    rest = []
    for m in upcoming:
        if m["stage"] != "league":
            continue
        p = mdl.predict(m); lh, la = poi.lams(m)
        rest.append((m["home"], m["away"], p, lh, la))
    NSIM = 10000
    cnt = {t: dict(title=0, top4=0, rel=0, pos_sum=0, pts_sum=0) for t in teams}
    base = {t: (tb[t]["pts"], tb[t]["gf"] - tb[t]["ga"], tb[t]["gf"]) for t in teams}
    for _ in range(NSIM):
        pts = {t: base[t][0] for t in teams}; gd = {t: base[t][1] for t in teams}; gf = {t: base[t][2] for t in teams}
        q = {t: random.gauss(0, 0.2) for t in teams}
        for h, a, p, lh, la in rest:
            dlt = q[h] - q[a]
            w0, w1, w2 = p[0] * math.exp(dlt), p[1], p[2] * math.exp(-dlt)
            r = random.random() * (w0 + w1 + w2)
            o = 0 if r < w0 else (1 if r < w0 + w1 else 2)
            for _try in range(30):
                x = PL.pois_draw(lh); y = PL.pois_draw(la)
                if (x > y and o == 0) or (x == y and o == 1) or (x < y and o == 2):
                    break
            else:
                x, y = (1, 0) if o == 0 else ((0, 0) if o == 1 else (0, 1))
            gd[h] += x - y; gd[a] += y - x; gf[h] += x; gf[a] += y
            pts[h] += 3 if o == 0 else (1 if o == 1 else 0)
            pts[a] += 3 if o == 2 else (1 if o == 1 else 0)
        order = sorted(teams, key=lambda t: (pts[t], gd[t], gf[t], random.random()), reverse=True)
        for i, t in enumerate(order):
            c = cnt[t]; c["pos_sum"] += i + 1; c["pts_sum"] += pts[t]
            if i < 8: c["title"] += 1
            if i < 24: c["top4"] += 1
            if i >= 24: c["rel"] += 1
    teams_out = []
    for t in teams:
        c = cnt[t]
        teams_out.append(dict(name=t, elo=round(strength[t]), att=round(att[t], 3), dfn=round(dfn[t], 3),
                              **{k: tb[t][k] for k in ("p", "w", "d", "l", "gf", "ga", "pts")},
                              form=forms[t][-5:], title=round(c["title"] / NSIM, 4), top4=round(c["top4"] / NSIM, 4),
                              rel=round(c["rel"] / NSIM, 4), exp_pos=round(c["pos_sum"] / NSIM, 1), exp_pts=round(c["pts_sum"] / NSIM, 1)))
    teams_out.sort(key=lambda x: (-x["pts"], -(x["gf"] - x["ga"]), -x["gf"]))

    cur_md = min(tb[t]["p"] for t in teams)
    opath = os.path.join(PL.DATA, "odds_history_cl.json")
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
    os.makedirs(PL.DATA, exist_ok=True)
    json.dump(odds_hist, open(opath, "w", encoding="utf-8"), ensure_ascii=False, sort_keys=True)

    results = [dict(date=m["date"].strftime("%Y-%m-%d"), md=m.get("md"), home=m["home"], away=m["away"], hg=m["hg"], ag=m["ag"])
               for m in sorted(cur_played, key=lambda x: x["date"])]
    scorers_live = S.fetch_fd_scorers("CL", teams)
    names_ar = {t: CN.AR[t] for t in all_names if t in CN.AR}
    out = dict(league="cl", league_ar="دوري أبطال أوروبا", rel_n=12, generated=PL.TODAY.strftime("%Y-%m-%d"),
               updated_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
               last_result_date=max((m["date"] for m in cur_played), default=PL.TODAY).strftime("%Y-%m-%d"),
               record=record, played_md=cur_md, through=str(PL.HORIZON.date()), season=cur_s,
               model="Elo + هجوم/دفاع (بواسون) من نتائج دوري الأبطال", backtest=bt_info, teams=teams_out, fixtures=fixtures,
               results=results, scorers_live=scorers_live, table_labels=["المراكز 1-8 (مباشرة)", "المراكز 1-24 (تأهل)", "الخروج (25-36)"],
               names_ar=names_ar)
    json.dump(out, open(os.path.join(PL.OUTDIR, "data_cl.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("[cl] تم. أعلى فرص المراكز الثمانية:", sorted(((t["title"], t["name"]) for t in teams_out), reverse=True)[:4])


if __name__ == "__main__":
    main()
