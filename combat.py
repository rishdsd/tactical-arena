from config import WIDTH, HEIGHT, BULLET_RADIUS
from arena import circle_hits_rect
from abilities import bullet_hits_water_wall
from logger import log


def update_bullets(bullets, characters, dt, walls, water_walls):
    for bullet in bullets:
        bullet.pos += bullet.velocity * dt
        stats = bullet.owner.stats

        if not (0 <= bullet.pos.x <= WIDTH and 70 <= bullet.pos.y <= HEIGHT):
            bullet.alive = False
            stats["bullets_oob"] += 1
            continue

        if any(
            circle_hits_rect(bullet.pos, BULLET_RADIUS, wall)
            for wall in walls
        ):
            bullet.alive = False
            stats["bullets_hit_wall"] += 1
            continue

        if bullet_hits_water_wall(
            bullet.pos, BULLET_RADIUS, water_walls
        ):
            bullet.alive = False
            stats["bullets_blocked"] += 1
            continue

        for victim in characters:
            if not victim.alive or victim.team == bullet.team:
                continue

            if bullet.pos.distance_to(victim.pos) <= (
                victim.radius + BULLET_RADIUS
            ):
                before = victim.hp
                victim.hp = max(0, victim.hp - bullet.damage)
                dealt = before - victim.hp
                bullet.alive = False

                stats["hits"] += 1
                stats["dmg_dealt"] += dealt
                victim.stats["dmg_bullet_taken"] += dealt
                log.note_damage()

                if victim.hp == 0:
                    victim.alive = False
                    bullet.owner.kills += 1
                    log.event("death", victim=victim.name, killer=bullet.owner.name,
                              cause="bullet", mode=victim.mode)

                break

    return [bullet for bullet in bullets if bullet.alive]
