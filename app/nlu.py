"""Rule-based understanding of budget questions (Hausa, English, Pidgin).

N-ATLaS also produces an English rendering of the question (see engine.py); both the original
text and that rendering are scanned here, so a match in either language works.
"""
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------- lexicons
# Hausa / English sector words -> ministry-level admin code (aggregate of the ministry + its agencies)
SECTOR_WORDS = {
    "052100000000": ["lafiya", "asibiti", "asibitoci", "magani", "magunguna", "health", "hospital", "clinic", "likita"],
    "051700000000": ["ilimi", "makaranta", "makarantu", "education", "school", "schools", "malamai", "dalibai", "firamare",
                     "sakandare", "primary school", "secondary school"],
    "056900000000": ["jami'a", "jamia", "university", "polytechnic", "kwalejin ilimi", "higher education",
                     "ilimi mai zurfi"],
    "056905500100": ["scholarship", "scholarships", "tallafin karatu", "guraben karatu"],
    "021500000000": ["noma", "manoma", "taki", "agriculture", "farming", "farmers", "fertilizer", "fertiliser", "irrigation",
                     "ban ruwa"],
    "025200000000": ["ruwan sha", "rijiya", "rijiyoyi", "burtsatse", "water", "borehole", "boreholes", "water supply"],
    "023400000000": ["hanya", "hanyoyi", "titi", "tituna", "gada", "gadoji", "road", "roads", "bridge", "works", "ministry of works", "ma'aikatar ayyuka", "ayyukan gine-gine"],
    "017000000000": ["tsaro", "security", "'yan bindiga", "yan bindiga", "bandits", "vigilante"],
    "017200000000": ["addini", "masallaci", "masallatai", "religious", "mosque", "zakka", "zakat", "hisbah", "almajiri",
                     "aikin hajji", "hajj"],
    "051400000000": ["harkokin mata", "ma'aikatar mata", "mata da yara", "women", "women affairs"],
    "051300000000": ["matasa", "wasanni", "youth", "sports", "nakasa", "disability", "disabilities"],
    "053500000000": ["muhalli", "ambaliya", "zaizayar kasa", "environment", "erosion", "flood", "sanitation"],
    "026800000000": ["dabbobi", "kiwo", "kifi", "kaji", "livestock", "fisheries", "poultry", "animal"],
    "023100000000": ["wutar lantarki", "lantarki", "makamashi", "energy", "electricity", "power", "solar"],
    "025300000000": ["gidaje", "filaye", "housing", "lands", "land"],
    "022200000000": ["kasuwanci", "masana'antu", "commerce", "industry", "trade", "market", "kasuwa"],
    "022900000000": ["sufuri", "transport", "motocin haya"],
    "055600000000": ["jin kai", "walwala", "humanitarian", "social welfare"],
    "016102100800": ["'yan gudun hijira", "yan gudun hijira", "gudun hijira", "idp", "idps", "displaced"],
    "032600000000": ["ma'aikatar shari'a", "justice", "law reform"],
    "031800000000": ["kotu", "kotuna", "judiciary", "court", "courts", "alkalai"],
    "012300000000": ["yada labarai", "rediyo", "talabijin", "information", "radio", "television", "rtv"],
    "023800000000": ["tsare-tsare", "tsare tsare", "budget and economic planning", "kasafin kudi da tsare"],
    "022000000000": ["ma'aikatar kudi", "ministry of finance"],
    "011200000000": ["majalisar dokoki", "house of assembly", "assembly", "'yan majalisa"],
    "011100000000": ["gidan gwamnati", "government house", "gwamna", "governor"],
    "022800000000": ["kimiyya", "science and technology"],
    "027900000000": ["fasahar zamani", "digital economy", "ict", "innovation"],
    "028900000000": ["koyon sana'a", "sana'o'i", "skills acquisition", "entrepreneurship"],
    "055100000000": ["kananan hukumomi", "local government", "sarakuna", "chieftaincy"],
    "011100800100": ["sema", "emergency management", "agajin gaggawa"],
    "052100300100": ["kiwon lafiya matakin farko", "primary health", "phc", "cibiyoyin lafiya"],
    "051700300100": ["subeb", "universal basic education"],
}

