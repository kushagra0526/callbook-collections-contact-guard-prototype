"""Benchmark: the agent's proposed next action, with one planted compliance problem, a look-alike that
must still go out, or nothing wrong. Truth = what the generator planted.

    python evaluate.py dev        # seeds 1-600, dev phrase bank
    python evaluate.py heldout    # seeds 50001-50600, eval/bank_heldout.py (frozen in git first)

Compared:
  trust      send whatever the agent proposes
  naive      a typical first guard: window checked on the server's clock (Bogota), keyword matching on what
             the debtor said (no negation / third person / past), counts every dial toward 7-in-7
  guard      collectguard.decide
"""
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from collectguard.rules import THREAT, decide  # noqa: E402
from collectguard.synth import scenario  # noqa: E402

KW = {"BLOCK": ["no me contacten", "dejen de", "stop", "leave me alone", "equivocado", "wrong number", "no soy", "policia", "police"],
      "ROUTE_HUMAN": ["abogad", "lawyer", "attorney", "pagu", "paid", "no reconozco", "not mine", "incorrect", "no es mia"]}


def naive(s):
    a = s["action"]
    text = " ".join(t["text"].lower() for t in s["turns"] if t["who"] == "debtor")
    for dec in ("BLOCK", "ROUTE_HUMAN"):
        if any(k in text for k in KW[dec]):
            return dec
    if THREAT.search(a.get("text", "")):
        return "BLOCK"
    lt = a["t"].astimezone(ZoneInfo("America/Bogota"))       # the server's clock, not the debtor's
    hm = lt.hour + lt.minute / 60
    if s["acct"]["juris"] == "CO":
        if lt.weekday() == 6 or not ((7 <= hm < 19) if lt.weekday() < 5 else (8 <= hm < 15)):
            return "RESCHEDULE"
    elif not 8 <= hm < 21:
        return "RESCHEDULE"
    calls = [h for h in s["history"] if h["channel"] == "call" and h["t"] > a["t"] - dt.timedelta(days=7)]
    if a["channel"] == "call" and len(calls) >= 7:
        return "RESCHEDULE"
    return "SEND"


def run(split):
    if split == "heldout":
        from eval.bank_heldout import BANK
        seeds = range(50001, 50601)
    else:
        from collectguard.bank_dev import BANK
        seeds = range(1, 601)
    fam = {n: defaultdict(lambda: [0, 0]) for n in ("trust", "naive", "guard")}
    wrong = []
    for seed in seeds:
        s = scenario(seed, BANK)
        r = decide(s["acct"], s["history"], s["turns"], s["action"])
        codes = {x["code"] for x in r["reasons"]}
        got = {"trust": "SEND", "naive": naive(s), "guard": r["decision"]}
        key = s["family"] or "clean"
        group = "lookalike" if s["expect_decision"] == "SEND" and s["family"] else ("clean" if not s["family"] else "planted")
        for n, d in got.items():
            ok = d == s["expect_decision"] and (n != "guard" or not s["expect_codes"] or bool(codes & s["expect_codes"]))
            fam[n][key][0] += ok
            fam[n][key][1] += 1
            fam[n]["_" + group][0] += ok
            fam[n]["_" + group][1] += 1
        if got["guard"] != s["expect_decision"] or (s["expect_codes"] and not codes & s["expect_codes"]):
            wrong.append({"seed": seed, "family": key, "juris": s["acct"]["juris"], "expected": s["expect_decision"], "got": got["guard"],
                          "codes": sorted(codes), "debtor": [t["text"] for t in s["turns"] if t["who"] == "debtor"][-2:],
                          "when": s["action"]["t"].strftime("%a %d %b %H:%M %Z"), "text": s["action"]["text"]})
    return {"split": split, "n": len(seeds), "by_family": {k: {n: fam[n][k] for n in fam} for k in sorted(fam["guard"])}, "wrong": wrong}


def show(r):
    print(f"\n== {r['split']}: {r['n']} proposed actions")
    print(f"{'family':<20}{'trust':>10}{'naive':>10}{'guard':>10}")
    for k, v in r["by_family"].items():
        print(f"{k:<20}" + "".join(f"{f'{v[n][0]}/{v[n][1]}':>10}" for n in ("trust", "naive", "guard")))
    print(f"guard wrong: {len(r['wrong'])}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    res = run(split)
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / f"out/eval_{split}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    show(res)
