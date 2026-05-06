"""Buddy companion service."""

import random
import uuid
from dataclasses import dataclass
from enum import Enum


class Rarity(str, Enum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class Species(str, Enum):
    CAT = "cat"
    DOG = "dog"
    RABBIT = "rabbit"
    OWL = "owl"
    DRAGON = "dragon"


class Mood(str, Enum):
    HAPPY = "happy"
    NEUTRAL = "neutral"
    THINKING = "thinking"
    SLEEPING = "sleeping"


@dataclass
class BuddyStats:
    xp: int = 0
    level: int = 1
    happiness: int = 100
    energy: int = 100


@dataclass
class Buddy:
    id: str
    name: str
    species: Species
    rarity: Rarity
    stats: BuddyStats
    mood: Mood = Mood.NEUTRAL
    accessory: str | None = None


NAMES = [
    "Clawdia",
    "Paws",
    "Whiskers",
    "Mittens",
    "Shadow",
    "Pixel",
    "Nova",
    "Sage",
    "Ember",
    "Frost",
]


def generate_buddy() -> Buddy:
    """Generate a random buddy companion."""
    species = random.choice(list(Species))
    rarity = random.choice(
        [Rarity.COMMON] * 50 + [Rarity.RARE] * 30 + [Rarity.EPIC] * 15 + [Rarity.LEGENDARY] * 5
    )

    return Buddy(
        id=str(uuid.uuid4()),
        name=random.choice(NAMES),
        species=species,
        rarity=rarity,
        stats=BuddyStats(),
    )


class BuddyService:
    _buddies: dict[str, Buddy] = {}

    @classmethod
    def get_buddy(cls, user_id: str) -> Buddy:
        if user_id not in cls._buddies:
            cls._buddies[user_id] = generate_buddy()
        return cls._buddies[user_id]

    @classmethod
    def add_xp(cls, user_id: str, amount: int) -> Buddy:
        buddy = cls.get_buddy(user_id)
        buddy.stats.xp += amount

        xp_needed = buddy.stats.level * 100
        while buddy.stats.xp >= xp_needed:
            buddy.stats.level += 1
            buddy.stats.happiness = min(100, buddy.stats.happiness + 10)

        return buddy

    @classmethod
    def update_mood(cls, user_id: str, mood: Mood) -> Buddy:
        buddy = cls.get_buddy(user_id)
        buddy.mood = mood
        return buddy
