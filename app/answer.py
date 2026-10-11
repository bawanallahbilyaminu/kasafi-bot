"""Answer composition.

1. `facts_block()` renders the retrieved facts as the ONLY material N-ATLaS may use.
2. `template_answer()` builds a deterministic answer straight from the facts. It is used
   when the LLM is off, fails, or its draft does not pass the grounding check.
3. `grounded()` checks every number in an LLM draft against the facts.
4. `citation()` is appended by code, never by the model.
"""
import re

from .config import BUDGET_TITLE_EN, BUDGET_TITLE_HA
from .fmt import naira, pct_str

HELP_HA = ("Sannu! Ni ne *Kasafi Bot* — ina amsa tambayoyi game da Kasafin Kudin Jihar Sokoto na 2026 "
           "da yadda aka aiwatar da kasafin 2025, daga takardun gwamnati kai tsaye.\n\n"
           "Kuna iya rubutu ko aiko da *sakon murya* da Hausa. Misalai:\n"
           "• Nawa aka ware wa lafiya a 2026?\n"
           "• Nawa aka kashe a fannin ilimi a 2025?\n"
           "• Wadanne ayyuka ne za a yi a Tambuwal?\n"
           "• Ayyukan rijiyoyin burtsatse nawa ne a kasafin?\n"
           "• Nawa ne kudaden shigar jiha?")
HELP_EN = ("Hello! I'm *Kasafi Bot*. I answer questions about the Sokoto State 2026 Approved Budget and how the 2025 "
           "budget was implemented, straight from government documents.\n\nType or send a *voice note* in Hausa "
           "or English. Examples:\n• How much is allocated to health in 2026?\n• How much was spent on education in 2025?\n"
           "• What projects are planned in Tambuwal?\n• What is the state's revenue?")
NOT_FOUND_HA = ("Yi hakuri, ban gane wace ma'aikata, fanni ko karamar hukuma kuke tambaya ba. "
                "Gwada misali: \"Nawa aka ware wa noma a 2026?\" ko \"Wadanne ayyuka ne a Wamakko?\"")
NOT_FOUND_EN = ("Sorry, I couldn't tell which ministry, sector or LGA you mean. Try: \"How much is allocated to "
                "agriculture in 2026?\" or \"What projects are in Wamakko?\"")


def citation(ret, lang):
    pages = sorted(p for p in ret.pages if p)
    pages += sorted({i["page"] for i in ret.items if i.get("page")} - set(pages))
    pg = ", ".join(str(p) for p in pages[:6])
    if lang == "ha":
        return f"📄 Madogara: {BUDGET_TITLE_HA}" + (f", shafi {pg}" if pg else "")
    return f"📄 Source: {BUDGET_TITLE_EN}" + (f", page {pg}" if pg else "")


def facts_block(ret, lang):
    lines = [f"- {f.text(lang)}" for f in ret.facts]
    for i in ret.items:
        if i["type"] == "project":
            extra = f" ({i['lga'].title()})" if i.get("lga") and i["lga"] != "State Wide" else ""
            lines.append(f"- {'Aiki' if lang == 'ha' else 'Project'}: {i['name']}{extra} — {naira(i['amount'], lang)}")
        elif i["type"] == "agency":
            lines.append(f"- {'Hukuma' if lang == 'ha' else 'Agency'}: {i['name']} — {naira(i['amount'], lang)}")
    return "\n".join(lines)


def items_block(ret, lang):
    out = []
    agencies = [i for i in ret.items if i["type"] == "agency"]
    projects = [i for i in ret.items if i["type"] == "project"]
    if agencies:
        out.append("Manyan hukumomin da ke karkashinta (2026):" if lang == "ha" else "Largest agencies (2026):")
        out += [f"• {i['name']}: {naira(i['amount'], lang)}" for i in agencies]
    if projects:
        if out:
            out.append("")
        out.append("Manyan ayyuka (2026):" if lang == "ha" else "Largest projects (2026):")
        for i in projects[:6]:
            loc = f" — {i['lga'].title()}" if i.get("lga") and i["lga"] != "State Wide" and ret.intent != "lga" else ""
            out.append(f"• {i['name'][:110]}{loc}: {naira(i['amount'], lang)}")
    return "\n".join(out)


def template_answer(ret, lang):
    if not ret.facts and not ret.items:
        return NOT_FOUND_HA if lang == "ha" else NOT_FOUND_EN
    head = {"ha": f"*{ret.subject_ha}*" if ret.subject_ha else "", "en": f"*{ret.subject_en}*" if ret.subject_en else ""}[lang]
    body = []
    for f in ret.facts[:10]:
        body.append(f"• {f.text(lang)}")
    if ret.items:
        body.append("\n" + items_block(ret, lang))
    if ret.note == "statewide":
        body.append("\nLura: ayyuka da yawa an tsara su a matsayin 'State Wide' (na duk jiha), su ma suna iya shafar wannan karamar hukuma."
                    if lang == "ha" else "\nNote: many projects are budgeted 'State Wide' and may also benefit this LGA.")
    return (head + "\n" if head else "") + "\n".join(body)


NUM_IN_TEXT = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _n(s):
    s = s.replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def allowed_numbers(ret, lang):
    allowed = set()
    texts = [f.text(l) for f in ret.facts for l in ("ha", "en")]
    texts += [naira(i["amount"], l) for i in ret.items for l in ("ha", "en")] + [i["name"] for i in ret.items]
    texts += [str(y) for y in range(2020, 2031)] + [f.label_en for f in ret.facts]
    for t in texts:
        for n in NUM_IN_TEXT.findall(t):
            allowed.add(_n(n))
    return allowed


def grounded(draft, ret, lang):
    allowed = allowed_numbers(ret, lang) | {str(i) for i in range(0, 11)} | {"100"}
    for n in NUM_IN_TEXT.findall(draft):
        k = _n(n)
        if k not in allowed:
            return False, n
    return True, None
