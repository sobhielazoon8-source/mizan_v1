#!/usr/bin/env python3
"""تجربة تحسين الدقة لكل دوري بأمانة منهجية:
  - تسخين: أول موسمين. ضبط المعاملات: المواسم 3 … (ن-3). اختبار نهائي مجمّد: آخر 3 مواسم مكتملة.
  - نعتمد معاملات دوري ما فقط إذا تحسّن logloss على مواسم الاختبار الثلاثة بمقدار ≥ 0.002 ولم تنخفض الدقة.
  - تجربة «أيام الراحة» (فارق أيام الراحة بين الفريقين) تُقاس بالمعيار نفسه.
الاستعمال: OF_ROOT=<openfootball> python3 -I tools/tune_leagues.py [رمز_دوري ...] > tune_result.json"""
import itertools, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
os.environ.setdefault("OF_ROOT", os.path.join(HERE, "..", "openfootball"))
import backtest as bt
import predict_league as PL

DEF_E, DEF_P, DEF_W = PL.PE, PL.PP, 0.5


class EloRest(bt.Elo):
    """Elo + تصحيح لفارق أيام الراحة (محدود بين -3 و+3 أيام)."""
    def __init__(self, beta=0.0, **kw):
        super().__init__(**kw)
        self.beta, self.last = beta, {}
    def predict(self, m):
        rh = min(max((m["date"] - self.last[m["home"]]).days, 2), 8) if m["home"] in self.last else 5
        ra = min(max((m["date"] - self.last[m["away"]]).days, 2), 8) if m["away"] in self.last else 5
        d = max(-3, min(3, rh - ra))
        diff = (self.rating(m["home"]) + self.home - self.rating(m["away"])) / self.scale + self.beta * d
        return bt.ordered_probs(diff, self.draw)
    def update(self, m):
        super().update(m)
        self.last[m["home"]] = m["date"]; self.last[m["away"]] = m["date"]


def ll(model, rows, start, end):
    p, o = bt.run(model, rows, start, end)
    m = bt.metrics(p, o)
    return m["logloss"], m["accuracy"], len(o)


def main(codes):
    out = {}
    for code in codes:
        hist, cur_played, upcoming, cur_s, _ = PL.load(code)
        rows = [r for r in hist if r["season"] != cur_s]
        seasons = sorted({r["season"] for r in rows})
        s_tune, s_tune_end, s_test = seasons[2], seasons[-4], seasons[-3]
        # 1) ضبط Elo وحده على مواسم الضبط
        best_e = (9, None)
        for k, home, draw, shrink in itertools.product([10, 15, 20, 25], [50, 65, 80, 95], [0.45, 0.55, 0.65], [0.1, 0.15, 0.25]):
            v = ll(bt.Elo(k, home, draw, shrink), rows, s_tune, s_tune_end)[0]
            if v < best_e[0]: best_e = (v, dict(k=k, home=home, draw=draw, shrink=shrink))
        best_p = (9, None)
        for lr, home, shrink in itertools.product([0.015, 0.02, 0.03, 0.04], [0.2, 0.3, 0.4], [0.05, 0.1, 0.2]):
            v = ll(bt.PoissonDC(lr, home, 0.2, shrink), rows, s_tune, s_tune_end)[0]
            if v < best_p[0]: best_p = (v, dict(lr=lr, home=home, shrink=shrink))
        def blend(pe, pp, w):
            return bt.Blend(bt.Elo(**pe), bt.PoissonDC(pp["lr"], pp["home"], 0.2, pp["shrink"]), w)
        best_w = (9, 0.5)
        for w in (0.3, 0.4, 0.5, 0.6, 0.7):
            v = ll(blend(best_e[1], best_p[1], w), rows, s_tune, s_tune_end)[0]
            if v < best_w[0]: best_w = (v, w)
        # 2) اختبار مجمّد على آخر 3 مواسم
        base = ll(blend(DEF_E, DEF_P, DEF_W), rows, s_test, None)
        tuned = ll(blend(best_e[1], best_p[1], best_w[1]), rows, s_test, None)
        # 3) أيام الراحة (فوق المعاملات الافتراضية)
        rest = {}
        for beta in (0.0, 0.01, 0.02, 0.04):
            e = EloRest(beta=beta, **DEF_E)
            rest[beta] = ll(bt.Blend(e, bt.PoissonDC(DEF_P["lr"], DEF_P["home"], 0.2, DEF_P["shrink"]), 0.5), rows, s_test, None)
        adopt = tuned[0] <= base[0] - 0.002 and tuned[1] >= base[1] - 0.002
        out[code] = dict(
            seasons=f"{seasons[0]}→{seasons[-1]}", tune_window=f"{s_tune}→{s_tune_end}", test_window=f"{s_test}→{seasons[-1]}", test_n=base[2],
            default=dict(logloss=round(base[0], 4), acc=round(base[1], 4)),
            tuned=dict(logloss=round(tuned[0], 4), acc=round(tuned[1], 4), elo=best_e[1], poisson=best_p[1], w=best_w[1]),
            adopt=adopt,
            rest={str(b): dict(logloss=round(v[0], 4), acc=round(v[1], 4)) for b, v in rest.items()})
        print(code, json.dumps(out[code], ensure_ascii=False), file=sys.stderr)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:] or ["es", "de", "it", "fr"])
