"""توحيد أسماء الأندية بين المواسم (تختلف أسماؤها في ملفات openfootball) مع الاسم العربي.
الصيغة: الاسم المعتمد | العربي | بدائل مفصولة بـ ;"""

_RAW = {
"es": """
Athletic Club | أتلتيك بلباو
Atlético Madrid | أتلتيكو مدريد | Atlético de Madrid; Club Atlético de Madrid
CA Osasuna | أوساسونا
Deportivo Alavés | ألافيس | CD Alavés
CD Leganés | ليغانيس
Cádiz CF | قادش
Córdoba CF | قرطبة
Deportivo La Coruña | ديبورتيفو لا كورونيا | RC Deportivo La Coruña
Elche CF | إلتشي
Espanyol | إسبانيول | Espanyol Barcelona; RCD Espanyol; RCD Espanyol de Barcelona
FC Barcelona | برشلونة | Barcelona
Getafe CF | خيتافي
Girona FC | جيرونا
Granada CF | غرناطة
Levante UD | ليفانتي
Málaga CF | مالقة
Celta Vigo | سيلتا فيغو | RC Celta; RC Celta de Vigo
RCD Mallorca | مايوركا
Rayo Vallecano | رايو فاليكانو | Rayo Vallecano de Madrid
Real Betis | ريال بيتيس | Real Betis Balompié
Real Madrid | ريال مدريد | Real Madrid C.F.; Real Madrid CF
Real Oviedo | ريال أوفييدو
Racing Santander | راسينغ سانتاندير | Real Racing Club de Santander
Real Sociedad | ريال سوسيداد | Real Sociedad de Fútbol
Real Valladolid | ريال بلد الوليد | Real Valladolid CF
SD Eibar | إيبار
SD Huesca | أويسكا
Sevilla FC | إشبيلية | Sevilla
Sporting Gijón | سبورتينغ خيخون
UD Almería | ألميريا
UD Las Palmas | لاس بالماس
Valencia CF | فالنسيا
Villarreal CF | فياريال | Villarreal
""",
"de": """
1. FC Heidenheim 1846 | هايدنهايم | Heidenheim
1. FC Köln | كولن
1. FC Nürnberg | نورمبرغ
1. FC Union Berlin | أونيون برلين | Union Berlin
1. FSV Mainz 05 | ماينتس
TSG 1899 Hoffenheim | هوفنهايم | 1899 Hoffenheim
Arminia Bielefeld | أرمينيا بيليفيلد
Bayer 04 Leverkusen | باير ليفركوزن | Bayer Leverkusen
FC Bayern München | بايرن ميونخ | Bayern München
Borussia Mönchengladbach | بوروسيا مونشنغلادباخ | Bor. Mönchengladbach; Borussia M'gladbach
Borussia Dortmund | بوروسيا دورتموند
Eintracht Braunschweig | براونشفايغ
Eintracht Frankfurt | آينتراخت فرانكفورت
FC Augsburg | أوغسبورغ
FC Ingolstadt 04 | إنغولشتات
FC Schalke 04 | شالكه
FC St. Pauli 1910 | سانت باولي | St. Pauli
Fortuna Düsseldorf | فورتونا دوسلدورف
Hamburger SV | هامبورغ
Hannover 96 | هانوفر
Hertha BSC | هيرتا برلين
Holstein Kiel | هولشتاين كيل
RB Leipzig | لايبزيغ
SC Freiburg | فرايبورغ
SC Paderborn 07 | بادربورن
SV 07 Elversberg | إلفرسبرغ
SV Darmstadt 98 | دارمشتات
SV Werder Bremen | فيردر بريمن | Werder Bremen
SpVgg Greuther Fürth 1903 | غرويتر فورت
VfB Stuttgart | شتوتغارت
VfL Bochum 1848 | بوخوم
VfL Wolfsburg | فولفسبورغ | Wolfsburg
""",
"it": """
AC Cesena | تشيزينا
AC Milan | ميلان | Milan
AC Monza | مونزا
ACF Fiorentina | فيورنتينا | Fiorentina
AS Livorno | ليفورنو
AS Roma | روما
Atalanta BC | أتالانتا | Atalanta
Benevento Calcio | بينيفينتو
Bologna FC 1909 | بولونيا | Bologna; Bologna FC
Brescia Calcio | بريشيا
Cagliari Calcio | كالياري | Cagliari
Calcio Catania | كاتانيا
Carpi FC | كاربي
Chievo Verona | كييفو
Como 1907 | كومو | Como
Delfino Pescara | بيسكارا
Empoli FC | إمبولي
FC Crotone | كروتوني
FC Internazionale Milano | إنتر ميلان | Inter
Frosinone Calcio | فروسينوني
Genoa CFC | جنوى | Genoa
Hellas Verona FC | هيلاس فيرونا | Hellas Verona
Juventus FC | يوفنتوس | Juventus
SS Lazio | لاتسيو | Lazio; Lazio Roma
US Lecce | ليتشي | Lecce
SSC Napoli | نابولي | Napoli
Parma Calcio 1913 | بارما | Parma; Parma FC
Pisa | بيزا
SPAL 2013 Ferrara | سبال
UC Sampdoria | سامبدوريا | Sampdoria
US Cremonese | كريمونيزي | Cremonese
US Palermo | باليرمو
US Salernitana 1919 | ساليرنيتانا
US Sassuolo Calcio | ساسوولو | Sassuolo; Sassuolo Calcio
Spezia Calcio | سبيتسيا
Torino FC | تورينو | Torino
Udinese Calcio | أودينيزي | Udinese
Venezia FC | البندقية
""",
"fr": """
AC Ajaccio | أجاكسيو
AJ Auxerre | أوكسير | Auxerre
AS Monaco FC | موناكو | AS Monaco
AS Nancy Lorraine | نانسي
AS Saint-Étienne | سانت إتيان
Amiens SC | أميان
Angers SCO | أنجيه
Clermont Foot 63 | كليرمون
Dijon FCO | ديجون
EA Guingamp | غانغان
ES Troyes AC | تروا | ESTAC Troyes
FC Lorient | لوريان
FC Metz | ميتز
FC Nantes | نانت
Gazélec FC Ajaccio | غازيليك أجاكسيو
Girondins Bordeaux | بوردو
Le Havre AC | لوهافر | Le Havre
Le Mans FC | لومان
Lille OSC | ليل | Lille
Montpellier HSC | مونبلييه
Nîmes Olympique | نيم
OGC Nice | نيس
Olympique Lyonnais | ليون
Olympique de Marseille | مرسيليا | Olympique Marseille
Paris FC | باريس إف سي
Paris Saint-Germain FC | باريس سان جيرمان | Paris Saint-Germain
Racing Club de Lens | لانس | RC Lens; Lens
RC Strasbourg Alsace | ستراسبورغ | RC Strasbourg
SC Bastia | باستيا
SM Caen | كاين
Stade Brestois 29 | بريست | Stade Brestois
Stade Rennais FC 1901 | رين | Stade Rennais; Rennes
Stade de Reims | ريمس
Toulouse FC | تولوز
Évian Thonon Gaillard | إيفيان
""",
}

ALIAS = {}   # الدوري -> {أي صيغة: الاسم المعتمد}
AR = {}      # الدوري -> {الاسم المعتمد: العربي}
for _code, _txt in _RAW.items():
    ALIAS[_code], AR[_code] = {}, {}
    for _line in _txt.strip().splitlines():
        _p = [x.strip() for x in _line.split("|")]
        _canon, _ar = _p[0], _p[1]
        AR[_code][_canon] = _ar
        ALIAS[_code][_canon] = _canon
        if len(_p) > 2:
            for _a in _p[2].split(";"):
                ALIAS[_code][_a.strip()] = _canon


def canon(code, name):
    try:
        return ALIAS[code][name]
    except KeyError:
        raise KeyError(f"اسم نادٍ غير معروف في {code}: {name!r}")
