"""مسجّلو الأهداف من ملفات openfootball (متوفرة للموسم 2025-26 فصاعداً فقط).
تُستخرج من أسطر «(مسجلو المضيف; مسجلو الضيف)» التي تلي سطر المباراة، ثم يُتحقق أن عدد أهداف كل جانب = النتيجة،
وإلا نُسقط تفاصيل تلك المباراة بدل أن ننشر أرقاماً مشكوكاً فيها."""
import fd
import re, unicodedata

TOKEN = re.compile(r"(?:(?P<name>[^\d,;()]+?)\s+)?(?P<min>\d+(?:\+\d+)?)'(?P<flag>\((?:p|og|pen|o\.g\.)\))?", re.I)


def clean_name(n):
    n = re.sub(r"\s+", " ", n).strip(" ,;")
    words = []
    for w in n.split(" "):
        if len(w) > 1 and w.isupper():
            w = w.capitalize() if "-" not in w else "-".join(x.capitalize() for x in w.split("-"))
        words.append(w)
    return " ".join(words)


def strip_key(n):
    n = unicodedata.normalize("NFKD", n.casefold())
    return "".join(c for c in n if not unicodedata.combining(c))


def parse_goals(raw, hg, ag):
    """يعيد [[جانب(0/1), دقيقة نصاً, اسم, علم(0 عادي/1 ركلة جزاء/2 هدف عكسي)]] أو None إن لم تتطابق الأعداد."""
    if not raw or hg is None:
        return None
    body = raw.strip()
    if body.startswith("("):
        body = body[1:]
    if body.endswith(")"):
        body = body[:-1]
    sides = body.split(";")
    if len(sides) > 2:
        return None
    if len(sides) == 1:
        # قائمة واحدة بلا فاصل: تُنسب للجانب الوحيد الذي سجّل، وإلا فالمعنى غامض فنُسقطها
        if hg == 0 and ag > 0:
            only = 1
        elif ag == 0 and hg > 0:
            only = 0
        else:
            return None
        sides = ["", ""]
        sides[only] = body
    out = []
    for si, part in enumerate(sides):
        last = None
        for m in TOKEN.finditer(part):
            name = m.group("name")
            if name:
                last = clean_name(name)
            if not last:
                return None
            fl = (m.group("flag") or "").lower()
            out.append([si, m.group("min"), last, 2 if "og" in fl or "o.g" in fl else (1 if fl else 0)])
    n0 = sum(1 for g in out if g[0] == 0)
    n1 = sum(1 for g in out if g[0] == 1)
    if (n0, n1) != (hg, ag):
        return None
    return out


def attach(rows, canon=lambda n: n):
    """rows: مباريات parse_file. يعيد {(YYYY-MM-DD, مضيف, ضيف): قائمة أهداف} للمباريات الصالحة."""
    res, total, ok = {}, 0, 0
    for r in rows:
        if r.get("hg") is None:
            continue
        total += 1
        g = parse_goals(r.get("goals_raw"), r["hg"], r["ag"]) if r.get("goals_raw") else ([] if r["hg"] + r["ag"] == 0 else None)
        if g is None:
            continue
        ok += 1
        res[(r["date"].strftime("%Y-%m-%d"), canon(r["home"]), canon(r["away"]))] = g
    return res, total, ok


def top_scorers(rows, goals_by_match, canon=lambda n: n, limit=40):
    """جدول الهدّافين من المباريات التي توفّرت تفاصيلها. الهدف العكسي لا يُحتسب للاعب."""
    tally = {}
    for r in rows:
        if r.get("hg") is None:
            continue
        key = (r["date"].strftime("%Y-%m-%d"), canon(r["home"]), canon(r["away"]))
        for side, _mn, name, flag in goals_by_match.get(key, []):
            if flag == 2:
                continue
            team = canon(r["home"] if side == 0 else r["away"])
            k = (strip_key(name), team)
            t = tally.setdefault(k, {"name": name, "team": team, "g": 0, "p": 0})
            t["g"] += 1
            t["p"] += 1 if flag == 1 else 0
            if len(name) > len(t["name"]):
                t["name"] = name
    best = sorted(tally.values(), key=lambda t: (-t["g"], t["p"], t["name"]))
    return [[t["name"], t["team"], t["g"], t["p"]] for t in best[:limit]]


_DROP = {"fc", "afc", "cf", "ac", "as", "us", "sc", "rc", "rcd", "ud", "cd", "ssc", "fk", "sv", "vfb", "vfl", "tsg", "the"}


def _norm(n):
    n = strip_key(n)
    words = re.findall(r"[a-z]+", n)
    return " ".join(w for w in words if w not in _DROP)


def match_team(fd_name, ours):
    """يطابق اسم نادٍ من football-data.org مع أسماء فرقنا المعتمدة؛ يعيد None إن لم يوجد تطابق وحيد."""
    t = _norm(fd_name)
    if not t:
        return None
    exact = [o for o in ours if _norm(o) == t]
    if len(exact) == 1:
        return exact[0]
    part = [o for o in ours if t in _norm(o) or _norm(o) in t]
    return part[0] if len(part) == 1 else None


def fetch_fd_scorers(fd_code, ours, limit=30):
    """الهدّافون الحاليون من football-data.org (المستوى المجاني). يعيد None عند أي خلل ولا يوقف البناء.
    الصيغة: [اسم، فريق، أهداف، تمريرات حاسمة (أو None)، ركلات جزاء (أو None), مباريات]"""
    import json, os, urllib.request
    tok = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not tok:
        return None
    try:
        j = fd.get(f"https://api.football-data.org/v4/competitions/{fd_code}/scorers?limit={limit}", tok, 30)
        top = []
        for x in j.get("scorers", []):
            pl, tm = x.get("player") or {}, x.get("team") or {}
            if not pl.get("name") or x.get("goals") is None:
                continue
            team = match_team(tm.get("name", ""), ours) or tm.get("name", "")
            top.append([pl["name"], team, int(x["goals"]), x.get("assists"), x.get("penalties"), x.get("playedMatches")])
        season = ((j.get("filters") or {}).get("season")) or ""
        print(f"[{fd_code}] هدّافون من football-data.org: {len(top)}")
        return dict(source="football-data.org", season=str(season), top=top) if len(top) >= 5 else None
    except Exception as e:
        print(f"[{fd_code}] تعذّر جلب الهدّافين:", type(e).__name__, str(e)[:100])
        return None
