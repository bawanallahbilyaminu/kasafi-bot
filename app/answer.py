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
from .retrieve import Retrieval

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
    """Facts for N-ATLaS. Every item line carries its year, so a 2026 allocation is never read as 2025 spending."""
    b26 = "kasafin 2026" if lang == "ha" else "2026 budget"
    subject = ret.subject_ha if lang == "ha" else ret.subject_en
    lines = []
    if subject:   # without this, N-ATLaS sees "Total budget: ..." and may say the agency is not in the facts
        lines.append(f"DUKKAN ADADIN DA KE KASA NA: {subject}" if lang == "ha" else f"ALL FIGURES BELOW ARE FOR: {subject}")
    lines += [f"- {f.text(lang)}" for f in ret.facts]
    for i in ret.items:
        if i["type"] == "project":
            extra = f" ({i['lga'].title()})" if i.get("lga") and i["lga"] != "State Wide" else ""
            lines.append(f"- {'Aiki' if lang == 'ha' else 'Project'} ({b26}, {'kudin da aka ware' if lang == 'ha' else 'allocated'}): "
                         f"{i['name']}{extra} — {naira(i['amount'], lang)}")
        elif i["type"] == "agency":
            lines.append(f"- {'Hukuma' if lang == 'ha' else 'Agency'} ({b26}): {i['name']} — {naira(i['amount'], lang)}")
        elif i["type"] == "status_project":
            lines.append(f"- {i['group_en'] if lang == 'en' else i['group_ha']} {i['name']} — 2025: {naira(i['budget_2025'], lang)}, "
                         f"{'an kashe' if lang == 'ha' else 'spent'}: {naira(i['spent_2025'], lang)}, 2026: {naira(i['amount'], lang)}")
        elif i["type"] == "category":
            part = "wani bangare kawai, kudin da aka WARE (ba abin da aka kashe ba)" if lang == "ha" else \
                "one part only, money ALLOCATED (not spent)"
            lines.append(f"- {'Rabe' if lang == 'ha' else 'Category'} ({b26}; {part}): {i['name']} — {naira(i['amount'], lang)}")
    return "\n".join(lines)


def focus(ret, years, compare=False):
    """What N-ATLaS may write from. When the question is about a past year only (e.g. 2025 spending), it gets
    only that year's facts (plus undated ones such as counts). The 2026 items are still shown to the user,
    added by code under the answer. Prevents a real-but-wrong-year number from passing the grounding check."""
    ys = {y for y in (years or []) if y}
    if compare or not ys or 2026 in ys:
        return ret
    f = Retrieval(ret.intent, ret.subject_ha, ret.subject_en, note=ret.note)
    f.facts = [x for x in ret.facts if x.year is None or x.year in ys]
    f.pages = ret.pages
    if not f.facts:          # nothing for that year: fall back to everything rather than say nothing
        return ret
    return f


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


SPEND_WORDS = re.compile(r"\b(kashe|kashewa|spent|spending|expended|received)\b", re.I)
NOT_SPENT = re.compile(r"ba (a|tare da an) kashe|not spent|without (any )?spending|nothing (was )?spent|unspent|no money spent", re.I)
ALLOC_WORDS = re.compile(r"\b(ware|warewa|allocated|allocation|budgeted|approved|kasafin|budget)\b", re.I)
MONEY = re.compile(r"₦\s?(\d[\d,]*(?:\.\d+)?)")


def _money_sets(ret):
    """Money values (as written in facts) split into spending figures and allocation figures."""
    spend, alloc = set(), set()
    for f in ret.facts:
        if f.is_pct or f.is_count:
            continue
        label = f"{f.label_ha} {f.label_en} {f.key}".lower()
        is_spend = any(w in label for w in ("kashe", "spent", "actual", "received", "karba", "karbi", "ytd", "trend_202"))
        if f.key.startswith("trend_2026") or "approved" in label or NOT_SPENT.search(label):
            is_spend = False
        target = spend if is_spend else alloc
        for l in ("ha", "en"):
            for n in MONEY.findall(f.text(l)):
                target.add(_n(n))
    for i in ret.items:
        if i.get("type") == "status_project":
            for k, dest in (("spent_2025", spend), ("budget_2025", alloc), ("amount", alloc)):
                if i.get(k) is not None:
                    for l in ("ha", "en"):
                        for n in MONEY.findall(naira(i[k], l)):
                            dest.add(_n(n))
        elif "amount" in i:
            for l in ("ha", "en"):
                for n in MONEY.findall(naira(i["amount"], l)):
                    alloc.add(_n(n))
    return spend, alloc


ALLOC_CTX = re.compile(r"\b(ware|warewa|kasafi|kasafin|budget|budgeted|allocated|allocation|approved)\b", re.I)
ALLOC_VERB = re.compile(r"\b(ware|warewa|allocated|allocation|budgeted|approved)\b", re.I)


