"""Shift type definitions and day constants."""
from enum import Enum


class ShiftType(str, Enum):
    """Types of shifts in the scheduling system."""
    DAY = "J"       # Jour (10h)
    EVENING = "S"   # Soir (10h)
    NIGHT = "N"     # Nuit (12h)
    ADMIN = "A"     # Admin (8h)
    OFF = "OFF"     # Rest day
    EDO = "EDO"     # Earned Day Off

    @property
    def hours(self) -> int:
        """Hours worked for this shift type."""
        return {
            ShiftType.DAY: 10,
            ShiftType.EVENING: 10,
            ShiftType.NIGHT: 12,
            ShiftType.ADMIN: 8,
            ShiftType.OFF: 0,
            ShiftType.EDO: 0,
        }.get(self, 0)

    @property
    def is_work(self) -> bool:
        """True if this is a working shift (not rest)."""
        return self not in (ShiftType.OFF, ShiftType.EDO)

    @classmethod
    def from_string(cls, s: str) -> "ShiftType":
        """Parse shift from various string formats."""
        mapping = {
            "j": cls.DAY, "jour": cls.DAY, "day": cls.DAY, "d": cls.DAY,
            "s": cls.EVENING, "soir": cls.EVENING, "evening": cls.EVENING, "e": cls.EVENING,
            "n": cls.NIGHT, "nuit": cls.NIGHT, "night": cls.NIGHT,
            "a": cls.ADMIN, "admin": cls.ADMIN,
            "off": cls.OFF, "repos": cls.OFF, "o": cls.OFF,
            "edo": cls.EDO,
        }
        key = str(s).strip().lower()
        if key in mapping:
            return mapping[key]
        # Try direct value match
        for member in cls:
            if member.value == s.upper():
                return member
        return cls.OFF  # Default fallback


# Day constants
WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven"]
WEEKEND = ["Sam", "Dim"]
ALL_DAYS = WEEKDAYS + WEEKEND

# Day normalization map
DAY_ALIASES = {
    "lun": "Lun", "lundi": "Lun", "mon": "Lun", "monday": "Lun",
    "mar": "Mar", "mardi": "Mar", "tue": "Mar", "tuesday": "Mar",
    "mer": "Mer", "mercredi": "Mer", "wed": "Mer", "wednesday": "Mer",
    "jeu": "Jeu", "jeudi": "Jeu", "thu": "Jeu", "thursday": "Jeu",
    "ven": "Ven", "vendredi": "Ven", "fri": "Ven", "friday": "Ven",
    "sam": "Sam", "samedi": "Sam", "sat": "Sam", "saturday": "Sam",
    "dim": "Dim", "dimanche": "Dim", "sun": "Dim", "sunday": "Dim",
}


def normalize_day(s: str) -> str:
    """Normalize day string to canonical format (Lun, Mar, etc.)."""
    key = str(s).strip().lower()
    return DAY_ALIASES.get(key, s.strip())
