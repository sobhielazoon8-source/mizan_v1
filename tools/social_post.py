#!/usr/bin/env python3
"""ينشئ بطاقات «توقعات اليوم» ويرسلها إلى صفحة فيسبوك (اختياري).
- يقرأ بيانات الموقع المنشورة (SITE_URL) أو ملفات محلية في DATA_DIR.
- البطاقات تُحفظ دائماً في OUT_DIR (تُرفع كـ artifact لتنشرها يدوياً في إنستغرام/تيك توك).
- النشر الفعلي فقط إذا SOCIAL_LIVE=1 ووُجد FB_PAGE_ID وFB_PAGE_TOKEN. غير ذلك: تشغيل تجريبي.
- الرابط يوضع في أول تعليق (لا في نص المنشور) وليس بصيغة «علّق لتحصل على الرابط».
- لا ينشر المباراة نفسها مرتين (data/social_posted.json)."""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
FONTS = os.path.join(ROOT, "src", "site_assets")
SITE = os.environ.get("SITE_URL", "https://sobhielazoon8-source.github.io/mizan_v1/").rstrip("/") + "/"
DATA_DIR = os.environ.get("DATA_DIR", "")
OUT = os.environ.get("OUT_DIR", os.path.join(ROOT, "social_out"))
STATE = os.path.join(ROOT, "data", "social_posted.json")
LEAGUES = [("en", "data.json", "الدوري الإنجليزي"), ("es", "data_es.json", "الدوري الإسباني"), ("de", "data_de.json", "الدوري الألماني"),
           ("it", "data_it.json", "الدوري الإيطالي"), ("fr", "data_fr.json", "الدوري الفرنسي"), ("cl", "data_cl.json", "دوري أبطال أوروبا")]
GREEN, CREAM, INK, GOLD = (20, 83, 45), (246, 244, 236), (27, 27, 27), (200, 150, 30)
MAX_CARDS = int(os.environ.get("MAX_CARDS", "3"))


from PIL import features
RAQM = features.check("raqm")   # إن توفّر raqm فهو يشكّل العربية ويعكس الاتجاه بنفسه


if not RAQM:
    sys.exit("خطأ: Pillow بلا raqm؛ الخط لا يحوي أشكال العربية المنفصلة. ثبّت libraqm0 وlibfribidi0")


def shape(t):
    return t   # raqm يشكّل العربية ويضبط الاتجاه


def font(sz, w="Bold"):
    return ImageFont.truetype(os.path.join(FONTS, f"Tajawal-{w}.ttf"), sz)


def load(name):
    try:
        if DATA_DIR:
            return json.load(open(os.path.join(DATA_DIR, name), encoding="utf-8"))
        with urllib.request.urlopen(SITE + name + "?t=" + str(int(datetime.now().timestamp())), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("تعذّر تحميل", name, e)
        return None


def ar(d, n):
    return (d.get("names_ar") or {}).get(n) or n


TEAMS_AR = {}


def name_ar(d, n):
    return (d.get("names_ar") or {}).get(n) or TEAMS_AR.get(n) or n


def pct3(a, b, c):
    v = [a * 100, b * 100, c * 100]
    r = [int(x) for x in v]
    rem = 100 - sum(r)
    for i in sorted(range(3), key=lambda i: -(v[i] - r[i]))[:rem]:
        r[i] += 1
    return r


def center(dr, y, text, f, fill, w=1080):
    t = shape(text)
    bw = dr.textlength(t, font=f)
    dr.text(((w - bw) / 2, y), t, font=f, fill=fill)


def card(d, f, league_ar, path):
    W, H = 1080, 1350
    im = Image.new("RGB", (W, H), CREAM)
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, W, 190], fill=GREEN)
    center(dr, 40, "ميزان الكرة", font(86, "ExtraBold"), CREAM)
    center(dr, 135, "توقعات مباريات اليوم بالاحتمالات", font(34, "Medium"), (214, 235, 220))
    center(dr, 235, league_ar, font(46, "Bold"), GREEN)
    h, a = name_ar(d, f["home"]), name_ar(d, f["away"])
    # أسماء الفريقين: المضيف يمين
    fh = font(64, "ExtraBold")
    for txt, cx in ((h, 810), (a, 270)):
        t = shape(txt)
        sz = 64
        while dr.textlength(t, font=font(sz, "ExtraBold")) > 460 and sz > 30:
            sz -= 4
        ff = font(sz, "ExtraBold")
        dr.text((cx - dr.textlength(t, font=ff) / 2, 380), t, font=ff, fill=INK)
    center(dr, 395, "×", font(70, "Bold"), GOLD)
    dr.text((810 - dr.textlength(shape("المضيف"), font=font(28, "Medium")) / 2, 470), shape("المضيف"), font=font(28, "Medium"), fill=(110, 110, 110))
    dr.text((270 - dr.textlength(shape("الضيف"), font=font(28, "Medium")) / 2, 470), shape("الضيف"), font=font(28, "Medium"), fill=(110, 110, 110))
    p = pct3(f["ph"], f["pd"], f["pa"])
    # شريط الاحتمالات (المضيف يمين)
    x0, x1, y0, y1 = 90, 990, 590, 680
    tot = 900
    segs = [(p[2], (176, 58, 46), a), (p[1], (150, 150, 150), "تعادل"), (p[0], GREEN, h)]
    x = x0
    for val, col, lab in segs:
        w = tot * val / 100
        dr.rectangle([x, y0, x + w, y1], fill=col)
        if w > 80:
            t = f"{val}%"
            ff = font(44, "Bold")
            dr.text((x + (w - dr.textlength(t, font=ff)) / 2, y0 + 20), t, font=ff, fill="white")
        x += w
    center(dr, 700, f"فوز {h} {p[0]}%  ·  تعادل {p[1]}%  ·  فوز {a} {p[2]}%", font(32, "Medium"), INK)
    sh = f["modal"] if f.get("draw_flag") else f["pick"]
    center(dr, 800, "أرجح نتيجة", font(40, "Medium"), (110, 110, 110))
    center(dr, 860, sh["s"].replace("-", " – "), font(190, "ExtraBold"), GREEN)
    if f.get("draw_flag"):
        center(dr, 1085, "مباراة مرشحة للتعادل", font(38, "Bold"), GOLD)
    center(dr, 1170, "هل تتفوق عليه؟ وجّه توقعك في التطبيق", font(44, "Bold"), INK)
    center(dr, 1245, "الرابط في أول تعليق", font(34, "Medium"), (110, 110, 110))
    dr.rectangle([0, H - 12, W, H], fill=GREEN)
    im.save(path, "PNG", optimize=True)


