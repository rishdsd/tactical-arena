"""Compact structured logging.

Events go to a JSONL file (one JSON object per line) so they never flood the
console. Run `python analyze_logs.py` to boil a file down to a short report you
can paste into a chat without burning context.
"""
import json
import os
import time

import config


def _default(o):
    if hasattr(o, "x") and hasattr(o, "y"):  # pygame.Vector2
        return [round(o.x), round(o.y)]
    return str(o)


class Logger:
    def __init__(self):
        self.t = 0.0          # current game time, updated by main loop
        self.match = 0
        self.round = 0
        self.path = None
        self._f = None
        self.reset_round()

    # ---- lifecycle ----
    def start(self, name):
        if not config.LOG_TO_FILE:
            return
        os.makedirs(config.LOG_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(config.LOG_DIR, f"{name}_{stamp}.jsonl")
        self._f = open(self.path, "w", buffering=1)

    def close(self):
        if self._f:
            self._f.close()
            self._f = None

    # ---- output ----
    def event(self, kind, **fields):
        if self._f is None:
            return
        rec = {"k": kind, "m": self.match, "r": self.round, "t": round(self.t, 2)}
        rec.update(fields)
        self._f.write(json.dumps(rec, default=_default) + "\n")

    def info(self, msg):
        print(msg, flush=True)

    def debug(self, msg):
        if config.LOG_VERBOSE:
            print(msg, flush=True)

    # ---- stalemate metrics ----
    def reset_round(self):
        self.round_started_t = self.t
        self.first_damage_t = None
        self.last_damage_t = self.t
        self.max_damage_gap = 0.0

    def note_damage(self):
        if self.first_damage_t is None:
            self.first_damage_t = self.t - self.round_started_t
        self.max_damage_gap = max(self.max_damage_gap, self.t - self.last_damage_t)
        self.last_damage_t = self.t

    def damage_summary(self):
        # Include the quiet stretch at the end of the round.
        gap = max(self.max_damage_gap, self.t - self.last_damage_t)
        return {
            "first_damage_t": None if self.first_damage_t is None else round(self.first_damage_t, 1),
            "max_damage_gap": round(gap, 1),
        }


log = Logger()
