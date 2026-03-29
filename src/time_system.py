"""
Game time system. All time tracked in minutes since game start.
Real calendar date derived from start date + elapsed minutes.
"""

import math
from dataclasses import dataclass

# Game start: April 1, 1849, 6:00 AM
START_YEAR  = 1849
START_MONTH = 4
START_DAY   = 1
START_HOUR  = 6
START_MIN   = 0

DAYS_IN_MONTH = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTH_NAMES   = ["", "January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
DAY_NAMES     = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# April 1 1849 was a Sunday (index 6)
START_DOW = 6


@dataclass
class GameTime:
    total_seconds: int = 0  # seconds elapsed since game start

    @property
    def total_minutes(self) -> int:
        """Backward compat — many systems use total_minutes."""
        return self.total_seconds // 60

    @total_minutes.setter
    def total_minutes(self, val: int):
        self.total_seconds = val * 60

    @property
    def hour(self) -> int:
        total_mins = START_HOUR * 60 + START_MIN + self.total_seconds // 60
        return (total_mins % (24 * 60)) // 60

    @property
    def minute(self) -> int:
        total_mins = START_HOUR * 60 + START_MIN + self.total_seconds // 60
        return total_mins % 60

    @property
    def second(self) -> int:
        return self.total_seconds % 60

    @property
    def period(self) -> str:
        h = self.hour
        if 5 <= h < 7:   return "dawn"
        if 7 <= h < 18:  return "day"
        if 18 <= h < 20: return "dusk"
        return "night"

    @property
    def total_days(self) -> int:
        return (START_HOUR * 60 + START_MIN + self.total_seconds // 60) // (24 * 60)

    @property
    def day_of_week(self) -> str:
        return DAY_NAMES[(START_DOW + self.total_days) % 7]

    @property
    def calendar(self):
        """Returns (year, month, day) tuple."""
        days_remaining = self.total_days
        year  = START_YEAR
        month = START_MONTH
        day   = START_DAY

        day += days_remaining
        while True:
            dim = DAYS_IN_MONTH[month]
            if month == 2 and year % 4 == 0:
                dim = 29
            if day <= dim:
                break
            day -= dim
            month += 1
            if month > 12:
                month = 1
                year += 1

        return year, month, day

    @property
    def date_string(self) -> str:
        y, mo, d = self.calendar
        dow = self.day_of_week[:3]
        return f"{dow} {MONTH_NAMES[mo]} {d}, {y}"

    @property
    def time_string(self) -> str:
        h, m, s = self.hour, self.minute, self.second
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d}:{s:02d} {suffix}"

    def advance(self, minutes: int):
        """Advance time by minutes (backward compat)."""
        self.total_seconds += minutes * 60

    def advance_seconds(self, seconds: int):
        """Advance time by seconds (for fine-grained actions like walking)."""
        self.total_seconds += seconds

    @property
    def year(self) -> int:
        return self.calendar[0]

    @property
    def month(self) -> int:
        return self.calendar[1]

    @property
    def day(self) -> int:
        return self.calendar[2]

    @property
    def season(self) -> str:
        """Returns 'spring', 'summer', 'fall', or 'winter'."""
        m = self.month
        if m in (3, 4, 5):   return "spring"
        if m in (6, 7, 8):   return "summer"
        if m in (9, 10, 11): return "fall"
        return "winter"
