#!/usr/bin/env python3
"""يدمج data.json داخل القالب وينتج dist/ : الصفحة، ملفات الدوريات، PWA، الخصوصية، ads.txt.
الإعدادات الاختيارية (ملف site_config.json في جذر المستودع):
  {"adsense_client": "ca-pub-XXXXXXXXXXXXXXXX", "adsense_slot": "1234567890",
   "apk_url": "https://.../mizan-kora.apk", "contact": "email"}
بدونها تُبنى الصفحة بلا إعلانات وبلا رابط للتطبيق."""
import json, os, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(HERE, "..")
out = os.path.join(root, "dist")
os.makedirs(out, exist_ok=True)

cfg = {}
cpath = os.path.join(root, "site_config.json")
if os.path.exists(cpath):
    cfg = json.load(open(cpath, encoding="utf-8"))
client = (cfg.get("adsense_client") or "").strip()
slot = (cfg.get("adsense_slot") or "").strip()
apk = (cfg.get("apk_url") or "").strip()
contact = (cfg.get("contact") or "").strip()
if client:
    assert client.startswith("ca-pub-") and client[7:].isdigit(), "adsense_client يجب أن يكون بصيغة ca-pub-1234567890"
if slot:
    assert slot.isdigit(), "adsense_slot أرقام فقط"

data = open(os.path.join(root, "data.json"), encoding="utf-8").read()
json.loads(data)
assert "</" not in data, "بيانات تحوي </ وقد تكسر الصفحة"
tpl = open(os.path.join(HERE, "site_template.html"), encoding="utf-8").read()
assert tpl.count("__DATA__") == 1

head = ""
ad_slot = ""
ads_note = ""
if client:
    head = f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={client}" crossorigin="anonymous"></script>'
    if slot:
        ad_slot = (f'<div class="adslot" aria-label="إعلان"><ins class="adsbygoogle" style="display:block" data-ad-client="{client}" '
                   f'data-ad-slot="{slot}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
                   '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>')
    ads_note = "يعرض الموقع إعلانات من Google."
tpl = tpl.replace("<!--HEAD_EXTRA-->", head).replace("<!--AD_SLOT-->", ad_slot).replace("<!--ADS_NOTE-->", ads_note)
tpl = tpl.replace("__APK_URL__", apk or "#")
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(tpl.replace("__DATA__", data))
open(os.path.join(out, "data.json"), "w", encoding="utf-8").write(data)

for code in ("es", "de", "it", "fr", "cl"):
    src = os.path.join(root, f"data_{code}.json")
    if os.path.exists(src):
        txt = open(src, encoding="utf-8").read()
        json.loads(txt)
        open(os.path.join(out, f"data_{code}.json"), "w", encoding="utf-8").write(txt)

assets = os.path.join(HERE, "site_assets")
for f in os.listdir(assets):
    if f.endswith(".ttf"):
        continue
    shutil.copy(os.path.join(assets, f), os.path.join(out, f))

manifest = {
    "name": "ميزان الكرة", "short_name": "ميزان الكرة", "lang": "ar", "dir": "rtl",
    "description": "توقعات مباريات كرة القدم بالاحتمالات",
    "start_url": "./", "scope": "./", "display": "standalone",
    "background_color": "#F6F4EC", "theme_color": "#14532D",
    "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
              {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"}],
}
json.dump(manifest, open(os.path.join(out, "manifest.webmanifest"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# عامل خدمة: الشبكة أولاً للصفحة والبيانات (لتبقى التوقعات حديثة) ثم النسخة المحفوظة عند انقطاع الاتصال
sw = """const C='mizan-kora-v5';
self.addEventListener('install',e=>{self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{
  const r=e.request; if(r.method!=='GET'||new URL(r.url).origin!==location.origin)return;
  e.respondWith(fetch(r).then(res=>{const c=res.clone();if(res.ok)caches.open(C).then(x=>x.put(r,c));return res;}).catch(()=>caches.match(r).then(m=>m||caches.match('./'))));
});
"""
open(os.path.join(out, "sw.js"), "w", encoding="utf-8").write(sw)

ads_txt = ""
if client:
    ads_txt = f"google.com, pub-{client[7:]}, DIRECT, f08c47fec0942fa0\n"
    open(os.path.join(out, "ads.txt"), "w").write(ads_txt)

contact_line = f"<p>للتواصل: <a href=\"mailto:{contact}\">{contact}</a></p>" if contact else ""
ads_par = ("<p>يعرض الموقع إعلانات من Google AdSense. تستخدم Google وشركاؤها ملفات تعريف الارتباط لعرض إعلانات بناءً على زياراتك لهذا الموقع ومواقع أخرى. "
           "يمكنك إدارة الإعلانات المخصصة من <a href=\"https://adssettings.google.com\">إعدادات إعلانات Google</a>.</p>") if client else "<p>لا يعرض الموقع إعلانات حالياً.</p>"
privacy = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>سياسة الخصوصية · ميزان الكرة</title><link rel="icon" href="favicon.png">
<style>body{{font-family:system-ui,'Segoe UI',Tahoma,sans-serif;max-width:720px;margin:0 auto;padding:20px 16px;line-height:1.9;color:#1b1b1b;background:#F6F4EC}}h1{{font-size:26px}}h2{{font-size:19px;margin-top:24px}}a{{color:#14532D}}</style></head><body>
<h1>سياسة الخصوصية</h1><p>«ميزان الكرة» موقع وتطبيق مجانيان لتوقعات كرة القدم بغرض الترفيه والتحليل، ولا يتضمنان أي مراهنات.</p>
<h2>ما الذي نجمعه؟</h2><p>لا نطلب حساباً ولا نجمع اسمك أو بريدك. توقعاتك الشخصية ولقبك في التحدي تُحفظ على جهازك فقط (التخزين المحلي) ولا تُرسل إلينا.</p>
<h2>الإعلانات</h2>{ads_par}
<h2>الإشعارات في التطبيق</h2><p>إشعارات التذكير بالمباريات تُجدوَل على جهازك محلياً ولا تمر عبر خادم.</p>
<h2>مصادر البيانات</h2><p>نتائج المباريات من openfootball (ترخيص CC0) وأرشيف footballcsv وfootball-data.org، والتوقعات إحصائية لا تضمن أي نتيجة.</p>
{contact_line}</body></html>"""
open(os.path.join(out, "privacy.html"), "w", encoding="utf-8").write(privacy)
open(os.path.join(out, ".nojekyll"), "w").close()
print("تم بناء", os.path.join(out, "index.html"), "| إعلانات:", "نعم" if client else "لا", "| apk:", "نعم" if apk else "لا")
