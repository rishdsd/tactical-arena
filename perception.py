"""Limited-information perception for bots.

Every character keeps a dict of Contacts: what it *believes* about each enemy.
A contact is only refreshed when the enemy is in line of sight (and in vision
range) or when a teammate calls it out. Behind a wall, the bot only has the
last-seen position, which gets stale.
"""
import pygame

from arena import clear_line_of_sight
from experience import profile

HUMAN_VISION = 900
MAX_MEMORY = 8.0  # contacts older than this are always dropped


class Contact:
    __slots__ = ("enemy", "pos", "seen_at", "visible", "visible_since", "velocity")

    def __init__(self, enemy, now):
        self.enemy = enemy
        self.pos = enemy.pos.copy()
        self.seen_at = now
        self.visible = False
        self.visible_since = None
        self.velocity = pygame.Vector2()


def update_perception(characters, now):
    alive = [c for c in characters if c.alive]

    # 1) Own eyes.
    for observer in alive:
        vision = (
            HUMAN_VISION if observer.is_human
            else profile(observer.experience).vision_range
        )
        contacts = observer.contacts

        for enemy in alive:
            if enemy.team == observer.team:
                continue

            contact = contacts.get(enemy)
            sees = (
                observer.pos.distance_to(enemy.pos) <= vision
                and clear_line_of_sight(observer.pos, enemy.pos)
            )

            if sees:
                if contact is None:
                    contact = contacts[enemy] = Contact(enemy, now)
                if contact.visible:
                    dt = now - contact.seen_at
                    if dt > 0:
                        raw = (enemy.pos - contact.pos) / dt
                        contact.velocity = contact.velocity * 0.8 + raw * 0.2
                else:
                    contact.velocity = pygame.Vector2()
                    contact.visible_since = now
                contact.pos = enemy.pos.copy()
                contact.seen_at = now
                contact.visible = True
            elif contact is not None:
                contact.visible = False
                contact.visible_since = None

        for enemy in list(contacts):
            c = contacts[enemy]
            if not enemy.alive or now - c.seen_at > MAX_MEMORY:
                del contacts[enemy]

    # 2) Team callouts: experienced bots listen to what teammates see right now.
    for listener in alive:
        if listener.is_human or not profile(listener.experience).shares_intel:
            continue
        for ally in alive:
            if ally is listener or ally.team != listener.team:
                continue
            for enemy, seen in ally.contacts.items():
                if not seen.visible or not enemy.alive:
                    continue
                mine = listener.contacts.get(enemy)
                if mine is None:
                    mine = listener.contacts[enemy] = Contact(enemy, now)
                    mine.pos = seen.pos.copy()
                    mine.seen_at = seen.seen_at
                elif seen.seen_at > mine.seen_at:
                    mine.pos = seen.pos.copy()
                    mine.seen_at = seen.seen_at
