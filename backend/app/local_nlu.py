"""
A no-API-key-required conversational fallback.

This is a straight Python port of the rule-based NLU that was in the
original prototype's client-side JS, moved server-side so the whole app
works out of the box with real live weather data even before anyone adds
an Anthropic key. Once a key is added to .env, main.py automatically
switches to the full Claude tool-calling path instead — nothing else to
configure.
"""
import re
import random

KNOWN_PLACES = [
    "kolkata", "durgapur", "mumbai", "delhi", "new delhi", "chennai", "bengaluru", "bangalore", "hyderabad",
    "pune", "jaipur", "ahmedabad", "lucknow", "bhopal", "patna", "chandigarh", "guwahati",
    "kochi", "cochin", "thiruvananthapuram", "bhubaneswar", "ranchi", "raipur", "dehradun",
    "shimla", "srinagar", "amritsar", "varanasi", "agra", "nagpur", "indore", "surat",
    "visakhapatnam", "vizag", "coimbatore", "madurai", "mysuru", "mysore", "goa", "panaji",
    "london", "new york", "tokyo", "paris", "dubai", "singapore", "sydney",
]

CLIMATE_FACTS = {
    "monsoon": {
        "en": "India's southwest monsoon typically arrives over Kerala around June 1st and withdraws by mid-September, delivering roughly 70-75% of the country's annual rainfall.",
        "hi": "भारत का दक्षिण-पश्चिम मानसून आमतौर पर 1 जून के आसपास केरल में आता है और सितंबर के मध्य तक वापस चला जाता है, जो देश की वार्षिक वर्षा का लगभग 70-75% देता है।",
        "bn": "ভারতের দক্ষিণ-পশ্চিম মৌসুমি বায়ু সাধারণত ১ জুনের কাছাকাছি কেরালায় পৌঁছায় এবং সেপ্টেম্বরের মাঝামাঝি সরে যায়, যা দেশের বার্ষিক বৃষ্টিপাতের প্রায় ৭০-৭৫% এনে দেয়।",
    },
    "el nino": {
        "en": "El Nino is a periodic warming of central and eastern Pacific waters that tends to weaken the Indian monsoon and raise the chance of below-normal rainfall, while La Nina usually has the opposite effect.",
        "hi": "अल नीनो प्रशांत महासागर के मध्य और पूर्वी हिस्सों के जल का समय-समय पर गर्म होना है, जो आमतौर पर भारतीय मानसून को कमजोर करता है और सामान्य से कम वर्षा की संभावना बढ़ाता है।",
        "bn": "এল নিনো হলো প্রশান্ত মহাসাগরের মধ্য ও পূর্বাঞ্চলের জলের সাময়িক উষ্ণতা বৃদ্ধি, যা সাধারণত ভারতীয় মৌসুমি বায়ুকে দুর্বল করে।",
    },
    "cyclone": {
        "en": "Tropical cyclones over the North Indian Ocean mostly form in the Bay of Bengal during pre-monsoon (April-May) and post-monsoon (October-December) windows.",
        "hi": "उत्तर हिंद महासागर के ऊपर उष्णकटिबंधीय चक्रवात ज्यादातर बंगाल की खाड़ी में मानसून-पूर्व (अप्रैल-मई) और मानसून-पश्चात (अक्टूबर-दिसंबर) के दौरान बनते हैं।",
        "bn": "উত্তর ভারত মহাসাগরের গ্রীষ্মমণ্ডলীয় ঘূর্ণিঝড়গুলো বেশিরভাগ বঙ্গোপসাগরে প্রাক-মৌসুমি (এপ্রিল-মে) এবং মৌসুম-পরবর্তী (অক্টোবর-ডিসেম্বর) সময়ে তৈরি হয়।",
    },
    "climate change": {
        "en": "Long-term warming is shifting India's rainfall toward fewer but more intense rainy days, lengthening heatwaves, and raising sea levels along the coast.",
        "hi": "दीर्घकालिक वार्मिंग भारत की वर्षा को कम लेकिन अधिक तीव्र दिनों की ओर स्थानांतरित कर रही है, गर्मी की लहरों को लंबा कर रही है, और तटीय क्षेत्रों में समुद्र के स्तर को बढ़ा रही है।",
        "bn": "দীর্ঘমেয়াদী উষ্ণতা বৃদ্ধি ভারতের বৃষ্টিপাতকে কম কিন্তু তীব্র দিনের দিকে সরিয়ে দিচ্ছে, তাপপ্রবাহকে দীর্ঘ করছে, এবং উপকূলীয় এলাকায় সমুদ্রপৃষ্ঠের উচ্চতা বাড়াচ্ছে।",
    },
}


