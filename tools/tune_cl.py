#!/usr/bin/env python3
"""ضبط معاملات دوري الأبطال بالبروتوكول نفسه: ضبط على المواسم الوسطى واختبار مجمّد على آخر 3 مواسم مكتملة.
CL_ROOT=<مجلد> python3 -I tools/tune_cl.py"""
import itertools, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import backtest as bt
import predict_cl as C
import league_names as N

known = [x for c in ("es", "de", "it", "fr") for x in N.AR[c]]
seasons = sorted(d for d in os.listdir(C.CL_ROOT) if d[:2] == "20" and os.path.exists(os.path.join(C.CL_ROOT, d, "cl.txt")))
rows = []
for s in seasons[:-1] if len(sys.argv) < 2 else seasons:
    rows += [r for r in C.parse_cl(os.path.join(C.CL_ROOT, s, "cl.txt"), s, known) if r["hg"] is not None]
rows.sort(key=lambda r: (r["date"], r["home"]))
ss = sorted({r["season"] for r in rows})
tune_a, tune_b, test_a = ss[2], ss[-4], ss[-3]


def ll(model, a, b):
    p, o = bt.run(model, rows, a, b)
    m = bt.metrics(p, o)
    return m["logloss"], m["accuracy"], len(o)


def mk(pe, pp, w=0.5):
    return bt.Blend(bt.Elo(**pe), bt.PoissonDC(pp["lr"], pp["home"], 0.2, pp["shrink"]), w)


be = (9, None)
for k, home, draw, shrink in itertools.product([10, 15, 20, 30], [40, 60, 80, 100], [0.45, 0.55, 0.65], [0.15, 0.25, 0.4]):
    v = ll(bt.Elo(k, home, draw, shrink), tune_a, tune_b)[0]
    if v < be[0]: be = (v, dict(k=k, home=home, draw=draw, shrink=shrink))
bp = (9, None)
for lr, home, shrink in itertools.product([0.015, 0.02, 0.03, 0.045], [0.2, 0.3, 0.4], [0.1, 0.2, 0.35]):
    v = ll(bt.PoissonDC(lr, home, 0.2, shrink), tune_a, tune_b)[0]
    if v < bp[0]: bp = (v, dict(lr=lr, home=home, shrink=shrink))
bw = min(((ll(mk(be[1], bp[1], w), tune_a, tune_b)[0], w) for w in (0.3, 0.5, 0.7)))
base = ll(mk(C.PE_CL, C.PP_CL, C.W_CL), test_a, None)
tuned = ll(mk(be[1], bp[1], bw[1]), test_a, None)
print(json.dumps(dict(tune=f"{tune_a}→{tune_b}", test=f"{test_a}→{ss[-1]}", test_n=base[2], current=dict(logloss=round(base[0], 4), acc=round(base[1], 4)),
                      tuned=dict(logloss=round(tuned[0], 4), acc=round(tuned[1], 4), elo=be[1], poisson=bp[1], w=bw[1])), ensure_ascii=False, indent=1))
