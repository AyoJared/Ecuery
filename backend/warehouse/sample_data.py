"""Synthetic daily history for the demo (Snowflake side).

Same metrics and cities as Tiger (tiger/sample_data.py) so the two join cleanly,
at daily grain going back years. Includes seasons, long-term trends and two
events modeled on real ones so Gemini has something to find:
  - June 2023 Canadian wildfire smoke (PM2.5 spike, worst in New York)
  - Spring 2020 lockdown (NO2 drop)
Rows are tagged source="demo-history"; the ETL workers will load real
EPA/NOAA/OpenAQ history alongside and this can be deleted.
"""

import math
import random
from datetime import date, timedelta
from typing import Iterator

from tiger.sample_data import LOCATIONS, METRICS

SOURCE = "demo-history"
HISTORY_START = date(2019, 1, 1)

# Pollutants: relative seasonal swing, peak day-of-year, trend per year, day-to-day noise
RELATIVE = {
    "pm25": (0.15, 15, -0.02, 0.18),
    "o3": (0.30, 190, 0.0, 0.12),
    "no2": (0.20, 15, -0.015, 0.15),
}
# Absolute: seasonal swing, peak day-of-year, trend per year, noise, (min, max) offset from avg
ABSOLUTE = {
    "co2": (3.0, 120, 2.4, 2.0, 10.0),
    "temperature": (11.0, 200, 0.03, 2.5, 6.0),
    "humidity": (8.0, 200, 0.0, 6.0, 12.0),
}
SMOKE_2023 = {"new_york": 110, "philadelphia": 90, "baltimore": 70, "pittsburgh": 45}
SMOKE_PEAK = date(2023, 6, 7)
LOCKDOWN = (date(2020, 3, 20), date(2020, 5, 31))


def _season(d: date, amplitude: float, peak_doy: int) -> float:
    return amplitude * math.cos(2 * math.pi * (d.timetuple().tm_yday - peak_doy) / 365.25)


def generate_history(start: date, end: date) -> Iterator[tuple]:
    """Yield (day, location, metric, unit, avg, min, max, samples, source) for start <= day < end."""
    rng = random.Random(7)
    today = date.today()
    d = start
    while d < end:
        years_ago = (today - d).days / 365.25
        for location, city in LOCATIONS.items():
            for metric, (unit, base, _swing, _noise, _peak, scaled) in METRICS.items():
                level = base * (city if scaled else 1.0)
                if metric in RELATIVE:
                    amp, peak, trend, noise = RELATIVE[metric]
                    avg = level * (1 + _season(d, amp, peak)) * (1 - trend) ** years_ago
                    avg *= 1 + rng.gauss(0, noise)
                    if metric == "pm25":
                        days_from_smoke = (d - SMOKE_PEAK).days
                        avg += SMOKE_2023[location] * math.exp(-((days_from_smoke / 1.2) ** 2))
                    if metric == "no2" and LOCKDOWN[0] <= d <= LOCKDOWN[1]:
                        avg *= 0.7
                    avg = max(avg, 0.5)
                    lo, hi = avg * rng.uniform(0.55, 0.75), avg * rng.uniform(1.3, 1.7)
                else:
                    amp, peak, trend, noise, spread = ABSOLUTE[metric]
                    center = 15.0 if metric == "temperature" else level
                    avg = center + _season(d, amp, peak) - trend * years_ago + rng.gauss(0, noise)
                    if metric == "humidity":
                        avg = min(max(avg, 20), 98)
                    lo, hi = avg - spread * rng.uniform(0.7, 1.0), avg + spread * rng.uniform(0.7, 1.0)
                    if metric == "humidity":
                        lo, hi = max(lo, 10), min(hi, 100)
                yield d, location, metric, unit, round(avg, 2), round(lo, 2), round(hi, 2), 96, SOURCE
        d += timedelta(days=1)
