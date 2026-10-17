from config import WIDTH, HEIGHT, BULLET_RADIUS
from arena import circle_hits_rect
from abilities import bullet_hits_water_wall


def update_bullets(bullets, characters, dt, walls, water_walls):
    for bullet in bullets:
        bullet.pos += bullet.velocity * dt

        if not (0 <= bullet.pos.x <= WIDTH and 70 <= bullet.pos.y <= HEIGHT):
            bullet.alive = False
            continue

        if any(
            circle_hits_rect(bullet.pos, BULLET_RADIUS, wall)
            for wall in walls
        ):
            bullet.alive = False
            continue

        if bullet_hits_water_wall(
            bullet.pos, BULLET_RADIUS, water_walls
        ):
            bullet.alive = False
            continue

        for victim in characters:
            if not victim.alive or victim.team == bullet.team:
                continue

            if bullet.pos.distance_to(victim.pos) <= (
                victim.radius + BULLET_RADIUS
            ):
                victim.hp = max(0, victim.hp - bullet.damage)
                bullet.alive = False

                if victim.hp == 0:
                    victim.alive = False
                    bullet.owner.kills += 1

                break

    return [bullet for bullet in bullets if bullet.alive]