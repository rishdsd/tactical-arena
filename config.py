import pygame

WIDTH, HEIGHT, FPS = 1000, 700, 60
ROUND_WIN_TARGET = 3
BG, GRID = (20, 24, 33), (30, 35, 46)
WALL_COLOR, WHITE, MUTED = (70, 81, 101), (240, 243, 250), (160, 170, 190)
BLUE, BLUE_LIGHT = (70, 180, 255), (150, 220, 255)
RED, RED_LIGHT = (240, 90, 95), (255, 175, 175)
GREEN, YELLOW = (90, 220, 140), (250, 205, 90)

PLAYER_RADIUS, PLAYER_SPEED, BOT_SPEED = 15, 245, 115
PLAYER_MAX_HP = BOT_MAX_HP = 100
PLAYER_DAMAGE, BOT_DAMAGE = 25, 12
PLAYER_BULLET_SPEED, BOT_BULLET_SPEED = 620, 420
PLAYER_FIRE_INTERVAL, BOT_FIRE_INTERVAL = 0.22, 0.82
MAGAZINE_SIZE, RELOAD_SECONDS, BULLET_RADIUS = 12, 1.2, 4

# Ember's signature ability.
FIRE_COOLDOWN = 8.0
FIRE_PROJECTILE_SPEED = 520
FIRE_PROJECTILE_RANGE = 420
FIRE_ZONE_RADIUS = 62
FIRE_ZONE_DURATION = 3.0
FIRE_DAMAGE = 5
FIRE_DAMAGE_INTERVAL = 0.5
FIRE_ORANGE, FIRE_YELLOW = (255, 105, 35), (255, 190, 70)

# Tidal's signature ability: Water Wall
WATER_WALL_COOLDOWN = 8.0
WATER_WALL_DURATION = 3.0
WATER_WALL_LENGTH = 150
WATER_WALL_THICKNESS = 12
WATER_WALL_MAX_RANGE = 280

WATER_CYAN = (65, 210, 245)
WATER_LIGHT = (175, 245, 255)

# ======================= Simulation & logging switches =======================
# SIMULATION_MODE = True  -> no human player: 2 AI bots vs 2 AI bots. Rounds and
#                            matches restart automatically, forever (or until
#                            SIM_MAX_MATCHES). False -> the normal game you play.
SIMULATION_MODE = True

SIM_RENDER = True           # False: no drawing (window stays blank/hidden-ish)
SIM_FAST_FORWARD = False    # True: run faster than real time (see note below)
SIM_STEPS_PER_FRAME = 8     # game steps per loop when fast-forwarding
SIM_BLUE_EXPERIENCE = (100, 100)
SIM_RED_EXPERIENCE = (80, 80)
SIM_ROUND_TIMEOUT = 90.0    # seconds of game time; then the round is a draw
SIM_ROUND_PAUSE = 1.0       # game seconds between rounds (0 when fast-forwarding)
SIM_MAX_MATCHES = 0         # 0 = run until you close the window

# The LLM planner switch. False = rules-only bots (the baseline for comparisons).
# Note: Ollama replies take real (wall-clock) time, so with SIM_FAST_FORWARD the
# LLM looks "slower" in game time. Use fast-forward mainly with the planner off.
LLM_PLANNER_ENABLED = True

LOG_TO_FILE = True
LOG_DIR = "logs"
LOG_VERBOSE = False         # True: also print Ollama/tactics chatter to console
LOG_PLANNER_EVENTS = True   # one file line per LLM decision
