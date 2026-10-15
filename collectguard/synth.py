"""Synthetic collection accounts, contact history, conversation and the agent's proposed next action,
clean or with one planted problem (or a look-alike that must still go out). Truth = what was planted.
Phrasing comes from a bank so the held-out bank can say things differently."""
import datetime as dt
import random
from zoneinfo import ZoneInfo

from .rules import co_holidays

FAMILIES = {   # family -> (expected decision, codes that must appear (any))
    "time": ("RESCHEDULE", {"US_TIME", "CO_TIME"}),
    "tz_trap": ("RESCHEDULE", {"US_TIME"}),
    "us_7in7": ("RESCHEDULE", {"US_7IN7"}),
    "us_convo": ("RESCHEDULE", {"US_CONVO"}),
    "co_week": ("RESCHEDULE", {"CO_WEEK_CHANNEL"}),
    "co_day": ("RESCHEDULE", {"CO_DAY"}),
    "cease": ("BLOCK", {"CEASE"}),
    "optout": ("BLOCK", {"OPTOUT"}),
    "attorney": ("ROUTE_HUMAN", {"ATTORNEY"}),
    "dispute": ("ROUTE_HUMAN", {"DISPUTE"}),
    "wrong_party": ("BLOCK", {"WRONG_PARTY"}),
    "reference": ("BLOCK", {"CO_REFERENCE", "US_THIRD"}),
    "threat": ("BLOCK", {"THREAT"}),
    "us_mini": ("BLOCK", {"US_MINI"}),
    "us_optout_note": ("BLOCK", {"US_OPTOUT"}),
    "co_id": ("BLOCK", {"CO_ID"}),
}
LOOKALIKES = ["neg_attorney", "other_attorney", "past_attorney", "neg_dispute", "dispute_review", "consent_late_call",
              "unconnected_calls", "co_saturday", "co_debtor", "neutral_stop_word"]


def _local(rng, acct, base_date, lawful=True):
    tz = ZoneInfo(acct["tz"])
    d = base_date
    while True:
        if acct["juris"] == "CO":
            if d.weekday() == 6 or d in co_holidays(d.year):
                d += dt.timedelta(days=1)
                continue
            lo, hi = (7, 18) if d.weekday() < 5 else (8, 14)
        else:
            lo, hi = 8, 20
        h = rng.randint(lo + 1, hi - 1)
        return dt.datetime(d.year, d.month, d.day, h, rng.choice([0, 15, 30, 45]), tzinfo=tz)


