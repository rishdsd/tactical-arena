import os
import sys
from collections import Counter

import config

# With rendering off we don't need a real window: use SDL's dummy video driver.
if config.SIMULATION_MODE and not config.SIM_RENDER:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

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
from entities import Bullet, FireProjectile, WaterWall
from rounds import make_new_round
from bots import bot_update
from bot_policy import choose_player_aim_target
from abilities import update_fire_abilities, update_water_walls, log_fire_zone
from combat import update_bullets
from rendering import render_frame
from logger import log
import ollama_client

SIM = config.SIMULATION_MODE
FIXED_DT = 1.0 / FPS

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption(
    "Tactical Arena — SIMULATION (AI vs AI)" if SIM else "Tactical Arena — 2v2 + Fire Burst"
)
clock = pygame.time.Clock()
font, small_font, large_font = (
    pygame.font.Font(None, 25), pygame.font.Font(None, 19), pygame.font.Font(None, 42),
)


def build_tactical_ais(chars):
    """Only bots experienced enough to plan get an LLM planner (and only if enabled)."""
    if not config.LLM_PLANNER_ENABLED:
        return {}
    return {
        id(c): TacticalAI(decision_interval=2.0)
        for c in chars
        if not c.is_human and profile(c.experience).uses_llm
    }


# -------------------- Game state --------------------
characters, bullets = make_new_round()
tactical_ais = build_tactical_ais(characters)
fire_projectiles, fire_zones = [], []
water_walls = []
player_fire_burst_ready_at = 0.0
water_wall_ready_at = 0.0
blue_rounds = red_rounds = 0
round_number = 1
match_number = 1
round_over = match_over = False
round_message = "Eliminate the other team!"
round_start_t = 0.0
round_end_t = 0.0
match_draws = 0
totals = Counter()   # run-wide results, for the console summary


# -------------------- Logging helpers --------------------
def _round_stats(c):
    out = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in c.stats.items()}
    ai = tactical_ais.get(id(c))
    if ai is not None:
        out.update({"ai_" + k: v for k, v in ai.stats.items()})
    return out


def log_round_start(now):
    global round_start_t
    round_start_t = now
    log.t = now
    log.reset_round()
    log.round = round_number
    log.match = match_number
    log.event(
        "round_start",
        chars=[{"name": c.name, "team": c.team, "exp": c.experience} for c in characters],
    )


def log_round_end(winner, reason, now):
    for zone in fire_zones:
        log_fire_zone(zone)
    log.event(
        "round_end",
        winner=winner or "draw",
        reason=reason,
        dur=round(now - round_start_t, 1),
        **log.damage_summary(),
        chars=[
            {
                "name": c.name, "team": c.team, "exp": c.experience,
                "alive": c.alive, "hp": c.hp, "kills": c.kills,
                "stats": _round_stats(c),
            }
            for c in characters
        ],
    )


# -------------------- Round / match flow --------------------
def start_next_round(now=0.0):
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
    round_message = "Round started!" if SIM else "Round started — work with your teammate!"
    log_round_start(now)


def start_new_match(now=0.0):
    global blue_rounds, red_rounds, round_number, match_over, match_number, match_draws
    blue_rounds = red_rounds = match_draws = 0
    round_number = 0
    match_over = False
    match_number += 1
    log.match = match_number
    start_next_round(now)


def end_round(winner, reason, now):
    """winner: 'blue', 'red' or None (draw)."""
    global round_over, round_message, blue_rounds, red_rounds
    global match_over, round_end_t, match_draws

    round_over = True
    round_end_t = now
    log_round_end(winner, reason, now)

    if winner == "blue":
        blue_rounds += 1
        totals["rounds_blue"] += 1
        round_message = "BLUE TEAM WINS THE ROUND!"
    elif winner == "red":
        red_rounds += 1
        totals["rounds_red"] += 1
        round_message = "RED TEAM WINS THE ROUND!"
    else:
        match_draws += 1
        totals["rounds_draw"] += 1
        round_message = f"DRAW ({reason})"

    if SIM:
        log.info(
            f"[Sim] match {match_number} round {round_number}: "
            f"{winner or 'draw'} ({reason}) in {now - round_start_t:.0f}s | "
            f"BLUE {blue_rounds}-{red_rounds} RED"
        )

    if blue_rounds >= ROUND_WIN_TARGET or red_rounds >= ROUND_WIN_TARGET:
        match_over = True
        match_winner = "blue" if blue_rounds >= ROUND_WIN_TARGET else "red"
        totals["matches_" + match_winner] += 1
        log.event("match_end", winner=match_winner, rounds=[blue_rounds, red_rounds], draws=match_draws)
        if SIM:
            log.info(f"[Sim] === MATCH {match_number} won by {match_winner.upper()} "
                     f"({blue_rounds}-{red_rounds}) ===")
        round_message = (
            "MATCH VICTORY — BLUE TEAM!" if match_winner == "blue" else "MATCH DEFEAT — RED TEAM!"
        )


