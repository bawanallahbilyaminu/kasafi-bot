"""Kasafi engine: voice/text question -> grounded budget answer.

    voice note --Hausa-ASR--> text --N-ATLaS(understand)--> English + hints
        --rules + DB--> facts --N-ATLaS(write)--> draft --grounding check--> answer + citation
"""
import logging
import time
from dataclasses import dataclass

from . import config
from .answer import HELP_EN, HELP_HA, citation, facts_block, focus, grounded, items_block, notes_block, template_answer
from .logstore import LogStore, user_hash
from .nlu import Understanding
from .retrieve import BudgetStore

log = logging.getLogger("natlas.engine")


@dataclass
class Reply:
    text: str
    interaction_id: int
    transcript: str = None
    lang: str = "ha"
    input_type: str = "text"


class Engine:
    def __init__(self, load_models=True):
        self.store = BudgetStore(config.BUDGET_DB)
        self.nlu = Understanding(config.BUDGET_DB)
        self.logs = LogStore()
        self.llm = self.asr = self.tts = None
        if load_models and config.TTS_ENABLED:
            try:
                from .tts import HausaTTS
                self.tts = HausaTTS()
            except Exception:  # noqa: BLE001  (voice replies are optional; text keeps working)
                log.exception("Hausa TTS failed to load; voice replies disabled")
        if load_models:
            from .llm import NATLaS
            self.llm = NATLaS()
            if config.ASR_ENABLED:
                from .asr import HausaASR
                self.asr = HausaASR()

    # ------------------------------------------------------------------ public
    @staticmethod
    def _progress(cb, stage, **info):
        """Tell the channel what stage we're in (Telegram shows it live). Never lets a UI error break an answer."""
        if cb:
            try:
                cb(stage, **info)
            except Exception:  # noqa: BLE001
                log.debug("progress callback failed", exc_info=True)

    def handle_voice(self, channel, uid, audio: bytes, suffix=".ogg", progress=None):
        t0 = time.time()
        if not self.asr:
            return self._finish(channel, uid, "voice", None, "Yi hakuri, ba a kunna sauraron murya ba.", t0, {})
        try:
            text, secs = self.asr.transcribe(audio, suffix)
        except Exception as e:  # noqa: BLE001
            log.exception("ASR failed")
            return self._finish(channel, uid, "voice", None, "Yi hakuri, ban ji sakon muryar sosai ba. Don Allah a sake gwadawa.",
                                t0, {"error": f"asr: {e}"})
        ms_asr = int((time.time() - t0) * 1000)
        if not text:
            return self._finish(channel, uid, "voice", "", "Yi hakuri, ban ji komai a sakon muryar ba.", t0,
                                {"audio_seconds": secs, "ms_asr": ms_asr})
        self._progress(progress, "heard", text=text)
        return self.handle_text(channel, uid, text, input_type="voice", extra={"audio_seconds": secs, "ms_asr": ms_asr},
                                t0=t0, progress=progress)

    def handle_text(self, channel, uid, text, input_type="text", extra=None, t0=None, progress=None):
        t0 = t0 or time.time()
        rec = dict(extra or {})
        self._progress(progress, "understand")
        # 1. understand: N-ATLaS translation/hints + rule-based linking against the budget's own names
        t1 = time.time()
        und = {}
        if self.llm and self.llm.enabled:
            try:
                und = self.llm.understand(text)
            except Exception as e:  # noqa: BLE001
                log.exception("understand failed")
                rec["error"] = f"understand: {e}"
        english = und.get("english") or ""
        hint = " ".join(str(und.get(k) or "") for k in ("topic", "wants"))
        p = self.nlu.parse(text, english=f"{english} {hint}")
        if und.get("wants") == "greeting" and not (p.mda_codes or p.lga_codes):
            p.intent = "greeting"
        if und.get("language") == "en" and p.lang == "ha" and len(text.split()) > 3:
            p.lang = "en"
        if und.get("wants") == "spending":
            p.performance = True
        if und.get("wants") == "comparison":
            p.compare = True
        if und.get("wants") == "project_status" and p.intent not in ("project_status", "greeting"):
            p.intent = p.analysis = "project_status"
        if und.get("wants") == "ranking" and p.intent not in ("ranking", "greeting", "project_status"):
            p.intent = p.analysis = "ranking"
            p.rank_order = p.rank_order or "top"
            p.rank_metric = p.rank_metric or ("implementation" if p.performance else "allocation")
            p.rank_unit = p.rank_unit or ("lga" if p.lga_codes == [] and "lga" in english.lower() else "ministry")
        if und.get("year") and not p.years:
            try:
                p.years = [int(und["year"])]
            except (TypeError, ValueError):
                pass
        rec["ms_understand"] = int((time.time() - t1) * 1000)
        lang = p.lang

        if p.intent == "greeting":
            return self._finish(channel, uid, input_type, text, HELP_HA if lang == "ha" else HELP_EN, t0,
                                {**rec, "natlas_understanding": und, "english": english, "lang": lang, "intent": p.intent})

        # 2. retrieve facts
        self._progress(progress, "search")
        t2 = time.time()
        ret = self.store.retrieve(p)
        rec["ms_retrieve"] = int((time.time() - t2) * 1000)
        llm_ret = focus(ret, p.years, p.compare)      # past-year questions: N-ATLaS sees only that year's facts
        facts = facts_block(llm_ret, lang)

        # 3. write: N-ATLaS drafts from facts only; every number must be in the facts
        t3 = time.time()
        answer, source, fail = None, "template", None
        if (ret.facts or ret.items) and self.llm and self.llm.enabled:
            self._progress(progress, "write")
            try:
                draft = self.llm.write(text, facts, lang)
                ok, bad = grounded(draft, llm_ret, lang)
                if ok and draft:
                    answer, source = draft, "natlas"
                    # keep the full figures list under the prose so citizens can check them
                    if ret.items:
                        answer += "\n\n" + items_block(ret, lang)
                    if notes_block(ret, lang):
                        answer += "\n\n" + notes_block(ret, lang)
                else:
                    fail = f"ungrounded number: {bad}"
            except Exception as e:  # noqa: BLE001
                log.exception("write failed")
                fail = f"write error: {e}"
        if answer is None:
            answer = template_answer(ret, lang)
        rec["ms_write"] = int((time.time() - t3) * 1000)
        if ret.facts or ret.items:
            answer = f"{answer.strip()}\n\n{citation(ret, lang)}"
        rec.update({"natlas_understanding": und, "english": english, "lang": lang, "intent": p.intent,
                    "entities": {"mda": p.mda_codes, "lga": p.lga_codes, "measure": p.measure, "years": p.years,
                                 "performance": p.performance, "project_terms": p.project_terms},
                    "facts": facts, "answer_source": source, "grounding_fail": fail})
        return self._finish(channel, uid, input_type, text, answer, t0, rec)

    def feedback(self, interaction_id, value):
        self.logs.feedback(interaction_id, value)

    def wants_voice(self, reply, user_pref=None):
        if not self.tts or reply.lang != "ha" or not reply.text:
            return False
        mode = user_pref or config.VOICE_REPLY
        return mode == "always" or (mode == "voice" and reply.input_type == "voice")

    def speak(self, reply):
        """Hausa voice note (OGG/Opus bytes) for a reply, or None. Logged on the interaction."""
        from .speak import to_speech
        t0 = time.time()
        try:
            audio = self.tts.speak(to_speech(reply.text))
        except Exception:  # noqa: BLE001
            log.exception("TTS failed")
            return None
        self.logs.voice_reply(reply.interaction_id, int((time.time() - t0) * 1000))
        return audio

    # ------------------------------------------------------------------ internals
    def _finish(self, channel, uid, input_type, transcript, answer, t0, rec):
        rec = dict(rec)
        rec.update({"channel": channel, "user_hash": user_hash(channel, uid), "input_type": input_type,
                    "transcript": transcript, "answer": answer, "ms_total": int((time.time() - t0) * 1000),
                    "asr_model": config.ASR_MODEL if input_type == "voice" else None,
                    "llm_model": (self.llm.model_id if self.llm and self.llm.enabled else None)})
        iid = self.logs.add(rec)
        return Reply(answer, iid, transcript if input_type == "voice" else None, lang=rec.get("lang") or "ha",
                     input_type=input_type)
