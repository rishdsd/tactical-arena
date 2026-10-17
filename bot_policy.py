import pygame

from config import FIRE_PROJECTILE_RANGE, WATER_WALL_MAX_RANGE
from arena import clear_line_of_sight


def choose_fire_burst_target(bot, enemies, now, use_clusters=True):
    """
    Decide whether a bot should use Fire Burst.
    `enemies` should only contain enemies the bot can currently see.
    Inexperienced bots pass use_clusters=False and only fire at single targets.
    """
    if now < bot.fire_burst_ready_at:
        return None

    candidates = [
        enemy
        for enemy in enemies
        if bot.pos.distance_to(enemy.pos) <= FIRE_PROJECTILE_RANGE - 20
        and clear_line_of_sight(bot.pos, enemy.pos)
    ]

    if not candidates:
        return None

    # Priority 1: target a cluster of at least two enemies.
    if use_clusters:
        for target in candidates:
            nearby = [
                enemy for enemy in candidates
                if enemy.pos.distance_to(target.pos) <= 115
            ]
            if len(nearby) >= 2:
                center = pygame.Vector2(0, 0)
                for enemy in nearby:
                    center += enemy.pos
                center /= len(nearby)

                if (
                    bot.pos.distance_to(center) <= FIRE_PROJECTILE_RANGE - 20
                    and clear_line_of_sight(bot.pos, center)
                ):
                    return center

    # Priority 2: attack a single enemy at a useful distance.
    target = min(candidates, key=lambda e: bot.pos.distance_squared_to(e.pos))
    distance = bot.pos.distance_to(target.pos)

    if 110 <= distance <= 220:
        return target.pos.copy()

    return None


def choose_water_wall_position(bot, characters, now):
    """
    Decide whether this bot should protect itself or a teammate.
    Only enemies the bot has seen in the last second count as threats
    (it can't react to what it doesn't know about).

    Returns (wall_position, threat_direction), or None.
    """
    if bot.is_human or now < bot.water_wall_ready_at:
        return None

    threats = [
        c.pos for c in bot.contacts.values()
        if c.enemy.alive and now - c.seen_at <= 1.0
    ]
    allies = [c for c in characters if c.alive and c.team == bot.team]

    candidates = []

    for ally in allies:
        for threat_pos in threats:
            threat_vector = threat_pos - ally.pos
            threat_distance = threat_vector.length()

            if not 110 <= threat_distance <= 320:
                continue
            if not clear_line_of_sight(threat_pos, ally.pos):
                continue

            threat_direction = threat_vector.normalize()
            offset = min(90, threat_distance * 0.45)
            wall_position = ally.pos + threat_direction * offset

            if bot.pos.distance_to(wall_position) > WATER_WALL_MAX_RANGE:
                continue

            score = bot.pos.distance_to(wall_position)
            if ally.is_human:
                score -= 35

            candidates.append((score, wall_position, threat_direction))

    if not candidates:
        return None

    _, position, direction = min(candidates, key=lambda item: item[0])
    return position, direction


def choose_player_aim_target(player, characters, mouse_pos):
    """
    Infer which enemy the human player is aiming at.
    Returns the enemy character, or None.
    """
    enemies = [c for c in characters if c.alive and c.team != player.team]
    cursor = pygame.Vector2(mouse_pos)
    candidates = []

    for enemy in enemies:
        cursor_distance = enemy.pos.distance_to(cursor)

        if cursor_distance > max(70, enemy.radius + 40):
            continue
        if not clear_line_of_sight(player.pos, enemy.pos):
            continue

        candidates.append((cursor_distance, enemy))

    if not candidates:
        return None

    return min(candidates, key=lambda item: item[0])[1]


def choose_combat_target(bot, now, memory_seconds, human_target=None):
    """
    Pick a Contact (the bot's belief about an enemy), not the enemy itself.
    Visible contacts are preferred; otherwise the freshest remembered one.
    Returns None when the bot knows nothing -> it should search.
    """
    contacts = [
        c for c in bot.contacts.values()
        if c.enemy.alive and (c.visible or now - c.seen_at <= memory_seconds)
    ]
    if not contacts:
        return None

    visible = [c for c in contacts if c.visible]

    # Blue teammate coordinates with the human player's target.
    if bot.team == "blue" and human_target is not None:
        for c in visible:
            if c.enemy is human_target:
                return c

    if visible:
        return min(
            visible,
            key=lambda c: (c.enemy.hp, bot.pos.distance_squared_to(c.pos)),
        )

    return max(contacts, key=lambda c: c.seen_at)