def check_elimination(now):
    blue_alive = any(c.alive for c in characters if c.team == "blue")
    red_alive = any(c.alive for c in characters if c.team == "red")
    if blue_alive and red_alive:
        return
    if blue_alive:
        end_round("blue", "elimination", now)
    elif red_alive:
        end_round("red", "elimination", now)
    else:
        end_round(None, "mutual_elimination", now)


def update_world(dt, now, human_target=None):
    """One simulation step shared by the human game and the AI-only simulation."""
    global fire_projectiles, fire_zones, water_walls, bullets

    update_perception(characters, now)

    for character in characters:
        bot_update(
            character, characters, bullets, dt, now,
            fire_projectiles, water_walls, human_target,
            tactical_ais.get(id(character)),
        )

    fire_projectiles, fire_zones = update_fire_abilities(
        fire_projectiles, fire_zones, characters, walls, now, dt
    )
    water_walls = update_water_walls(water_walls, now)
    bullets = update_bullets(bullets, characters, dt, walls, water_walls)


def sim_info_text():
    mode = "FAST" if config.SIM_FAST_FORWARD else "1x"
    llm = "LLM" if config.LLM_PLANNER_ENABLED else "rules"
    return (
        f"SIM {mode} {llm} | match {match_number} round {round_number} | "
        f"BLUE {blue_rounds}-{red_rounds} RED | draws {match_draws}"
    )


def draw(now, player):
    render_frame(
        screen, font, small_font, large_font, now, characters, bullets,
        fire_projectiles, fire_zones, water_walls, blue_rounds, red_rounds, round_number,
        round_over, match_over, round_message, player,
        player_fire_burst_ready_at, water_wall_ready_at, walls,
        sim_info=sim_info_text() if SIM else None,
    )


# -------------------- Startup --------------------
log.start("sim" if SIM else "play")
log.event(
    "run_start",
    sim=SIM,
    blue_exp=[c.experience for c in characters if c.team == "blue"],
    red_exp=[c.experience for c in characters if c.team == "red"],
    llm=config.LLM_PLANNER_ENABLED,
    model=ollama_client.MODEL,
    round_timeout=config.SIM_ROUND_TIMEOUT if SIM else None,
    fast_forward=config.SIM_FAST_FORWARD if SIM else False,
)
if SIM:
    log.info(f"[Sim] AI vs AI. Logging to {log.path}")
    if config.SIM_FAST_FORWARD and config.LLM_PLANNER_ENABLED:
        log.info("[Sim] Warning: fast-forward with the LLM on. Ollama replies take wall-clock "
                 "time, so planners will react slowly in game time.")
log_round_start(0.0)


# ==================== Main loop ====================
running = True
sim_time = 0.0

while running:
    if SIM:
        # ---------- AI vs AI ----------
        fast = config.SIM_FAST_FORWARD
        if not fast:
            clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
                running = False

        steps = config.SIM_STEPS_PER_FRAME if fast else 1
        for _ in range(steps):
            if not running:
                break
            sim_time += FIXED_DT
            now = sim_time
            log.t = now

            if not round_over:
                update_world(FIXED_DT, now)
                if not round_over:
                    check_elimination(now)
                if not round_over and now - round_start_t >= config.SIM_ROUND_TIMEOUT:
                    end_round(None, "timeout", now)
            else:
                pause = 0.0 if fast else config.SIM_ROUND_PAUSE
                if now - round_end_t >= pause:
                    if match_over:
                        if config.SIM_MAX_MATCHES and match_number >= config.SIM_MAX_MATCHES:
                            running = False
                        else:
                            start_new_match(now)
                    else:
                        start_next_round(now)

        if config.SIM_RENDER:
            draw(sim_time, None)
        continue

    # ---------- Human game ----------
    dt = min(clock.tick(FPS) / 1000.0, 0.04)
    now = pygame.time.get_ticks() / 1000.0
    log.t = now
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

                    water_walls.append(WaterWall(position, aim, now))
                    water_wall_ready_at = now + WATER_WALL_COOLDOWN
                    round_message = "Water Wall deployed!"
            elif event.key == pygame.K_RETURN and round_over and not match_over:
                start_next_round(now)
            elif event.key == pygame.K_RETURN and match_over:
                start_new_match(now)

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

        # Test the timer directly: the `reloading` property turns False once the
        # deadline passes, so it can't be used as the completion condition.
        if player.reloading_until > 0 and now >= player.reloading_until:
            player.ammo = MAGAZINE_SIZE
            player.reloading_until = 0.0
            round_message = "Reload complete."

        human_target = choose_player_aim_target(player, characters, pygame.mouse.get_pos())
        update_world(dt, now, human_target)
        if not round_over:
            check_elimination(now)

    draw(now, player)


# -------------------- Shutdown --------------------
log.event("run_end", totals=dict(totals))
if SIM:
    log.info(f"[Sim] finished. Totals: {dict(totals)}")
    if log.path:
        log.info(f"[Sim] Log file: {log.path}   (summarize with: python analyze_logs.py)")
log.close()
pygame.quit()
sys.exit()
