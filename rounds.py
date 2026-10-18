from entities import Character
from config import SIMULATION_MODE, SIM_BLUE_EXPERIENCE, SIM_RED_EXPERIENCE

# Experience levels (1-100) for the normal game with a human player.
# Low = simple play, high = cover, peeking, flanking.
ALLY_EXPERIENCE = 100
ENEMY_EXPERIENCE = (80, 80)
# (For SIMULATION_MODE the levels come from config.py: SIM_BLUE/RED_EXPERIENCE.)


def make_new_round():
    if SIMULATION_MODE:
        return [
            Character("BLUE 1", "blue", (100, 350), experience=SIM_BLUE_EXPERIENCE[0]),
            Character("BLUE 2", "blue", (145, 430), experience=SIM_BLUE_EXPERIENCE[1]),
            Character("RED 1", "red", (860, 250), experience=SIM_RED_EXPERIENCE[0]),
            Character("RED 2", "red", (860, 470), experience=SIM_RED_EXPERIENCE[1]),
        ], []

    return [
        Character("YOU", "blue", (100, 350), True),
        Character("ALLY", "blue", (145, 430), experience=ALLY_EXPERIENCE),
        Character("ENEMY 1", "red", (860, 250), experience=ENEMY_EXPERIENCE[0]),
        Character("ENEMY 2", "red", (860, 470), experience=ENEMY_EXPERIENCE[1]),
    ], []
