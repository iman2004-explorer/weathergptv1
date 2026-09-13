"""
Farmer advisory: recommends 2-3 crops for the current Indian growing season
(Kharif / Rabi / Zaid), adjusted with live weather, in EN/HI/BN.
"""
from datetime import date

SEASON_LABELS = {
    "kharif": {"en": "Kharif (Monsoon) season", "hi": "खरीफ (मानसून) मौसम", "bn": "খরিফ (বর্ষা) মৌসুম"},
    "rabi":   {"en": "Rabi (Winter) season",     "hi": "रबी (शीत ऋतु) मौसम", "bn": "রবি (শীত) মৌসুম"},
    "zaid":   {"en": "Zaid (Summer) season",     "hi": "जायद (गर्मी) मौसम",  "bn": "জায়েদ (গ্রীষ্ম) মৌসুম"},
}

CROP_DB = {
    "kharif": [
        {"en": {"name": "Rice (Paddy)", "care": "Needs standing water in the field; transplant seedlings after 20–25 days; watch for stem borer and blast disease; drain the field about 2 weeks before harvest."},
         "hi": {"name": "धान (चावल)", "care": "खेत में पानी भरा रखें; 20–25 दिनों बाद पौध रोपाई करें; तना छेदक और ब्लास्ट रोग पर नज़र रखें; कटाई से लगभग 2 हफ्ते पहले पानी निकाल दें।"},
         "bn": {"name": "ধান", "care": "জমিতে পানি জমিয়ে রাখুন; ২০–২৫ দিন পর চারা রোপণ করুন; কাণ্ড ছিদ্রকারী পোকা ও ব্লাস্ট রোগের দিকে নজর রাখুন; কাটার প্রায় ২ সপ্তাহ আগে জমি থেকে পানি সরিয়ে দিন।"}},
        {"en": {"name": "Maize", "care": "Sow after the first good monsoon shower; keep row spacing around 60cm; ensure drainage to avoid waterlogging; apply nitrogen in split doses."},
         "hi": {"name": "मक्का", "care": "पहली अच्छी बारिश के बाद बुवाई करें; कतार की दूरी लगभग 60 सेमी रखें; जलभराव से बचाव के लिए जल निकासी सुनिश्चित करें; नाइट्रोजन को बांटकर डालें।"},
         "bn": {"name": "ভুট্টা", "care": "প্রথম ভালো বৃষ্টির পর বপন করুন; সারির দূরত্ব প্রায় ৬০ সেমি রাখুন; জল জমা এড়াতে নিষ্কাশন নিশ্চিত করুন; নাইট্রোজেন কয়েক ভাগে প্রয়োগ করুন।"}},
        {"en": {"name": "Cotton", "care": "Best sown in well-drained black soil; needs warm days and moderate rain; watch for bollworm; avoid waterlogging after heavy rain."},
         "hi": {"name": "कपास", "care": "अच्छी जल निकासी वाली काली मिट्टी में बोयें; गर्म दिन और मध्यम बारिश ज़रूरी; बॉलवर्म पर नज़र रखें; भारी बारिश के बाद जलभराव से बचें।"},
         "bn": {"name": "তুলা", "care": "ভালো নিষ্কাশনযুক্ত কালো মাটিতে বপন করুন; গরম দিন ও মাঝারি বৃষ্টি প্রয়োজন; বলওয়ার্ম পোকার দিকে নজর রাখুন; ভারী বৃষ্টির পর জল জমা এড়ান।"}},
    ],
    "rabi": [
        {"en": {"name": "Wheat", "care": "Sow once daytime temperatures drop below about 25°C; needs 4–6 light irrigations; watch for aphids in cool, humid spells; harvest before pre-monsoon showers."},
         "hi": {"name": "गेहूं", "care": "दिन का तापमान लगभग 25°C से कम होने पर बुवाई करें; 4–6 हल्की सिंचाई ज़रूरी; ठंडी नम स्थिति में एफिड्स पर नज़र रखें; मानसून-पूर्व बारिश से पहले कटाई करें।"},
         "bn": {"name": "গম", "care": "দিনের তাপমাত্রা প্রায় ২৫°C এর নিচে নামলে বপন করুন; ৪–৬ বার হালকা সেচ দিন; ঠান্ডা আর্দ্র সময়ে জাব পোকার দিকে নজর রাখুন; বর্ষা শুরুর আগেই ফসল কাটুন।"}},
        {"en": {"name": "Mustard", "care": "Sow in October–November on well-drained soil; low water need; watch for aphid attack in foggy weather; avoid excess irrigation."},
         "hi": {"name": "सरसों", "care": "अक्टूबर–नवंबर में अच्छी जल निकासी वाली मिट्टी में बोयें; कम पानी की ज़रूरत; कोहरे के मौसम में एफिड्स का ध्यान रखें; अधिक सिंचाई से बचें।"},
         "bn": {"name": "সরিষা", "care": "অক্টোবর–নভেম্বরে ভালো নিষ্কাশনযুক্ত মাটিতে বপন করুন; কম পানির প্রয়োজন; কুয়াশাচ্ছন্ন আবহাওয়ায় জাব পোকা লক্ষ্য রাখুন; বেশি সেচ এড়িয়ে চলুন।"}},
        {"en": {"name": "Chickpea (Gram)", "care": "Sow in well-drained loam after the monsoon retreats; drought-tolerant, needs only 1–2 irrigations; watch for pod borer near flowering."},
         "hi": {"name": "चना", "care": "मानसून हटने के बाद अच्छी जल निकासी वाली दोमट मिट्टी में बोयें; सूखा-सहिष्णु, केवल 1–2 सिंचाई की ज़रूरत; फूल आने के समय फली छेदक का ध्यान रखें।"},
         "bn": {"name": "ছোলা", "care": "বর্ষা শেষের পর ভালো নিষ্কাশনযুক্ত দোআঁশ মাটিতে বপন করুন; খরা সহনশীল, মাত্র ১–২ বার সেচ প্রয়োজন; ফুল আসার সময় পড বোরার পোকা লক্ষ্য রাখুন।"}},
    ],
    "zaid": [
        {"en": {"name": "Watermelon", "care": "Needs sandy loam and frequent light irrigation in the heat; mulch to retain soil moisture; harvest before peak summer heat stress."},
         "hi": {"name": "तरबूज", "care": "बलुई दोमट मिट्टी और गर्मी में बार-बार हल्की सिंचाई चाहिए; मिट्टी की नमी बनाए रखने के लिए मल्चिंग करें; अत्यधिक गर्मी से पहले कटाई करें।"},
         "bn": {"name": "তরমুজ", "care": "বেলে দোআঁশ মাটি এবং গরমে ঘন ঘন হালকা সেচ প্রয়োজন; মাটির আর্দ্রতা ধরে রাখতে মালচিং করুন; তীব্র গরমের আগেই ফসল তুলুন।"}},
        {"en": {"name": "Moong (Green Gram)", "care": "Short-duration crop, good for hot dry spells; light irrigation every 8–10 days; avoid sowing right before a heavy rain forecast."},
         "hi": {"name": "मूंग", "care": "कम अवधि की फसल, गर्म-शुष्क मौसम के लिए अच्छी; हर 8–10 दिन में हल्की सिंचाई; भारी बारिश के पूर्वानुमान से ठीक पहले बुवाई न करें।"},
         "bn": {"name": "মুগ", "care": "স্বল্প মেয়াদী ফসল, গরম শুষ্ক আবহাওয়ায় ভালো হয়; প্রতি ৮–১০ দিনে হালকা সেচ দিন; ভারী বৃষ্টির পূর্বাভাসের ঠিক আগে বপন করবেন না।"}},
        {"en": {"name": "Cucumber", "care": "Needs consistent light watering in high heat; provide shade netting if temperatures exceed 40°C; harvest in the early morning to avoid heat wilt."},
         "hi": {"name": "खीरा", "care": "अधिक गर्मी में लगातार हल्की सिंचाई चाहिए; तापमान 40°C से अधिक होने पर शेड नेट लगाएं; गर्मी से मुरझाने से बचाने के लिए सुबह जल्दी कटाई करें।"},
         "bn": {"name": "শসা", "care": "প্রচণ্ড গরমে নিয়মিত হালকা সেচ প্রয়োজন; তাপমাত্রা ৪০°C ছাড়ালে শেড নেট ব্যবহার করুন; গরমে নেতিয়ে পড়া এড়াতে সকালে ফসল তুলুন।"}},
    ],
}

