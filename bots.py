import math
import random
import pygame

from config import (
    WIDTH, HEIGHT, BOT_SPEED, BOT_FIRE_INTERVAL, BOT_BULLET_SPEED,
    FIRE_COOLDOWN, WATER_WALL_COOLDOWN,
)
from entities import Bullet, FireProjectile, WaterWall
from bot_policy import (
    choose_fire_burst_target, choose_water_wall_position, choose_combat_target,
)
from arena import move_with_walls, circle_hits_rect, walls
from experience import profile
from logger import log
import config
from tactics import (
    step_toward, reset_tactics, update_cover_peek, update_flank,
)

PLANNER_DECISION_TTL = 8.0   # seconds an LLM decision stays valid
CRITICAL_HP = 0.30           # tactical bots always seek cover below this


# -------------------- Abilities --------------------

def use_abilities(bot, prof, characters, fire_projectiles, water_walls, now):
    if fire_projectiles is not None and prof.uses_fire:
        seen = [c.enemy for c in bot.contacts.values() if c.visible and c.enemy.alive]
        if seen:
            target = choose_fire_burst_target(
                bot, seen, now, use_clusters=prof.fire_cluster
            )
            if target is not None:
                direction = target - bot.pos
                if direction.length_squared() > 0:
                    direction = direction.normalize()
                    fire_projectiles.append(
                        FireProjectile(bot.pos + direction * (bot.radius + 5), direction, bot)
                    )
                    bot.fire_burst_ready_at = now + FIRE_COOLDOWN
                    bot.stats["fire_casts"] += 1
                    log.event(
                        "cast", ability="fire", bot=bot.name, hp=bot.hp, mode=bot.mode,
                        pos=bot.pos, aim=target, dist=round(bot.pos.distance_to(target)),
                    )

    if water_walls is not None and prof.water_wall:
        decision = choose_water_wall_position(bot, characters, now)
        if decision is not None:
            position, threat_direction = decision
            water_walls.append(WaterWall(position, threat_direction, now))
            bot.water_wall_ready_at = now + WATER_WALL_COOLDOWN
            bot.stats["water_casts"] += 1
            log.event("cast", ability="water", bot=bot.name, hp=bot.hp, mode=bot.mode, pos=position)


# -------------------- Decision making --------------------

def health_state(ratio):
    if ratio <= CRITICAL_HP:
        return "critical"
    if ratio <= 0.60:
        return "hurt"
    return "healthy"


def rule_mode(bot, contact, prof, now, visible_count):
    """Rule-based baseline. Also used as a hint for (and fallback from) the LLM."""
    if contact is None:
        return "search"
    if not prof.tactical:
        return "attack"

    hp = bot.hp / bot.max_hp
    if hp <= prof.cover_hp:
        return "cover_peek"

    if (
        prof.flank
        and not contact.visible
        and now - contact.seen_at >= 1.5
        and now >= bot.flank_done_until
    ):
        return "flank"

    if prof.flank and visible_count >= 2 and hp < 0.85:
        return "cover_peek"

    return "attack"


def resolve_mode(bot, contact, prof, now, rule):
    if contact is None:
        return "search"
    if not prof.tactical:
        return "attack"  # novices never get fancy

    mode = rule
    if bot.planner_action and now - bot.planner_at <= PLANNER_DECISION_TTL:
        mode = bot.planner_action

    # Guard rails around whatever the LLM said.
    if mode == "flank" and (not prof.flank or now < bot.flank_done_until):
        mode = "attack"
    if bot.hp / bot.max_hp <= CRITICAL_HP:
        mode = "cover_peek"
    if mode == "cover_peek" and now < bot.cover_failed_until:
        mode = "attack"
    return mode


def consult_planner(bot, contact, prof, now, visible_count, rule, tactical_ai, characters):
    hp_ratio = bot.hp / bot.max_hp
    actions = ["attack", "cover_peek"] + (["flank"] if prof.flank else [])

    observation = {
        "bot_hp": bot.hp,
        "health": health_state(hp_ratio),
        "experience_tier": prof.tier,
        "enemy_visible_now": contact.visible,
        "seconds_since_enemy_seen": round(now - contact.seen_at, 1),
        "enemy_distance": round(bot.pos.distance_to(contact.pos)),
        "enemy_hp": contact.enemy.hp if contact.visible else None,
        "visible_enemy_count": visible_count,
        "ally_alive": any(
            c.alive and c is not bot and c.team == bot.team for c in characters
        ),
        "rules_suggest": rule,
        "available_actions": actions,
    }

    tactical_ai.request_decision(observation)
    decision = tactical_ai.get_latest_decision()

    if decision is not None:
        bot.planner_action = decision["action"]
        bot.planner_at = now
        agrees = decision.get("rules_suggest") == decision["action"]
        bot.stats["planner_n"] += 1
        bot.stats["planner_agree"] += int(agrees)
        bot.stats["planner_" + decision["action"]] += 1
        bot.stats["planner_latency"] += decision.get("latency", 0.0)
        if config.LOG_PLANNER_EVENTS:
            log.event(
                "planner", bot=bot.name, hp=bot.hp, rule=decision.get("rules_suggest"),
                choice=decision["action"], lat=round(decision.get("latency", 0.0), 2),
                vis=visible_count, dist=observation["enemy_distance"],
                reason=decision.get("reason", "")[:80],
            )


