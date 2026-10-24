"""توحيد أسماء أندية دوري أبطال أوروبا بين المصادر (openfootball وfootball-data.org) وأسماء دورياتنا الخمسة.
الاسم المعتمد لأندية دورياتنا = اسمها في ملفات data_xx.json (فيظهر بالعربية تلقائياً)، ولغيرها اسم إنجليزي مختصر + ترجمة هنا."""
import re

# متغيّر الاسم (بلا رمز الدولة) ← الاسم المعتمد
ALIAS = {
    # إسبانيا
    "FC Barcelona": "FC Barcelona", "Real Madrid": "Real Madrid", "Real Madrid CF": "Real Madrid",
    "Atlético Madrid": "Atlético Madrid", "Club Atlético de Madrid": "Atlético Madrid", "Sevilla FC": "Sevilla FC",
    "Valencia CF": "Valencia CF", "Villarreal CF": "Villarreal CF", "Athletic Club": "Athletic Club", "Málaga CF": "Málaga CF",
    "Real Sociedad": "Real Sociedad", "Real Sociedad de Fútbol": "Real Sociedad", "Girona FC": "Girona FC",
    # ألمانيا
    "Bayern München": "FC Bayern München", "FC Bayern München": "FC Bayern München", "Borussia Dortmund": "Borussia Dortmund",
    "RB Leipzig": "RB Leipzig", "Bayer Leverkusen": "Bayer 04 Leverkusen", "Bayer 04 Leverkusen": "Bayer 04 Leverkusen",
    "FC Schalke 04": "FC Schalke 04", "VfL Wolfsburg": "VfL Wolfsburg", "Eintracht Frankfurt": "Eintracht Frankfurt",
    "VfB Stuttgart": "VfB Stuttgart", "1899 Hoffenheim": "TSG 1899 Hoffenheim", "1. FC Union Berlin": "1. FC Union Berlin",
    "Bor. Mönchengladbach": "Borussia Mönchengladbach",
    # إنجلترا
    "Manchester City": "Manchester City FC", "Manchester City FC": "Manchester City FC", "Chelsea FC": "Chelsea FC",
    "Liverpool FC": "Liverpool FC", "Arsenal FC": "Arsenal FC", "Manchester United": "Manchester United FC",
    "Manchester United FC": "Manchester United FC", "Tottenham Hotspur": "Tottenham Hotspur FC",
    "Tottenham Hotspur FC": "Tottenham Hotspur FC", "Newcastle United FC": "Newcastle United FC", "Aston Villa FC": "Aston Villa FC",
    "Leicester City": "Leicester City FC",
    # إيطاليا
    "Juventus": "Juventus FC", "Juventus FC": "Juventus FC", "SSC Napoli": "SSC Napoli", "AC Milan": "AC Milan",
    "Inter": "FC Internazionale Milano", "FC Internazionale Milano": "FC Internazionale Milano", "AS Roma": "AS Roma",
    "Atalanta": "Atalanta BC", "Atalanta BC": "Atalanta BC", "SS Lazio": "SS Lazio", "Lazio Roma": "SS Lazio",
    "Bologna FC 1909": "Bologna FC 1909",
    # فرنسا
    "Paris Saint-Germain": "Paris Saint-Germain FC", "Paris Saint-Germain FC": "Paris Saint-Germain FC",
    "Olympique Lyonnais": "Olympique Lyonnais", "Lille OSC": "Lille OSC", "AS Monaco": "AS Monaco FC", "AS Monaco FC": "AS Monaco FC",
    "Olympique Marseille": "Olympique de Marseille", "Olympique de Marseille": "Olympique de Marseille",
    "Stade Brestois 29": "Stade Brestois 29", "Montpellier HSC": "Montpellier HSC", "Stade Rennais": "Stade Rennais FC 1901",
    "Racing Club de Lens": "Racing Club de Lens",
    # أندية من دوريات أخرى
    "FC Porto": "FC Porto", "SL Benfica": "SL Benfica", "Sport Lisboa e Benfica": "SL Benfica", "Sporting CP": "Sporting CP",
    "Sporting Clube de Portugal": "Sporting CP", "Sporting Braga": "Sporting Braga", "Sporting Clube de Braga": "Sporting Braga",
    "Shakhtar Donetsk": "Shakhtar Donetsk", "FK Shakhtar Donetsk": "Shakhtar Donetsk", "Dinamo Kiev": "Dynamo Kyiv",
    "AFC Ajax": "Ajax", "Club Brugge KV": "Club Brugge", "Zenit St. Petersburg": "Zenit", "Olympiakos Piraeus": "Olympiacos",
    "PAE Olympiakos SFP": "Olympiacos", "Celtic FC": "Celtic", "CSKA Moskva": "CSKA Moscow", "Galatasaray": "Galatasaray",
    "Galatasaray SK": "Galatasaray", "FC Basel 1893": "FC Basel", "Dinamo Zagreb": "Dinamo Zagreb", "GNK Dinamo Zagreb": "Dinamo Zagreb",
    "FC København": "FC Copenhagen", "PSV": "PSV Eindhoven", "PSV Eindhoven": "PSV Eindhoven", "BSC Young Boys": "Young Boys",
    "RB Salzburg": "Red Bull Salzburg", "FC Red Bull Salzburg": "Red Bull Salzburg", "Viktoria Plzeň": "Viktoria Plzeň",
    "BATE Borisov": "BATE Borisov", "RSC Anderlecht": "Anderlecht", "APOEL Nikosia": "APOEL", "Beşiktaş": "Beşiktaş",
    "Malmö FF": "Malmö FF", "Lokomotiv Moskva": "Lokomotiv Moscow", "Feyenoord Rotterdam": "Feyenoord", "Feyenoord": "Feyenoord",
    "FK Crvena Zvezda": "Red Star Belgrade", "Crvena Zvezda": "Red Star Belgrade", "KRC Genk": "Genk", "Spartak Moskva": "Spartak Moscow",
    "PFC Ludogorets Razgrad": "Ludogorets", "NK Maribor": "Maribor", "FK Bodø/Glimt": "Bodø/Glimt", "Qarabağ Ağdam FK": "Qarabağ",
    "Qarabağ FK": "Qarabağ", "KAA Gent": "Gent", "AC Sparta Praha": "Sparta Prague", "ŠK Slovan Bratislava": "Slovan Bratislava",
    "SK Sturm Graz": "Sturm Graz", "Royale Union Saint-Gilloise": "Union Saint-Gilloise", "SK Slavia Praha": "Slavia Prague",
    "Slavia Praha": "Slavia Prague", "Paphos FC": "Pafos", "Pafos FC": "Pafos", "FK Kairat": "Kairat", "Trabzonspor": "Trabzonspor",
    "Oţelul Galaţi": "Oțelul Galați", "FC Nordsjælland": "Nordsjælland", "CFR Cluj": "CFR Cluj", "FC Steaua Bucureşti": "Steaua București",
    "Austria Wien": "Austria Wien", "FK Astana": "Astana", "Maccabi Tel Aviv": "Maccabi Tel Aviv", "FK Rostov": "Rostov",
    "Legia Warszawa": "Legia Warsaw", "AEK Athen": "AEK Athens", "FC Midtjylland": "Midtjylland", "FK Krasnodar": "Krasnodar",
    "Ferencvárosi TC": "Ferencváros", "İstanbul Başakşehir": "Başakşehir", "FC Sheriff": "Sheriff Tiraspol", "Rangers FC": "Rangers",
    "Maccabi Haifa": "Maccabi Haifa", "Royal Antwerp FC": "Royal Antwerp", "Fenerbahçe SK": "Fenerbahçe", "Fenerbahçe": "Fenerbahçe",
}

