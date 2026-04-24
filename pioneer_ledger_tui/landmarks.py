"""The 18 landmarks along the 2040-mile Oregon Trail.

Mile positions are historical (1848 trail). Kinds drive the screen the
game shows on arrival:

  start     — starting town, visited implicitly
  river     — must cross; triggers the river-crossing decision screen
  fort      — trade; triggers the fort screen
  landmark  — purely narrative, a flavor pause
  choice    — forks in the road (The Dalles / Barlow)
  end       — victory screen
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Landmark:
    name: str
    mile: int
    kind: str
    blurb: str = ""


LANDMARKS: list[Landmark] = [
    Landmark("Independence, Missouri",    0,    "start",
             "The jumping-off point. Wagon trains roll out every spring."),
    Landmark("Kansas River Crossing",     102,  "river",
             "A wide, muddy river. No bridges this far west."),
    Landmark("Big Blue River Crossing",   185,  "river",
             "Fast current after spring rains."),
    Landmark("Fort Kearney",              304,  "fort",
             "A U.S. Army outpost on the Platte. Last glimpse of the East."),
    Landmark("Chimney Rock",              554,  "landmark",
             "A stone spire visible for two days' ride. Pioneers carve names."),
    Landmark("Fort Laramie",              640,  "fort",
             "A busy trading post run by the American Fur Company."),
    Landmark("Independence Rock",         830,  "landmark",
             "If you reach it by July 4th, you're on schedule."),
    Landmark("South Pass",                932,  "landmark",
             "The Continental Divide. Down from here, all water runs west."),
    Landmark("Green River Crossing",      989,  "river",
             "Deep, green, and cold. Ferrymen take advantage."),
    Landmark("Soda Springs",              1086, "landmark",
             "Natural carbonated springs bubble up through the rocks."),
    Landmark("Fort Hall",                 1151, "fort",
             "A Hudson's Bay Company outpost. Supplies are dear here."),
    Landmark("Snake River Crossing",      1296, "river",
             "Treacherous rapids and lava banks."),
    Landmark("Fort Boise",                1395, "fort",
             "A quiet fort on the Boise River. Last trade before the mountains."),
    Landmark("Blue Mountains",            1534, "landmark",
             "Steep timbered slopes. Wagons must be lowered by rope."),
    Landmark("Fort Walla Walla",          1660, "fort",
             "A Hudson's Bay post. Prices are low; the end is near."),
    Landmark("The Dalles",                1770, "choice",
             "The Columbia Gorge narrows here. Raft downriver, or take the new Barlow Road?"),
    Landmark("Barlow Toll Road",          1930, "landmark",
             "A rough wagon road around Mt. Hood, opened 1846. $5 toll."),
    Landmark("Willamette Valley",         2040, "end",
             "Green, wet, and waiting. You have reached Oregon."),
]


def next_landmark_after(mile: int) -> Landmark | None:
    """Return the next landmark strictly after `mile`, or None if past end."""
    for lm in LANDMARKS:
        if lm.mile > mile:
            return lm
    return None


def landmark_at(mile: int) -> Landmark | None:
    """Return the landmark exactly at `mile`, or None."""
    for lm in LANDMARKS:
        if lm.mile == mile:
            return lm
    return None


TOTAL_MILES = LANDMARKS[-1].mile  # 2040
