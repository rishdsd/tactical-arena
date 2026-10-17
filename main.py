import sys
import pygame

from tactical_ai import TacticalAI
from perception import update_perception
from experience import profile
from config import (
    WIDTH, HEIGHT, FPS, ROUND_WIN_TARGET, PLAYER_SPEED, MAGAZINE_SIZE,
    RELOAD_SECONDS, PLAYER_FIRE_INTERVAL, FIRE_COOLDOWN, WATER_WALL_COOLDOWN,
    WATER_WALL_MAX_RANGE,
)
from arena import walls, move_with_walls
from entities import Character, Bullet, FireProjectile, WaterWall
from rounds import make_new_round
from bots import bot_update
from bot_policy import choose_player_aim_target
from abilities import (
    update_fire_abilities,
    update_water_walls
)
from combat import update_bullets
from rendering import render_frame


pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Tactical Arena — 2v2 + Fire Burst")
clock = pygame.time.Clock()
font, small_font, large_font = pygame.font.Font(None, 25), pygame.font.Font(None, 19), pygame.font.Font(None, 42)

characters, bullets = make_new_round()
def build_tactical_ais(chars):
    # Only bots experienced enough to plan get an LLM planner.
    return {
        id(c): TacticalAI(decision_interval=2.0)
        for c in chars
        if not c.is_human and profile(c.experience).uses_llm
    }


tactical_ais = build_tactical_ais(characters)
fire_projectiles, fire_zones = [], []
player_fire_burst_ready_at = 0.0
water_walls = []
water_wall_ready_at = 0.0
blue_rounds = red_rounds = 0
round_number = 1
round_over = match_over = False
round_message = "Eliminate the other team!"


def start_next_round():
    global characters, bullets, fire_projectiles, fire_zones
    global water_walls, water_wall_ready_at
    global player_fire_burst_ready_at
    global round_over, round_message, round_number
    global tactical_ais

    characters, bullets = make_new_round()
    tactical_ais = build_tactical_ais(characters)
    fire_projectiles, fire_zones = [], []
    water_walls = []

    player_fire_burst_ready_at = 0.0
    water_wall_ready_at = 0.0

    round_over = False
    round_number += 1
    round_message = "Round started — work with your teammate!"


running = True
while running:
    dt = min(clock.tick(FPS) / 1000.0, 0.04)
    now = pygame.time.get_ticks() / 1000.0
    player = next(c for c in characters if c.is_human)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif (
                event.key == pygame.K_r
                and not round_over
                and player.reloading_until == 0
                and player.ammo < MAGAZINE_SIZE
            ):
                player.reloading_until = now + RELOAD_SECONDS
                round_message = "Reloading..."
            elif (
                event.key == pygame.K_q
                and not round_over
                and player.alive
                and now >= player_fire_burst_ready_at
            ):
                direction = pygame.Vector2(pygame.mouse.get_pos()) - player.pos
                if direction.length_squared() > 0:
                    direction = direction.normalize()
                    fire_projectiles.append(
                        FireProjectile(player.pos + direction * (player.radius + 5), direction, player)
                    )
                    player_fire_burst_ready_at = now + FIRE_COOLDOWN
                    round_message = "Fire Burst launched!"
            elif (
                event.key == pygame.K_e
                and not round_over
                and player.alive
                and now >= water_wall_ready_at
            ):
                aim = pygame.Vector2(pygame.mouse.get_pos()) - player.pos

                if aim.length_squared() > 0:
                    aim = aim.normalize()

                    # Place the wall at the cursor, capped by maximum range.
                    cursor = pygame.Vector2(pygame.mouse.get_pos())
                    offset = cursor - player.pos

                    if offset.length() > WATER_WALL_MAX_RANGE:
                        offset.scale_to_length(WATER_WALL_MAX_RANGE)

                    position = player.pos + offset
                    position.x = max(80, min(WIDTH - 80, position.x))
                    position.y = max(90, min(HEIGHT - 20, position.y))

                    water_walls.append(
                        WaterWall(position, aim, now)
                    )

                    water_wall_ready_at = now + WATER_WALL_COOLDOWN
                    round_message = "Water Wall deployed!"
            elif event.key == pygame.K_RETURN and round_over and not match_over:
                start_next_round()
            elif event.key == pygame.K_RETURN and match_over:
                blue_rounds = red_rounds = 0
                round_number = 1
                match_over = False
                start_next_round()

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if (
                not round_over and player.alive and not player.reloading
                and player.ammo > 0 and now - player.last_shot >= PLAYER_FIRE_INTERVAL
            ):
                direction = pygame.Vector2(pygame.mouse.get_pos()) - player.pos
                if direction.length_squared() > 0:
                    direction = direction.normalize()
                    bullets.append(Bullet(player.pos + direction * (player.radius + 4), direction, player))
                    player.ammo -= 1
                    player.last_shot = now

    if not round_over:
        keys = pygame.key.get_pressed()
        movement = pygame.Vector2(
            int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
            int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        if player.alive and movement.length_squared() > 0:
            move_with_walls(player.pos, movement.normalize() * PLAYER_SPEED * dt, player.radius)

        # Important: test the timer directly. The reloading property becomes False
        # once the deadline passes, so it cannot be used as this completion condition.
        if player.reloading_until > 0 and now >= player.reloading_until:
            player.ammo = MAGAZINE_SIZE
            player.reloading_until = 0.0
            round_message = "Reload complete."

        # Infer which enemy the player is aiming at this frame.
        human_target = choose_player_aim_target(
            player,
            characters,
            pygame.mouse.get_pos(),
        )

        update_perception(characters, now)

        for character in characters:
            bot_update(
                character,
                characters,
                bullets,
                dt,
                now,
                fire_projectiles,
                water_walls,
                human_target,
                tactical_ais.get(id(character)),
            )

        fire_projectiles, fire_zones = update_fire_abilities(
            fire_projectiles, fire_zones, characters, walls, now, dt
        )
        water_walls = update_water_walls(water_walls, now)
        bullets = update_bullets(
            bullets, characters, dt, walls, water_walls
        )

        blue_alive = any(c.alive for c in characters if c.team == "blue")
        red_alive = any(c.alive for c in characters if c.team == "red")
        if not blue_alive or not red_alive:
            round_over = True
            if blue_alive:
                blue_rounds += 1
                round_message = "BLUE TEAM WINS THE ROUND!"
            else:
                red_rounds += 1
                round_message = "RED TEAM WINS THE ROUND!"
            if blue_rounds >= ROUND_WIN_TARGET or red_rounds >= ROUND_WIN_TARGET:
                match_over = True
                round_message = (
                    "MATCH VICTORY — BLUE TEAM!"
                    if blue_rounds >= ROUND_WIN_TARGET
                    else "MATCH DEFEAT — RED TEAM!"
                )

    render_frame(
        screen, font, small_font, large_font, now, characters, bullets,
        fire_projectiles, fire_zones, water_walls, blue_rounds, red_rounds, round_number,
        round_over, match_over, round_message, player, player_fire_burst_ready_at, water_wall_ready_at, walls,
    )

pygame.quit()
sys.exit()
