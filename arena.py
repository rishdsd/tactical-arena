import pygame
from functools import lru_cache
from config import WIDTH, HEIGHT, PLAYER_RADIUS, BOT_SPEED

walls = [
    pygame.Rect(240, 145, 70, 220),
    pygame.Rect(420, 90, 190, 55),
    pygame.Rect(470, 280, 70, 210),
    pygame.Rect(700, 160, 55, 230),
    pygame.Rect(180, 500, 220, 45),
]


def circle_hits_rect(pos, radius, rect):
    closest_x = max(rect.left, min(pos.x, rect.right))
    closest_y = max(rect.top, min(pos.y, rect.bottom))
    dx, dy = pos.x - closest_x, pos.y - closest_y
    return dx * dx + dy * dy < radius * radius


def move_with_walls(pos, movement, radius):
    """Move on each axis independently and only resolve collisions on that axis."""
    # X axis
    if movement.x != 0:
        pos.x += movement.x
        for wall in walls:
            if circle_hits_rect(pos, radius, wall):
                if movement.x > 0:
                    pos.x = wall.left - radius
                else:
                    pos.x = wall.right + radius

    # Y axis. Do not snap horizontally when vertical movement hits a wall.
    if movement.y != 0:
        pos.y += movement.y
        for wall in walls:
            if circle_hits_rect(pos, radius, wall):
                if movement.y > 0:
                    pos.y = wall.top - radius
                else:
                    pos.y = wall.bottom + radius

    pos.x = max(radius, min(WIDTH - radius, pos.x))
    pos.y = max(70 + radius, min(HEIGHT - radius, pos.y))


def clear_line_of_sight(start, end):
    distance = start.distance_to(end)
    if distance <= 1:
        return True
    steps = max(2, int(distance / 8))
    for i in range(1, steps):
        point = start.lerp(end, i / steps)
        if any(wall.collidepoint(point.x, point.y) for wall in walls):
            return False
    return True

@lru_cache(maxsize=None)
def walkable_grid_point(gx, gy, radius=PLAYER_RADIUS):
    point = pygame.Vector2(gx * 25 + 12.5, gy * 25 + 82.5)

    if point.x < radius or point.x > WIDTH - radius:
        return False

    if point.y < 70 + radius or point.y > HEIGHT - radius:
        return False

    return not any(
        circle_hits_rect(point, radius, wall)
        for wall in walls
    )


def find_path(start_pos, goal_pos, radius=PLAYER_RADIUS):
    """Use breadth-first search to find a route around arena walls."""
    cell = 25
    cols = WIDTH // cell
    rows = (HEIGHT - 70) // cell

    def to_grid(pos):
        return (
            max(0, min(cols - 1, int(pos.x // cell))),
            max(0, min(rows - 1, int((pos.y - 70) // cell))),
        )

    start = to_grid(start_pos)
    goal = to_grid(goal_pos)

    if start == goal:
        return []

    # Find walkable tiles close to the target.
    goals = []

    for gy in range(max(0, goal[1] - 3), min(rows, goal[1] + 4)):
        for gx in range(max(0, goal[0] - 3), min(cols, goal[0] + 4)):
            if walkable_grid_point(gx, gy, radius):
                center = pygame.Vector2(
                    gx * cell + cell / 2,
                    70 + gy * cell + cell / 2,
                )

                if center.distance_squared_to(goal_pos) <= (cell * 2) ** 2:
                    goals.append((gx, gy))

    if not goals:
        return []

    goal_set = set(goals)
    queue = [start]
    came_from = {start: None}
    found = None

    directions = (
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, 1), (1, -1), (-1, 1), (-1, -1),
    )

    for current in queue:
        if current in goal_set:
            found = current
            break

        for dx, dy in directions:
            nxt = (current[0] + dx, current[1] + dy)

            if nxt in came_from:
                continue

            if not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                continue

            if not walkable_grid_point(*nxt, radius):
                continue

            # Don't cut diagonally through wall corners.
            if dx and dy:
                if not walkable_grid_point(
                    current[0] + dx, current[1], radius
                ):
                    continue

                if not walkable_grid_point(
                    current[0], current[1] + dy, radius
                ):
                    continue

            came_from[nxt] = current
            queue.append(nxt)

    if found is None:
        return []

    path = []
    node = found

    while node is not None:
        path.append(
            pygame.Vector2(
                node[0] * cell + cell / 2,
                70 + node[1] * cell + cell / 2,
            )
        )
        node = came_from[node]

    path.reverse()
    return path[1:]