# Cross-cutting topics answered from the FUNCTIONAL classification (all MDAs together)
FUNCTION_WORDS = {
    "710": ["social protection", "kariyar zamantakewa", "kariya ga marasa karfi", "marasa galihu", "marasa karfi",
            "talakawa", "cash transfer", "tallafin kudi", "social safety net", "safety net", "social security",
            "jin dadin jama'a", "tallafi ga talakawa"],
    "7102": ["pension", "pensions", "fansho", "'yan fansho", "yan fansho", "gratuity", "old age", "tsofaffi"],
    "7101": ["disability benefits", "masu bukata ta musamman"],
    "7104": ["family and children", "kananan yara", "children welfare"],
    "7105": ["unemployment", "rashin aikin yi", "marasa aikin yi"],
    "703": ["public order", "public safety", "oda da tsaro"],
    "705": ["environmental protection", "kare muhalli"],
    "706": ["community amenities", "housing and community"],
    "708": ["recreation", "culture and religion", "al'adu"],
}

LGA_ALIASES = {
    "33310100": ["binji"], "33311100": ["kware"], "33311500": ["silame"],
    "33311600": ["sokoto north", "sakkwato ta arewa", "sokoto ta arewa"],
    "33311700": ["sokoto south", "sakkwato ta kudu", "sokoto ta kudu"],
    "33311900": ["tangaza"], "33312100": ["wamakko", "wamako"], "33320400": ["gada"], "33320500": ["goronyo"],
    "33320700": ["gwadabawa"], "33320800": ["illela"], "33320900": ["isa"], "33321300": ["sabon birni"],
    "33322200": ["wurno"], "33330200": ["bodinga"], "33330300": ["dange shuni", "dange-shuni", "dange"],
    "33331000": ["kebbe"], "33331400": ["shagari"], "33331800": ["tambuwal"], "33332300": ["yabo"],
    "33342400": ["state wide", "statewide", "duk jiha", "fadin jiha"],
}

MEASURE_WORDS = {
    "personnel": ["albashi", "salary", "salaries", "personnel", "wages", "albashin ma'aikata"],
    "overhead": ["gudanarwa", "overhead", "running cost", "kudaden gudanarwa", "recurrent"],
    "capital": ["manyan ayyuka", "ayyukan raya kasa", "capital", "capital projects", "aikace-aikace"],
    "debt_service": ["bashi", "basussuka", "debt", "loan", "loans"],
    "revenue": ["kudaden shiga", "kudaden shigar", "kudin shiga", "kudin shigar", "samun kudi", "haraji", "revenue", "igr", "faac", "income", "tax", "kason tarayya"],
}
PERF_WORDS = ["an kashe", "aka kashe", "kashe", "kashewa", "an yi amfani", "aiwatarwa", "aiwatar", "spent", "spend",
              "performance", "actual", "released", "implemented", "implementation", "an saki", "aka saki"]
PROJECT_WORDS = ["aikin", "ayyukan", "project", "projects", "construction", "gina", "ginawa", "gyara", "gyaran",
                 "renovation", "rehabilitation", "purchase", "procurement", "saya", "sayen"]
# Hausa object words -> English search keywords for the project list
PROJECT_KEYWORDS = {
    "asibiti": "hospital", "asibitoci": "hospital", "makaranta": "school", "makarantu": "school",
    "hanya": "road", "hanyoyi": "road", "titi": "road", "tituna": "road", "rijiya": "borehole", "burtsatse": "borehole",
    "rijiyoyi": "borehole", "masallaci": "mosque", "masallatai": "mosque", "gada": "bridge", "kasuwa": "market",
    "mota": "vehicle", "motoci": "vehicle", "babur": "motorcycle", "babura": "motorcycle", "taki": "fertilizer",
    "lantarki": "electricity", "hasken rana": "solar", "ruwa": "water", "magani": "drugs", "magunguna": "drugs",
    "dam": "dam", "madatsar ruwa": "dam", "cibiyar lafiya": "health centre", "ofis": "office", "gidaje": "housing",
    "fitilun titi": "street light", "kwamfuta": "computer", "tallafi": "empowerment", "agaji": "relief",
}
WHAT_DONE = ["me ake", "me za a", "me aka", "mene ne ake", "wadanne", "wanne aiki", "wane aiki", "wane ayyuka",
             "what projects", "which projects", "what is being done", "what will be done", "ayyukan da"]
TOTAL_RE = (r"jimilla|gaba daya|baki daya|duka kasafi|dukkan kasafi|total budget|whole budget|overall|"
            r"kasafin (kudin )?jiha|state budget|budget of sokoto|sokoto (state )?budget|size of the budget|girman kasafi")
