#!/usr/bin/env python3
"""يصدّر سجلّ مباريات الدوريات الأوروبية (clubs_es/de/it/fr.json) بنفس بنية clubs.json لموسوعة التطبيق.
الاستعمال: OF_ROOT=<مجلد openfootball> python3 -I tools/build_league_history.py <مجلد الإخراج>"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import leagues as L
import league_names as N

ROOT = os.environ.get("OF_ROOT", os.path.join(HERE, "..", "openfootball"))
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for code, cfg in L.LEAGUES.items():
    data = L.load_league(code, os.path.join(ROOT, cfg["repo"]))
    rows = []
    # الموسم الجاري غير مكتمل: نستبعده كي لا يُحتسب «لقب» لمتصدر مؤقت (يُعرض من بيانات الموسم الحالي)
    seasons = sorted(data)[:-1]
    for si, s in enumerate(seasons):
        for r in data[s]:
            if r["hg"] is None:
                continue
            rows.append((si, r["date"], N.canon(code, r["home"]), N.canon(code, r["away"]), r["hg"], r["ag"]))
    rows.sort(key=lambda x: (x[1], x[2]))
    names = sorted({x[2] for x in rows} | {x[3] for x in rows})
    idx = {n: i for i, n in enumerate(names)}
    j = dict(teams=names, seasons=seasons,
             rows=[[si, 1, int(d.strftime("%Y%m%d")), idx[h], idx[a], hg, ag] for si, d, h, a, hg, ag in rows],
             note=f"{cfg['ar']}: الدرجة الأولى منذ {seasons[0]}", names_ar=N.AR[code])
    json.dump(j, open(os.path.join(out, f"clubs_{code}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(code, len(names), "أندية", len(rows), "مباراة", seasons[0], "→", seasons[-1])
