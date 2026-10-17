import pygame
from config import (
    PLAYER_RADIUS, PLAYER_MAX_HP, BOT_MAX_HP, MAGAZINE_SIZE,
    PLAYER_BULLET_SPEED, BOT_BULLET_SPEED, PLAYER_DAMAGE, BOT_DAMAGE,
    FIRE_PROJECTILE_SPEED, FIRE_ZONE_DURATION,
)

class Character:
    def __init__(self, name, team, position, is_human=False, experience=None):
        self.name, self.team = name, team
        self.pos = pygame.Vector2(position)
        self.is_human = is_human
        self.experience = experience if experience is not None else (100 if is_human else 50)
        # What this character believes about enemies (fog of war).
        self.contacts = {}
        # Bot decision state.
        self.mode = None
        self.planner_action, self.planner_at = None, -99.0
        self.tac_state, self.cover_pos = 'normal', None
        self.tac_since, self.peek_visible_since = 0.0, None
        self.cover_failed_until = 0.0
        self.flank_pos, self.flank_since, self.flank_done_until = None, 0.0, 0.0
        self.search_goal, self.search_until = None, 0.0
        self.strafe_sign, self.strafe_until = 1, 0.0
        self.radius = PLAYER_RADIUS
        self.max_hp = PLAYER_MAX_HP if is_human else BOT_MAX_HP
        self.hp, self.alive = self.max_hp, True
        self.last_shot = -10.0
        self.fire_burst_ready_at = 0.0
        self.water_wall_ready_at = 0.0
        self.ammo = MAGAZINE_SIZE if is_human else 999
        self.reloading_until = 0.0
        self.kills = 0

    @property
    def reloading(self):
        now = pygame.time.get_ticks() / 1000.0
        return self.reloading_until > now


class Bullet:
    def __init__(self, position, direction, owner):
        self.pos = pygame.Vector2(position)
        self.owner, self.team = owner, owner.team
        self.velocity = pygame.Vector2(direction) * (
            PLAYER_BULLET_SPEED if owner.is_human else BOT_BULLET_SPEED
        )
        self.damage = PLAYER_DAMAGE if owner.is_human else BOT_DAMAGE
        self.alive = True


class FireProjectile:
    def __init__(self, position, direction, owner):
        self.pos = pygame.Vector2(position)
        self.velocity = pygame.Vector2(direction) * FIRE_PROJECTILE_SPEED
        self.owner, self.team = owner, owner.team
        self.distance_travelled = 0.0
        self.alive = True


class FireZone:
    def __init__(self, position, owner, now):
        self.pos = pygame.Vector2(position)
        self.owner, self.team = owner, owner.team
        self.created_at = now
        self.expires_at = now + FIRE_ZONE_DURATION
        self.next_damage_at = {}


class WaterWall:
    def __init__(self, position, aim_direction, now):
        from config import (
            WATER_WALL_DURATION,
            WATER_WALL_LENGTH,
            WATER_WALL_THICKNESS,
        )

        self.pos = pygame.Vector2(position)

        # The wall is perpendicular to the player's aim direction.
        direction = pygame.Vector2(aim_direction).normalize()
        self.axis = pygame.Vector2(-direction.y, direction.x)

        self.half_length = WATER_WALL_LENGTH / 2
        self.thickness = WATER_WALL_THICKNESS
        self.expires_at = now + WATER_WALL_DURATION

    @property
    def start(self):
        return self.pos - self.axis * self.half_length

    @property
    def end(self):
        return self.pos + self.axis * self.half_length