#!/usr/bin/env python3
"""Run the experience-level experiment: many AI-vs-AI matches per matchup.

    python run_experiments.py                # full run (see CONDITIONS below)
    python run_experiments.py --quick        # 3 matches per condition, to test it
    python run_experiments.py --jobs 4       # conditions in parallel (default 3)
    python run_experiments.py --out logs/experiment_X   # resume an interrupted run

Each condition runs main.py in its own process (rules-only bots, fast-forward,
no window) and writes one log file. At the end you get, in the output folder:

    NN_<name>.jsonl      raw log of every round/match for that condition
    report_NN_<name>.txt the detailed analyze_logs.py report for that condition
    comparison.md / .csv one table comparing all conditions  <- start here
    experiment.json      exactly what was run

A "game" here means one MATCH (first team to 3 rounds).
Blue is always the stronger team; blue spawns on the left, red on the right.
"""
import argparse
import csv
import json
import math
import os
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------- EDIT ME -----------------------------
GAMES_PER_CONDITION = 100   # matches per condition

# name, blue experience, red experience, random seed.
# Both bots on a team get the same level. Seeds differ so the repeated
# 100-vs-80 run measures pure run-to-run noise (same matchup, new dice).
CONDITIONS = [
    {"name": "100_vs_20",        "blue": 100, "red": 20,  "seed": 101},
    {"name": "100_vs_40",        "blue": 100, "red": 40,  "seed": 102},
    {"name": "100_vs_50",        "blue": 100, "red": 50,  "seed": 103},
    {"name": "100_vs_80_run1",   "blue": 100, "red": 80,  "seed": 104},
    {"name": "100_vs_80_run2",   "blue": 100, "red": 80,  "seed": 105},
    # Control: identical teams. Any blue/red gap here is spawn-side bias,
    # not skill. Delete this line if you don't want it.
    {"name": "100_vs_100_control", "blue": 100, "red": 100, "seed": 106},
]

STEPS_PER_FRAME = 40        # game steps per loop iteration (speed knob)
# --------------------------------------------------------------------

print_lock = threading.Lock()
children = []


def say(msg):
    with print_lock:
        print(msg, flush=True)


# ------------------------------ running ------------------------------
def is_complete(path):
    """A finished log ends with a run_end event."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", "ignore").strip().splitlines()
        return bool(tail) and json.loads(tail[-1]).get("k") == "run_end"
    except (OSError, ValueError):
        return False


def run_condition(idx, cond, games, outdir):
    name = f"{idx:02d}_{cond['name']}"
    log_path = os.path.join(outdir, name + ".jsonl")

    if is_complete(log_path):
        say(f"[{name}] already finished, skipping")
        return name, log_path, "skipped"

    env = dict(
        os.environ,
        ARENA_SIM="1",
        ARENA_LLM="0",
        ARENA_BLUE_EXP=f"{cond['blue']},{cond['blue']}",
        ARENA_RED_EXP=f"{cond['red']},{cond['red']}",
        ARENA_MAX_MATCHES=str(games),
        ARENA_SEED=str(cond["seed"]),
        ARENA_STEPS=str(STEPS_PER_FRAME),
        ARENA_LOG_PATH=log_path,
        SDL_VIDEODRIVER="dummy",
        SDL_AUDIODRIVER="dummy",
        PYGAME_HIDE_SUPPORT_PROMPT="1",
    )

    started = time.time()
    say(f"[{name}] started: blue Lv{cond['blue']} vs red Lv{cond['red']}, {games} matches")
    proc = subprocess.Popen(
        [sys.executable, "main.py"], cwd=HERE, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    children.append(proc)

    done = 0
    tail = []
    step = max(1, games // 5)
    for line in proc.stdout:
        tail = (tail + [line.rstrip()])[-15:]
        if "=== MATCH" in line:
            done += 1
            if done % step == 0 or done == games:
                elapsed = time.time() - started
                eta = elapsed / done * (games - done)
                say(f"[{name}] {done}/{games} matches | {elapsed / 60:.1f} min elapsed, ~{eta / 60:.1f} min left")
    rc = proc.wait()

    if rc != 0 or not is_complete(log_path):
        say(f"[{name}] FAILED (exit {rc}). Last output:\n    " + "\n    ".join(tail))
        return name, log_path, "failed"

    say(f"[{name}] finished in {(time.time() - started) / 60:.1f} min")
    return name, log_path, "ok"


# ----------------------------- analysis ------------------------------
def wilson(k, n, z=1.96):
    """95% confidence interval for a win rate."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def pct(a, b):
    return 100.0 * a / b if b else float("nan")


