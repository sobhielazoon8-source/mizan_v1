#!/usr/bin/env python3
"""يدمج data.json داخل القالب وينتج dist/index.html (صفحة واحدة مستقلة)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(HERE, "..")
data = open(os.path.join(root, "data.json"), encoding="utf-8").read()
json.loads(data)                       # تحقق من سلامة JSON
assert "</" not in data, "بيانات تحوي </ وقد تكسر الصفحة"
tpl = open(os.path.join(HERE, "site_template.html"), encoding="utf-8").read()
assert tpl.count("__DATA__") == 1
out = os.path.join(root, "dist")
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(tpl.replace("__DATA__", data))
open(os.path.join(out, "data.json"), "w", encoding="utf-8").write(data)   # تقرؤه الصفحة دورياً للتحديث دون إعادة تحميل
open(os.path.join(out, ".nojekyll"), "w").close()
print("تم بناء", os.path.join(out, "index.html"))
