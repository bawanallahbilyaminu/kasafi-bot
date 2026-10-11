"""Turn a written Hausa answer into text a Hausa TTS voice can read aloud.

- numbers -> Hausa words (124 -> "dari da ashirin da hudu")
- "₦124.41 biliyan" -> "Naira biliyan dari da ashirin da hudu da miliyan dari hudu da goma"
- "kashi 10.6 cikin 100" -> "kashi goma digo shida cikin dari"
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


def to_speech(answer):
    t = headline(answer)
    t = re.sub(r"[*_`#•📄🎙️👍👎🙏]", " ", t)
    t = re.sub(r"\((personnel|overhead|capital|debt service)\)", "", t, flags=re.I)
    t = t.replace("—", ",").replace(" - ", ", ").replace(":", ",")
    # money: ₦124.41 biliyan / ₦500 miliyan / ₦12,345
    t = re.sub(r"₦\s?([\d,]+(?:\.\d+)?)\s*(tiriliyan|biliyan|miliyan|dubu)\b", lambda m: naira_words(m.group(1), m.group(2)), t)
    t = re.sub(r"₦\s?([\d,]+(?:\.\d+)?)", lambda m: "Naira " + decimal_words(m.group(1)), t)
    # percentages
    t = re.sub(r"kashi ([\d.]+) cikin 100", lambda m: f"kashi {decimal_words(m.group(1))} cikin dari", t)
    t = re.sub(r"([\d.]+)\s?%", lambda m: f"kashi {decimal_words(m.group(1))} cikin dari", t)
    # Jan-Sat / Q4 style abbreviations
    t = t.replace("Jan-Sat", "Janairu zuwa Satumba").replace("Janairu-Yuni", "Janairu zuwa Yuni")
    t = t.replace("Janairu-Satumba", "Janairu zuwa Satumba")
    # remaining numbers (years, counts)
    t = re.sub(r"\d[\d,]*(?:\.\d+)?", lambda m: decimal_words(m.group(0)), t)
    t = re.sub(r"\s*\(([^)]*)\)", r", \1,", t)          # brackets -> pauses
    t = re.sub(r"\s*,\s*(,\s*)+", ", ", t)
    t = re.sub(r"\s+([,.])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip(" ,.") + "."
