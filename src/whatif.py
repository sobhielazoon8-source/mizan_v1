"""«ماذا لو؟» وكاشف المفاجآت.

ماذا لو: لا نعيد المحاكاة. أثناء محاكاة الموسم الأصلية (10,000 مرة) نسجّل لكل مباراة قريبة نتيجتها في كل تشغيل،
ثم نحسب احتمالات اللقب/المراكز/الهبوط مشروطةً بنتيجة تلك المباراة (فوز المضيف/تعادل/فوز الضيف) من التشغيلات التي وقعت فيها.
هذا تقدير إحصائي سليم، وتُخفى النتيجة النادرة (أقل من MIN_N تشغيل) بدل عرض رقم مشكوك فيه.

كاشف المفاجآت: لكل مباراة منتهية في الموسم الجاري نحسب ما كان النموذج سيعطيه من احتمال للنتيجة التي وقعت قبل المباراة
(تشغيل زمني متدرّج: يتنبأ بما قبلها فقط)، ونعرض الأقل احتمالاً."""
from datetime import timedelta

MIN_N = 250


class WhatIf:
    def __init__(self, rest, teams, cuts, today, fixtures, days=8, cap=14):
        """rest: قائمة (home, away, ...) بنفس ترتيب المحاكاة. cuts=(k_title, k_top, k_rel_from)."""
        self.cuts = cuts
        self.teams = list(teams)
        pos = {}
        for i, r in enumerate(rest):
            pos.setdefault((r[0], r[1]), i)
        lim = (today + timedelta(days=days)).strftime("%Y-%m-%d")
        chosen = [f for f in sorted(fixtures, key=lambda f: (f["date"], f["home"])) if f["date"] <= lim and (f["home"], f["away"]) in pos][:cap]
        self.track = {(f["home"], f["away"]): pos[(f["home"], f["away"])] for f in chosen}
        self.n = {k: [0, 0, 0] for k in self.track}
        self.c = {k: [{t: [0, 0, 0] for t in self.teams} for _ in range(3)] for k in self.track}

    def record(self, outs, order):
        k1, k2, k3 = self.cuts
        top1, top2, rel = order[:k1], order[:k2], order[k3:]
        for k, ri in self.track.items():
            o = outs[ri]
            self.n[k][o] += 1
            cc = self.c[k][o]
            for t in top1:
                cc[t][0] += 1
            for t in top2:
                cc[t][1] += 1
            for t in rel:
                cc[t][2] += 1

    def attach(self, fixtures):
        """يُضيف f['wi'] = {n:[..3], t:{فريق: [9 أرقام: (لقب، قمة، هبوط) × (فوز مضيف، تعادل، فوز ضيف)] أو None}}."""
        done = 0
        for f in fixtures:
            k = (f["home"], f["away"])
            if k not in self.track:
                continue
            n = self.n[k]
            t_out = {}
            for t in self.teams:
                vals = []
                for o in range(3):
                    if n[o] < MIN_N:
                        vals += [None, None, None]
                    else:
                        c = self.c[k][o][t]
                        vals += [round(c[0] / n[o], 3), round(c[1] / n[o], 3), round(c[2] / n[o], 3)]
                t_out[t] = vals
            f["wi"] = dict(n=n, t=t_out)
            done += 1
        return done


def upset_list(pre, results, limit=12):
    """pre: {(date, home, away): [ph, pd, pa]}؛ results: قائمة نتائج الموسم الجاري. يعيد الأقل احتمالاً للنتيجة الواقعة."""
    out = []
    for r in results:
        p = pre.get((r["date"], r["home"], r["away"]))
        if not p:
            continue
        o = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
        out.append(dict(date=r["date"], md=r.get("md"), home=r["home"], away=r["away"], hg=r["hg"], ag=r["ag"],
                        ph=round(p[0], 4), pd=round(p[1], 4), pa=round(p[2], 4), o=o, po=round(p[o], 4)))
    out.sort(key=lambda x: (x["po"], x["date"]))
    return out[:limit]
