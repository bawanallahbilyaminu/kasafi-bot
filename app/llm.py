"""N-ATLaS language model wrapper.

Backends
  transformers : loads NCAIR1/N-ATLaS locally (4-bit on an 8 GB GPU such as an RTX 4060)
  openai       : any OpenAI-compatible server serving N-ATLaS (vLLM on Colab, llama.cpp server, ...)
  none         : no model; the engine falls back to template answers (for testing only)

N-ATLaS is used for two jobs:
  understand()  Hausa/English/Pidgin question -> English rendering + topic hints (JSON)
  write()       grounded answer in the user's language from the retrieved facts only
"""
import json
import logging
import re
import threading
import time

from . import config

log = logging.getLogger("natlas.llm")

UNDERSTAND_SYSTEM = (
    "You help citizens of Sokoto State, Nigeria, ask about the state budget. "
    "Read the user's message (it may be Hausa, English or Nigerian Pidgin) and reply with ONLY a JSON object:\n"
    '{"language": "ha|en|pcm", "english": "<faithful English translation of the question>", '
    '"topic": "<ministry, sector, LGA or project the question is about, in English, or empty>", '
    '"wants": "allocation|spending|projects|project_status|ranking|comparison|revenue|overview|greeting|other", '
    '"year": <year or null>}\n'
    "project_status = which projects started, continued, stalled, are new or were dropped between years; "
    "ranking = which ministry/LGA/project got the most or least; comparison = change between years."
)
UNDERSTAND_SHOTS = [
    ("Nawa aka ware wa ma'aikatar lafiya a kasafin 2026?",
     '{"language": "ha", "english": "How much was allocated to the Ministry of Health in the 2026 budget?", '
     '"topic": "health", "wants": "allocation", "year": 2026}'),
    ("Wadanne ayyuka ne za a yi a karamar hukumar Tambuwal?",
     '{"language": "ha", "english": "What projects will be carried out in Tambuwal Local Government?", '
     '"topic": "Tambuwal", "wants": "projects", "year": null}'),
    ("Ayyuka nawa aka fara a 2025 amma ba a kammala ba, har yanzu suna cikin kasafin 2026?",
     '{"language": "ha", "english": "How many projects started in 2025 were not completed and are still in the 2026 budget?", '
     '"topic": "", "wants": "project_status", "year": null}'),
    ("Wace ma'aikata ce ta fi samun kudi a bana?",
     '{"language": "ha", "english": "Which ministry received the most money this year?", '
     '"topic": "", "wants": "ranking", "year": 2026}'),
    ("Shin nawa ne aka kashe a fannin ilimi a bara?",
     '{"language": "ha", "english": "How much was spent on education last year?", '
     '"topic": "education", "wants": "spending", "year": 2025}'),
]

WRITE_SYSTEM_HA = (
    "Kai mataimaki ne mai bayyana kasafin kudin Jihar Sokoto ga 'yan kasa cikin Hausa mai sauki. "
    "Ka amsa tambayar ta amfani da BAYANAN da aka ba ka KADAI. Kada ka kirkiri wani adadi ko suna. "
    "Ka rubuta adadin kudi daidai yadda suke a cikin bayanan (misali ₦12.5 biliyan). "
    "Idan bayanan ba su isa ba, ka fadi haka. Amsa ta kasance gajeriya: jimloli 2 zuwa 5. "
    "Kada ka sanya shafi ko madogara; za a kara su daga baya. "
    "Idan bayanan sun kunshi jerin ayyuka ko hukumomi, KADA ka sake lissafa su daya bayan daya, kuma kada ka "
    "fassara sunayensu: ka takaita a jimla daya (misali, mafi girma da adadin kudinsa). Za a jera su a kasa."
)
WRITE_SYSTEM_EN = (
    "You explain the Sokoto State budget to citizens in plain English. Answer the question using ONLY the FACTS "
    "provided. Never invent a figure or a name. Copy amounts exactly as written in the facts (e.g. ₦12.5 billion). "
    "If the facts are not enough, say so. Keep it short: 2 to 5 sentences. Do not add page numbers or sources; "
    "they are appended later. If the facts include a list of projects or agencies, do NOT re-list them one by one "
    "and do not rename them: summarise in one sentence (e.g. the largest one and its amount). The full list is "
    "appended below your answer."
)


