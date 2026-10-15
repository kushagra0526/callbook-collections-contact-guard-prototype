import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectguard.bank_dev import BANK  # noqa: E402
from collectguard.rules import co_holidays, decide, lawful_time  # noqa: E402
from collectguard.statements import detect  # noqa: E402
from collectguard.synth import scenario  # noqa: E402

BOG, LA = ZoneInfo("America/Bogota"), ZoneInfo("America/Los_Angeles")
T = dt.datetime(2026, 10, 14, 10, 0, tzinfo=BOG)


def turns(*lines):
    return [{"who": "debtor", "text": x, "t": T - dt.timedelta(days=1)} for x in lines]


def test_colombian_holidays_2026_follow_ley_emiliani():
    h = co_holidays(2026)
    assert dt.date(2026, 1, 12) in h and dt.date(2026, 4, 3) in h and dt.date(2026, 5, 18) in h and dt.date(2026, 11, 16) in h
    assert dt.date(2026, 1, 6) not in h                                      # moved to Monday 12 Jan


def test_statements_respect_negation_third_person_and_past():
    kinds = lambda *x: {s["kind"] for s in detect(turns(*x))}
    assert "ATTORNEY" in kinds("Hable con mi abogado.")
    assert "ATTORNEY" not in kinds("No tengo abogado.", "Mi hermano tiene abogado.", "Tenía abogado pero ya no.")
    assert "DISPUTE" in kinds("Ya pagué eso.") and "DISPUTE" not in kinds("No es que no reconozca la deuda, es que no tengo plata.")
    assert "OPTOUT:sms" in kinds("STOP") and "OPTOUT:sms" not in kinds("I stopped by the bank")


def test_time_window_is_the_debtors_clock_not_the_servers():
    us = {"juris": "US-CA", "tz": "America/Los_Angeles"}
    assert not lawful_time(us, dt.datetime(2026, 10, 14, 9, 0, tzinfo=BOG))     # 07:00 in Los Angeles
    co = {"juris": "CO", "tz": "America/Bogota"}
    assert lawful_time(co, dt.datetime(2026, 10, 17, 14, 0, tzinfo=BOG))        # Saturday 14:00 ok
    assert not lawful_time(co, dt.datetime(2026, 10, 18, 10, 0, tzinfo=BOG))    # Sunday
    assert not lawful_time(co, dt.datetime(2026, 10, 12, 10, 0, tzinfo=BOG))    # Día de la Raza


def test_reg_f_counts_only_connected_calls_and_waits_after_a_conversation():
    acct = {"juris": "US-NY", "tz": "America/New_York"}
    t = dt.datetime(2026, 10, 14, 11, 0, tzinfo=ZoneInfo("America/New_York"))
    act = {"t": t, "channel": "call", "recipient": "debtor", "kind": "collect", "text": ""}
    unconnected = [{"t": t - dt.timedelta(hours=5 * k + 1), "channel": "call", "recipient": "debtor", "connected": False, "conversation": False} for k in range(10)]
    assert decide(acct, unconnected, [], act)["decision"] == "SEND"
    seven = [{"t": t - dt.timedelta(hours=20 * k + 1), "channel": "call", "recipient": "debtor", "connected": True, "conversation": False} for k in range(7)]
    assert {r["code"] for r in decide(acct, seven, [], act)["reasons"]} == {"US_7IN7"}
    convo = [{"t": t - dt.timedelta(days=3), "channel": "call", "recipient": "debtor", "connected": True, "conversation": True}]
    assert {r["code"] for r in decide(acct, convo, [], act)["reasons"]} == {"US_CONVO"}


def test_colombia_one_channel_per_week_after_direct_contact():
    acct = {"juris": "CO", "tz": "America/Bogota", "creditor": "Banco Andino"}
    t = dt.datetime(2026, 10, 15, 10, 0, tzinfo=BOG)                             # Thursday
    hist = [{"t": t - dt.timedelta(days=2), "channel": "call", "recipient": "debtor", "connected": True, "conversation": True}]
    act = {"t": t, "channel": "whatsapp", "recipient": "debtor", "kind": "collect", "text": "Banco Andino: acuerdo de pago."}
    assert decide(acct, hist, [], act)["decision"] == "RESCHEDULE"
    act["channel"] = "call"
    assert decide(acct, hist, [], act)["decision"] == "SEND"


def test_consent_lets_a_late_call_through_in_the_us_only():
    acct = {"juris": "US-FL", "tz": "America/New_York"}
    ny = ZoneInfo("America/New_York")
    t = dt.datetime(2026, 10, 15, 21, 30, tzinfo=ny)
    tr = [{"who": "debtor", "text": "Call me tomorrow at 9:30 pm, I work late.", "t": dt.datetime(2026, 10, 14, 18, 0, tzinfo=ny)}]
    act = {"t": t, "channel": "call", "recipient": "debtor", "kind": "collect", "text": ""}
    assert decide(acct, [], tr, act)["decision"] == "SEND"
    assert decide(acct, [], [], act)["decision"] == "RESCHEDULE"


def test_generated_cases_match_truth():
    for seed in range(1, 250):
        s = scenario(seed, BANK)
        r = decide(s["acct"], s["history"], s["turns"], s["action"])
        assert r["decision"] == s["expect_decision"], (seed, s["family"], r["reasons"])
