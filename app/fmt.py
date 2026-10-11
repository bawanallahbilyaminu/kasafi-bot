"""Number formatting for answers (Hausa and English)."""


def naira(v, lang="ha"):
    """₦ amount in short form: ₦12.5 biliyan / ₦12.5 billion."""
    if v is None:
        return "—"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if lang == "ha":
        units = [(1e12, "tiriliyan"), (1e9, "biliyan"), (1e6, "miliyan"), (1e3, "dubu")]
    else:
        units = [(1e12, "trillion"), (1e9, "billion"), (1e6, "million"), (1e3, "thousand")]
    for size, word in units:
        if a >= size:
            n = a / size
            s = f"{n:,.2f}".rstrip("0").rstrip(".")
            return f"{sign}₦{s} {word}"
    return f"{sign}₦{a:,.0f}"


def pct(part, whole):
    if not whole:
        return None
    return round(100.0 * part / whole, 1)


def pct_str(p, lang="ha"):
    if p is None:
        return "—"
    s = f"{p:.1f}".rstrip("0").rstrip(".")
    return f"kashi {s} cikin 100" if lang == "ha" else f"{s}%"
