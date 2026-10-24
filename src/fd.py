"""طلب إلى football-data.org مع احترام حدّ المستوى المجاني (10 طلبات/دقيقة): عند 429 ننتظر ثم نعيد المحاولة."""
import json, time, urllib.error, urllib.request


def get(url, token, timeout=30, retries=2):
    for i in range(retries + 1):
        req = urllib.request.Request(url, headers={"X-Auth-Token": token})
        try:
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < retries:
                wait = 65
                try:
                    wait = min(70, int(e.headers.get("X-RequestCounter-Reset", wait)) + 2)
                except (TypeError, ValueError):
                    pass
                print(f"football-data 429: انتظار {wait}ث ثم إعادة المحاولة")
                time.sleep(wait)
                continue
            raise
