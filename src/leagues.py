"""إعدادات الدوريات الأوروبية وقراءة ملفاتها من openfootball (ترخيص CC0)."""
import os, re
from datetime import datetime

MONTHS = {m: i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}
DATE_RE = re.compile(r"^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(?P<mon>[A-Z][a-z]{2})\s+(?P<d>\d{1,2})(?:\s+(?P<y>\d{4}))?\s*$")
MD_RE = re.compile(r"(?:Matchday|Regular Season\s*-)\s*(\d+)")
MID_RE = re.compile(r"^\s*(?:(?P<h1>\d{1,2}):(?P<m1>\d{2})\s+)?(?P<home>[^\s()][^()]*?)\s{2,}(?P<hg>\d+)-(?P<ag>\d+)(?:\s*\(\d+-\d+\))?\s{2,}(?P<away>[^\s()][^()]*?)\s*$")

# مفتاح الدوري: (الاسم العربي، مجلد المستودع، نمط اسم الملف، المنطقة الزمنية، عدد الفرق، مباريات الموسم، فرق الهبوط، أول موسم نستعمله)
LEAGUES = {
    "es": dict(ar="الدوري الإسباني", repo="espana", tz="Europe/Madrid", teams=20, rel=3, first="2013-14",
               path=lambda root, s: f"{root}/{s}/1-liga.txt"),
    "de": dict(ar="الدوري الألماني", repo="deutschland", tz="Europe/Berlin", teams=18, rel=2, first="2013-14",
               path=lambda root, s: f"{root}/{s}/1-bundesliga.txt"),
    "it": dict(ar="الدوري الإيطالي", repo="italy", tz="Europe/Rome", teams=20, rel=3, first="2013-14",
               path=lambda root, s: f"{root}/{s}/1-seriea.txt"),
    "fr": dict(ar="الدوري الفرنسي", repo="france", tz="Europe/Paris", teams=None, rel=3, first="2014-15",
               path=lambda root, s: f"{root}/france/{s}_fr1.txt"),
}


def fr_teams(season):
    return 20 if season < "2023-24" else 18


def expected_teams(code, season):
    return fr_teams(season) if code == "fr" else LEAGUES[code]["teams"]


def seasons_available(code, root):
    out = []
    for s in range(2000, 2100):
        ss = f"{s}-{(s + 1) % 100:02d}"
        if ss < LEAGUES[code]["first"]:
            continue
        if os.path.exists(LEAGUES[code]["path"](root, ss)):
            out.append(ss)
    return out


def parse_file(path, season):
    y0 = int(season[:4])
    out, date, md, cur_time = [], None, None, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.lstrip().startswith("▪"):
                m = MD_RE.search(line)
                if m:
                    md = int(m.group(1))
                continue
            d = DATE_RE.match(line)
            if d:
                mon = MONTHS[d.group("mon")]
                year = int(d.group("y")) if d.group("y") else (y0 if mon >= 7 else y0 + 1)
                date = datetime(year, mon, int(d.group("d"))); cur_time = None
                continue
            if not date or not line.strip() or line.lstrip().startswith(("#", "(", "=")):
                continue
            tag = re.search(r"\s*\[(awarded|cancelled|postponed|abandoned)\]\s*$", line)
            if tag:
                line = line[:tag.start()].rstrip()
            tag = tag.group(1) if tag else None
            tm = re.match(r"^\s+(\d{1,2}):(\d{2})\s+", line)
            if tm:
                cur_time = (int(tm.group(1)), int(tm.group(2)))
            if " v " in line:
                body = re.sub(r"^\s+\d{1,2}:\d{2}\s+", "", line).strip()
                sc = re.search(r"\s(\d+)-(\d+)(?:\s*\(\d+-\d+\))?\s*$", body)
                hg = ag = None
                if sc:
                    hg, ag = int(sc.group(1)), int(sc.group(2)); body = body[:sc.start()].rstrip()
                parts = re.split(r"\s+v\s+", body)
                if len(parts) != 2:
                    raise ValueError(f"{path}: سطر غير مفهوم: {line!r}")
                if tag != "cancelled":
                    out.append(dict(season=season, date=date, home=parts[0].strip(), away=parts[1].strip(),
                                    hg=hg, ag=ag, md=md, time=cur_time))
                continue
            mid = MID_RE.match(line)
            if mid:
                if mid.group("h1"):
                    cur_time = (int(mid.group("h1")), int(mid.group("m1")))
                if tag != "cancelled":
                    out.append(dict(season=season, date=date, home=mid.group("home").strip(), away=mid.group("away").strip(),
                                    hg=int(mid.group("hg")), ag=int(mid.group("ag")), md=md, time=cur_time))
                continue
            # أي سطر يبدأ بوقت أو يحوي نتيجة ولم نفهمه: نرفضه ولا نتجاهله بصمت
            if tm and re.search(r"\d+-\d+", line):
                raise ValueError(f"{path}: سطر مباراة غير مفهوم: {line!r}")
    return out


def load_league(code, root):
    """يعيد {الموسم: [مباريات]} بعد التحقق من العدد."""
    res = {}
    for s in seasons_available(code, root):
        rows = parse_file(LEAGUES[code]["path"](root, s), s)
        res[s] = rows
    return res