REGIONAL_CROPS = {
    "laterite": [
        {"en": {"name": "Paddy (aman)", "care": "Use a short-duration variety where water is uncertain; keep bunds intact and drain excess water after heavy rain."}},
        {"en": {"name": "Groundnut", "care": "Choose light, well-drained soil; use seed treatment and avoid waterlogging during pegging."}},
        {"en": {"name": "Sesame", "care": "Sow on a fine, well-drained seedbed; thin crowded plants and avoid excess nitrogen."}},
    ],
    "alluvial": [
        {"en": {"name": "Paddy (aman)", "care": "Maintain shallow standing water after transplanting; split nitrogen and monitor stem borer and blast."}},
        {"en": {"name": "Potato", "care": "Use certified seed, ridge the crop, and ensure drainage; stop irrigation before harvest."}},
        {"en": {"name": "Jute", "care": "Sow in fertile moist soil, weed early, and rett fibre only in clean, suitable water."}},
    ],
    "north_hills": [
        {"en": {"name": "Tea", "care": "Maintain shade and drainage, mulch the root zone, and scout flushes regularly for pests."}},
        {"en": {"name": "Large cardamom", "care": "Keep partial shade, remove diseased clumps, and avoid stagnant water around rhizomes."}},
        {"en": {"name": "Ginger", "care": "Use clean rhizomes, raised beds, mulch, and strict drainage to reduce rhizome rot."}},
    ],
    "coastal": [
        {"en": {"name": "Salt-tolerant paddy", "care": "Use locally recommended tolerant varieties, protect field bunds, and drain standing storm water promptly."}},
        {"en": {"name": "Sesame", "care": "Sow on raised, well-drained beds after the main rain spell and avoid waterlogging."}},
        {"en": {"name": "Vegetables", "care": "Use raised beds, trellising where needed, and clean water; harvest frequently during humid weather."}},
    ],
}