# أسماء عربية لأندية من خارج دورياتنا الخمسة (أندية دورياتنا تأخذ أسماءها من data_xx.json)
AR = {
    "FC Porto": "بورتو", "SL Benfica": "بنفيكا", "Sporting CP": "سبورتينغ لشبونة", "Sporting Braga": "براغا",
    "Shakhtar Donetsk": "شاختار دونيتسك", "Dynamo Kyiv": "دينامو كييف", "Ajax": "أياكس", "Club Brugge": "كلوب بروج",
    "Zenit": "زينيت", "Olympiacos": "أولمبياكوس", "Celtic": "سلتيك", "CSKA Moscow": "سسكا موسكو", "Galatasaray": "غلطة سراي",
    "FC Basel": "بازل", "Dinamo Zagreb": "دينامو زغرب", "FC Copenhagen": "كوبنهاغن", "PSV Eindhoven": "آيندهوفن",
    "Young Boys": "يونغ بويز", "Red Bull Salzburg": "ريد بول سالزبورغ", "Viktoria Plzeň": "فيكتوريا بلزن",
    "BATE Borisov": "باتي بوريسوف", "Anderlecht": "أندرلخت", "APOEL": "أبويل نيقوسيا", "Beşiktaş": "بشكتاش",
    "Malmö FF": "مالمو", "Lokomotiv Moscow": "لوكوموتيف موسكو", "Feyenoord": "فينورد", "Red Star Belgrade": "النجم الأحمر",
    "Genk": "جنك", "Spartak Moscow": "سبارتاك موسكو", "Ludogorets": "لودوغوريتس", "Maribor": "ماريبور",
    "Bodø/Glimt": "بودو غليمت", "Qarabağ": "قره باغ", "Gent": "خنت", "Sparta Prague": "سبارتا براغ",
    "Slovan Bratislava": "سلوفان براتيسلافا", "Sturm Graz": "شتورم غراتس", "Union Saint-Gilloise": "يونيون سان جيلواز",
    "Slavia Prague": "سلافيا براغ", "Pafos": "بافوس", "Kairat": "كايرات ألماتي", "Trabzonspor": "طرابزون سبور",
    "Oțelul Galați": "أوتيلول غالاتس", "Nordsjælland": "نوردشيلاند", "CFR Cluj": "كلوج", "Steaua București": "ستيوا بوخارست",
    "Austria Wien": "النمسا فيينا", "Astana": "أستانا", "Maccabi Tel Aviv": "مكابي تل أبيب", "Rostov": "روستوف",
    "Legia Warsaw": "ليغيا وارسو", "AEK Athens": "أيك أثينا", "Midtjylland": "ميتييلاند", "Krasnodar": "كراسنودار",
    "Ferencváros": "فيرنتسفاروش", "Başakşehir": "باشاك شهير", "Sheriff Tiraspol": "شريف تيراسبول", "Rangers": "رينجرز",
    "Maccabi Haifa": "مكابي حيفا", "Royal Antwerp": "أنتويرب", "Fenerbahçe": "فنربخشة",
    "Leicester City FC": "ليستر سيتي", "Borussia Mönchengladbach": "مونشنغلادباخ",
}

_CTRY = re.compile(r"\s*\([A-Z]{3}\)\s*$")


def strip_country(n):
    return _CTRY.sub("", n or "").strip()


def canon(name, known=()):
    """يعيد الاسم المعتمد. إن لم يوجد في الجدول يُجرَّب التطابق مع أسماء دورياتنا ثم يُترك الاسم كما هو."""
    n = strip_country(name)
    if n in ALIAS:
        return ALIAS[n]
    import scorers as S
    hit = S.match_team(n, list(known)) if known else None
    return hit or n
