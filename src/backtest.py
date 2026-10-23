#!/usr/bin/env python3
"""اختبار رجعي (walk-forward) لتوقع نتائج الدوري الإنجليزي الممتاز.

كل مباراة يُتنبأ بها بالمعلومات المتاحة قبلها فقط، ثم تُحدَّث التقييمات.
المعاملات تُختار على مواسم التدريب فقط (1992-93 إلى 2004-05) ثم تُجمَّد،
ويُقاس الأداء على مواسم الاختبار (2005-06 إلى 2020-21).
"""
import csv, glob, math, os, re, sys, itertools, json
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("HISTORY_DIR", os.path.join(HERE, "..", "data", "history"))
TRAIN_END = "2004-05"   # آخر موسم تدريب (يشمل)


def load():
    rows = []
    for path in sorted(glob.glob(f"{ROOT}/*/*/eng.1.csv")):
        season = path.split("/")[-2]
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                m = re.match(r"^\s*(\d+)-(\d+)\s*$", r["FT"] or "")
                if not m:
                    continue
                d = datetime.strptime(r["Date"].strip(), "%a %b %d %Y")
                rows.append(dict(season=season, date=d, home=r["Team 1"].strip(),
                                 away=r["Team 2"].strip(), hg=int(m.group(1)), ag=int(m.group(2))))
    rows.sort(key=lambda x: (x["date"], x["home"]))
    return rows


def outcome(hg, ag):
    return 0 if hg > ag else (1 if hg == ag else 2)  # 0 فوز المضيف، 1 تعادل، 2 فوز الضيف


# ---------- مقاييس ----------
def metrics(preds, outs):
    n = len(outs)
    acc = sum(1 for p, o in zip(preds, outs) if max(range(3), key=lambda i: p[i]) == o) / n
    ll = -sum(math.log(max(p[o], 1e-12)) for p, o in zip(preds, outs)) / n
    br = sum(sum((p[i] - (1 if i == o else 0)) ** 2 for i in range(3)) for p, o in zip(preds, outs)) / n
    # RPS (مقياس ترتيبي مناسب لنتائج مرتبة فوز/تعادل/خسارة)
    rps = 0.0
    for p, o in zip(preds, outs):
        cp = [p[0], p[0] + p[1]]
        co = [1 if o == 0 else 0, 1 if o <= 1 else 0]
        rps += sum((cp[i] - co[i]) ** 2 for i in range(2)) / 2
    return dict(n=n, accuracy=acc, logloss=ll, brier=br, rps=rps / n)


# ---------- نماذج ----------
class Frequency:
    """خط أساس: النسب التاريخية المتراكمة للنتائج فقط (لا يعرف الفرق)."""
    def __init__(self): self.c = [1, 1, 1]
    def predict(self, m):
        s = sum(self.c); return [x / s for x in self.c]
    def update(self, m): self.c[outcome(m["hg"], m["ag"])] += 1
    def new_season(self): pass


def ordered_probs(diff, draw):
    """احتمالات (مضيف، تعادل، ضيف) من فارق القوة بنموذج لوجستي ترتيبي."""
    sig = lambda x: 1 / (1 + math.exp(-x))
    p_home_or_draw = sig(diff + draw)      # P(المضيف لا يخسر)
    p_home = sig(diff - draw)              # P(المضيف يفوز)
    ph = p_home
    pd = max(p_home_or_draw - p_home, 1e-6)
    pa = max(1 - p_home_or_draw, 1e-6)
    s = ph + pd + pa
    return [ph / s, pd / s, pa / s]