REGION_LABELS = {
    "laterite": "Bankura–Purulia–Jhargram laterite belt",
    "alluvial": "Gangetic alluvial plains",
    "north_hills": "Darjeeling–Kalimpong hill zone",
    "coastal": "South Bengal coastal and delta zone",
}


def _region(location: dict | None) -> str:
    text = " ".join(str(location.get(key, "")) for key in ("display_name", "state", "district")).lower()
    if any(name in text for name in ("darjeeling", "kalimpong")):
        return "north_hills"
    if any(name in text for name in ("south 24", "north 24", "parganas", "medinipur", "midnapur", "howrah")):
        return "coastal"
    if any(name in text for name in ("bankura", "purulia", "jhargram")):
        return "laterite"
    return "alluvial"


def _localized_region_crops(region: str, lang: str) -> list[dict]:
    crops = REGIONAL_CROPS[region]
    return [{"name": crop["en"]["name"], "care": crop["en"]["care"]} for crop in crops]


def _disease_risks(weather_data: dict, region: str) -> list[str]:
    today = (weather_data.get("days") or [{}])[0]
    risks = []
    if today.get("precip_prob", 0) >= 70 or weather_data.get("current", {}).get("humidity", 0) >= 85:
        risks.append("High humidity/rain: monitor rice blast, sheath blight, leaf spot, fruit rot, and fungal disease; improve airflow and avoid late-evening irrigation.")
    if today.get("temp_max", 30) >= 32 and today.get("precip_prob", 0) >= 50:
        risks.append("Warm wet weather: scout for stem borers, aphids, whiteflies, and caterpillars; use field sanitation and integrated pest management before spraying.")
    if region == "north_hills" and (today.get("precip_prob", 0) >= 60 or weather_data.get("current", {}).get("humidity", 0) >= 80):
        risks.append("Hill crops: watch ginger/cardamom rhizome rot and tea fungal leaf disease; use raised drainage and remove infected material.")
    if region == "laterite" and today.get("temp_max", 30) >= 35:
        risks.append("Hot laterite fields: watch for mite and sucking-pest pressure; mulch, irrigate at the root zone, and inspect leaf undersides.")
    return risks or ["No major weather-triggered crop disease signal detected; continue routine scouting twice each week."]


