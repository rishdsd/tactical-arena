import math
import time

import pygame

from config import WIDTH, HEIGHT, BOT_SPEED
from arena import clear_line_of_sight, find_path, move_with_walls, circle_hits_rect, walls


def _in_bounds(p, r):
    return r <= p.x <= WIDTH - r and 70 + r <= p.y <= HEIGHT - r


def _blocked(p, r):
    return any(circle_hits_rect(p, r, wall) for wall in walls)


# -------------------- Movement --------------------

def _get_path(bot, dest):
    """BFS is expensive, so reuse a path for a few tenths of a second."""
    now = time.monotonic()
    cache = getattr(bot, "path_cache", None)

    if cache is None or cache["dest"].distance_to(dest) > 30 or now - cache["at"] > 0.4:
        cache = {
            "dest": pygame.Vector2(dest),
            "path": find_path(bot.pos, dest, bot.radius),
            "at": now,
        }
        bot.path_cache = cache

    path = cache["path"]
    while path and bot.pos.distance_to(path[0]) < 14:
        path.pop(0)
    return path


def step_toward(bot, dest, dt, arrive=16):
    """Wall-aware movement toward dest. Returns True once arrived."""
    if bot.pos.distance_to(dest) <= arrive:
        return True

    path = _get_path(bot, dest)
    waypoint = path[0] if path else dest
    direction = waypoint - bot.pos

    if direction.length_squared() > 1:
        move_with_walls(bot.pos, direction.normalize() * BOT_SPEED * dt, bot.radius)

    return bot.pos.distance_to(dest) <= arrive + 2


def reset_tactics(bot, now):
    bot.tac_state = "seek_cover"
    bot.cover_pos = None
    bot.tac_since = now
    bot.peek_visible_since = None
    bot.flank_pos = None
    bot.flank_since = now


# -------------------- Cover / peek --------------------

def find_cover_position(bot, threat_pos):
    """Nearby spot that hides the bot from where it believes the enemy is."""
    candidates = []

    for radius in (55, 90, 125, 160):
        for i in range(16):
            angle = 2 * math.pi * i / 16
            p = bot.pos + pygame.Vector2(math.cos(angle), math.sin(angle)) * radius

            if not _in_bounds(p, bot.radius) or _blocked(p, bot.radius):
                continue
            if clear_line_of_sight(p, threat_pos):
                continue

            score = bot.pos.distance_to(p) + 0.20 * p.distance_to(threat_pos)
            candidates.append((score, p))

    candidates.sort(key=lambda item: item[0])

    # Only pay for pathfinding on the few best candidates.
    for _, p in candidates[:6]:
        if bot.pos.distance_to(p) <= 20 or find_path(bot.pos, p, bot.radius):
            return p
    return None


def update_cover_peek(bot, contact, dt, now, prof):
    """cover -> peek -> shoot -> cover. Returns True if it handled movement."""
    threat = contact.pos

    if bot.cover_pos is None:
        bot.cover_pos = find_cover_position(bot, threat)
        if bot.cover_pos is None:
            bot.cover_failed_until = now + 2.0
            print(f"[Tactics] {bot.name}: no reachable cover found", flush=True)
            return False
        bot.tac_state = "seek_cover"
        bot.tac_since = now
        print(f"[Tactics] {bot.name}: cover cycle started", flush=True)

    state = bot.tac_state

    # The enemy moved and can now see our cover spot: pick a new one.
    if (
        state in ("in_cover", "return_cover")
        and now - contact.seen_at < 1.0
        and clear_line_of_sight(bot.cover_pos, threat)
    ):
        bot.cover_pos = None
        return True

    if state == "seek_cover":
        if step_toward(bot, bot.cover_pos, dt):
            bot.tac_state = "in_cover"
            bot.tac_since = now
            print(f"[Tactics] {bot.name}: in cover", flush=True)
        return True

    if state == "in_cover":
        if now - bot.tac_since >= prof.peek_pause:
            bot.tac_state = "peeking"
            bot.tac_since = now
            bot.peek_visible_since = None
            print(f"[Tactics] {bot.name}: peeking", flush=True)
        return True

    if state == "peeking":
        if contact.visible:
            if bot.peek_visible_since is None:
                bot.peek_visible_since = now
            elif now - bot.peek_visible_since >= prof.peek_exposure:
                bot.tac_state = "return_cover"
                print(f"[Tactics] {bot.name}: returning to cover", flush=True)
        else:
            bot.peek_visible_since = None
            if now - bot.tac_since >= 1.5:
                bot.tac_state = "return_cover"
                print(f"[Tactics] {bot.name}: peek timed out", flush=True)
            else:
                step_toward(bot, threat, dt)
        return True

    if state == "return_cover":
        if step_toward(bot, bot.cover_pos, dt):
            bot.tac_state = "in_cover"
            bot.tac_since = now
            bot.peek_visible_since = None
            print(f"[Tactics] {bot.name}: back in cover", flush=True)
        return True

    return False


# -------------------- Flank --------------------

def find_flank_position(bot, threat_pos):
    """A spot that sees the enemy's last position from a different angle."""
    to_bot = bot.pos - threat_pos
    base = math.atan2(to_bot.y, to_bot.x)
    candidates = []

    for radius in (140, 190, 240):
        for deg in range(-135, 136, 30):
            if abs(deg) < 60:
                continue  # that's roughly where we already are
            a = base + math.radians(deg)
            p = threat_pos + pygame.Vector2(math.cos(a), math.sin(a)) * radius

            if not _in_bounds(p, bot.radius) or _blocked(p, bot.radius):
                continue
            if not clear_line_of_sight(p, threat_pos):
                continue
            candidates.append((bot.pos.distance_to(p), p))

    candidates.sort(key=lambda item: item[0])
    for _, p in candidates[:5]:
        if find_path(bot.pos, p, bot.radius):
            return p
    return None


def update_flank(bot, contact, dt, now):
    """Walk around to a new angle. Returns True if it handled movement."""
    if bot.flank_pos is None:
        bot.flank_pos = find_flank_position(bot, contact.pos)
        bot.flank_since = now
        if bot.flank_pos is None:
            bot.flank_done_until = now + 4.0
            bot.planner_action = None
            return False
        print(f"[Tactics] {bot.name}: flanking", flush=True)

    if step_toward(bot, bot.flank_pos, dt) or now - bot.flank_since > 5.0:
        bot.flank_pos = None
        bot.flank_done_until = now + 5.0
        bot.planner_action = None
        print(f"[Tactics] {bot.name}: flank finished", flush=True)
        return False

    return True
