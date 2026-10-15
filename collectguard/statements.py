"""What the debtor said that changes what the agent may do next (Spanish and English).

DISPUTE        "no reconozco esa deuda", "ya pagué", "me cobraron mal", "I already paid", "this isn't my debt"
CEASE          "no me contacten más", "dejen de molestarme", "stop contacting me"
OPTOUT:<ch>    "no me manden más mensajes", "stop calling", "STOP" (SMS)
ATTORNEY       "tengo abogado", "hable con mi abogado", "I have a lawyer"
WRONG_PARTY    "número equivocado", "no soy esa persona", "wrong number"
CONSENT_TIME   "llámeme el martes a las 10", "call me tomorrow at 9 pm"  -> the time they asked for

A match does not count when it is negated ("no tengo abogado", "no es que no reconozca la deuda"),
about someone else ("mi hermano tiene abogado"), or in the past and over ("tenía abogado pero ya no").
"""
import re
import unicodedata

PAT = {
    "DISPUTE": [
        r"no reconozco (esa|la|esta|ninguna) deuda", r"(esa|la|esta) deuda no es m[ií]a", r"ya (la |lo )?pagu[eé]",
        r"me cobraron mal", r"me est[aá]n cobrando de m[aá]s", r"el (cobro|valor|saldo) est[aá] mal", r"no debo (eso|nada|ese valor)",
        r"i (already )?paid (this|it|that)", r"(this|that) (debt )?(is not|isn't) mine", r"i don'?t owe", r"i dispute",
        r"charged (me )?(incorrectly|wrong)", r"wrong (amount|balance)",
    ],
    "CEASE": [
        r"no me (vuelvan a )?(contacten|contactar|busquen)( m[aá]s)?", r"dejen de (molestarme|contactarme|buscarme|acosarme)",
        r"no quiero que me (vuelvan a )?contact", r"stop contacting me", r"leave me alone", r"do not contact me",
        r"cease (all )?(communication|contact)",
    ],
    "OPTOUT:sms": [r"no me (manden|env[ií]en|escriban) m[aá]s (mensajes|sms)", r"stop texting", r"^\s*stop\s*$", r"no m[aá]s mensajes"],
    "OPTOUT:whatsapp": [r"no me (manden|env[ií]en|escriban) m[aá]s (por )?whatsapp", r"no m[aá]s whatsapp"],
    "OPTOUT:email": [r"no me (manden|env[ií]en) m[aá]s correos", r"stop emailing", r"unsubscribe"],
    "OPTOUT:call": [r"no me (vuelvan a )?llam(en|ar)( m[aá]s)?", r"dejen de llamarme", r"stop calling( me)?", r"don'?t call me"],
    "ATTORNEY": [r"(tengo|tiene|ya tengo) (un |una )?abogad[oa]", r"(hable|hablen|habla) con mi abogad[oa]", r"mi abogad[oa]",
                 r"i (have|got) (a|an) (lawyer|attorney)", r"my (lawyer|attorney)", r"represented by"],
    "WRONG_PARTY": [r"n[uú]mero equivocado", r"no soy (esa persona|[eé]l|ella|quien ustedes buscan)", r"aqu[ií] no vive",
                    r"wrong number", r"i'?m not (him|her|that person)", r"(he|she) doesn'?t live here"],
}
NEG = re.compile(r"\b(no es que|no|nunca|ya no|i don'?t|i do not|not|never)\s+(\w+\s+){0,2}$")
OTHER = re.compile(r"\b(mi|my) (herman[oa]|espos[oa]|mam[aá]|pap[aá]|vecin[oa]|amig[oa]|brother|sister|wife|husband|mom|dad|neighbou?r|friend)\b[^.,;]{0,25}$")
PAST_OVER = re.compile(r"\b(ten[ií]a|had)\b.*\b(pero ya no|but not anymore|not any more)\b")

DAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
CONSENT = re.compile(r"(ll[aá]m(eme|ame|enme)|call me( back)?)\s+(el |on |)?(?P<day>ma[nñ]ana|pasado ma[nñ]ana|tomorrow|hoy|today|"
                     r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|monday|tuesday|wednesday|thursday|friday|saturday|sunday)?"
                     r"\s*(a las |at )(?P<h>\d{1,2})(:(?P<m>\d\d))?\s*(?P<ap>am|pm|a\.m\.|p\.m\.|de la noche|de la ma[nñ]ana|de la tarde)?")


def _fold(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def detect(turns):
    """turns: [{'who': 'debtor'|'agent', 'text': str, 't': datetime}] -> list of {kind, turn, quote, ...}."""
    found = []
    for i, tr in enumerate(turns):
        if tr["who"] != "debtor":
            continue
        low = tr["text"].lower()
        for kind, pats in PAT.items():
            for p in pats:
                m = re.search(p, low)
                if not m:
                    continue
                pre = low[max(0, m.start() - 30):m.start()]
                if kind != "DISPUTE" and NEG.search(pre):
                    continue                                       # "no tengo abogado", "i don't have a lawyer"
                if kind == "DISPUTE" and re.search(r"(no es que|it'?s not that|not that)\s*$", pre):
                    continue                                       # "no es que no reconozca la deuda"
                if OTHER.search(pre):
                    continue                                       # someone else's lawyer / number
                if PAST_OVER.search(low[max(0, m.start() - 10):]):
                    continue
                found.append({"kind": kind, "turn": i, "quote": tr["text"].strip()})
                break
        m = CONSENT.search(_fold(tr["text"]))
        if m and not NEG.search(_fold(tr["text"])[:m.start()][-25:]):
            found.append({"kind": "CONSENT_TIME", "turn": i, "quote": tr["text"].strip(), "parsed": m.groupdict(), "said_at": tr["t"]})
    return found


def consent_time(item, tz):
    """Resolve 'llámeme el martes a las 10' to a local datetime after the moment it was said."""
    import datetime as dt
    g = item["parsed"]
    said = item["said_at"].astimezone(tz)
    h = int(g["h"])
    ap = (g.get("ap") or "").replace(".", "")
    if ap in ("pm", "de la noche", "de la tarde") and h < 12:
        h += 12
    if ap in ("am", "de la manana") and h == 12:
        h = 0
    if not ap and h < 7:
        h += 12                                       # "a las 3" in a call means afternoon
    day = _fold(g.get("day") or "")
    base = said.date()
    if day in ("manana", "tomorrow"):
        base += dt.timedelta(days=1)
    elif day == "pasado manana":
        base += dt.timedelta(days=2)
    elif day in DAYS:
        base += dt.timedelta(days=(DAYS[day] - said.weekday()) % 7 or 7)
    t = dt.datetime(base.year, base.month, base.day, h, int(g.get("m") or 0), tzinfo=tz)
    if t <= said:
        t += dt.timedelta(days=1)
    return t