CAPITAL_CTX = re.compile(r"\b(capital|manyan ayyuka|ayyukan raya kasa)\b", re.I)


def _capital_sets(ret):
    """Money values from capital facts (and projects) vs from other facts (totals, personnel, overhead...)."""
    cap, other = set(), set()
    for f in ret.facts:
        if f.is_pct or f.is_count:
            continue
        label = f"{f.key} {f.label_en} {f.label_ha}".lower()
        dest = cap if (f.key.startswith("capital") or "capital" in label or "manyan ayyuka" in label) else other
        for l in ("ha", "en"):
            for n in MONEY.findall(f.text(l)):
                dest.add(_n(n))
    for i in ret.items:
        for k in ("amount", "budget_2025", "spent_2025"):
            if i.get(k) is not None:
                for l in ("ha", "en"):
                    for n in MONEY.findall(naira(i[k], l)):
                        cap.add(_n(n))
    return cap, other


TOTAL_CTX = re.compile(r"\b(total|jimilla|jimillar|overall|altogether|gaba daya|baki daya)\b", re.I)
NO_INFO = re.compile(r"not mentioned|no information|not provided|not available|no data|does not (contain|include|mention)|"
                     r"ba a ambaci|babu bayani|ba a bayar|ba ni da bayani|ba a samu bayani", re.I)


def capital_ok(draft, ret):
    """A figure described as capital / projects ("₦4.8 million on capital projects") must be a capital figure,
    not the department's total."""
    cap, other = _capital_sets(ret)
    cap_facts = set()
    for f in ret.facts:
        if not (f.is_pct or f.is_count) and (f.key.startswith("capital") or "capital" in f"{f.label_en}".lower()):
            for l in ("ha", "en"):
                cap_facts |= {_n(n) for n in MONEY.findall(f.text(l))}
    if not cap:
        return True, None
    for clause in re.split(r"\.(?=\s|$)|[;\n]|:(?=\s)", draft):
        prev_end = 0
        for m in MONEY.finditer(clause):
            n = _n(m.group(1))
            since_prev = clause[prev_end:m.start()]       # words between the previous figure (or clause start) and this one
            prev_end = m.end()
            near = clause[max(0, m.start() - 30):m.start()] + " " + clause[m.end():m.end() + 40]
            near = re.sub(r"₦\s?\d[\d,]*(?:\.\d+)?.*", "", clause[m.end():m.end() + 40])  # stop at the next figure
            near = clause[max(0, m.start() - 30):m.start()] + " " + near
            if CAPITAL_CTX.search(near) and n in other and n not in cap:
                return False, f"₦{n} presented as capital but it is a total/recurrent figure"
            if TOTAL_CTX.search(since_prev) and not CAPITAL_CTX.search(near) and not CAPITAL_CTX.search(since_prev) \
                    and n in cap_facts and n not in other:
                return False, f"₦{n} presented as the total but it is the capital part"
    return True, None


def claims_ok(draft, ret):
    """A figure described as SPENT must be a spending figure, and one described as ALLOCATED must be an allocation.
    Each figure is judged by the words just before it ("na kasafin ₦32.85 biliyan" = allocation), then by the verb
    of its clause ("an kashe ₦16.22 biliyan" = spent). Catches real-but-mislabelled numbers, e.g. a 2026 category
    allocation presented as money spent."""
    spend, alloc = _money_sets(ret)
    for clause in re.split(r"\.(?=\s|$)|[;\n]|:(?=\s)|\b(?:amma|but|while|whereas)\b", draft):   # not the "." in ₦34.37
        neg = bool(NOT_SPENT.search(clause))
        clause_spend = bool(SPEND_WORDS.search(clause)) and not neg
        clause_alloc = bool(ALLOC_VERB.search(clause)) or neg
        for m in MONEY.finditer(clause):
            n = _n(m.group(1))
            before = clause[max(0, m.start() - 32):m.start()]
            if ALLOC_CTX.search(before) and not SPEND_WORDS.search(before):
                expect = "alloc"
            elif SPEND_WORDS.search(before) and not NOT_SPENT.search(before):
                expect = "spend"
            elif clause_spend and not clause_alloc:
                expect = "spend"
            elif clause_alloc and not clause_spend:
                expect = "alloc"
            else:
                continue
            if expect == "spend" and n not in spend and n in alloc:
                return False, f"₦{n} presented as spent but it is an allocation"
            if expect == "alloc" and n not in alloc and n in spend:
                return False, f"₦{n} presented as allocated but it is spending"
    return capital_ok(draft, ret)


def grounded(draft, ret, lang):
    if (ret.facts or ret.items) and NO_INFO.search(draft or ""):
        return False, "N-ATLaS said there was no information, but figures were found"
    allowed = allowed_numbers(ret, lang) | {str(i) for i in range(0, 11)} | {"100"}
    for n in NUM_IN_TEXT.findall(draft):
        k = _n(n)
        if k not in allowed:
            return False, n
    return claims_ok(draft, ret)
