"""يبني ملفات «الموسوعة» لتطبيق ميزان:
  clubs.json   : نتائج الدرجتين الأولى والثانية في إنجلترا منذ 1992-93 (مصادر CC0: footballcsv + openfootball)
  nations.json : نتائج المنتخبات منذ 1872 (مصدر CC0: martj42/international_results) + تقييم Elo حالي
  nations_backtest.json : اختبار زمني لدقة نموذج المنتخبات
التشغيل: OF_DIR=<openfootball/england> python3 -I tools/build_history.py <مجلد_الإخراج>
"""
import csv, glob, itertools, json, math, os, re, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import predict as pr  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "dist_history")
os.makedirs(OUT, exist_ok=True)
CSV_ROOT = os.environ.get("HISTORY_DIR", os.path.join(HERE, "..", "data", "history"))
OF = pr.OF


def ymd(d):
    return d.year * 10000 + d.month * 100 + d.day


# ---------------------------------------------------------------- الأندية
def csv_rows(tier):
    rows = []
    for path in sorted(glob.glob(f"{CSV_ROOT}/*/*/eng.{tier}.csv")):
        season = path.split("/")[-2]
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                m = re.match(r"^\s*(\d+)-(\d+)\s*$", r["FT"] or "")
                if not m:
                    continue
                d = datetime.strptime(r["Date"].strip(), "%a %b %d %Y")
                rows.append(dict(season=season, tier=tier, date=d, home=r["Team 1"].strip(), away=r["Team 2"].strip(),
                                 hg=int(m.group(1)), ag=int(m.group(2))))
    return rows


def of_rows(season, fname, tier):
    y0 = int(season[:4])
    out, date = [], None
    path = f"{OF}/{season}/{fname}"
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        d = pr.DATE_RE.match(line)
        if d:
            mon = pr.MONTHS[d.group("mon")]
            year = int(d.group("y")) if d.group("y") else (y0 if mon >= 7 else y0 + 1)
            date = datetime(year, mon, int(d.group("d")))
            continue
        if not date:
            continue
        mid = pr.MID_RE.match(line) if " v " not in line else None
        if mid:
            out.append(dict(season=season, tier=tier, date=date, home=mid.group("home").strip(), away=mid.group("away").strip(),
                            hg=int(mid.group("hg")), ag=int(mid.group("ag"))))
            continue
        if " v " in line:
            body = re.sub(r"^\s+\d{1,2}:\d{2}\s+", "", line).strip()
            sc = re.search(r"\s(\d+)-(\d+)(?:\s*\(\d+-\d+\))?\s*$", body)
            if not sc:
                continue
            hg, ag = int(sc.group(1)), int(sc.group(2))
            parts = re.split(r"\s+v\s+", body[:sc.start()].rstrip())
            if len(parts) == 2:
                out.append(dict(season=season, tier=tier, date=date, home=parts[0].strip(), away=parts[1].strip(), hg=hg, ag=ag))
    return out


