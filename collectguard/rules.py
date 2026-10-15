"""Decide what happens to the agent's proposed next action: SEND, RESCHEDULE (with the next lawful
time), BLOCK, or ROUTE_HUMAN. Every reason names the rule. Rules are data per jurisdiction.

Colombia - Ley 2300 de 2023 ("Dejen de fregar"), as summarised publicly (verify article text):
  Mon-Fri 07:00-19:00, Sat 08:00-15:00, never Sundays or holidays; after a direct contact in a week,
  no other channel that week and not more than once a day; no personal references (co-debtor only).
US - Regulation F (12 CFR 1006) / FDCPA:
  08:00-21:00 in the consumer's local time (1006.6(b)(1)); calls presumed to violate above 7 in 7 days
  or within 7 days after a telephone conversation (1006.14(b)(2)), excluding unconnected calls and calls
  inside a consent window (1006.14(b)(3)); attorney (1006.6(b)(2)); cease (FDCPA 805(c)); dispute pauses
  collection until verification (809(b)); opt-out notice in each electronic message (1006.6(e));
  "attempt to collect a debt" disclosure (1006.18(e)); no threats of arrest / unintended suits (807).
"""
import datetime as dt
import re
from zoneinfo import ZoneInfo

from .statements import consent_time, detect

CITE = {
    "CO_TIME": "Ley 2300/2023 horarios (L-V 7-19, S 8-15, no domingos/festivos)",
    "CO_WEEK_CHANNEL": "Ley 2300/2023: tras contacto directo, no varios canales en la misma semana",
    "CO_DAY": "Ley 2300/2023: no más de un contacto en el mismo día",
    "CO_REFERENCE": "Ley 2300/2023: no contactar referencias personales",
    "CO_ID": "Ley 2300/2023: identificar la entidad y el motivo",
    "US_TIME": "Reg F 1006.6(b)(1): 8am-9pm consumer local time",
    "US_7IN7": "Reg F 1006.14(b)(2)(i)(A): >7 calls in 7 days",
    "US_CONVO": "Reg F 1006.14(b)(2)(i)(B): call within 7 days after a conversation",
    "US_THIRD": "Reg F 1006.6(d): third-party communication limits",
    "US_MINI": "Reg F 1006.18(e): 'attempt to collect a debt' disclosure",
    "US_OPTOUT": "Reg F 1006.6(e): opt-out notice in electronic messages",
    "CEASE": "FDCPA 805(c) / Ley 2300: consumer asked to stop contact",
    "OPTOUT": "Consumer opted out of this channel (Reg F 1006.6(e) / Ley 2300 canales autorizados)",
    "ATTORNEY": "Reg F 1006.6(b)(2): consumer represented by an attorney",
    "DISPUTE": "FDCPA 809(b): disputed debt, collection paused until verification",
    "WRONG_PARTY": "Wrong party: stop, disclose nothing (Reg F 1006.6(d))",
    "THREAT": "FDCPA 807(4)/(5), Ley 2300: no threats or simulated judicial action",
}
SEVERITY = {"SEND": 0, "RESCHEDULE": 1, "ROUTE_HUMAN": 2, "BLOCK": 3}
THREAT = re.compile(r"\b(c[aá]rcel|arrest|jail|polic[ií]a|police|orden de captura|warrant|juzgado|orden judicial|"
                    r"embargo inmediato|we will sue you|lo vamos a demandar|vamos a demandarl)", re.I)
MINI = re.compile(r"(attempt to collect a debt|intento de cobrar una deuda)", re.I)
OPTOUT_NOTE = re.compile(r"(reply stop|responde stop|responda stop|unsubscribe|darse de baja|text stop)", re.I)


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return dt.date(y, month, day)


def co_holidays(y):
    """Colombian holidays incl. Ley Emiliani (moved to the following Monday)."""
    def monday(d):
        return d + dt.timedelta(days=(7 - d.weekday()) % 7)
    e = easter(y)
    fixed = [dt.date(y, 1, 1), dt.date(y, 5, 1), dt.date(y, 7, 20), dt.date(y, 8, 7), dt.date(y, 12, 8), dt.date(y, 12, 25)]
    moved = [monday(dt.date(y, m, d)) for m, d in ((1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11))]
    easter_based = [e - dt.timedelta(days=3), e - dt.timedelta(days=2),
                    monday(e + dt.timedelta(days=39)), monday(e + dt.timedelta(days=60)), monday(e + dt.timedelta(days=68))]
    return set(fixed + moved + easter_based)


def lawful_time(acct, t):
    """Is local time t inside the contact window? (t aware)"""
    lt = t.astimezone(ZoneInfo(acct["tz"]))
    if acct["juris"] == "CO":
        if lt.weekday() == 6 or lt.date() in co_holidays(lt.year):
            return False
        hm = lt.hour + lt.minute / 60
        return (7 <= hm < 19) if lt.weekday() < 5 else (8 <= hm < 15)
    hm = lt.hour + lt.minute / 60
    return 8 <= hm < 21


def next_lawful(acct, t, ok=lambda x: True):
    x = t
    for _ in range(4 * 24 * 21):
        x = x + dt.timedelta(minutes=15)
        if lawful_time(acct, x) and ok(x):
            return x
    return None


def _same_week(a, b):
    return a.isocalendar()[:2] == b.isocalendar()[:2]


