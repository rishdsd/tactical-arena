import pygame

from config import WIDTH, HEIGHT, FIRE_PROJECTILE_RANGE, FIRE_ZONE_RADIUS, FIRE_DAMAGE, FIRE_DAMAGE_INTERVAL, WATER_WALL_THICKNESS, WATER_WALL_DURATION
from arena import circle_hits_rect
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
                victim.hp = max(0, victim.hp - FIRE_DAMAGE)
                zone.next_damage_at[victim] = now + FIRE_DAMAGE_INTERVAL
                if victim.hp == 0:
                    victim.alive = False
                    zone.owner.kills += 1
    fire_zones = [z for z in fire_zones if now < z.expires_at]
    return fire_projectiles, fire_zones

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