class Elo:
    def __init__(self, k=20.0, home=60.0, draw=0.45, shrink=0.25, newteam=1420.0, gd=True):
        self.k, self.home, self.draw, self.shrink, self.newteam, self.gd = k, home, draw, shrink, newteam, gd
        self.r = {}
        self.scale = 400 / math.log(10)  # يحوّل نقاط Elo إلى وحدات لوجستية
    def rating(self, t): return self.r.get(t, self.newteam)
    def predict(self, m):
        diff = (self.rating(m["home"]) + self.home - self.rating(m["away"])) / self.scale
        return ordered_probs(diff, self.draw)
    def update(self, m):
        rh, ra = self.rating(m["home"]), self.rating(m["away"])
        exp_h = 1 / (1 + 10 ** (-(rh + self.home - ra) / 400))
        o = outcome(m["hg"], m["ag"])
        s = 1.0 if o == 0 else (0.5 if o == 1 else 0.0)
        mult = 1.0
        if self.gd:
            g = abs(m["hg"] - m["ag"])
            mult = 1.0 if g <= 1 else (1.5 if g == 2 else (11 + g) / 8)
        delta = self.k * mult * (s - exp_h)
        self.r[m["home"]] = rh + delta
        self.r[m["away"]] = ra - delta
    def new_season(self):
        if not self.r: return
        mean = sum(self.r.values()) / len(self.r)
        for t in self.r: self.r[t] += (mean - self.r[t]) * self.shrink


def pois(k, lam): return math.exp(-lam) * lam ** k / math.factorial(k)


class PoissonDC:
    """قوة هجوم ودفاع لكل فريق تُحدَّث تدريجياً (انحدار تدرجي لاحتمال بواسون)."""
    def __init__(self, lr=0.04, home=0.25, base=0.20, shrink=0.2, rho=0.0):
        self.lr, self.home, self.base, self.shrink = lr, home, base, shrink
        self.att, self.dfn = {}, {}
        self.hscale = None
    def _g(self, d, t): return d.get(t, 0.0)
    def lams(self, m):
        h, a = m["home"], m["away"]
        lh = math.exp(self.base + self.home + self._g(self.att, h) - self._g(self.dfn, a))
        la = math.exp(self.base + self._g(self.att, a) - self._g(self.dfn, h))
        return lh, la
    def predict(self, m):
        lh, la = self.lams(m)
        P = [[pois(i, lh) * pois(j, la) for j in range(9)] for i in range(9)]
        ph = sum(P[i][j] for i in range(9) for j in range(9) if i > j)
        pd = sum(P[i][i] for i in range(9))
        pa = sum(P[i][j] for i in range(9) for j in range(9) if i < j)
        s = ph + pd + pa
        return [ph / s, pd / s, pa / s]
    def update(self, m):
        lh, la = self.lams(m)
        eh, ea = m["hg"] - lh, m["ag"] - la
        h, a = m["home"], m["away"]
        self.att[h] = self._g(self.att, h) + self.lr * eh
        self.dfn[a] = self._g(self.dfn, a) - self.lr * eh
        self.att[a] = self._g(self.att, a) + self.lr * ea
        self.dfn[h] = self._g(self.dfn, h) - self.lr * ea
    def new_season(self):
        for d in (self.att, self.dfn):
            for t in d: d[t] *= (1 - self.shrink)


class Blend:
    def __init__(self, a, b, w=0.5): self.a, self.b, self.w = a, b, w
    def predict(self, m):
        pa, pb = self.a.predict(m), self.b.predict(m)
        return [self.w * x + (1 - self.w) * y for x, y in zip(pa, pb)]
    def update(self, m): self.a.update(m); self.b.update(m)
    def new_season(self): self.a.new_season(); self.b.new_season()


def run(model, rows, start, end=None):
    """يمشي زمنياً: يتنبأ قبل المباراة، يسجّل إن كانت ضمن [start, end]، ثم يحدّث."""
    preds, outs, prev = [], [], None
    for m in rows:
        if prev is not None and m["season"] != prev:
            model.new_season()
        prev = m["season"]
        if m["season"] >= start and (end is None or m["season"] <= end):
            preds.append(model.predict(m)); outs.append(outcome(m["hg"], m["ag"]))
        model.update(m)
    return preds, outs