STATUS_WORDS = ["an fara", "aka fara", "fara a", "ba a kammala", "ba a gama", "ba a kare", "ba su kare", "ba su kammala",
                "bakari", "ba kari", "ci gaba", "ongoing", "continuing", "carried over", "carry over", "uncompleted",
                "incomplete", "not completed", "not finished", "abandoned", "watsi", "ba a fara", "sabbin ayyuka",
                "sababbin ayyuka", "new projects", "started", "still running", "har yanzu", "kammala", "completed",
                "finished", "dropped", "an daina", "stalled", "tsaya", "tsaye", "status"]
RANK_TOP = ["mafi yawa", "mafi girma", "fi yawa", "fi girma", "mafi samun", "fi samun", "highest", "largest", "biggest",
            "most", "top", "ta fi", "ya fi", "suka fi"]
RANK_BOTTOM = ["mafi karanci", "mafi kankanta", "fi karanci", "fi kankanta", "mafi kadan", "lowest", "smallest", "least",
               "bottom", "worst"]
GROWTH_WORDS = ["karu", "karuwa", "kari", "increase", "increased", "grew", "growth", "rise"]
DECLINE_WORDS = ["ragu", "raguwa", "decrease", "decreased", "cut", "cuts", "reduced", "reduction", "fall"]
COMPARE_WORDS = ["bambanci", "kwatanta", "idan aka kwatanta", "compared", "compare", "comparison", "change", "difference",
                 "versus", "vs", "fiye da bara", "da bara"] + GROWTH_WORDS + DECLINE_WORDS
PROJECT_NOUNS = ["ayyuka", "ayyukan", "aiki", "aikin", "project", "projects"]
UNIT_LGA = ["kananan hukumomi", "karamar hukuma", "lga", "lgas", "local government", "local governments"]
YEAR_RE = re.compile(r"\b(2024|2025|2026|2027|2028)\b")
GREETING_WORDS = ["sannu", "salam", "assalamu", "hello", "hi", "barka", "ina kwana", "ina wuni", "good morning",
                  "/start", "start", "taimako", "help"]
HAUSA_MARKERS = ["nawa", " ne", " ce", "kasafin", "kudin", "kudi", " an ", "aka", "shin", "wane", "wace", "menene",
                 "mene", "yaya", " da ", " na ", " ta ", "ma'aikatar", "jihar", "gwamnati", "nawa ne", "ayyukan",
                 "sannu", "barka", "lafiya", "ilimi"]