def dedupe(rows):
    """يستبعد مباريات الملحق (تكرار الثنائي مضيف/ضيف نفسه في الموسم الواحد) محتفظاً بأولها."""
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["date"]):
        k = (r["season"], r["tier"], r["home"], r["away"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def build_clubs():
    from collections import Counter, defaultdict
    need = {1: 380, 2: 552}
    by = defaultdict(list)
    for r in csv_rows(1) + csv_rows(2):
        if r["season"] <= "2019-20":
            by[(r["season"], r["tier"])].append(r)
    of_by = defaultdict(list)
    for s in sorted(d for d in os.listdir(OF) if re.fullmatch(r"\d{4}-\d{2}", d) and "2000-01" <= d < pr.CUR):
        for t, fn in ((1, "1-premierleague.txt"), (2, "2-championship.txt")):
            of_by[(s, t)] = dedupe(of_rows(s, fn, t))
    known = {r["home"] for v in by.values() for r in v} | {r["away"] for v in by.values() for r in v}
    for v in of_by.values():
        for r in v:
            if " FC" in r["home"] or r["home"].startswith("AFC "):
                known.add(r["home"]); known.add(r["away"])

    def fix(n):
        if n in known:
            return n
        for c in (n + " FC", n + " AFC", "AFC " + n):
            if c in known:
                return c
        return n
    rows = []
    for key in sorted(set(by) | set(of_by)):
        s_, t_ = key
        csv_r, of_r = by.get(key, []), of_by.get(key, [])
        for r in of_r:
            r["home"], r["away"] = fix(r["home"]), fix(r["away"])
        n_need = need[t_]
        if s_ >= "2020-21":
            pick = of_r
        elif len(csv_r) == n_need or not of_r:
            pick = csv_r
        elif len(of_r) == n_need:
            pick = of_r
        else:
            pick = csv_r if len(csv_r) >= len(of_r) else of_r
        rows += pick
    cnt = Counter((r["season"], r["tier"]) for r in rows)
    for (s_, t_), n in sorted(cnt.items()):
        ok = n == need[t_] or (t_ == 1 and s_ < "1995-96" and n == 462)
        if not ok:
            print(f"تنبيه: الموسم {s_} الدرجة {t_} فيه {n} مباراة بدل {need[t_]}")
    rows.sort(key=lambda r: (r["date"], r["home"]))
    names = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    idx = {n: i for i, n in enumerate(names)}
    seasons_l = sorted({r["season"] for r in rows})
    sidx = {s: i for i, s in enumerate(seasons_l)}
    data = dict(teams=names, seasons=seasons_l,
                rows=[[sidx[r["season"]], r["tier"], ymd(r["date"]), idx[r["home"]], idx[r["away"]], r["hg"], r["ag"]] for r in rows],
                note="الدرجة الأولى منذ 1992-93 والثانية منذ 1998-99 (إنجلترا)")
    json.dump(data, open(f"{OUT}/clubs.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("أندية:", len(names), "مباريات:", len(rows), "مواسم:", seasons_l[0], "→", seasons_l[-1])


# ---------------------------------------------------------------- المنتخبات
def k_of(t):
    t = t.lower()
    if t == "fifa world cup":
        return 60
    if "qualification" in t:
        return 40
    if t in ("uefa euro", "copa américa", "african cup of nations", "afc asian cup", "gold cup", "concacaf championship",
             "confederations cup", "oceania nations cup", "uefa nations league finals"):
        return 50
    if "nations league" in t:
        return 40
    if t == "friendly":
        return 20
    return 30


def gmult(gd):
    gd = abs(gd)
    return 1.0 if gd <= 1 else (1.5 if gd == 2 else (11 + gd) / 8)


HOME_ADV = 100.0


def probs(diff, scale, draw):
    sig = lambda x: 1 / (1 + math.exp(-x))
    x = diff / scale
    ph = sig(x - draw)
    pdh = sig(x + draw)
    p = [ph, max(pdh - ph, 1e-6), max(1 - pdh, 1e-6)]
    s = sum(p)
    return [v / s for v in p]


def run_elo(rows, scale, draw, until=None, eval_from=None):
    r, preds, outs = {}, [], []
    for m in rows:
        a, b = m["home"], m["away"]
        ra, rb = r.get(a, 1500.0), r.get(b, 1500.0)
        adv = 0.0 if m["neutral"] else HOME_ADV
        diff = ra + adv - rb
        if eval_from is not None and m["date"] >= eval_from and (until is None or m["date"] <= until):
            preds.append(probs(diff, scale, draw))
            outs.append(0 if m["hg"] > m["ag"] else (1 if m["hg"] == m["ag"] else 2))
        w = 1.0 if m["hg"] > m["ag"] else (0.5 if m["hg"] == m["ag"] else 0.0)
        we = 1 / (10 ** (-(ra + adv - rb) / 400) + 1)
        d = k_of(m["tour"]) * gmult(m["hg"] - m["ag"]) * (w - we)
        r[a], r[b] = ra + d, rb - d
    return r, preds, outs


def metrics(preds, outs):
    n = len(outs)
    acc = sum(1 for p, o in zip(preds, outs) if max(range(3), key=lambda i: p[i]) == o) / n
    ll = -sum(math.log(p[o]) for p, o in zip(preds, outs)) / n
    return acc, ll


def build_nations():
    rows = []
    with open(os.path.join(HERE, "..", "data", "international", "results.csv"), encoding="utf-8") as f:
        for x in csv.DictReader(f):
            if x["home_score"] in ("", "NA") or x["away_score"] in ("", "NA"):
                continue
            rows.append(dict(date=datetime.strptime(x["date"], "%Y-%m-%d"), home=x["home_team"], away=x["away_team"],
                             hg=int(x["home_score"]), ag=int(x["away_score"]), tour=x["tournament"], neutral=x["neutral"] == "TRUE"))
    rows.sort(key=lambda m: m["date"])
    d_train_end, d_test = datetime(2009, 12, 31), datetime(2010, 1, 1)
    best = (9e9, None)
    for scale, draw in itertools.product([150, 175, 200, 225, 250, 300, 400], [0.3, 0.5, 0.6, 0.7, 0.8, 1.0]):
        _, p, o = run_elo([m for m in rows if m["date"] <= d_train_end], scale, draw, eval_from=datetime(1990, 1, 1))
        acc, ll = metrics(p, o)
        if ll < best[0]:
            best = (ll, (scale, draw))
    scale, draw = best[1]
    _, p, o = run_elo(rows, scale, draw, eval_from=d_test)
    acc, ll = metrics(p, o)
    home_acc = sum(1 for x in o if x == 0) / len(o)
    # الأهم: مباريات المنافسات فقط (بلا الودية) ثم آخر 8 سنوات
    _, p2, o2 = run_elo(rows, scale, draw, eval_from=datetime(2018, 1, 1))
    acc2, ll2 = metrics(p2, o2)
    ratings, _, _ = run_elo(rows, scale, draw)
    names = sorted({m["home"] for m in rows} | {m["away"] for m in rows})
    tours = sorted({m["tour"] for m in rows})
    idx = {n: i for i, n in enumerate(names)}
    tidx = {t: i for i, t in enumerate(tours)}
    last = {}
    for m in rows:
        last[m["home"]] = last[m["away"]] = ymd(m["date"])
    data = dict(teams=names, tours=tours,
                rows=[[ymd(m["date"]), idx[m["home"]], idx[m["away"]], m["hg"], m["ag"], tidx[m["tour"]], 1 if m["neutral"] else 0] for m in rows],
                elo=[round(ratings.get(n, 1500.0)) for n in names], last=[last.get(n, 0) for n in names],
                params=dict(scale=scale, draw=draw, home_adv=HOME_ADV))
    json.dump(data, open(f"{OUT}/nations.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    bt = dict(params=dict(scale=scale, draw=draw), train="≤2009", test_from="2010-01-01", matches=len(o), acc=round(acc, 4),
              logloss=round(ll, 4), always_home=round(home_acc, 4),
              recent=dict(from_="2018-01-01", matches=len(o2), acc=round(acc2, 4), logloss=round(ll2, 4)))
    json.dump(bt, open(f"{OUT}/nations_backtest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("منتخبات:", len(names), "مباريات:", len(rows), "| اختبار 2010→:", bt)
    top = sorted(((ratings[n], n) for n in names if last.get(n, 0) >= 20250101), reverse=True)[:10]
    print("أعلى 10:", [(n, round(v)) for v, n in top])


if __name__ == "__main__":
    build_clubs()
    build_nations()
