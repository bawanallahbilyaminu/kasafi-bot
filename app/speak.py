"""Turn a written Hausa answer into text a Hausa TTS voice can read aloud.

- numbers -> Hausa words (124 -> "dari da ashirin da hudu")
- "₦124.41 biliyan" -> "Naira biliyan dari da ashirin da hudu da miliyan dari hudu da goma"
- "kashi 10.6 cikin 100" -> "kashi goma digo shida cikin ɗari"
- "Naira biliyan 8.75", "biliyan 8.75", "8.75 biliyan", "₦8.75bn" -> "naira biliyan takwas da miliyan ɗari bakwai da hamsin"
- lowercase, with the hooked letters (ɓ ɗ ƙ) restored in common words: the voice model's alphabet
- markdown, emoji, bullets and the source line are removed
- only the headline part of the answer is kept (short voice notes)
"""
import re

ONES = ["", "daya", "biyu", "uku", "hudu", "biyar", "shida", "bakwai", "takwas", "tara"]
TENS = ["", "goma", "ashirin", "talatin", "arba'in", "hamsin", "sittin", "saba'in", "tamanin", "casa'in"]


def _below_1000(n):
    parts = []
    h, rest = divmod(n, 100)
    if h:
        parts.append("dari" if h == 1 else f"dari {ONES[h]}")
    t, o = divmod(rest, 10)
    if t == 1:
        parts.append("goma" + (f" sha {ONES[o]}" if o else ""))
    else:
        if t:
            parts.append(TENS[t])
        if o:
            parts.append(ONES[o])
    return " da ".join(parts)


def number_words(n):
    """Integer -> Hausa words (up to trillions)."""
    n = int(n)
    if n == 0:
        return "sifili"
    if n < 0:
        return "debe " + number_words(-n)
    out = []
    for size, word in ((10 ** 12, "tiriliyan"), (10 ** 9, "biliyan"), (10 ** 6, "miliyan"), (10 ** 3, "dubu")):
        q, n = divmod(n, size)
        if q:
            out.append(f"{word} {_below_1000(q) if q < 1000 else number_words(q)}")
    if n:
        out.append(_below_1000(n))
    return " da ".join(out)


def decimal_words(s):
    """'10.6' -> 'goma digo shida'"""
    s = s.replace(",", "")
    if "." in s:
        a, b = s.split(".", 1)
        b = b.rstrip("0")
        return number_words(int(a or 0)) + (" digo " + " ".join(ONES[int(d)] if d != "0" else "sifili" for d in b) if b else "")
    return number_words(int(s))


UNIT = {"tiriliyan": 10 ** 12, "biliyan": 10 ** 9, "miliyan": 10 ** 6, "dubu": 10 ** 3}


def naira_words(value, unit):
    """(124.41, 'biliyan') -> 'Naira biliyan dari da ashirin da hudu da miliyan dari hudu da goma'"""
    total = round(float(value.replace(",", "")) * UNIT.get(unit, 1))
    if unit in UNIT:  # speak at most two levels, rounded (e.g. billions + millions)
        step = UNIT[unit] // 1000
        total = round(total / step) * step
    return "Naira " + number_words(total)


def headline(answer, max_sentences=3, max_chars=420):
    """Keep the first paragraph / first few lines: the part worth hearing."""
    text = answer.split("📄")[0].strip()
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    first = paras[0] if paras else text
    lines = [l.strip(" •*-") for l in first.splitlines() if l.strip()]
    if len(lines) > 1:                       # template answer: title + bullet facts
        keep = lines[:1 + max_sentences]
        out = ". ".join(keep)
    else:
        sents = re.split(r"(?<=[.!?])\s+", first)
        out = " ".join(sents[:max_sentences])
    return out[:max_chars]