def get_season(month: int) -> str:
    """month: 1=Jan..12=Dec"""
    if 6 <= month <= 10:
        return "kharif"   # Jun-Oct, monsoon
    if month in (11, 12, 1, 2):
        return "rabi"     # Nov-Feb
    return "zaid"          # Mar-May


def compute_crop_advisory(weather_data: dict, lang: str = "en", location: dict | None = None) -> dict:
    month = date.today().month
    season = get_season(month)
    today = (weather_data.get("days") or [{}])[0]
    region = _region(location)
    crops = REGIONAL_CROPS.get(region, CROP_DB[season])

    tip = None
    precip = today.get("precip_prob", 0)
    tmax = today.get("temp_max", 30)
    if season == "kharif" and precip >= 60:
        tip = {
            "en": "Good rainfall is expected soon — a solid window for sowing or transplanting monsoon crops. Check field drainage first.",
            "hi": "जल्द अच्छी बारिश की संभावना है — मानसून फसलों की बुवाई/रोपाई के लिए उपयुक्त समय। पहले खेत की जल निकासी जांच लें।",
            "bn": "শীঘ্রই ভালো বৃষ্টির সম্ভাবনা — বর্ষার ফসল বপন/রোপণের উপযুক্ত সময়। প্রথমে জমির নিষ্কাশন যাচাই করুন।",
        }[lang]
    elif season == "zaid" and tmax >= 38:
        tip = {
            "en": "Temperatures are running high — irrigate in the early morning or evening and consider mulching to protect young plants.",
            "hi": "तापमान अधिक है — सुबह जल्दी या शाम को सिंचाई करें और युवा पौधों की सुरक्षा के लिए मल्चिंग पर विचार करें।",
            "bn": "তাপমাত্রা বেশি — সকালে বা সন্ধ্যায় সেচ দিন এবং কচি গাছ রক্ষায় মালচিং বিবেচনা করুন।",
        }[lang]
    else:
        tip = {
            "en": "Conditions look stable for this season — proceed with normal sowing/care schedules below.",
            "hi": "इस मौसम के लिए स्थितियां सामान्य दिख रही हैं — नीचे दिए गए सामान्य बुवाई/देखभाल कार्यक्रम के अनुसार आगे बढ़ें।",
            "bn": "এই মৌসুমের জন্য অবস্থা স্থিতিশীল দেখাচ্ছে — নিচের স্বাভাবিক বপন/পরিচর্যার সময়সূচি অনুসরণ করুন।",
        }[lang]

    return {
        "season": season,
        "season_label": SEASON_LABELS[season][lang],
        "tip": tip,
        "region": REGION_LABELS.get(region, "Local growing zone"),
        "crops": _localized_region_crops(region, lang) if region in REGIONAL_CROPS else [
            {"name": c[lang]["name"], "care": c[lang]["care"]} for c in crops
        ],
        "disease_risks": _disease_risks(weather_data, region),
    }