def summarize(path):
    with open(path) as f:
        ev = [json.loads(line) for line in f if line.strip()]
    start = next(e for e in ev if e["k"] == "run_start")
    rounds = [e for e in ev if e["k"] == "round_end"]
    matches = [e for e in ev if e["k"] == "match_end"]
    zones = [e for e in ev if e["k"] == "fire_zone"]

    n_m, n_r = len(matches), len(rounds)
    blue_m = sum(1 for m in matches if m["winner"] == "blue")
    lo, hi = wilson(blue_m, n_m)
    rw = Counter(r["winner"] for r in rounds)

    team = {"blue": Counter(), "red": Counter()}
    bots = Counter()
    for r in rounds:
        for c in r["chars"]:
            bots[c["team"]] += 1
            for k, v in c["stats"].items():
                team[c["team"]][k] += v

    def cover_share(t):
        s = team[t]
        total = sum(v for k, v in s.items() if k.startswith("t_")) or 1
        return pct(s["t_cover_peek"], total)

    dmg_total = sum(team[t]["dmg_dealt"] for t in team) or 1
    ticks = sum(v[1] for z in zones for v in z["victims"].values())
    hiding = sum(v[2] for z in zones for v in z["victims"].values())
    durs = [r["dur"] for r in rounds]

    return {
        "blue_exp": start["blue_exp"][0], "red_exp": start["red_exp"][0],
        "matches": n_m, "rounds": n_r,
        "blue_match_win": pct(blue_m, n_m), "ci_lo": 100 * lo, "ci_hi": 100 * hi,
        "blue_round": pct(rw["blue"], n_r), "red_round": pct(rw["red"], n_r),
        "draw_round": pct(rw["draw"], n_r),
        "median_round_s": statistics.median(durs) if durs else float("nan"),
        "acc_blue": pct(team["blue"]["hits"], team["blue"]["shots"]),
        "acc_red": pct(team["red"]["hits"], team["red"]["shots"]),
        "cover_blue": cover_share("blue"), "cover_red": cover_share("red"),
        "fire_share": pct(sum(team[t]["dmg_fire_dealt"] for t in team), dmg_total),
        "burn_hiding": pct(hiding, ticks),
        "flanks_per_bot_round": sum(team[t]["flanks"] for t in team) / max(1, sum(bots.values())),
    }


def write_comparison(results, outdir):
    cols = [
        ("#", lambda i, n, s: str(i)),
        ("Matchup (blue vs red)", lambda i, n, s: f"Lv{s['blue_exp']} vs Lv{s['red_exp']}  ({n.split('_', 1)[1]})"),
        ("Matches", lambda i, n, s: str(s["matches"])),
        ("Blue match win % [95% CI]", lambda i, n, s: f"{s['blue_match_win']:.0f} [{s['ci_lo']:.0f}-{s['ci_hi']:.0f}]"),
        ("Rounds blue/red/draw %", lambda i, n, s: f"{s['blue_round']:.0f}/{s['red_round']:.0f}/{s['draw_round']:.0f}"),
        ("Median round s", lambda i, n, s: f"{s['median_round_s']:.0f}"),
        ("Accuracy % b/r", lambda i, n, s: f"{s['acc_blue']:.0f}/{s['acc_red']:.0f}"),
        ("Time in cover % b/r", lambda i, n, s: f"{s['cover_blue']:.0f}/{s['cover_red']:.0f}"),
        ("Fire % of damage", lambda i, n, s: f"{s['fire_share']:.0f}"),
        ("Burn ticks while hiding %", lambda i, n, s: f"{s['burn_hiding']:.0f}"),
        ("Flanks/bot/round", lambda i, n, s: f"{s['flanks_per_bot_round']:.2f}"),
    ]
    rows = [[fn(i, n, s) for _, fn in cols] for i, (n, s) in enumerate(results, 1)]
    header = [c for c, _ in cols]

    md = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    md += ["| " + " | ".join(r) + " |" for r in rows]
    table = "\n".join(md)

    with open(os.path.join(outdir, "comparison.md"), "w") as f:
        f.write("# Experience-level experiment\n\n" + table + "\n\n"
                "Blue is the stronger team and spawns on the left. "
                "The two 100-vs-80 rows are the same matchup with different seeds: "
                "their gap shows how much is just luck. The 100-vs-100 row shows "
                "side bias.\n")
    with open(os.path.join(outdir, "comparison.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return table


# -------------------------------- main --------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--games", type=int, default=GAMES_PER_CONDITION, help="matches per condition")
    ap.add_argument("--jobs", type=int, default=3, help="conditions to run in parallel")
    ap.add_argument("--quick", action="store_true", help="3 matches per condition (smoke test)")
    ap.add_argument("--out", help="output folder (reuse one to resume)")
    args = ap.parse_args()

    games = 3 if args.quick else args.games
    outdir = args.out or os.path.join(HERE, "logs", "experiment_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(outdir, exist_ok=True)

    with open(os.path.join(outdir, "experiment.json"), "w") as f:
        json.dump({"games_per_condition": games, "steps_per_frame": STEPS_PER_FRAME,
                   "conditions": CONDITIONS, "started": time.ctime()}, f, indent=2)

    say(f"Output folder: {outdir}")
    say(f"{len(CONDITIONS)} conditions x {games} matches, {args.jobs} in parallel. Ctrl+C to stop; rerun with --out to resume.\n")

    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = [pool.submit(run_condition, i, c, games, outdir) for i, c in enumerate(CONDITIONS, 1)]
            outcomes = [f.result() for f in futures]
    except KeyboardInterrupt:
        for p in children:
            if p.poll() is None:
                p.terminate()
        say("\nStopped. Finished conditions are kept; rerun with --out " + outdir + " to resume.")
        sys.exit(130)

    results = []
    for name, path, status in outcomes:
        if status == "failed":
            continue
        results.append((name, summarize(path)))
        with open(os.path.join(outdir, f"report_{name}.txt"), "w") as f:
            out = subprocess.run([sys.executable, "analyze_logs.py", path], cwd=HERE,
                                 capture_output=True, text=True)
            f.write(out.stdout or out.stderr)

    if results:
        say("\n" + write_comparison(results, outdir))
    failed = [o[0] for o in outcomes if o[2] == "failed"]
    if failed:
        say("\nFAILED conditions (rerun with --out to retry): " + ", ".join(failed))
    say(f"\nTotal time {(time.time() - t0) / 60:.1f} min.\nStart with: {os.path.join(outdir, 'comparison.md')}")


if __name__ == "__main__":
    main()
