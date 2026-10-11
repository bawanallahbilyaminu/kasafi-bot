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
           "• Nawa ne kudaden shigar jiha?\n\n"
           "🔊 Idan kun aiko da sakon murya, zan amsa muku da murya ma. Aiko /murya don samun amsa da murya kullum.")
HELP_EN = ("Hello! I'm *Kasafi Bot*. I answer questions about the Sokoto State 2026 Approved Budget and how the 2025 "
           "budget was implemented, straight from government documents.\n\nType or send a *voice note* in Hausa "
           "or English. Examples:\n• How much is allocated to health in 2026?\n• How much was spent on education in 2025?\n"
           "• What projects are planned in Tambuwal?\n• What is the state's revenue?")
NOT_FOUND_HA = ("Yi hakuri, ban gane wace ma'aikata, fanni ko karamar hukuma kuke tambaya ba. "
                "Gwada misali: \"Nawa aka ware wa noma a 2026?\" ko \"Wadanne ayyuka ne a Wamakko?\"")
NOT_FOUND_EN = ("Sorry, I couldn't tell which ministry, sector or LGA you mean. Try: \"How much is allocated to "
                "agriculture in 2026?\" or \"What projects are in Wamakko?\"")


DOC_HA = {"budget2026": "Kasafin Kudin Jihar Sokoto na 2026 (wanda aka amince)",
          "budget2025": "Kasafin Kudin Jihar Sokoto na 2025 (wanda aka amince)"}
DOC_EN = {"budget2026": "Sokoto State 2026 Approved Budget", "budget2025": "Sokoto State 2025 Approved Budget"}


def _doc(src, lang):
    if src in DOC_HA:
        return DOC_HA[src] if lang == "ha" else DOC_EN[src]
    y, q = src[:4], src[-1]
    return (f"Rahoton aiwatar da kasafi na Q{q} {y}" if lang == "ha" else f"Budget Implementation Report Q{q} {y}")


def citation(ret, lang):
    by = {}
    for f in ret.facts:
        if f.page:
            by.setdefault(getattr(f, "source", "budget2026"), set()).add(f.page)
    for i in ret.items:
        if i.get("page"):
            by.setdefault("budget2026", set()).add(i["page"])
    if not by:
        return ""
    word = "shafi" if lang == "ha" else "page"
    parts = [f"{_doc(src, lang)}, {word} {', '.join(str(x) for x in sorted(pg)[:6])}"
             for src, pg in sorted(by.items(), key=lambda kv: kv[0] != "budget2026")]
    return ("📄 Madogara: " if lang == "ha" else "📄 Source: ") + "; ".join(parts)


def facts_block(ret, lang):
    lines = [f"- {f.text(lang)}" for f in ret.facts]
    for i in ret.items:
        if i["type"] == "project":
            extra = f" ({i['lga'].title()})" if i.get("lga") and i["lga"] != "State Wide" else ""
            lines.append(f"- {'Aiki' if lang == 'ha' else 'Project'}: {i['name']}{extra} — {naira(i['amount'], lang)}")
        elif i["type"] == "agency":
            lines.append(f"- {'Hukuma' if lang == 'ha' else 'Agency'}: {i['name']} — {naira(i['amount'], lang)}")
        elif i["type"] == "status_project":
            lines.append(f"- {i['group_en'] if lang == 'en' else i['group_ha']} {i['name']} — 2025: {naira(i['budget_2025'], lang)}, "
                         f"{'an kashe' if lang == 'ha' else 'spent'}: {naira(i['spent_2025'], lang)}, 2026: {naira(i['amount'], lang)}")
        elif i["type"] == "category":
            lines.append(f"- {'Rabe' if lang == 'ha' else 'Category'}: {i['name']} — {naira(i['amount'], lang)}")
    return "\n".join(lines)


def items_block(ret, lang):
    out = []
    cats = [i for i in ret.items if i["type"] == "category"]
    if cats:
        out.append("Rabe-rabensa (2026):" if lang == "ha" else "Breakdown (2026):")
        out += [f"• {i['name'] if lang == 'ha' else i.get('name_en', i['name'])}: {naira(i['amount'], lang)}" for i in cats]
    status = [i for i in ret.items if i["type"] == "status_project"]
    group = None
    for i in status:
        g = i["group_ha"] if lang == "ha" else i["group_en"]
        if g != group:
            if out:
                out.append("")
            out.append(g)
            group = g
        if lang == "ha":
            out.append(f"• {i['name'][:100]} — 2025: {naira(i['budget_2025'], lang)}, an kashe: {naira(i['spent_2025'], lang)}, "
                       f"2026: {naira(i['amount'], lang)}")
        else:
            out.append(f"• {i['name'][:100]} — 2025: {naira(i['budget_2025'], lang)}, spent: {naira(i['spent_2025'], lang)}, "
                       f"2026: {naira(i['amount'], lang)}")
    agencies = [i for i in ret.items if i["type"] == "agency"]
    projects = [i for i in ret.items if i["type"] == "project"]
    if agencies:
        if out:
            out.append("")
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


def notes_block(ret, lang):
    if ret.note == "jan_sep":
        return ("Lura: abin da aka kashe a 2025 na watan Janairu zuwa Satumba ne kawai (daga kasafin 2026); "
                "kudin da aka kashe a Oktoba-Disamba ba ya ciki." if lang == "ha" else
                "Note: 2025 spending covers January-September only (as published in the 2026 budget); "
                "October-December spending is not included.")
    if ret.note == "statewide":
        return ("Lura: ayyuka da yawa an tsara su a matsayin 'State Wide' (na duk jiha), su ma suna iya shafar wannan karamar hukuma."
                if lang == "ha" else "Note: many projects are budgeted 'State Wide' and may also benefit this LGA.")
    return ""


def template_answer(ret, lang):
    if not ret.facts and not ret.items:
        return NOT_FOUND_HA if lang == "ha" else NOT_FOUND_EN
    head = {"ha": f"*{ret.subject_ha}*" if ret.subject_ha else "", "en": f"*{ret.subject_en}*" if ret.subject_en else ""}[lang]
    body = []
    for f in ret.facts[:18]:
        body.append(f"• {f.text(lang)}")
    if ret.items:
        body.append("\n" + items_block(ret, lang))
    note = notes_block(ret, lang)
    if note:
        body.append("\n" + note)
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
