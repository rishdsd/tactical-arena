"""Turns a 1-100 experience level into concrete bot behaviour settings.

Low experience  -> walks at the enemy, shoots badly, forgets quickly, no tricks.
High experience -> uses cover, peeks, flanks, leads shots, shares enemy
                   sightings with teammates, uses abilities well.
"""
from types import SimpleNamespace


def _lerp(a, b, t):
    return a + (b - a) * t


def profile(experience):
    exp = max(1, min(100, int(experience)))
    t = (exp - 1) / 99.0

    if exp < 25:
        tier = "novice"
    elif exp < 70:
        tier = "regular"
    else:
        tier = "veteran"

    return SimpleNamespace(
        experience=exp,
        tier=tier,
        # --- Skill numbers (scale smoothly) ---
        aim_error=_lerp(0.30, 0.04, t),          # radians of random aim error
        fire_interval_mult=_lerp(1.4, 0.85, t),  # multiplies BOT_FIRE_INTERVAL
        reaction_time=_lerp(0.80, 0.12, t),      # delay between spotting and firing
        memory_seconds=_lerp(0.8, 6.0, t),       # how long a last-seen position is trusted
        vision_range=_lerp(450, 800, t),         # how far the bot can spot enemies
        peek_pause=_lerp(0.90, 0.35, t),         # seconds waiting in cover between peeks
        peek_exposure=_lerp(1.00, 0.50, t),      # seconds exposed during a peek
        # --- Behaviour unlocks (thresholds) ---
        tactical=exp >= 25,                      # may use cover/peek at all
        cover_hp=0.0 if exp < 25 else (0.40 if exp < 70 else 0.60),
        strafes=exp >= 25,
        uses_fire=exp >= 20,
        fire_cluster=exp >= 40,
        water_wall=exp >= 40,
        shares_intel=exp >= 40,
        uses_llm=exp >= 40,
        flank=exp >= 70,
        lead_shots=exp >= 70,
    )