STOP = {"of", "and", "the", "for", "state", "sokoto", "ministry", "agency", "department", "board", "office", "&",
        "development", "affairs", "commission", "programme", "sokoto's", "ma'aikatar", "hukumar"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = s.lower().replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", s).strip()


def has_word(text, w):
    # allow the Hausa linking suffix -n / -r ("bashi" matches "bashin", "kudaden shiga" matches "kudaden shigar")
    return re.search(r"(?<![a-z'])" + re.escape(w) + r"(?:n|r)?(?![a-z'])", text) is not None


@dataclass
class Parsed:
    text: str
    lang: str = "ha"
    intent: str = "unknown"  # greeting | overview | revenue | mda | lga | project | unknown
    mda_codes: list = field(default_factory=list)
    function_codes: list = field(default_factory=list)
    lga_codes: list = field(default_factory=list)
    measure: str = None  # personnel | overhead | capital | debt_service | revenue | None
    years: list = field(default_factory=list)
    performance: bool = False
    project_terms: list = field(default_factory=list)
    wants_projects: bool = False
    analysis: str = None      # project_status | ranking
    rank_order: str = None    # top | bottom
    rank_metric: str = None   # allocation | implementation | growth | decline
    rank_unit: str = None     # ministry | lga | project
    compare: bool = False

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class Understanding:
    def __init__(self, budget_db):
        con = sqlite3.connect(budget_db)
        self.mdas = con.execute("SELECT code, name FROM line_items WHERE kind='exp_admin' AND measure='total' "
                                "AND length(code)=12 AND substr(code,3)!='0000000000'").fetchall()
        self.lgas = dict(con.execute("SELECT code, name FROM line_items WHERE kind='exp_location' AND measure='total' "
                                     "AND length(code)=8").fetchall())
        self.lgas.update(dict(con.execute("SELECT DISTINCT location_code, location_name FROM projects "
                                          "WHERE length(location_code)=8").fetchall()))
        self.lga_aliases = {c: list(LGA_ALIASES.get(c, [])) + [norm(n)] for c, n in self.lgas.items()}
        con2 = sqlite3.connect(budget_db)
        self.functions = [(c, n) for c, n in con2.execute(
            "SELECT code, name FROM line_items WHERE kind='exp_function' AND measure='total' AND length(code) IN (3,4)")
            if re.fullmatch(r"[A-Z ,&.()'-]+", n or "")]  # skip names garbled in the PDF
        con2.close()
        con.close()
        self.mda_tokens = []
        ministry_names = {c[:4]: norm(n) for c, n in self.mdas if c[4:] == "0" * 8}
        for code, name in self.mdas:
            # an HQ unit named exactly like its ministry ("Ministry of Health") resolves to the whole ministry
            if code[4:] != "0" * 8 and norm(name) == ministry_names.get(code[:4]):
                code = code[:4] + "0" * 8
            n = norm(name)
            toks = [t for t in re.findall(r"[a-z']+", n) if t not in STOP and len(t) > 2]
            acr = re.findall(r"\(([a-z]{3,})\)", n)
            self.mda_tokens.append((code, name, set(toks), acr))

    def detect_lang(self, t):
        words = re.findall(r"[a-z']+", t)
        en_words = {"how", "much", "many", "what", "which", "who", "the", "is", "are", "was", "were", "did", "does", "for",
                    "of", "to", "in", "on", "allocated", "spent", "budget", "projects", "project", "ministry", "still",
                    "and", "with", "has", "have", "state", "money", "total", "show", "tell", "me", "about", "this", "that",
                    "highest", "lowest", "most", "least", "compare", "between", "ongoing", "started", "completed"}
        ha_words = {"nawa", "ne", "ce", "kasafi", "kasafin", "kudi", "kudin", "an", "aka", "shin", "wane", "wace", "wadanne",
                    "menene", "mene", "yaya", "da", "na", "ta", "ma'aikatar", "jihar", "gwamnati", "ayyuka", "ayyukan",
                    "sannu", "barka", "lafiya", "ilimi", "ware", "kashe", "ina", "su", "suka", "ya", "ta", "mafi", "fi", "a"}
        en = sum(w in en_words for w in words)
        ha = sum(w in ha_words for w in words)
        return "en" if en > ha else "ha"

    def match_mdas(self, t):
        found = []
        for code, words in SECTOR_WORDS.items():
            if any(has_word(t, w) for w in words):
                found.append(code)
        # exact-ish matches against official MDA names (English renderings, acronyms)
        qtok = set(re.findall(r"[a-z']+", t))
        best = []
        for code, name, toks, acr in self.mda_tokens:
            if any(a in qtok for a in acr):
                best.append((10, code)); continue
            if not toks:
                continue
            hit = len(toks & qtok) / len(toks)
            if hit >= 0.99 or (hit >= 0.6 and len(toks & qtok) >= 2):
                best.append((hit * len(toks), code))
        best.sort(reverse=True)
        for _, code in best[:2]:
            if code not in found:
                found.append(code)
        # if both a ministry and one of its agencies matched by name, keep the more specific agency
        specific = [c for c in found if c[4:] != "00000000"]
        found = [c for c in found if not (c[4:] == "00000000" and any(s[:4] == c[:4] for s in specific))] if specific else found
        return found[:3]

    @staticmethod
    def _only_budget_words(t):
        """'Menene kasafin 2026?' / 'what is the budget' -> nothing but question words + 'budget'."""
        words = set(re.findall(r"[a-z']+", t))
        if not words & {"kasafi", "kasafin", "budget"}:
            return False
        filler = {"menene", "mene", "me", "nawa", "ne", "ce", "shin", "yaya", "kasafi", "kasafin", "kudi", "kudin",
                  "jiha", "jihar", "sokoto", "sakkwato", "na", "ta", "a", "da", "gwamnati", "gwamnatin", "budget",
                  "what", "is", "the", "of", "how", "much", "state", "for", "in", "this", "year", "bana", "shekara",
                  "shekarar", "ina", "son", "sanin", "fada", "min", "mini", "game", "akan", "aka", "an", "kashe",
                  "ware", "daga", "zuwa", "yanzu", "spent", "so", "far", "has", "been", "much", "many", "har", "tun",
                  "jimillar", "duka", "dukka", "gaba", "daya", "allocated", "used", "amfani", "yi"}
        return words <= filler

    def match_functions(self, t):
        found = [c for c, words in FUNCTION_WORDS.items() if any(has_word(t, w) for w in words)]
        qtok = set(re.findall(r"[a-z']+", t))
        weak = {"general", "services", "and", "affairs", "n.e.c", "nec", "other", "of", "the", "public"}
        for code, name in self.functions:
            toks = {w for w in re.findall(r"[a-z]+", name.lower()) if w not in weak and len(w) > 2}
            if len(toks) >= 2 and toks <= qtok and code not in found:
                found.append(code)
        return found[:2]

    def match_lgas(self, t):
        out = []
        for code, al in self.lga_aliases.items():
            if any(has_word(t, a) for a in al):
                out.append(code)
        # "gada" means bridge in Hausa as well as an LGA name: only treat as LGA if 'karamar hukuma' / 'lga' is said
        if "33320400" in out and not re.search(r"karamar hukuma|lga|local government|a gada|gada lga", t):
            out.remove("33320400")
        if "33320900" in out and not re.search(r"karamar hukuma|lga|local government|isa lga|a isa", t):
            out.remove("33320900")  # "isa" also means "enough/reach"
        return out

    def parse(self, text, english=None):
        t = norm(text)
        both = t + " || " + norm(english or "")
        p = Parsed(text=text)
        p.lang = self.detect_lang(t)
        p.years = sorted({int(y) for y in YEAR_RE.findall(both)})
        p.performance = any(has_word(both, w) for w in PERF_WORDS)
        for m, words in MEASURE_WORDS.items():
            if any(has_word(both, w) for w in words):
                p.measure = m
                break
        p.mda_codes = self.match_mdas(both)
        p.lga_codes = self.match_lgas(both)
        p.function_codes = self.match_functions(both)
        terms = []
        for ha, en in PROJECT_KEYWORDS.items():
            if has_word(both, ha) or has_word(both, en):
                terms.append(en)
        p.project_terms = sorted(set(terms))
        is_project = any(has_word(both, w) for w in PROJECT_WORDS)
        p.wants_projects = is_project or any(w in both for w in WHAT_DONE)

        mentions_projects = any(has_word(both, w) for w in PROJECT_NOUNS)
        p.compare = any(has_word(both, w) for w in COMPARE_WORDS)
        top = any(has_word(both, w) for w in RANK_TOP)
        bottom = any(has_word(both, w) for w in RANK_BOTTOM)
        if top or bottom:
            p.rank_order = "bottom" if bottom and not top else "top"
            if any(has_word(both, w) for w in GROWTH_WORDS):
                p.rank_metric = "growth"
            elif any(has_word(both, w) for w in DECLINE_WORDS):
                p.rank_metric = "decline"
            elif p.performance or has_word(both, "aiwatar") or has_word(both, "aiwatarwa"):
                p.rank_metric = "implementation"
            else:
                p.rank_metric = "allocation"
            p.rank_unit = ("lga" if any(has_word(both, w) for w in UNIT_LGA) and not p.lga_codes
                           else "project" if mentions_projects else "ministry")

        if len(t) < 25 and any(has_word(t, g) for g in GREETING_WORDS) and not (p.mda_codes or p.lga_codes):
            p.intent = "greeting"
        elif mentions_projects and any(has_word(both, w) for w in STATUS_WORDS) and (
                len(p.years) >= 2 or not p.rank_order):
            p.intent = p.analysis = "project_status"
        elif p.rank_order and not (p.rank_unit == "ministry" and p.mda_codes and not p.function_codes and
                                   p.rank_metric == "allocation" and len(p.mda_codes) == 1 and not mentions_projects
                                   and not any(has_word(both, w) for w in ["wace", "wane", "which", "what"])):
            p.intent = p.analysis = "ranking"
        elif p.lga_codes:
            p.intent = "lga"
        elif is_project and p.project_terms:
            p.intent = "project"
        elif p.function_codes and not (p.mda_codes and any(has_word(t, w) for v in SECTOR_WORDS.values() for w in v)):
            p.intent = "function"
        elif p.mda_codes:
            p.intent = "mda"
        elif p.measure == "revenue":
            p.intent = "revenue"
        elif p.measure in ("personnel", "overhead", "debt_service", "capital"):
            p.intent = "overview"
        elif p.project_terms:
            p.intent = "project"
        elif re.search(TOTAL_RE, both) or self._only_budget_words(t):
            p.intent = "overview"
        return p