# MMS-TTS Hausa was trained on text written with the hooked letters (ɓ ɗ ƙ); its vocabulary has no capitals or
# digits. Our answers are typed with plain b/d/k, so common words are restored to standard spelling before
# synthesis. Only unambiguous words are listed (e.g. not "kasa", which can be ƙasa or kasa).
# NATIVE-SPEAKER REVIEW WELCOME: add or correct words here.
HOOKED = {
    "dari": "ɗari", "daya": "ɗaya", "hudu": "huɗu", "digo": "ɗigo", "kudi": "kuɗi", "kudin": "kuɗin", "kudade": "kuɗaɗe", "kudaden": "kuɗaɗen",
    "karamar": "ƙaramar", "kananan": "ƙananan", "karshe": "ƙarshe", "karin": "ƙarin", "kari": "ƙari",
    "karu": "ƙaru", "karuwa": "ƙaruwa", "kididdiga": "ƙididdiga", "kididdigar": "ƙididdigar",
    "karbi": "karɓi", "karba": "karɓa", "karbar": "karɓar", "kadan": "kaɗan", "wadannan": "waɗannan",
    "wadanne": "waɗanne", "dalibai": "ɗalibai", "kauye": "ƙauye", "kauyuka": "ƙauyuka", "kungiya": "ƙungiya",
    "kungiyoyi": "ƙungiyoyi", "bunkasa": "bunƙasa", "akalla": "aƙalla", "dauki": "ɗauki", "kasashe": "ƙasashe",
}
UNITS = "tiriliyan|biliyan|miliyan|dubu"
NUM = r"[\d,]*\d(?:\.\d+)?"


def _money(num, unit, naira=True):
    return naira_words(num, unit) if naira else naira_words(num, unit)[len("Naira "):]


def to_speech(answer):
    t = headline(answer)
    t = re.sub(r"[*_`#•📄🎙️👍👎🙏🔊]", " ", t)
    t = re.sub(r"\((personnel|overhead|capital|debt service)\)", "", t, flags=re.I)
    t = t.replace("—", ",").replace(" - ", ", ").replace(":", ",")
    t = re.sub(r"\b(\d+(?:\.\d+)?)\s?bn\b", r"\1 biliyan", t)
    t = re.sub(r"\b(\d+(?:\.\d+)?)\s?m\b", r"\1 miliyan", t)
    # money, in every order N-ATLaS writes it:
    #   ₦8.75 biliyan | N8.75 biliyan | Naira 8.75 biliyan | Naira biliyan 8.75 | biliyan 8.75 | 8.75 biliyan
    cur = r"(?:₦|\bN(?=\d)|\bNaira\s+)"
    t = re.sub(rf"{cur}\s?({NUM})\s*({UNITS})\b", lambda m: _money(m.group(1), m.group(2)), t, flags=re.I)
    t = re.sub(rf"\bNaira\s+({UNITS})\s+({NUM})", lambda m: _money(m.group(2), m.group(1).lower()), t, flags=re.I)
    t = re.sub(rf"\b({UNITS})\s+({NUM})", lambda m: _money(m.group(2), m.group(1).lower(), naira=False), t, flags=re.I)
    t = re.sub(rf"(?<![\d.])({NUM})\s*({UNITS})\b", lambda m: _money(m.group(1), m.group(2).lower(), naira=False), t, flags=re.I)
    t = re.sub(rf"{cur}\s?({NUM})", lambda m: "Naira " + decimal_words(m.group(1)), t)
    # percentages: "kashi 49.4 cikin 100", "kashi 49.4%", "49.4%"
    t = re.sub(r"kashi\s+([\d.]+)\s*(?:%|cikin\s+100)", lambda m: f"kashi {decimal_words(m.group(1))} cikin ɗari", t)
    t = re.sub(r"([\d.]+)\s?%", lambda m: f"kashi {decimal_words(m.group(1))} cikin ɗari", t)
    # month ranges
    for a, b in (("Jan-Sat", "Janairu zuwa Satumba"), ("Janairu-Yuni", "Janairu zuwa Yuni"),
                 ("Janairu-Satumba", "Janairu zuwa Satumba"), ("Oktoba-Disamba", "Oktoba zuwa Disamba")):
        t = t.replace(a, b)
    # remaining numbers (years, counts)
    t = re.sub(r"\d(?:[\d,]*\d)?(?:\.\d+)?", lambda m: decimal_words(m.group(0)), t)
    t = re.sub(r"\s*\(([^)]*)\)", r", \1,", t)          # brackets -> pauses
    t = re.sub(r"\s*,\s*(,\s*)+", ", ", t)
    t = re.sub(r"\s+([,.])", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.") + "."
    # lowercase + standard Hausa spelling (the voice model's alphabet)
    t = t.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"[a-zɓɗƙ']+", lambda m: HOOKED.get(m.group(0), m.group(0)), t)
