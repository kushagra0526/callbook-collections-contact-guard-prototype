"""One morning of an AI collection agent's queue, checked before anything goes out -> out/report.html

    python demo.py
"""
import html
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from collectguard.bank_dev import BANK  # noqa: E402
from collectguard.rules import decide  # noqa: E402
from collectguard.synth import scenario  # noqa: E402

WANT = ["tz_trap", "co_week", "dispute", "other_attorney", "consent_late_call", "threat", "unconnected_calls", "optout", "co_saturday", "us_convo"]
e = html.escape
COL = {"SEND": "#2f8f57", "RESCHEDULE": "#c98a12", "ROUTE_HUMAN": "#3b6fd1", "BLOCK": "#c0392b"}


def build():
    picked, seen = [], set()
    for seed in range(1, 600):
        s = scenario(seed, BANK)
        if s["family"] in WANT and s["family"] not in seen:
            seen.add(s["family"])
            s["result"] = decide(s["acct"], s["history"], s["turns"], s["action"])
            picked.append(s)
    picked.sort(key=lambda s: WANT.index(s["family"]))
    return picked


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = build()
    for s in rows:
        a, r = s["action"], s["result"]
        lt = a["t"].astimezone(ZoneInfo(s["acct"]["tz"]))
        why = "; ".join(f"{x['code']}: {x['why']}" for x in r["reasons"]) or "all checks pass"
        print(f"{s['family']:<18} {s['acct']['juris']:<6} {a['channel']:<8} {lt:%a %H:%M} -> {r['decision']:<11} {why}")
    ev = {}
    for k, f in (("dev", "out/eval_dev.json"), ("heldout_first_run", "out/heldout_first_run.json")):
        if (HERE / f).exists():
            ev[k] = json.loads((HERE / f).read_text(encoding="utf-8"))
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/report.html").write_text(render(rows, ev), encoding="utf-8")
    print("wrote out/report.html")


def render(rows, ev):
    trs = ""
    for s in rows:
        a, r = s["action"], s["result"]
        tz = ZoneInfo(s["acct"]["tz"])
        lt = a["t"].astimezone(tz)
        server = a["t"].astimezone(ZoneInfo("America/Bogota"))
        said = next((x["quote"] for x in r["statements"]), None) or next((t["text"] for t in reversed(s["turns"]) if t["who"] == "debtor"), "")
        hist = f"{sum(1 for h in s['history'] if h['channel'] == 'call' and h['connected'])} connected / {sum(1 for h in s['history'] if h['channel'] == 'call' and not h['connected'])} unconnected calls"
        why = "<br>".join(f"<b>{e(x['code'])}</b> {e(x['why'])} <span class='mut'>· {e(x['rule'])}{(' · ' + e(x['evidence'])) if x['evidence'] and x['code'] in ('US_TIME', 'CO_TIME', 'US_7IN7', 'US_CONVO') else ''}</span>"
                          for x in r["reasons"]) or "<span class='mut'>all checks pass</span>"
        trs += (f"<tr><td>{e(s['acct']['juris'])}<div class='mut'>{e(s['acct']['tz'])}</div></td><td>“{e(said)}”<div class='mut'>{e(hist)}</div></td>"
                f"<td>{e(a['kind'])} · {e(a['channel'])} → {e(a['recipient'])}<div class='mut'>{lt:%a %d %b %H:%M} local · server {server:%H:%M} Bogotá</div>"
                f"{('<div class=msg>' + e(a['text']) + '</div>') if a['text'] else ''}</td>"
                f"<td><span class='pill' style='background:{COL[r['decision']]}'>{r['decision']}</span></td><td>{why}</td></tr>")
    bench = ""
    for k, lab in (("dev", "dev (600)"), ("heldout_first_run", "held-out, first run (600)")):
        if k in ev:
            f = ev[k]["by_family"]
            bench += (f"<tr><td>{lab}</td>" + "".join(f"<td>{f[g]['trust'][0]}/{f[g]['trust'][1]}</td><td>{f[g]['naive'][0]}/{f[g]['naive'][1]}</td><td><b>{f[g]['guard'][0]}/{f[g]['guard'][1]}</b></td>"
                                                      for g in ("_planted", "_lookalike", "_clean")) + "</tr>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Collections contact guard</title><style>
:root{{--bg:#f5f6f8;--fg:#15181d;--mut:#5f6674;--card:#fff;--line:#e1e4ea}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14.5px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:26px 16px 60px}}h1{{font-size:25px;margin:0 0 4px}}h2{{font-size:17px;margin:24px 0 8px}}.sub,.mut{{color:var(--mut)}}.mut{{font-size:12.5px}}
table{{width:100%;border-collapse:collapse;background:var(--card);font-size:13.5px}}td,th{{border:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}}
.pill{{color:#fff;border-radius:6px;padding:2px 8px;font-weight:700;font-size:12px;white-space:nowrap}}.msg{{margin-top:4px;font-size:12.5px;background:#f1f3f6;border-radius:6px;padding:4px 6px}}
</style></head><body><main>
<h1>Every AI collection action, checked before it goes out</h1>
<div class="sub">Colombia (Ley 2300 de 2023) and US (Regulation F / FDCPA) rules as data. Synthetic accounts and conversations. Unofficial prototype by Kushagra Pratap Singh, not affiliated with Callbook AI. Not legal advice.</div>
<h2>The agent's queue</h2><div style="overflow-x:auto"><table><tr><th>account</th><th>debtor said · history</th><th>proposed action</th><th>decision</th><th>why (rule)</th></tr>{trs}</table></div>
<h2>Benchmark (decision right; the guard must also name the rule)</h2><div style="overflow-x:auto"><table>
<tr><th rowspan="2">set</th><th colspan="3">planted problems</th><th colspan="3">look-alikes that must go out</th><th colspan="3">clean actions</th></tr>
<tr><th>trust</th><th>naive</th><th>guard</th><th>trust</th><th>naive</th><th>guard</th><th>trust</th><th>naive</th><th>guard</th></tr>{bench}</table></div>
</main></body></html>"""


if __name__ == "__main__":
    main()
