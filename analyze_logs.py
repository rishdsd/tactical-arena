"""Summarize a simulation log into a short report.

Usage:
    python analyze_logs.py                 # newest file in logs/
    python analyze_logs.py logs/sim_X.jsonl

Paste the output (not the raw log) when you want help interpreting a run.
"""
import glob
import json
import os
import statistics
import sys
from collections import Counter, defaultdict


def load(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


def per(a, n):
    return f"{a / n:.1f}" if n else "n/a"


def med(values):
    return f"{statistics.median(values):.0f}" if values else "n/a"


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        files = sorted(glob.glob("logs/*.jsonl"), key=os.path.getmtime)
        if not files:
            sys.exit("No log files found in logs/")
        path = files[-1]

    ev = load(path)
    start = next((e for e in ev if e["k"] == "run_start"), {})
    rounds = [e for e in ev if e["k"] == "round_end"]
    matches = [e for e in ev if e["k"] == "match_end"]
    zones = [e for e in ev if e["k"] == "fire_zone"]
    casts = [e for e in ev if e["k"] == "cast"]
    planners = [e for e in ev if e["k"] == "planner"]
    deaths = [e for e in ev if e["k"] == "death"]

    print(f"LOG: {os.path.basename(path)}")
    print(f"Setup: blue Lv{start.get('blue_exp')} vs red Lv{start.get('red_exp')} | "
          f"LLM={'on (' + str(start.get('model')) + ')' if start.get('llm') else 'off'} | "
          f"timeout={start.get('round_timeout')}s | fast={start.get('fast_forward')}")
    if not rounds:
        print("No finished rounds yet.")
        return

    n = len(rounds)
    wins = Counter(r["winner"] for r in rounds)
    reasons = Counter(r["reason"] for r in rounds)
    durs = [r["dur"] for r in rounds]
    gaps = [r["max_damage_gap"] for r in rounds]
    firsts = [r["first_damage_t"] for r in rounds if r["first_damage_t"] is not None]

    print("\n== RESULTS ==")
    mw = Counter(m["winner"] for m in matches)
    print(f"Matches finished: {len(matches)} (blue {mw['blue']}, red {mw['red']})")
    print(f"Rounds: {n} | blue {wins['blue']} ({pct(wins['blue'], n)}), "
          f"red {wins['red']} ({pct(wins['red'], n)}), draws {wins['draw']} ({pct(wins['draw'], n)})")
    print(f"End reasons: {dict(reasons)}")
    print(f"Round length s: median {med(durs)}, max {max(durs):.0f} | "
          f"first damage at s: median {med(firsts)}")
    print(f"Longest no-damage stretch per round (stalemate gauge) s: median {med(gaps)}, max {max(gaps):.0f}")

    # ---- aggregate character stats by team ----
    team = defaultdict(Counter)
    team_chars = Counter()
    for r in rounds:
        for c in r["chars"]:
            team_chars[c["team"]] += 1
            team[c["team"]]["kills"] += c["kills"]
            for k, v in c["stats"].items():
                team[c["team"]][k] += v

    print("\n== COMBAT (per bot per round) ==")
    for t in ("blue", "red"):
        s, k = team[t], team_chars[t]
        if not k:
            continue
        print(f"{t}: shots {per(s['shots'], k)}, accuracy {pct(s['hits'], s['shots'])} "
              f"(wall {pct(s['bullets_hit_wall'], s['shots'])}, water {pct(s['bullets_blocked'], s['shots'])}) | "
              f"dmg dealt {per(s['dmg_dealt'], k)} (fire {per(s['dmg_fire_dealt'], k)}) | kills {per(s['kills'], k)}")

    print("\n== TIME SPENT IN EACH MODE ==")
    for t in ("blue", "red"):
        s = team[t]
        total = sum(v for key, v in s.items() if key.startswith("t_")) or 1
        shares = {key[2:]: pct(v, total) for key, v in s.items() if key.startswith("t_")}
        print(f"{t}: {shares}")

    print("\n== FIRE BURST ==")
    fire_casts = [c for c in casts if c["ability"] == "fire"]
    hit_zones = [z for z in zones if z["victims"]]
    print(f"Casts {len(fire_casts)} ({per(len(fire_casts), n)}/round) -> zones that hurt anyone: "
          f"{len(hit_zones)}/{len(zones)} ({pct(len(hit_zones), len(zones))})")
    exposures = [(v[0], v[1], v[2], v[3]) for z in zones for v in z["victims"].values()]  # team,ticks,hiding,wall
    if exposures:
        ticks = sum(e[1] for e in exposures)
        long_stays = sum(1 for e in exposures if e[1] >= 4)
        print(f"Victim exposures: {len(exposures)} | avg ticks {ticks / len(exposures):.1f} (max 6 = stood in it all 3s) | "
              f"stayed >=2s: {pct(long_stays, len(exposures))}")
        print(f"Of all burn ticks: taken while hiding in cover {pct(sum(e[2] for e in exposures), ticks)}, "
              f"through a wall {pct(sum(e[3] for e in exposures), ticks)}")
        for t in ("blue", "red"):
            mine = [e for e in exposures if e[0] == t]
            if mine:
                print(f"  {t} burned: {len(mine)} exposures, {sum(e[1] for e in mine)} ticks "
                      f"= {sum(e[1] for e in mine) * 5} dmg")
    total_dmg = sum(team[t]["dmg_dealt"] for t in team) or 1
    print(f"Fire share of all damage: {pct(sum(team[t]['dmg_fire_dealt'] for t in team), total_dmg)}")

    print("\n== WATER WALL ==")
    water = [c for c in casts if c["ability"] == "water"]
    print(f"Casts {len(water)} ({per(len(water), n)}/round) | bullets blocked by water: "
          f"{sum(team[t]['bullets_blocked'] for t in team)}")

    print("\n== TACTICS (per bot per round) ==")
    for t in ("blue", "red"):
        s, k = team[t], team_chars[t]
        if not k:
            continue
        print(f"{t}: cover cycles {per(s['cover_cycles'], k)}, peeks {per(s['peeks'], k)} "
              f"(exposed {per(s['peek_exposed'], k)}, timed out {per(s['peek_timeouts'], k)}), "
              f"cover re-picks {per(s['cover_repicks'], k)}, no-cover {per(s['cover_not_found'], k)}, "
              f"flanks {per(s['flanks'], k)} (finished {per(s['flanks_done'], k)})")

    print("\n== LLM PLANNER ==")
    ai_req = sum(team[t]["ai_requests"] for t in team)
    ai_fail = sum(team[t]["ai_failed"] for t in team)
    n_dec = sum(team[t]["planner_n"] for t in team)
    if ai_req:
        agree = sum(team[t]["planner_agree"] for t in team)
        lat = sum(team[t]["planner_latency"] for t in team)
        acts = Counter()
        for t in team:
            for key, v in team[t].items():
                if key.startswith("planner_") and key[8:] in ("attack", "cover_peek", "flank"):
                    acts[key[8:]] += v
        print(f"Requests {ai_req}, failed {ai_fail} | decisions used {n_dec} | avg latency {lat / max(n_dec, 1):.2f}s")
        print(f"Agrees with rules' suggestion: {pct(agree, n_dec)} | choices: {dict(acts)}")
        if planners:
            diff = [p for p in planners if p["rule"] != p["choice"]]
            print(f"Disagreements: {len(diff)} (sample reasons: "
                  f"{[p['reason'] for p in diff[:3]]})")
    else:
        print("No planner activity (LLM off or no eligible bots).")

    print("\n== DEATHS ==")
    cause = Counter(d["cause"] for d in deaths)
    mode = Counter(d.get("mode") for d in deaths)
    print(f"By cause: {dict(cause)} | victim's mode at death: {dict(mode)}")


if __name__ == "__main__":
    main()