def tune(rows):
    """يختار المعاملات على مواسم التدريب فقط (1993-94 إلى 2004-05) بمعيار logloss."""
    best_e = (1e9, None)
    for k, home, draw, shrink in itertools.product([10, 15, 20, 30], [40, 60, 80], [0.35, 0.45, 0.55], [0.15, 0.3]):
        p, o = run(Elo(k, home, draw, shrink), [r for r in rows if r["season"] <= TRAIN_END], "1993-94")
        v = metrics(p, o)["logloss"]
        if v < best_e[0]: best_e = (v, dict(k=k, home=home, draw=draw, shrink=shrink))
    best_p = (1e9, None)
    for lr, home, shrink in itertools.product([0.02, 0.04, 0.06, 0.09], [0.2, 0.3], [0.1, 0.3, 0.5]):
        p, o = run(PoissonDC(lr, home, 0.2, shrink), [r for r in rows if r["season"] <= TRAIN_END], "1993-94")
        v = metrics(p, o)["logloss"]
        if v < best_p[0]: best_p = (v, dict(lr=lr, home=home, shrink=shrink))
    return best_e, best_p


def main():
    rows = load()
    seasons = sorted({r["season"] for r in rows})
    print(f"مباريات: {len(rows)} | مواسم: {len(seasons)} ({seasons[0]} → {seasons[-1]})")
    (ve, pe), (vp, pp) = tune(rows)
    print("معاملات Elo المختارة على التدريب:", pe, f"logloss={ve:.4f}")
    print("معاملات بواسون المختارة على التدريب:", pp, f"logloss={vp:.4f}")

    test_start = "2005-06"
    models = {
        "1) نسب تاريخية فقط (لا يعرف الفرق)": Frequency(),
        "2) Elo": Elo(**pe),
        "3) هجوم/دفاع (بواسون)": PoissonDC(pp["lr"], pp["home"], 0.2, pp["shrink"]),
        "4) مزيج Elo + بواسون": Blend(Elo(**pe), PoissonDC(pp["lr"], pp["home"], 0.2, pp["shrink"]), 0.5),
    }
    res = {}
    for name, mdl in models.items():
        p, o = run(mdl, rows, test_start)
        res[name] = (metrics(p, o), p, o)
    # دائماً «المضيف يفوز»
    outs = res["2) Elo"][2]
    always_home = sum(1 for o in outs if o == 0) / len(outs)

    print(f"\nمباريات الاختبار: {len(outs)} (من {test_start})")
    print(f"دقة «المضيف دائماً يفوز»: {always_home:.3%}")
    print(f"{'النموذج':44s} {'الدقة':>8s} {'LogLoss':>9s} {'Brier':>8s} {'RPS':>8s}")
    for name, (m, _, _) in res.items():
        print(f"{name:44s} {m['accuracy']:8.3%} {m['logloss']:9.4f} {m['brier']:8.4f} {m['rps']:8.4f}")

    # معايرة المزيج: هل 60% تعني فعلاً ~60%؟
    _, p, o = res["4) مزيج Elo + بواسون"]
    print("\nمعايرة المزيج (احتمال أعلى نتيجة متوقعة مقابل ما حدث فعلاً):")
    bins = [(0.33, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 1.01)]
    for lo, hi in bins:
        sel = [(pp_, oo) for pp_, oo in zip(p, o) if lo <= max(pp_) < hi]
        if sel:
            hit = sum(1 for pp_, oo in sel if max(range(3), key=lambda i: pp_[i]) == oo) / len(sel)
            avg = sum(max(pp_) for pp_, _ in sel) / len(sel)
            print(f"  توقع {avg:5.1%}  →  تحقق {hit:5.1%}   (عدد {len(sel)})")

    # دقة كل موسم اختبار للمزيج
    by = {}
    for m, pp_, oo in zip([r for r in rows if r["season"] >= test_start], p, o):
        s = by.setdefault(m["season"], [0, 0])
        s[0] += 1; s[1] += 1 if max(range(3), key=lambda i: pp_[i]) == oo else 0
    print("\nدقة المزيج في كل موسم:", {k: f"{v[1] / v[0]:.1%}" for k, v in by.items()})

    out = {k: v[0] for k, v in res.items()}
    out["always_home_acc"] = always_home
    out["params_elo"], out["params_poisson"] = pe, pp
    json.dump(out, open(os.path.join(HERE, "..", "backtest_result.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