def fb(path, ep, fields, files=None):
    token = os.environ["FB_PAGE_TOKEN"]
    url = f"https://graph.facebook.com/v21.0/{path}"
    boundary = "----mizan" + str(int(datetime.now().timestamp()))
    body = b""
    allf = dict(fields, access_token=token)
    for k, v in allf.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fn, data) in (files or {}).items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\nContent-Type: image/png\r\n\r\n'.encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = {}
    if os.path.exists(STATE):
        state = json.load(open(STATE, encoding="utf-8"))
    cands = []
    for code, fn, lar in LEAGUES:
        d = load(fn)
        if not d:
            continue
        for f in d.get("fixtures", []):
            if f["date"] == today:
                cands.append((max(f["ph"], f["pd"], f["pa"]), code, lar, d, f))
    # الأكثر إثارة: الأقل حسماً أولاً (المتقاربة) مع تنويع الدوريات
    cands.sort(key=lambda x: x[0])
    picked, seen = [], set()
    for c in cands:
        k = f"{today}|{c[1]}|{c[4]['home']}|{c[4]['away']}"
        if k in state:
            continue
        if c[1] in seen and len(cands) > MAX_CARDS:
            continue
        seen.add(c[1])
        picked.append((k,) + c)
        if len(picked) >= MAX_CARDS:
            break
    os.makedirs(OUT, exist_ok=True)
    print(f"مباريات اليوم المرشحة: {len(cands)} | ستُنشأ بطاقات: {len(picked)}")
    live = os.environ.get("SOCIAL_LIVE") == "1" and os.environ.get("FB_PAGE_ID") and os.environ.get("FB_PAGE_TOKEN")
    changed = False
    for k, _, code, lar, d, f in picked:
        path = os.path.join(OUT, f"{today}_{code}_{len(os.listdir(OUT))}.png")
        card(d, f, lar, path)
        cap = (f"توقع ميزان الكرة: {name_ar(d, f['home'])} × {name_ar(d, f['away'])}\n"
               f"{lar} · أرجح نتيجة {(f['modal'] if f.get('draw_flag') else f['pick'])['s'].replace('-', '–')}\n"
               "ما توقعك أنت؟ اكتبه في التعليقات 👇\n#كرة_القدم #ميزان_الكرة")
        print("بطاقة:", path)
        if not live:
            print("(تشغيل تجريبي: لا نشر)")
            continue
        try:
            r = fb(f"{os.environ['FB_PAGE_ID']}/photos", None, {"caption": cap, "published": "true"}, {"source": (os.path.basename(path), open(path, "rb").read())})
            pid = r.get("post_id") or r.get("id")
            fb(f"{pid}/comments", None, {"message": f"التوقعات الكاملة لكل الدوريات مجاناً: {SITE}"})
            state[k] = {"post": pid, "at": datetime.now(timezone.utc).isoformat()}
            changed = True
            print("نُشر:", pid)
        except Exception as e:
            print("فشل النشر:", getattr(e, "read", lambda: b"")()[:300] or e)
    if changed:
        json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
