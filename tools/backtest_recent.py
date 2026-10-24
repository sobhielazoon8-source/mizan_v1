"""اختبار زمني على المواسم الحديثة 2020-21 إلى 2025-26 (يكرّر نفس النموذج بنفس المعاملات دون إعادة ضبط).
التشغيل: OF_DIR=openfootball/england python3 -I tools/backtest_recent.py"""
import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
os.environ.setdefault('OF_DIR', '/home/claude/openfootball/england')
import backtest as bt, predict as pr
hist, cur, up = pr.load_all()
rows = sorted(hist, key=lambda r: (r['season'], r['date']))
seasons = sorted({r['season'] for r in rows}); print(seasons[0], seasons[-1], len(rows))
def mk():
    return bt.Blend(bt.Elo(**pr.PE), bt.PoissonDC(pr.PP['lr'], pr.PP['home'], 0.2, pr.PP['shrink']), 0.5)
def seg(a, b):
    p, o = bt.run(mk(), rows, a, b)
    m = bt.metrics(p, o)
    ah = sum(1 for x in o if x == 0) / len(o)
    # draws
    dr = sum(1 for x in o if x == 1) / len(o)
    print(f"{a}→{b}: n={len(o)} دقة={m['accuracy']:.3%} logloss={m['logloss']:.4f} مضيف_دائماً={ah:.3%} تعادلات={dr:.1%}")
seg('2005-06', '2019-20')
seg('2020-21', '2025-26')
for s in ['2020-21','2021-22','2022-23','2023-24','2024-25','2025-26']:
    seg(s, s)