# -------------------- Movement --------------------

def pick_search_goal(bot, prof):
    for _ in range(25):
        p = pygame.Vector2(
            random.uniform(60, WIDTH - 60), random.uniform(100, HEIGHT - 60)
        )
        if prof.tactical:
            # Experienced bots push toward the enemy half rather than wandering.
            if bot.team == "blue":
                p.x = max(p.x, WIDTH * 0.4)
            else:
                p.x = min(p.x, WIDTH * 0.6)
        if any(circle_hits_rect(p, bot.radius + 4, w) for w in walls):
            continue
        return p
    return pygame.Vector2(WIDTH / 2, HEIGHT / 2)


def update_search(bot, dt, now, prof):
    if bot.search_goal is None or now > bot.search_until:
        bot.search_goal = pick_search_goal(bot, prof)
        bot.search_until = now + 6.0

    if step_toward(bot, bot.search_goal, dt, arrive=24):
        bot.search_goal = None
    return True


def normal_combat_movement(bot, contact, dt, now, prof):
    delta = contact.pos - bot.pos
    distance = delta.length()

    # Enemy not in sight: go to where we last saw them. Once we're there and
    # still can't see anyone, the trail is cold.
    if not contact.visible:
        if step_toward(bot, contact.pos, dt, arrive=14):
            bot.contacts.pop(contact.enemy, None)
        return

    if distance <= 1:
        return

    # Novice: walk up to the enemy and stand still while shooting.
    if not prof.strafes:
        if distance > 180:
            step_toward(bot, contact.pos, dt)
        return

    if distance > 235:
        step_toward(bot, contact.pos, dt)
    elif distance < 115:
        move_with_walls(bot.pos, -delta.normalize() * BOT_SPEED * dt, bot.radius)
    else:
        if now >= bot.strafe_until:
            bot.strafe_sign = random.choice((-1, 1))
            bot.strafe_until = now + random.uniform(0.5, 1.5)
        perpendicular = pygame.Vector2(-delta.y, delta.x).normalize()
        move_with_walls(
            bot.pos, perpendicular * bot.strafe_sign * BOT_SPEED * dt, bot.radius
        )


# -------------------- Shooting --------------------

def try_shoot(bot, contact, prof, now, bullets):
    if contact is None or not contact.visible or contact.visible_since is None:
        return
    # Reaction time: inexperienced bots take a moment to start shooting.
    if now - contact.visible_since < prof.reaction_time:
        return
    if now - bot.last_shot < BOT_FIRE_INTERVAL * prof.fire_interval_mult:
        return

    aim_point = contact.pos.copy()
    distance = bot.pos.distance_to(aim_point)
    if distance <= 1:
        return

    if prof.lead_shots:
        velocity = contact.velocity
        if velocity.length() > 300:
            velocity.scale_to_length(300)
        aim_point += velocity * (distance / BOT_BULLET_SPEED) * 0.7

    delta = aim_point - bot.pos
    angle = math.atan2(delta.y, delta.x)
    angle += random.uniform(-prof.aim_error, prof.aim_error)
    aim = pygame.Vector2(math.cos(angle), math.sin(angle))
    bullets.append(Bullet(bot.pos + aim * (bot.radius + 3), aim, bot))
    bot.last_shot = now
    bot.stats["shots"] += 1


# -------------------- Main entry point --------------------

def bot_update(
    bot,
    characters,
    bullets,
    dt,
    now,
    fire_projectiles=None,
    water_walls=None,
    human_target=None,
    tactical_ai=None,
):
    if not bot.alive or bot.is_human:
        return
    if not any(c.alive and c.team != bot.team for c in characters):
        return

    prof = profile(bot.experience)

    use_abilities(bot, prof, characters, fire_projectiles, water_walls, now)

    contact = choose_combat_target(bot, now, prof.memory_seconds, human_target)
    visible_count = sum(1 for c in bot.contacts.values() if c.visible)
    rule = rule_mode(bot, contact, prof, now, visible_count)

    # Occasional high-level decision from the LLM (non-blocking).
    if tactical_ai is not None and contact is not None and prof.uses_llm:
        consult_planner(bot, contact, prof, now, visible_count, rule, tactical_ai, characters)

    mode = resolve_mode(bot, contact, prof, now, rule)
    bot.stats["t_" + mode] += dt
    if mode != bot.mode:
        bot.mode = mode
        bot.stats["mode_switches"] += 1
        reset_tactics(bot, now)

    handled = False
    if mode == "cover_peek":
        handled = update_cover_peek(bot, contact, dt, now, prof)
    elif mode == "flank":
        handled = update_flank(bot, contact, dt, now)
    elif mode == "search":
        handled = update_search(bot, dt, now, prof)

    if not handled and contact is not None:
        normal_combat_movement(bot, contact, dt, now, prof)

    # While running between cover spots, don't shoot; only while peeking.
    hiding = mode == "cover_peek" and handled and bot.tac_state != "peeking"
    if not hiding:
        try_shoot(bot, contact, prof, now, bullets)
