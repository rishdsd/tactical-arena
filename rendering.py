import pygame
from config import (
    WIDTH, HEIGHT, BG, GRID, WALL_COLOR, WHITE, MUTED, BLUE, BLUE_LIGHT,
    RED, RED_LIGHT, GREEN, YELLOW, MAGAZINE_SIZE, BULLET_RADIUS,
    FIRE_ZONE_RADIUS, FIRE_ZONE_DURATION, FIRE_ORANGE, FIRE_YELLOW, WATER_CYAN, WATER_LIGHT
)


def render_frame(
    screen, font, small_font, large_font, now, characters, bullets,
    fire_projectiles, fire_zones, water_walls,
    blue_rounds, red_rounds, round_number,
    round_over, match_over, round_message, player,
    player_fire_burst_ready_at, water_wall_ready_at, walls,
):
    def draw_text(text, x, y, color=WHITE, font_obj=None):
        if font_obj is None:
            font_obj = font
        screen.blit(font_obj.render(text, True, color), (x, y))

    screen.fill(BG)
    for x in range(0, WIDTH, 40):
        pygame.draw.line(screen, GRID, (x, 70), (x, HEIGHT))
    for y in range(70, HEIGHT, 40):
        pygame.draw.line(screen, GRID, (0, y), (WIDTH, y))
    pygame.draw.rect(screen, (14, 17, 24), (0, 0, WIDTH, 70))
    draw_text("TACTICAL ARENA | 2v2", 18, 10, WHITE, large_font)
    draw_text(f"BLUE {blue_rounds} - {red_rounds} RED", 440, 18, YELLOW)
    draw_text(f"ROUND {round_number}", 805, 18)

    for wall in walls:
        pygame.draw.rect(screen, WALL_COLOR, wall, border_radius=5)
        pygame.draw.rect(screen, (105, 118, 140), wall, 2, border_radius=5)

    # Water barriers: dark outline with a bright cyan center.
    for wall in water_walls:
        pygame.draw.line(
            screen, (25, 105, 145),
            wall.start, wall.end,
            wall.thickness + 6,
        )
        pygame.draw.line(
            screen, WATER_CYAN,
            wall.start, wall.end,
            wall.thickness,
        )
        pygame.draw.line(
            screen, WATER_LIGHT,
            wall.start, wall.end,
            3,
        )

    # Draw active fire zones and their projectiles.
    for zone in fire_zones:
        remaining = max(0.0, zone.expires_at - now)
        pulse = int(5 * (1.0 - remaining / FIRE_ZONE_DURATION))
        pygame.draw.circle(screen, (130, 48, 25), zone.pos, FIRE_ZONE_RADIUS)
        pygame.draw.circle(screen, FIRE_ORANGE, zone.pos, max(8, FIRE_ZONE_RADIUS - pulse), 4)
        pygame.draw.circle(screen, FIRE_YELLOW, zone.pos, max(6, FIRE_ZONE_RADIUS // 2), 2)

    for projectile in fire_projectiles:
        pygame.draw.circle(screen, FIRE_ORANGE, projectile.pos, 8)
        pygame.draw.circle(screen, FIRE_YELLOW, projectile.pos, 4)

    for bullet in bullets:
        pygame.draw.circle(screen, BLUE_LIGHT if bullet.team == "blue" else RED_LIGHT, bullet.pos, BULLET_RADIUS)

    for character in characters:
        color = BLUE if character.team == "blue" else RED
        highlight = BLUE_LIGHT if character.team == "blue" else RED_LIGHT
        if not character.alive:
            pygame.draw.circle(screen, (75, 80, 90), character.pos, character.radius, 2)
            continue
        pygame.draw.circle(screen, color, character.pos, character.radius)
        pygame.draw.circle(screen, highlight, character.pos, character.radius, 2)
        bar = pygame.Rect(character.pos.x - 22, character.pos.y - 29, 44, 6)
        pygame.draw.rect(screen, (55, 40, 48), bar)
        hp_color = GREEN if character.hp > 35 else YELLOW if character.hp > 15 else RED
        pygame.draw.rect(screen, hp_color, (bar.x, bar.y, bar.width * character.hp / character.max_hp, bar.height))
        label = character.name if character.is_human else f"{character.name} Lv{character.experience}"
        name_surface = small_font.render(label, True, WHITE)
        screen.blit(name_surface, name_surface.get_rect(center=(character.pos.x, character.pos.y + 29)))

    if player.alive:
        aim = pygame.Vector2(pygame.mouse.get_pos()) - player.pos
        if aim.length_squared() > 0:
            aim.scale_to_length(player.radius + 10)
            pygame.draw.line(screen, WHITE, player.pos, player.pos + aim, 3)
    mx, my = pygame.mouse.get_pos()
    pygame.draw.circle(screen, WHITE, (mx, my), 8, 1)
    pygame.draw.line(screen, WHITE, (mx - 12, my), (mx - 4, my), 1)
    pygame.draw.line(screen, WHITE, (mx + 4, my), (mx + 12, my), 1)
    pygame.draw.line(screen, WHITE, (mx, my - 12), (mx, my - 4), 1)
    pygame.draw.line(screen, WHITE, (mx, my + 4), (mx, my + 12), 1)

    pygame.draw.rect(screen, (14, 17, 24), (0, HEIGHT - 55, WIDTH, 55))
    ally = next(c for c in characters if c.name == "ALLY")
    draw_text(f"YOU HP: {player.hp}", 16, HEIGHT - 42, GREEN if player.hp > 30 else RED)
    draw_text(f"AMMO: {player.ammo}/{MAGAZINE_SIZE}", 175, HEIGHT - 42, YELLOW)
    draw_text(f"ALLY: {'UP' if ally.alive else 'DOWN'} ({ally.hp} HP)", 365, HEIGHT - 42, BLUE_LIGHT)
    fire_ready_in = max(0.0, player_fire_burst_ready_at - now)
    fire_label = (
        "Q FIRE: READY"
        if fire_ready_in <= 0
        else f"Q FIRE: {fire_ready_in:.1f}s"
    )
    draw_text(
        fire_label, 570, HEIGHT - 42,
        FIRE_YELLOW if fire_ready_in <= 0 else MUTED,
        small_font,
    )

    water_ready_in = max(0.0, water_wall_ready_at - now)
    water_label = (
        "E WATER: READY"
        if water_ready_in <= 0
        else f"E WATER: {water_ready_in:.1f}s"
    )
    draw_text(
        water_label, 750, HEIGHT - 42,
        WATER_LIGHT if water_ready_in <= 0 else MUTED,
        small_font,
    )

    draw_text(
        "WASD move | Mouse aim | Click shoot | R reload",
        570, HEIGHT - 22, MUTED, small_font,
    )

    if player.reloading:
        draw_text("RELOADING...", 18, HEIGHT - 72, YELLOW, small_font)

    if round_over:
        color = GREEN if blue_rounds > red_rounds else RED
        overlay = large_font.render(round_message, True, color)
        screen.blit(overlay, overlay.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 15)))
        prompt = "Enter: restart match" if match_over else "Enter: next round"
        label = font.render(prompt, True, WHITE)
        screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 25)))
    pygame.display.flip()