def decide(acct, history, turns, action):
    """acct: juris, tz, co_debtor_ok; history: [{t, channel, recipient, connected, conversation}];
    turns: conversation; action: {t, channel, recipient: debtor|co_debtor|reference, kind: collect|payment_link|
    debt_review|verification, text}."""
    tz = ZoneInfo(acct["tz"])
    reasons = []

    def add(dec, code, why, evidence=""):
        reasons.append({"decision": dec, "code": code, "why": why, "rule": CITE[code], "evidence": evidence})

    st = detect(turns)
    kinds = {s["kind"]: s for s in st}
    us = acct["juris"] != "CO"
    t = action["t"]
    # who is being contacted
    if action["recipient"] == "reference":
        add("BLOCK", "CO_REFERENCE" if not us else "US_THIRD", "message goes to a personal reference, not the debtor")
    if "WRONG_PARTY" in kinds:
        add("BLOCK", "WRONG_PARTY", "the person said it is the wrong number/person", kinds["WRONG_PARTY"]["quote"])
    if "CEASE" in kinds:
        add("BLOCK", "CEASE", "the debtor asked to stop all contact", kinds["CEASE"]["quote"])
    oo = kinds.get(f"OPTOUT:{action['channel']}")
    if oo:
        add("BLOCK", "OPTOUT", f"the debtor opted out of {action['channel']}", oo["quote"])
    if "ATTORNEY" in kinds:
        add("ROUTE_HUMAN", "ATTORNEY", "the debtor is represented: contact goes to the attorney", kinds["ATTORNEY"]["quote"])
    if "DISPUTE" in kinds and action["kind"] in ("collect", "payment_link"):
        add("ROUTE_HUMAN", "DISPUTE", "debt disputed: send a debt review / verification, not a payment ask", kinds["DISPUTE"]["quote"])
    # message content
    text = action.get("text", "")
    m = THREAT.search(text)
    if m:
        add("BLOCK", "THREAT", f"message threatens '{m.group(0)}'", text)
    if us and action["kind"] in ("collect", "payment_link") and action["channel"] != "call" and not MINI.search(text):
        add("BLOCK", "US_MINI", "missing the 'attempt to collect a debt' disclosure", text)
    if us and action["channel"] in ("sms", "email") and not OPTOUT_NOTE.search(text):
        add("BLOCK", "US_OPTOUT", "electronic message without an opt-out instruction", text)
    if not us and action["channel"] != "call" and acct.get("creditor") and acct["creditor"].lower() not in text.lower():
        add("BLOCK", "CO_ID", f"message doesn't say who is collecting ({acct['creditor']})", text)
    # consent window (the debtor asked to be called at a time): counts for US time and frequency
    consent = None
    if "CONSENT_TIME" in kinds:
        ct = consent_time(kinds["CONSENT_TIME"], tz)
        if abs((t - ct).total_seconds()) <= 30 * 60:
            consent = ct
    # time window
    if not lawful_time(acct, t) and not (us and consent and action["channel"] == "call"):
        nxt = next_lawful(acct, t)
        lt = t.astimezone(tz)
        add("RESCHEDULE", "US_TIME" if us else "CO_TIME", f"{lt:%a %d %b %H:%M} local is outside the window", f"next lawful {nxt.astimezone(tz):%a %H:%M}" if nxt else "")
    # frequency
    past = [h for h in history if h["t"] < t and h["recipient"] == action["recipient"]]
    if us and action["channel"] == "call" and not consent:
        win_start = t - dt.timedelta(days=7)
        counted = [h for h in past if h["channel"] in ("call", "voicemail") and h["connected"] and h["t"] > win_start and not h.get("consent")]
        if len(counted) + 1 > 7:
            oldest = sorted(counted)[len(counted) - 7] if False else sorted(h["t"] for h in counted)[len(counted) - 7]
            add("RESCHEDULE", "US_7IN7", f"would be call #{len(counted) + 1} in 7 days", f"next after {(oldest + dt.timedelta(days=7)).astimezone(tz):%a %d %b %H:%M}")
        convos = [h for h in past if h.get("conversation") and h["channel"] == "call"]
        if convos:
            last = max(h["t"] for h in convos).astimezone(tz).date()
            if t.astimezone(tz).date() < last + dt.timedelta(days=7):
                add("RESCHEDULE", "US_CONVO", f"telephone conversation on {last:%a %d %b}; no calls for 7 days", f"from {last + dt.timedelta(days=7):%a %d %b}")
    if not us:
        lt = t.astimezone(tz)
        direct = [h for h in past if h.get("conversation") and _same_week(h["t"].astimezone(tz), lt)]
        if direct:
            chans = {h["channel"] for h in direct}
            if action["channel"] not in chans:
                add("RESCHEDULE", "CO_WEEK_CHANNEL", f"direct contact this week by {', '.join(sorted(chans))}; not via {action['channel']}", "next week")
        today = [h for h in past if h["t"].astimezone(tz).date() == lt.date() and h["connected"]]
        if today:
            add("RESCHEDULE", "CO_DAY", f"already contacted today ({today[-1]['channel']} at {today[-1]['t'].astimezone(tz):%H:%M})", "tomorrow")
    decision = max((r["decision"] for r in reasons), key=SEVERITY.get, default="SEND")
    return {"decision": decision, "reasons": reasons, "statements": [{k: v for k, v in s.items() if k != "parsed"} for s in st]}