def scenario(seed, B):
    rng = random.Random(seed)
    if rng.random() < 0.55:
        acct = {"juris": "CO", "tz": "America/Bogota"}
    else:
        st, tz = rng.choice(B["us_states"])
        acct = {"juris": "US-" + st, "tz": tz}
    us = acct["juris"] != "CO"
    acct["creditor"] = rng.choice(B["creditors"])
    lang = "es" if (not us or rng.random() < B["us_spanish"]) else "en"
    base = dt.date(2026, rng.randint(9, 12), rng.randint(1, 28))
    now = _local(rng, acct, base)
    u = rng.random()
    fam = rng.choice(sorted(FAMILIES)) if u < 0.55 else (rng.choice(LOOKALIKES) if u < 0.8 else None)
    for _ in range(5):                       # re-fit until the family suits this account
        fam = _fit(fam, acct, rng)
    tz = ZoneInfo(acct["tz"])
    hist = []
    # clean history: a few attempts more than a week ago, plus a couple of unconnected ones this week
    for _ in range(rng.randint(0, 4)):
        tt = _local(rng, acct, (now - dt.timedelta(days=rng.randint(8, 20))).date())
        hist.append({"t": tt, "channel": rng.choice(["call", "sms", "whatsapp"]), "recipient": "debtor",
                     "connected": rng.random() < 0.6, "conversation": False})
    convo_t = now - dt.timedelta(days=rng.randint(8, 14))
    turns = [{"who": "agent", "text": rng.choice(B["agent_open"][lang]).format(c=acct["creditor"]), "t": convo_t}]
    for _ in range(rng.randint(1, 3)):
        turns.append({"who": "debtor", "text": rng.choice(B["neutral"][lang]), "t": convo_t})
    channel = rng.choice(["call", "sms", "whatsapp", "email"] if not us else ["call", "sms", "email"])
    kind = rng.choice(["collect", "payment_link", "collect"])
    action = {"t": now, "channel": channel, "recipient": "debtor", "kind": kind, "text": ""}

    def say(key):
        turns.append({"who": "debtor", "text": rng.choice(B[key][lang]), "t": convo_t})

    if fam == "time":
        lt = now.astimezone(tz)
        if us:
            h = rng.choice([6, 7, 21, 22])
            action["t"] = lt.replace(hour=h, minute=rng.choice([0, 30]))
        else:
            opt = rng.choice(["sunday", "holiday", "late", "sat_late"])
            d = lt.date()
            if opt == "sunday":
                d += dt.timedelta(days=(6 - d.weekday()) % 7)
                action["t"] = dt.datetime(d.year, d.month, d.day, 10, 0, tzinfo=tz)
            elif opt == "holiday":
                hol = sorted(x for x in co_holidays(d.year) if x.weekday() < 6)
                h_ = rng.choice(hol)
                action["t"] = dt.datetime(h_.year, h_.month, h_.day, 10, 0, tzinfo=tz)
            elif opt == "late":
                d += dt.timedelta(days=(0 - d.weekday()) % 7 + rng.randint(0, 4))
                if d in co_holidays(d.year):
                    d += dt.timedelta(days=1)
                action["t"] = dt.datetime(d.year, d.month, d.day, rng.choice([19, 20, 6]), 30, tzinfo=tz)
            else:
                d += dt.timedelta(days=(5 - d.weekday()) % 7)
                action["t"] = dt.datetime(d.year, d.month, d.day, 16, 0, tzinfo=tz)
    elif fam == "tz_trap":
        bog = ZoneInfo("America/Bogota")
        d = now.date()
        action["t"] = dt.datetime(d.year, d.month, d.day, 8, 0, tzinfo=bog).astimezone(tz)   # 08:00 on the Bogota server clock
    elif fam == "us_7in7":
        action["channel"] = "call"
        for k in range(7):
            hist.append({"t": now - dt.timedelta(hours=10 + k * 20), "channel": "call", "recipient": "debtor", "connected": True, "conversation": False})
    elif fam == "us_convo":
        action["channel"] = "call"
        hist.append({"t": now - dt.timedelta(days=rng.randint(1, 5), hours=1), "channel": "call", "recipient": "debtor", "connected": True, "conversation": True})
    elif fam == "co_week":
        lt = now.astimezone(tz)
        if lt.weekday() < 2:
            lt = lt + dt.timedelta(days=2 - lt.weekday())
            while lt.date() in co_holidays(lt.year):
                lt += dt.timedelta(days=1)
            action["t"] = now = lt
        first = lt - dt.timedelta(days=lt.weekday() - rng.randint(0, lt.weekday() - 1))
        ch = rng.choice([c for c in ["call", "sms", "whatsapp", "email"] if c != action["channel"]])
        hist.append({"t": first.replace(hour=10), "channel": ch, "recipient": "debtor", "connected": True, "conversation": True})
    elif fam == "co_day":
        hist.append({"t": now - dt.timedelta(hours=2), "channel": action["channel"], "recipient": "debtor", "connected": True, "conversation": False})
    elif fam in ("cease", "attorney", "wrong_party"):
        say(fam)
    elif fam == "optout":
        key = {"sms": "optout_sms", "whatsapp": "optout_whatsapp", "email": "optout_email", "call": "optout_call"}[action["channel"]]
        say(key)
    elif fam == "dispute":
        action["kind"] = "collect"
        say("dispute")
    elif fam == "reference":
        action["recipient"] = "reference"
    elif fam == "neg_attorney":
        say("neg_attorney")
    elif fam == "other_attorney":
        say("other_attorney")
    elif fam == "past_attorney":
        say("past_attorney")
    elif fam == "neg_dispute":
        say("neg_dispute")
    elif fam == "dispute_review":
        say("dispute")
        action["kind"] = "debt_review"
    elif fam == "consent_late_call":
        action["channel"] = "call"
        lt = now.astimezone(tz)
        when = lt.replace(hour=21, minute=30)
        turns.append({"who": "debtor", "text": rng.choice(B["consent_930pm"][lang]), "t": when - dt.timedelta(days=1, hours=3)})
        action["t"] = when
    elif fam == "unconnected_calls":
        action["channel"] = "call"
        for k in range(9):
            hist.append({"t": now - dt.timedelta(hours=6 + k * 15), "channel": "call", "recipient": "debtor", "connected": False, "conversation": False})
        for k in range(3):
            hist.append({"t": now - dt.timedelta(hours=8 + k * 30), "channel": "call", "recipient": "debtor", "connected": True, "conversation": False})
    elif fam == "co_saturday":
        d = now.date() + dt.timedelta(days=(5 - now.date().weekday()) % 7)
        while d in co_holidays(d.year):
            d += dt.timedelta(days=7)
        action["t"] = dt.datetime(d.year, d.month, d.day, 14, 0, tzinfo=tz)
    elif fam == "co_debtor":
        action["recipient"] = "co_debtor"
    elif fam == "neutral_stop_word":
        say("stop_lookalike")
    if fam in ("us_mini", "us_optout_note", "co_id") and action["channel"] == "call":
        action["channel"] = "sms"
    if fam == "us_mini":
        action["kind"] = "collect"
    # message text
    if action["channel"] != "call":
        parts = [rng.choice(B["msg_body"][lang]).format(c=acct["creditor"])]
        if us and fam != "us_mini" and action["kind"] in ("collect", "payment_link"):
            parts.append(rng.choice(B["mini"][lang]))
        if us and action["channel"] in ("sms", "email") and fam != "us_optout_note":
            parts.append(rng.choice(B["optout_note"][lang]))
        if fam == "threat":
            parts.append(rng.choice(B["threat"][lang]))
        text = " ".join(parts)
        if fam == "co_id":
            text = text.replace(acct["creditor"], "nosotros")
        action["text"] = text
    elif fam == "threat":
        action["channel"] = rng.choice(["sms", "email"] if us else ["sms", "whatsapp"])
        parts = [rng.choice(B["msg_body"][lang]).format(c=acct["creditor"]), rng.choice(B["threat"][lang])]
        if us:
            parts += [rng.choice(B["mini"][lang]), rng.choice(B["optout_note"][lang])]
        action["text"] = " ".join(parts)
    exp = FAMILIES.get(fam, ("SEND", set()))
    return {"seed": seed, "family": fam, "acct": acct, "history": sorted(hist, key=lambda h: h["t"]), "turns": turns,
            "action": action, "expect_decision": exp[0], "expect_codes": exp[1], "lang": lang}


def _fit(fam, acct, rng):
    us = acct["juris"] != "CO"
    if fam in ("tz_trap", "us_7in7", "us_convo", "us_mini", "us_optout_note", "consent_late_call", "unconnected_calls") and not us:
        return rng.choice(["co_week", "co_day", "co_id", "co_saturday", "co_debtor", "time"])
    if fam in ("co_week", "co_day", "co_id", "co_saturday", "co_debtor") and us:
        return rng.choice(["tz_trap", "us_7in7", "us_convo", "us_mini", "unconnected_calls", "time"])
    if fam == "tz_trap" and acct["tz"] not in ("America/Los_Angeles", "America/Phoenix", "America/Denver", "Pacific/Honolulu", "America/Anchorage"):
        return "us_7in7"
    return fam