class NATLaS:
    def __init__(self):
        self.backend = config.LLM_BACKEND
        self.model_id = config.NATLAS_MODEL if self.backend == "transformers" else config.OPENAI_MODEL
        self._lock = threading.Lock()
        self._model = self._tok = self._client = None
        if self.backend == "transformers":
            self._load_transformers()
        elif self.backend == "openai":
            from openai import OpenAI
            self._client = OpenAI(base_url=config.OPENAI_BASE_URL, api_key=config.OPENAI_API_KEY)

    @property
    def enabled(self):
        return self.backend in ("transformers", "openai")

    def _load_transformers(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        kw = {"token": config.HF_TOKEN} if config.HF_TOKEN else {}
        t0 = time.time()
        self._tok = AutoTokenizer.from_pretrained(config.NATLAS_MODEL, **kw)
        if config.LLM_4BIT and torch.cuda.is_available():
            from transformers import BitsAndBytesConfig
            q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                   bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True)
            self._model = AutoModelForCausalLM.from_pretrained(config.NATLAS_MODEL, quantization_config=q,
                                                               device_map="auto", **kw)
        else:
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            self._model = AutoModelForCausalLM.from_pretrained(config.NATLAS_MODEL, torch_dtype=dtype,
                                                               device_map="auto", **kw)
        self._model.eval()
        log.info("N-ATLaS loaded (%s) in %.1fs", config.NATLAS_MODEL, time.time() - t0)

    # ------------------------------------------------------------------ core
    def chat(self, messages, max_new_tokens=256, temperature=0.2):
        if self.backend == "openai":
            r = self._client.chat.completions.create(model=config.OPENAI_MODEL, messages=messages,
                                                     max_tokens=max_new_tokens, temperature=temperature)
            return r.choices[0].message.content.strip()
        if self.backend != "transformers":
            raise RuntimeError("LLM backend disabled")
        import torch
        with self._lock:
            if getattr(self._tok, "chat_template", None):
                ids = self._tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
            else:  # plain Llama-3 format
                txt = "<|begin_of_text|>" + "".join(
                    f"<|start_header_id|>{m['role']}<|end_header_id|>\n\n{m['content']}<|eot_id|>" for m in messages
                ) + "<|start_header_id|>assistant<|end_header_id|>\n\n"
                ids = self._tok(txt, return_tensors="pt", add_special_tokens=False).input_ids
            ids = ids.to(self._model.device)
            eos = [self._tok.eos_token_id]
            eot = self._tok.convert_tokens_to_ids("<|eot_id|>")
            if isinstance(eot, int) and eot >= 0:
                eos.append(eot)
            with torch.no_grad():
                out = self._model.generate(ids, attention_mask=torch.ones_like(ids), max_new_tokens=max_new_tokens,
                                           do_sample=temperature > 0, temperature=max(temperature, 0.01), top_p=0.9,
                                           eos_token_id=eos, pad_token_id=self._tok.eos_token_id)
            return self._tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    # ------------------------------------------------------------------ tasks
    def understand(self, text):
        msgs = [{"role": "system", "content": UNDERSTAND_SYSTEM}]
        for q, a in UNDERSTAND_SHOTS:
            msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        msgs.append({"role": "user", "content": text})
        raw = self.chat(msgs, max_new_tokens=120, temperature=0.0)
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {"raw": raw}
        try:
            d = json.loads(m.group(0))
            d["raw"] = raw
            return d
        except json.JSONDecodeError:
            return {"raw": raw}

    def write(self, question, facts, lang):
        system = WRITE_SYSTEM_HA if lang == "ha" else WRITE_SYSTEM_EN
        label = "BAYANAI" if lang == "ha" else "FACTS"
        qlabel = "TAMBAYA" if lang == "ha" else "QUESTION"
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": f"{label}:\n{facts}\n\n{qlabel}: {question}"}]
        return self.chat(msgs, max_new_tokens=220, temperature=0.2)
