import pygame

from config import WIDTH, HEIGHT, FIRE_PROJECTILE_RANGE, FIRE_ZONE_RADIUS, FIRE_DAMAGE, FIRE_DAMAGE_INTERVAL, WATER_WALL_THICKNESS, WATER_WALL_DURATION
from arena import circle_hits_rect, clear_line_of_sight
from logger import log
from entities import FireZone, WaterWall


def update_fire_abilities(fire_projectiles, fire_zones, characters, walls, now, dt):
    # Move Fire Burst projectiles and create a burning zone on impact/range.
    for projectile in fire_projectiles:
        step = projectile.velocity * dt
        projectile.pos += step
        projectile.distance_travelled += step.length()

        hit_wall = any(circle_hits_rect(projectile.pos, 6, wall) for wall in walls)
        hit_enemy = any(
            c.alive and c.team != projectile.team
            and projectile.pos.distance_to(c.pos) <= c.radius + 6
            for c in characters
        )
        out_of_bounds = not (
            0 <= projectile.pos.x <= WIDTH and 70 <= projectile.pos.y <= HEIGHT
        )
        reached_range = projectile.distance_travelled >= FIRE_PROJECTILE_RANGE

        if hit_wall or hit_enemy or out_of_bounds or reached_range:
            zone_pos = projectile.pos - projectile.velocity.normalize() * (8 if hit_wall else 0)
            zone_pos.x = max(FIRE_ZONE_RADIUS, min(WIDTH - FIRE_ZONE_RADIUS, zone_pos.x))
            zone_pos.y = max(70 + FIRE_ZONE_RADIUS, min(HEIGHT - FIRE_ZONE_RADIUS, zone_pos.y))
            if not out_of_bounds:
                fire_zones.append(FireZone(zone_pos, projectile.owner, now))
            projectile.alive = False
    fire_projectiles = [p for p in fire_projectiles if p.alive]

    # Damage opposing characters while they stand inside a fire zone.
    for zone in fire_zones:
        if now >= zone.expires_at:
            continue
        for victim in characters:
            if not victim.alive or victim.team == zone.team:
                continue
            inside = victim.pos.distance_to(zone.pos) <= FIRE_ZONE_RADIUS + victim.radius
            if not inside:
                zone.next_damage_at.pop(victim, None)
                continue
            if now >= zone.next_damage_at.get(victim, zone.created_at):
                before = victim.hp
                victim.hp = max(0, victim.hp - FIRE_DAMAGE)
                dealt = before - victim.hp
                zone.next_damage_at[victim] = now + FIRE_DAMAGE_INTERVAL

                # Bookkeeping: was the victim hiding? Was a wall in between?
                hiding = (
                    victim.mode == "cover_peek"
                    and victim.tac_state in ("seek_cover", "in_cover", "return_cover")
                )
                through_wall = not clear_line_of_sight(victim.pos, zone.pos)
                entry = zone.ticks.setdefault(victim, [0, 0, 0])
                entry[0] += 1
                entry[1] += int(hiding)
                entry[2] += int(through_wall)
                victim.stats["dmg_fire_taken"] += dealt
                victim.stats["fire_ticks"] += 1
                victim.stats["fire_ticks_hiding"] += int(hiding)
                victim.stats["fire_ticks_through_wall"] += int(through_wall)
                zone.owner.stats["dmg_dealt"] += dealt
                zone.owner.stats["dmg_fire_dealt"] += dealt
                log.note_damage()

                if victim.hp == 0:
                    victim.alive = False
                    zone.owner.kills += 1
                    log.event("death", victim=victim.name, killer=zone.owner.name,
                              cause="fire", mode=victim.mode)

    for zone in fire_zones:
        if now >= zone.expires_at:
            log_fire_zone(zone)
    fire_zones = [z for z in fire_zones if now < z.expires_at]
    return fire_projectiles, fire_zones


def log_fire_zone(zone):
    """One summary line per burning zone: who stood in it, and for how long."""
    if zone.logged:
        return
    zone.logged = True
    log.event(
        "fire_zone",
        owner=zone.owner.name,
        pos=zone.pos,
        victims={v.name: [v.team] + t for v, t in zone.ticks.items()},  # team, ticks, hiding, wall
    )

def update_water_walls(water_walls, now):
    """Remove barriers after their duration expires."""
    return [
        wall for wall in water_walls
        if now < wall.expires_at
    ]


def bullet_hits_water_wall(bullet_pos, bullet_radius, water_walls):
    """Return True when a bullet intersects any active water barrier."""
    point = pygame.Vector2(bullet_pos)

    for wall in water_walls:
        start = wall.start
        end = wall.end
        segment = end - start

        length_squared = segment.length_squared()
        if length_squared == 0:
            closest = start
        else:
            t = (point - start).dot(segment) / length_squared
            t = max(0.0, min(1.0, t))
            closest = start + segment * t

        collision_distance = (
            bullet_radius + wall.thickness / 2
        )

        if point.distance_squared_to(closest) <= collision_distance ** 2:
            return True

    return False