def extract_location(text: str):
    lower = text.lower()
    m = re.search(r"\b(?:in|for|at|near)\s+([a-z][a-z\s]{2,25})", lower)
    if m:
        candidate = re.split(r"[?.!,]", m.group(1).strip())[0].strip()
        candidate = re.sub(
            r"\b(right now|now|today|tomorrow|tonight|this week|next week|this weekend|this|please)\b", "", candidate
        ).strip()
        candidate = re.sub(r"\s+", " ", candidate)
        if len(candidate) > 1:
            return candidate
    for place in KNOWN_PLACES:
        if place in lower:
            return place
    direct = re.sub(
        r"\b(weather|forecast|temperature|rain|climate|alerts?|advisories?|in|for|at|near|today|tomorrow|now|please|what|is|the|of|me|give|tell)\b",
        " ",
        lower,
    )
    direct = re.sub(r"[^a-z\s-]", " ", direct)
    direct = re.sub(r"\s+", " ", direct).strip()
    if 2 <= len(direct) <= 40 and len(direct.split()) <= 5:
        return direct
    return None


def classify_intent(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(hi|hello|hey|namaste|namaskar)\b", lower) and len(lower) < 20:
        return "greeting"
    if re.search(r"\b(thank|thanks|shukriya|dhanyavad)\b", lower):
        return "thanks"
    for key in CLIMATE_FACTS:
        if key in lower:
            return f"climate:{key}"
    if re.search(r"\b(alert|advisory|warning|safe|danger|hazard)\b", lower) or re.search(r"चेतावनी|सतर्कता|সতর্কতা", text):
        return "alerts"
    if re.search(r"\b(crop|plant|sow|farm|farming|farmer|kisan|fasal|harvest|cultivat|agri)\b", lower) or re.search(r"फसल|किसान|खेती|চাষ|ফসল|কৃষক", text):
        return "farming"
    if re.search(r"\b(rain|precipitation|umbrella|shower)\b", lower) or re.search(r"बारिश|वर्षा|বৃষ্টি", text):
        return "rain"
    if re.search(r"\b(forecast|week|days|tomorrow|next few)\b", lower) or re.search(r"पूर्वानुमान|পূর্বাভাস", text):
        return "forecast"
    if re.search(r"\b(weather|temperature|hot|cold|humid|wind|climate|condition)\b", lower) or re.search(r"मौसम|তাপমাত্রা|আবহাওয়া", text):
        return "current"
    return "current"


def generate_reply(intent: str, weather_bundle: dict, language: str, place: str = None) -> str:
    if intent == "greeting":
        if language == "hi":
            return "नमस्ते! मुझसे किसी भी शहर के मौसम, पूर्वानुमान या चेतावनियों के बारे में पूछें।"
        if language == "bn":
            return "নমস্কার! আমাকে যেকোনো শহরের আবহাওয়া, পূর্বাভাস বা সতর্কতা সম্পর্কে জিজ্ঞাসা করুন।"
        return random.choice([
            "Hey there! Ask me about the weather, a forecast, or alerts for any city.",
            "Namaste! Tell me a place and I'll pull up the latest conditions.",
        ])

    if intent == "thanks":
        if language == "hi":
            return "खुशी हुई मदद करके! कुछ और पूछना हो तो बताइए।"
        if language == "bn":
            return "সাহায্য করতে পেরে ভালো লাগলো! আর কিছু জানতে চাইলে বলুন।"
        return "Happy to help — ask away if you need anything else."

    if intent.startswith("climate:"):
        key = intent.split(":", 1)[1]
        return CLIMATE_FACTS[key][language]

    if not weather_bundle:
        if language == "hi":
            return "कृपया कोई शहर या स्थान बताइए, जैसे 'कोलकाता में मौसम कैसा है?'"
        if language == "bn":
            return "অনুগ্রহ করে একটি শহর বা স্থানের নাম বলুন, যেমন 'কলকাতার আবহাওয়া কেমন?'"
        return 'Tell me a city to check — for example, "weather in Kolkata" or "forecast for Delhi".'

    c = weather_bundle["current"]
    today = weather_bundle["days"][0]
    place = weather_bundle["place"]
    advisories = weather_bundle.get("advisories", [])

    if intent == "farming":
        advisory = weather_bundle["crop_advisory"]
        sep = "、 " if language == "bn" else ", "
        crop_names = sep.join(cr["name"] for cr in advisory["crops"])
        if language == "hi":
            return f"{place} में अभी {advisory['season_label']} है। सुझाई गई फसलें: {crop_names}। पूरी देखभाल जानकारी नीचे किसान सलाह पैनल में है।"
        if language == "bn":
            return f"{place}-এ এখন {advisory['season_label']} চলছে। প্রস্তাবিত ফসল: {crop_names}। সম্পূর্ণ পরিচর্যার তথ্য নিচের কৃষক পরামর্শ প্যানেলে দেওয়া আছে।"
        return f"{place} is currently in the {advisory['season_label']}. Suggested crops: {crop_names}. Full care details are in the Farmer Advisory panel below."

    if intent == "rain":
        if today["precip_prob"] >= 60:
            if language == "hi":
                return f"हाँ, {place} में आज बारिश की संभावना काफी अधिक है ({today['precip_prob']}%) — छाता साथ रखें।"
            if language == "bn":
                return f"হ্যাঁ, {place}-এ আজ বৃষ্টির সম্ভাবনা যথেষ্ট বেশি ({today['precip_prob']}%) — ছাতা সাথে রাখুন।"
            return f"Yes — {place} has a fairly high chance of rain today ({today['precip_prob']}%), so carry an umbrella."
        if language == "hi":
            return f"{place} में आज बारिश की संभावना कम है, सिर्फ {today['precip_prob']}%।"
        if language == "bn":
            return f"{place}-এ আজ বৃষ্টির সম্ভাবনা কম, মাত্র {today['precip_prob']}%।"
        return f"Rain looks unlikely in {place} today — only about a {today['precip_prob']}% chance."

    if intent == "forecast":
        hi_temp = max(d["temp_max"] for d in weather_bundle["days"])
        lo_temp = min(d["temp_min"] for d in weather_bundle["days"])
        if language == "hi":
            return f"{place} के अगले 7 दिनों में तापमान {lo_temp}° से {hi_temp}° के बीच रहेगा। पूरा विवरण दाईं ओर पैनल में है।"
        if language == "bn":
            return f"{place}-এর আগামী ৭ দিনে তাপমাত্রা {lo_temp}° থেকে {hi_temp}° এর মধ্যে থাকবে। সম্পূর্ণ বিবরণ ডানদিকের প্যানেলে দেওয়া আছে।"
        return f"Over the next 7 days in {place}, expect highs up to {hi_temp}° and lows around {lo_temp}°. Full day-by-day trace is in the panel on the right."

    if intent == "alerts":
        if advisories:
            lines = " ".join(f"{a['icon']} {a['title']} — {a['text']}" for a in advisories)
            if language == "hi":
                return f"{place} के लिए सक्रिय परामर्श: " + lines
            if language == "bn":
                return f"{place}-এর জন্য সক্রিয় সতর্কতা: " + lines
            return f"Active advisories for {place}: " + lines
        if language == "hi":
            return f"{place} के लिए फिलहाल कोई सक्रिय मौसम चेतावनी नहीं है।"
        if language == "bn":
            return f"{place}-এর জন্য এই মুহূর্তে কোনো সক্রিয় আবহাওয়া সতর্কতা নেই।"
        return f"No active weather advisories for {place} right now — conditions look routine."

    # default: current conditions
    if language == "hi":
        return f"{place} में अभी {c['temp']}° है (महसूस {c['feels_like']}°), {c['weather_label']}, नमी {c['humidity']}% और हवा {c['wind']} किमी/घं।"
    if language == "bn":
        return f"{place}-এ এখন {c['temp']}° (অনুভূত {c['feels_like']}°), {c['weather_label']}, আর্দ্রতা {c['humidity']}% এবং বাতাস {c['wind']} কিমি/ঘণ্টা।"
    return f"{place} is at {c['temp']}° right now (feels like {c['feels_like']}°), {c['weather_label'].lower()}, with {c['humidity']}% humidity and wind at {c['wind']} km/h."


def not_found_reply(query: str, language: str) -> str:
    if language == "hi":
        return f'मुझे "{query}" नाम की कोई जगह नहीं मिली। कृपया वर्तनी जांचें या कोई और नाम आज़माएं।'
    if language == "bn":
        return f'আমি "{query}" নামে কোনো জায়গা খুঁজে পাইনি। বানান পরীক্ষা করুন বা অন্য নাম চেষ্টা করুন।'
    return f'I couldn\'t find a place called "{query}". Please check the spelling or try another name.'
