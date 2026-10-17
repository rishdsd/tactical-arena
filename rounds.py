from entities import Character

# Experience levels (1-100). Low = simple play, high = cover, peeking, flanking.
ALLY_EXPERIENCE = 100
ENEMY_EXPERIENCE = (1000, 1000)


def make_new_round():
    return [
        Character("YOU", "blue", (100, 350), True),
        Character("ALLY", "blue", (145, 430), experience=ALLY_EXPERIENCE),
        Character("ENEMY 1", "red", (860, 250), experience=ENEMY_EXPERIENCE[0]),
        Character("ENEMY 2", "red", (860, 470), experience=ENEMY_EXPERIENCE[1]),
    ], []
