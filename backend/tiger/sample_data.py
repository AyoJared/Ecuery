"""Synthetic sensor readings for the demo.

Used to seed a real Tiger service (setup_db) and to back the mock repo when
no database is configured. The Python ETL workers will replace this with real
EPA/NOAA/OpenAQ data; rows are tagged source="demo-sensor" so they're easy to
tell apart (and delete) later.
"""

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Iterator

SOURCE = "demo-sensor"
STEP = timedelta(minutes=15)

# metric: (unit, baseline, daily swing, noise, peak hour UTC, scaled by city?)
METRICS: dict[str, tuple[str, float, float, float, int, bool]] = {
    "pm25": ("µg/m³", 9.0, 4.0, 1.5, 12, True),
    "o3": ("ppb", 32.0, 14.0, 3.0, 19, True),
    "no2": ("ppb", 18.0, 8.0, 2.5, 12, True),
    "co2": ("ppm", 420.0, 12.0, 4.0, 11, True),
    "temperature": ("°C", 21.0, 6.0, 0.8, 19, False),
    "humidity": ("%", 60.0, 15.0, 3.0, 9, False),
}

# location: pollution multiplier
LOCATIONS: dict[str, float] = {
    "philadelphia": 1.15,
    "new_york": 1.25,
    "pittsburgh": 1.05,
    "baltimore": 1.0,
}


def floor_to_step(t: datetime) -> datetime:
    t = t.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return t - timedelta(minutes=t.minute % 15)


def generate(start: datetime, end: datetime) -> Iterator[tuple[datetime, str, str, float, str, str]]:
    """Yield (time, location, metric, value, unit, source) every 15 minutes."""
    rng = random.Random(42)
    smoke_peak = floor_to_step(end) - timedelta(days=3)  # a short smoke event 3 days ago
    t = floor_to_step(start)
    while t < end:
        hour = t.hour + t.minute / 60
        for location, city in LOCATIONS.items():
            for metric, (unit, base, swing, noise, peak, scaled) in METRICS.items():
                value = base * (city if scaled else 1.0)
                value += swing * math.cos(2 * math.pi * (hour - peak) / 24)
                value += rng.gauss(0, noise)
                if metric == "pm25" and location == "philadelphia":
                    hours_from_peak = abs((t - smoke_peak).total_seconds()) / 3600
                    value += 25 * math.exp(-((hours_from_peak / 6) ** 2))
                yield t, location, metric, round(max(value, 0.0), 2), unit, SOURCE
        t += STEP
