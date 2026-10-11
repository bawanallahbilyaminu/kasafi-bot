"""Registration before first use: the user's name and organisation.

Works the same on Telegram and WhatsApp (plain text replies; Telegram adds buttons). Stored in the log database
(`users` table) under the same salted user hash as the interactions, so activity can be reviewed per user and per
organisation without storing phone numbers or Telegram ids. If someone asks a question before registering, it is
kept and answered as soon as they finish.
"""
from dataclasses import dataclass

COMMANDS = {"join", "start", "/start", "help", "taimako", "menu", "/help", "/taimako"}
NONE_WORDS = {"babu", "none", "no", "nil", "ba ni da", "ba", "-", "n/a", "na"}

ASK_NAME = ("Barka da zuwa *Kasafi Bot*! 👋\n"
            "Ina amsa tambayoyi kan kasafin kudin Jihar Sokoto, ta rubutu ko sakon murya.\n\n"
            "Kafin mu fara, don Allah rubuta *sunanka* (misali: Aminu Bello).\n"
            "_Welcome! Please type your name to get started._")
ASK_ORG = ("Na gode, *{name}*. 🙏\n"
           "Wace *ma'aikata, hukuma ko kungiya* kake aiki da ita? "
           "(misali: Ma'aikatar Kasafi, UNICEF, Jami'ar Usmanu Danfodiyo). Idan babu, rubuta *Babu*.\n"
           "_Which ministry, agency or organisation are you with? Type 'None' if none._")
LATER = "Zan amsa wannan tambayar da zarar ka gama rajista. 🙂\n\n"
BAD_NAME = "Don Allah rubuta sunanka (harafi 2 zuwa 60). _Please type your name._"
DONE = ("✅ Mun gama, *{name}*! Yanzu kana iya tambaya ta *rubutu* ko *sakon murya*.\n\n"
        "_Muna adana sunanka, kungiyarka da tambayoyinka domin inganta Kasafi Bot. Ba mu adana lambar wayarka._")
DONE_PENDING = "\n\nGa amsar tambayar da ka fara aikowa: ⬇️"


@dataclass
class Step:
    done: bool                  # registered: carry on and answer
    reply: str = None           # message to send now (a prompt, or the welcome)
    pending: str = None         # question asked before registering, to answer now
    stage: str = None           # 'name' | 'org' while registering


def clean(text, limit):
    t = " ".join((text or "").split()).strip(" .,*_")
    return t[:limit]


class Onboarding:
    def __init__(self, logs):
        self.logs = logs

    def profile(self, uhash):
        u = self.logs.get_user(uhash)
        return u if u and u["stage"] == "done" else None

    def restart(self, uhash, channel):
        self.logs.upsert_user(uhash, channel=channel, stage="name", pending=None)

    def step(self, uhash, channel, text=None, pending=None):
        """Advance registration with the user's message. `pending` is a question (or a voice-note reference)
        to keep if they haven't registered yet."""
        u = self.logs.get_user(uhash)
        if u and u["stage"] == "done":
            return Step(True)
        msg = (text or "").strip()
        if not u:
            is_cmd = msg.lower() in COMMANDS or msg.lower().startswith(("join ", "/"))
            keep = pending or (msg if msg and not is_cmd else None)
            self.logs.upsert_user(uhash, channel=channel, stage="name", pending=keep)
            return Step(False, ASK_NAME, stage="name")
        if pending and not u["pending"]:
            self.logs.upsert_user(uhash, pending=pending)
        if u["stage"] == "name":
            if "?" in msg or len(msg.split()) > 5:     # a question, not a name: keep it for later
                if not u["pending"]:
                    self.logs.upsert_user(uhash, pending=msg)
                return Step(False, LATER + ASK_NAME.split("\n\n", 1)[1], stage="name")
            name = clean(msg, 60)
            if not msg or msg.lower() in COMMANDS or msg.startswith("/") or len(name) < 2 or pending:
                return Step(False, BAD_NAME if msg and not pending else ASK_NAME, stage="name")
            self.logs.upsert_user(uhash, name=name, stage="org")
            return Step(False, ASK_ORG.format(name=name), stage="org")
        # stage == 'org'
        if not msg or msg.startswith("/") or pending:
            return Step(False, ASK_ORG.format(name=u["name"]), stage="org")
        org = clean(msg, 120)
        org = "None" if org.lower() in NONE_WORDS else org
        self.logs.upsert_user(uhash, organization=org, stage="done", pending=None, completed=True)
        keep = u["pending"]
        return Step(True, DONE.format(name=u["name"]) + (DONE_PENDING if keep else ""), pending=keep)
