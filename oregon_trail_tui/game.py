"""Core game engine — deterministic, UI-free.

The `Game` class owns all state: party, supplies, date, weather, miles,
RNG, event log. It exposes pure methods the Textual UI (and tests)
drive. No timers — this is a turn-based simulation. The hunting
mini-game timer lives in the UI layer.

Design goals (see DECISIONS.md):

- No vendored code; clean-room mechanics.
- Seedable RNG via `random.Random(seed)`.
- Every player-visible message routes through `Game.log(...)`.
- `Game.advance_day(pace, ration)` is the daily tick — everything the
  daily trail loop needs happens inside it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from .landmarks import LANDMARKS, Landmark, TOTAL_MILES, next_landmark_after

# --- constants --------------------------------------------------------------

PROFESSIONS: dict[str, tuple[int, int, str]] = {
    # name → (starting cash, score multiplier, flavor)
    "banker":    (1600, 1, "a Boston banker — the soft hands show"),
    "carpenter": (800,  2, "a Springfield carpenter — a sturdy wagon builds itself"),
    "farmer":    (400,  3, "an Illinois farmer — you have done harder things"),
}

MONTHS = ["March", "April", "May", "June", "July"]

# shop prices at Matt's General Store (Independence, 1848)
PRICES: dict[str, tuple[int, str]] = {
    "oxen":     (40,   "pair of oxen"),       # ~ two animals per pair
    "food":     (1,    "100 lbs of food"),    # $1 per 100 lbs at wholesale (abstracted)
    "clothing": (10,   "set of clothing"),
    "ammo":     (2,    "box of 20 bullets"),
    "wheel":    (10,   "spare wagon wheel"),
    "axle":     (10,   "spare wagon axle"),
    "tongue":   (10,   "spare wagon tongue"),
}

PACE = {
    # pace name → miles/day, daily health cost (0..5)
    "steady":    (15, 0),
    "strenuous": (20, 1),
    "grueling":  (25, 3),
}

RATION = {
    # name → lbs/person/day, daily health effect (+1 recover / 0 / -2)
    "filling":   (3, 1),
    "meager":    (2, 0),
    "bare":      (1, -2),
}

WEATHERS = ["warm", "cool", "cold", "rainy", "very hot", "snowy"]

DISEASES = [
    "dysentery", "cholera", "typhoid", "measles",
    "exhaustion", "snake_bite", "broken_leg",
]

# Disease severity — daily HP damage when untreated.
DISEASE_DMG: dict[str, int] = {
    "dysentery":   3,
    "cholera":     5,
    "typhoid":     4,
    "measles":     2,
    "exhaustion":  1,
    "snake_bite":  3,
    "broken_leg":  1,
}


# --- data classes -----------------------------------------------------------


@dataclass(eq=False)
class Traveler:
    """A single pioneer. `eq=False` so list.remove() / list.index() use
    identity (see the skill's @dataclass(eq=False) gotcha)."""
    name: str
    health: int = 100
    alive: bool = True
    disease: str | None = None
    is_leader: bool = False


@dataclass
class Supplies:
    food: int = 0           # lbs
    oxen: int = 0           # individual animals (a yoke = 2)
    clothing: int = 0
    ammo: int = 0           # bullets
    wheels: int = 0
    axles: int = 0
    tongues: int = 0
    cash: float = 0.0

    def value(self) -> float:
        """Rough $-value of remaining supplies, for the final score."""
        return (
            self.cash
            + self.food * 0.5
            + self.oxen * 20
            + self.clothing * 10
            + self.ammo * 0.10
            + (self.wheels + self.axles + self.tongues) * 10
        )


@dataclass
class PendingEvent:
    """Something the UI needs to display / act on before the next day."""
    kind: str                 # "landmark" | "river" | "fort" | "event" | "choice" | "end"
    title: str
    body: str
    data: dict = field(default_factory=dict)


# --- main engine ------------------------------------------------------------


class Game:
    """Oregon Trail game state + turn logic.

    Usage:
        g = Game(seed=42)
        g.choose_profession("farmer")
        g.start_month("April")
        g.set_party(["Ben", "Sarah", "Mary", "Tom", "John"])
        g.apply_shop({"oxen": 4, "food": 800, "ammo": 100, ...})
        g.start_trail()
        while not g.over:
            ev = g.advance_day("steady", "meager")
            # UI handles ev (landmark / river / event) via respond_*() calls
    """

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self.profession: str | None = None
        self.party: list[Traveler] = []
        self.supplies = Supplies()

        self.miles_traveled = 0
        self.date = date(1848, 3, 1)  # overwritten by start_month()
        self.weather = "cool"
        self.pace = "steady"
        self.ration = "filling"

        self.messages: list[str] = []
        self.over = False
        self.victory = False
        self.final_score = 0

        # Track which landmarks we've already fired so we don't re-fire
        # as miles accumulate.
        self._visited_landmarks: set[str] = set()
        self.current_landmark: Landmark = LANDMARKS[0]

        # Pending event from the latest advance_day() call — UI inspects
        # this to decide what to show before advancing again.
        self.pending: PendingEvent | None = None

        # Stats
        self.days_on_trail = 0
        self.miles_log: list[int] = [0]  # one entry per day for a chart

    # ----- setup ---------------------------------------------------------

    def choose_profession(self, name: str) -> None:
        if name not in PROFESSIONS:
            raise ValueError(f"unknown profession {name!r}")
        self.profession = name
        cash, _mult, _flavor = PROFESSIONS[name]
        self.supplies.cash = float(cash)

    def start_month(self, month: str) -> None:
        if month not in MONTHS:
            raise ValueError(f"unknown start month {month!r}")
        m_idx = MONTHS.index(month) + 3  # March → 3
        self.date = date(1848, m_idx, 1)

    def set_party(self, names: list[str]) -> None:
        if len(names) != 5:
            raise ValueError("Oregon Trail party must be exactly 5 pioneers")
        self.party = [
            Traveler(name=n, is_leader=(i == 0))
            for i, n in enumerate(names)
        ]

    # ----- shop (stage 2) -------------------------------------------------

    def price(self, item: str, qty: int = 1) -> float:
        unit, _label = PRICES[item]
        if item == "food":
            # $0.20/lb — close to 1848 prices ($4-5 for 25lb sack of flour)
            return qty * 0.20
        if item == "oxen":
            # $40 per yoke (2), user buys individual animals here
            return qty * 20.0
        if item == "ammo":
            # $0.10 per round (the "box of 20" is just UI bundling)
            return qty * 0.10
        return qty * unit

    def can_afford(self, item: str, qty: int) -> bool:
        return self.supplies.cash >= self.price(item, qty) - 1e-9

    def buy(self, item: str, qty: int) -> bool:
        """Purchase `qty` of `item`. Returns False if unaffordable."""
        cost = self.price(item, qty)
        if cost > self.supplies.cash + 1e-9:
            return False
        self.supplies.cash -= cost
        match item:
            case "oxen":     self.supplies.oxen += qty
            case "food":     self.supplies.food += qty
            case "clothing": self.supplies.clothing += qty
            case "ammo":     self.supplies.ammo += qty  # box already expanded by UI
            case "wheel":    self.supplies.wheels += qty
            case "axle":     self.supplies.axles += qty
            case "tongue":   self.supplies.tongues += qty
            case _:          raise ValueError(item)
        return True

    def apply_shop(self, order: dict[str, int]) -> bool:
        """Shortcut used by tests: buy several items atomically."""
        total = sum(self.price(k, v) for k, v in order.items())
        if total > self.supplies.cash + 1e-9:
            return False
        for k, v in order.items():
            if v:
                self.buy(k, v)
        return True

    # ----- trail ---------------------------------------------------------

    def start_trail(self) -> None:
        self.log("Independence, Missouri. The wagons are loaded. Godspeed.")
        self._visited_landmarks.add("Independence, Missouri")

    def survivors(self) -> list[Traveler]:
        return [t for t in self.party if t.alive]

    def leader(self) -> Traveler | None:
        for t in self.party:
            if t.is_leader:
                return t
        return None

    def alive(self) -> int:
        return sum(1 for t in self.party if t.alive)

    # --- daily tick ------------------------------------------------------

    def advance_day(self, pace: str, ration: str) -> PendingEvent | None:
        """One trail day. Returns a PendingEvent the UI must acknowledge."""
        if self.over:
            return None
        self.pace = pace
        self.ration = ration
        self.days_on_trail += 1
        self.date += timedelta(days=1)

        # 1) weather drift
        self._roll_weather()

        # 2) mileage
        miles = self._daily_miles()
        prev = self.miles_traveled
        self.miles_traveled = min(TOTAL_MILES, self.miles_traveled + miles)
        self.miles_log.append(self.miles_traveled)

        # 3) food consumption
        self._consume_food()

        # 4) health update from pace / ration / weather / disease
        self._health_tick()

        # 5) landmark crossed?
        crossed = self._landmark_between(prev, self.miles_traveled)
        if crossed is not None:
            self._visited_landmarks.add(crossed.name)
            self.current_landmark = crossed
            self.pending = self._landmark_event(crossed)
            return self.pending

        # 6) end of trail?
        if self.miles_traveled >= TOTAL_MILES:
            return self._trigger_end(victory=True)

        # 7) party wipe?
        if self.alive() == 0:
            return self._trigger_end(victory=False)

        # 8) random event?
        if self.rng.random() < 0.40:
            ev = self._roll_event()
            if ev is not None:
                self.pending = ev
                return ev

        self.pending = None
        return None

    # --- internal mechanics ----------------------------------------------

    def _daily_miles(self) -> int:
        base, _ = PACE[self.pace]
        # oxen: less than 2 = disabled wagon
        if self.supplies.oxen < 2:
            self.log("Your oxen can no longer pull the wagon.")
            return 0
        # thinning team slows you
        if self.supplies.oxen < 4:
            base = int(base * 0.75)
        # weather modifier
        if self.weather == "snowy":
            base = int(base * 0.4)
        elif self.weather == "rainy":
            base = int(base * 0.7)
        elif self.weather == "very hot":
            base = int(base * 0.85)
        # mountain slog
        if 1500 <= self.miles_traveled <= 1700:
            base = int(base * 0.7)
        # small daily jitter ±3
        return max(0, base + self.rng.randint(-3, 3))

    def _consume_food(self) -> None:
        per, _ = RATION[self.ration]
        need = per * self.alive()
        if self.supplies.food >= need:
            self.supplies.food -= need
        else:
            # starvation
            self.supplies.food = 0
            self.log("You do not have enough food. The party is starving.")
            for t in self.survivors():
                t.health -= 8

    def _health_tick(self) -> None:
        _, pace_cost = PACE[self.pace]
        _, ration_boost = RATION[self.ration]
        weather_cost = 2 if self.weather in ("cold", "snowy") and self.supplies.clothing < 3 else 0
        weather_cost += 1 if self.weather == "very hot" else 0

        for t in self.survivors():
            delta = -pace_cost - weather_cost + ration_boost
            if t.disease is not None:
                delta -= DISEASE_DMG[t.disease]
                # small daily chance the illness resolves if HP stays high
                if self.rng.random() < 0.12 and t.health > 35:
                    self.log(f"{t.name} recovered from {t.disease}.")
                    t.disease = None
            t.health = max(0, min(100, t.health + delta))
            if t.health <= 0:
                self._kill(t)

    def _kill(self, t: Traveler) -> None:
        if not t.alive:
            return
        t.alive = False
        cause = t.disease or "exhaustion"
        # preserve the cultural signature verbatim — the ONLY hard-coded
        # line from the MECC original (public-domain quotation scale).
        if cause == "dysentery":
            self.log(f"{t.name} has died of dysentery.")
        else:
            self.log(f"{t.name} has died of {cause}.")

    def _roll_weather(self) -> None:
        # month-biased weather table
        month = self.date.month
        if month in (12, 1, 2, 3):
            choices = ["snowy", "cold", "cold", "rainy"]
        elif month in (4, 5):
            choices = ["cool", "cool", "warm", "rainy"]
        elif month in (6, 7, 8):
            choices = ["warm", "very hot", "warm", "rainy"]
        elif month in (9, 10):
            choices = ["cool", "rainy", "cold", "warm"]
        else:
            choices = ["cold", "snowy", "rainy", "cold"]
        # mountain biome biases cold
        if 1500 <= self.miles_traveled <= 1700 and self.rng.random() < 0.6:
            self.weather = self.rng.choice(["cold", "snowy", "rainy"])
        else:
            self.weather = self.rng.choice(choices)

    # --- landmarks -------------------------------------------------------

    def _landmark_between(self, prev: int, now: int) -> Landmark | None:
        for lm in LANDMARKS:
            if lm.mile <= prev:
                continue
            if lm.mile > now:
                break
            if lm.name in self._visited_landmarks:
                continue
            return lm
        return None

    def _landmark_event(self, lm: Landmark) -> PendingEvent:
        if lm.kind == "river":
            depth = self.rng.randint(2, 10)
            width = self.rng.randint(100, 900)
            return PendingEvent(
                kind="river",
                title=f"You have reached {lm.name}.",
                body=(f"The river here is about {width} feet wide and {depth} "
                      f"feet deep. What will you do?"),
                data={"depth": depth, "width": width, "landmark": lm.name},
            )
        if lm.kind == "fort":
            return PendingEvent(
                kind="fort",
                title=f"You have reached {lm.name}.",
                body=lm.blurb + " You may trade here.",
                data={"landmark": lm.name},
            )
        if lm.kind == "choice":
            return PendingEvent(
                kind="choice",
                title=f"You have reached {lm.name}.",
                body=lm.blurb,
                data={"landmark": lm.name,
                      "options": ["Float the Columbia (fast, risky)",
                                  "Take the Barlow Toll Road ($5, slow, safe)"]},
            )
        if lm.kind == "end":
            return self._trigger_end(victory=True)
        return PendingEvent(
            kind="landmark",
            title=f"You have reached {lm.name}.",
            body=lm.blurb,
            data={"landmark": lm.name},
        )

    # --- random events ---------------------------------------------------

    def _roll_event(self) -> PendingEvent | None:
        roll = self.rng.random()
        # picks distributed to roughly match the original MECC feel;
        # numbers tweaked for a ~2040-mile game.
        if roll < 0.12:  # illness
            return self._event_illness()
        if roll < 0.22:  # wagon breakdown
            return self._event_breakdown()
        if roll < 0.30:  # bandits / theft
            return self._event_theft()
        if roll < 0.37:  # ox injury or death
            return self._event_ox()
        if roll < 0.45:  # lose trail / heavy fog
            return self._event_lost()
        if roll < 0.55:  # wild fruit / found supplies
            return self._event_fortune()
        if roll < 0.65:  # stranger
            return self._event_stranger()
        if roll < 0.75:  # snake bite / broken limb
            return self._event_injury()
        if roll < 0.85:  # bad water / hailstorm
            return self._event_hazard()
        if roll < 0.95:  # buffalo / deer sighting — hunting bonus notice
            return PendingEvent(
                kind="event",
                title="Wildlife spotted.",
                body="A herd of buffalo crosses the trail. Hunting here would go well.",
                data={"hunt_bonus": True},
            )
        return None

    def _pick_alive(self) -> Traveler | None:
        alive = self.survivors()
        if not alive:
            return None
        return self.rng.choice(alive)

    def _event_illness(self) -> PendingEvent:
        t = self._pick_alive()
        if t is None:
            return PendingEvent("event", "", "", {})
        disease = self.rng.choices(
            ["dysentery", "cholera", "typhoid", "measles", "exhaustion"],
            weights=[5, 3, 3, 3, 4],
        )[0]
        if t.disease is None:
            t.disease = disease
            self.log(f"{t.name} has come down with {disease}.")
        return PendingEvent(
            kind="event",
            title="Illness.",
            body=f"{t.name} has come down with {disease}.",
            data={"who": t.name, "disease": disease},
        )

    def _event_breakdown(self) -> PendingEvent:
        part = self.rng.choice(["wheel", "axle", "tongue"])
        have = {"wheel": self.supplies.wheels,
                "axle": self.supplies.axles,
                "tongue": self.supplies.tongues}[part]
        if have > 0:
            # fix it
            match part:
                case "wheel":  self.supplies.wheels -= 1
                case "axle":   self.supplies.axles -= 1
                case "tongue": self.supplies.tongues -= 1
            body = (f"A wagon {part} broke. Luckily you had a spare. "
                    "You repaired it and went on.")
        else:
            # lose a day
            self.date += timedelta(days=2)
            body = (f"A wagon {part} broke and you had no spare. "
                    "You spent 2 days whittling a replacement.")
        return PendingEvent("event", "Wagon breakdown.", body,
                            {"part": part, "had_spare": have > 0})

    def _event_theft(self) -> PendingEvent:
        kind = self.rng.choice(["food", "ammo", "clothing"])
        if kind == "food":
            amt = min(self.supplies.food, self.rng.randint(30, 120))
            self.supplies.food -= amt
            body = f"Thieves came in the night and stole {amt} lbs of food."
        elif kind == "ammo":
            amt = min(self.supplies.ammo, self.rng.randint(10, 40))
            self.supplies.ammo -= amt
            body = f"Thieves came in the night and stole {amt} bullets."
        else:
            amt = min(self.supplies.clothing, self.rng.randint(1, 3))
            self.supplies.clothing -= amt
            body = f"Thieves came in the night and stole {amt} sets of clothing."
        return PendingEvent("event", "Theft.", body, {"kind": kind})

    def _event_ox(self) -> PendingEvent:
        if self.supplies.oxen <= 0:
            return PendingEvent("event", "", "", {})
        if self.rng.random() < 0.4:
            self.supplies.oxen -= 1
            body = "An ox has died. The team is weaker now."
            kind = "death"
        else:
            body = "An ox is lame. You lose half a day tending to it."
            self.date += timedelta(days=1)
            kind = "injury"
        return PendingEvent("event", "Ox trouble.", body, {"kind": kind})

    def _event_lost(self) -> PendingEvent:
        days = self.rng.randint(1, 3)
        self.date += timedelta(days=days)
        # set miles back slightly too
        self.miles_traveled = max(0, self.miles_traveled - days * 4)
        return PendingEvent(
            kind="event",
            title="Lost your way.",
            body=f"You wandered off the trail and lost {days} days finding it again.",
            data={"days": days},
        )

    def _event_fortune(self) -> PendingEvent:
        if self.rng.random() < 0.5:
            amt = self.rng.randint(30, 120)
            self.supplies.food += amt
            return PendingEvent("event", "Wild fruit.",
                                f"You found a stand of berries. +{amt} lbs of food.",
                                {"food": amt})
        amt = self.rng.randint(20, 80)
        self.supplies.food += amt
        return PendingEvent("event", "Abandoned wagon.",
                            f"You found an abandoned wagon. +{amt} lbs of food.",
                            {"food": amt})

    def _event_stranger(self) -> PendingEvent:
        r = self.rng.random()
        if r < 0.4:
            amt = self.rng.randint(10, 30)
            self.supplies.ammo += amt
            body = f"A trapper shares {amt} bullets with you."
        elif r < 0.7:
            t = self._pick_alive()
            if t is not None and t.disease is not None:
                body = f"A missionary prays over {t.name}. They recover from {t.disease}."
                t.disease = None
            else:
                body = "A missionary blesses the wagon and rides on."
        else:
            # warn about the trail ahead
            body = "A passing guide tells you the next stretch is hard. Take care."
        return PendingEvent("event", "Friendly stranger.", body, {})

    def _event_injury(self) -> PendingEvent:
        t = self._pick_alive()
        if t is None:
            return PendingEvent("event", "", "", {})
        choice = self.rng.choice(["snake_bite", "broken_leg"])
        if t.disease is None:
            t.disease = choice
        readable = choice.replace("_", " ")
        return PendingEvent(
            kind="event",
            title="Injury.",
            body=f"{t.name} has suffered a {readable}.",
            data={"who": t.name, "injury": choice},
        )

    def _event_hazard(self) -> PendingEvent:
        if self.rng.random() < 0.5:
            t = self._pick_alive()
            if t and t.disease is None and self.rng.random() < 0.5:
                t.disease = "dysentery"
                body = f"Bad water at camp. {t.name} has come down with dysentery."
            else:
                body = "Bad water at camp. Everyone felt ill but recovered."
        else:
            lost = min(self.supplies.food, self.rng.randint(10, 40))
            self.supplies.food -= lost
            body = f"A hailstorm scatters supplies. You lose {lost} lbs of food."
        return PendingEvent("event", "Hazard.", body, {})

    # --- river crossings -------------------------------------------------

    def resolve_river(self, choice: str, depth: int) -> str:
        """Apply a river-crossing choice. Returns a log-ready message."""
        assert choice in ("ford", "caulk", "ferry", "wait")
        if choice == "wait":
            self.date += timedelta(days=1)
            new_depth = max(1, depth - self.rng.randint(1, 3))
            self.pending = PendingEvent(
                kind="river",
                title="You waited a day.",
                body=f"The river is now {new_depth} ft deep. What next?",
                data={"depth": new_depth,
                      "width": (self.pending.data.get("width", 400) if self.pending else 400),
                      "landmark": self.pending.data.get("landmark") if self.pending else None},
            )
            return f"You wait. Waters recede to {new_depth} ft."

        if choice == "ferry":
            if self.supplies.cash >= 5:
                self.supplies.cash -= 5
                self.pending = None
                return "You took the ferry across. ($5)"
            return "You do not have $5 for the ferry."

        risk = 0.0
        if choice == "ford":
            risk = 0.05 if depth <= 2 else 0.25 if depth <= 4 else 0.75
        else:  # caulk
            risk = 0.10 if depth <= 5 else 0.25

        if self.rng.random() < risk:
            # mishap
            lost_food = min(self.supplies.food, self.rng.randint(50, 300))
            lost_oxen = 1 if self.rng.random() < 0.3 and self.supplies.oxen > 2 else 0
            self.supplies.food -= lost_food
            self.supplies.oxen -= lost_oxen
            # hurt random traveler
            t = self._pick_alive()
            if t is not None:
                t.health = max(0, t.health - 20)
                if t.health == 0:
                    self._kill(t)
            self.pending = None
            return (f"Disaster! The wagon tipped. Lost {lost_food} lbs of food" +
                    (f" and {lost_oxen} ox" if lost_oxen else "") + ".")
        self.pending = None
        verb = "forded" if choice == "ford" else "caulked and floated"
        return f"You {verb} the river safely."

    # --- fort trading ----------------------------------------------------

    def fort_prices(self, fort_name: str) -> dict[str, float]:
        """Prices at a fort — cheaper the farther from Independence."""
        # Find fort in LANDMARKS
        distance = next((lm.mile for lm in LANDMARKS if lm.name == fort_name), 0)
        # 1.0 at start → 0.7 at 2000 miles
        scale = max(0.7, 1.0 - (distance / 2000) * 0.3)
        return {
            "food":     round(0.02 * scale, 3),   # $/lb (retail vs wholesale $0.01)
            "clothing": round(15 * scale, 2),
            "ammo":     round(3 * scale, 2),
            "wheel":    round(15 * scale, 2),
            "axle":     round(15 * scale, 2),
            "tongue":   round(15 * scale, 2),
            "oxen":     round(45 * scale, 2),     # per animal
        }

    def fort_buy(self, fort_name: str, item: str, qty: int) -> bool:
        # Only allow trading at actual forts on the trail.
        if not any(lm.name == fort_name and lm.kind == "fort" for lm in LANDMARKS):
            return False
        prices = self.fort_prices(fort_name)
        if item not in prices:
            return False
        cost = prices[item] * qty
        if cost > self.supplies.cash + 1e-9:
            return False
        self.supplies.cash -= cost
        match item:
            case "oxen":     self.supplies.oxen += qty
            case "food":     self.supplies.food += qty
            case "clothing": self.supplies.clothing += qty
            case "ammo":     self.supplies.ammo += qty
            case "wheel":    self.supplies.wheels += qty
            case "axle":     self.supplies.axles += qty
            case "tongue":   self.supplies.tongues += qty
        return True

    # --- hunting ---------------------------------------------------------

    def resolve_hunt(self, hits: int, animals: list[str]) -> str:
        """Convert a list of animal names the player bagged → food lbs."""
        table = {"rabbit": 5, "deer": 40, "buffalo": 100, "bear": 80, "squirrel": 2}
        total = 0
        for a in animals:
            total += table.get(a, 10)
        # player can only haul so much at once
        total = min(total, 200)
        self.supplies.food += total
        # ammo cost: ~3 rounds per attempted animal (hits+misses logged in UI)
        return f"You brought {total} lbs of meat back to the wagon."

    # --- end -------------------------------------------------------------

    def _trigger_end(self, victory: bool) -> PendingEvent:
        self.over = True
        self.victory = victory
        mult = PROFESSIONS[self.profession][1] if self.profession else 1
        alive = self.alive()
        supplies_value = self.supplies.value()
        self.final_score = int(alive * mult * supplies_value) if victory else 0
        if victory:
            body = (f"You made it to Oregon! {alive} of 5 survived. "
                    f"Final score: {self.final_score}.")
            title = "Willamette Valley."
        else:
            body = "The entire party has perished on the trail."
            title = "The trail ends here."
        self.pending = PendingEvent("end", title, body, {"score": self.final_score})
        return self.pending

    # --- logging ---------------------------------------------------------

    def log(self, msg: str) -> None:
        self.messages.append(msg)

    # --- snapshot for UI / agent ----------------------------------------

    def snapshot(self) -> dict:
        return {
            "profession": self.profession,
            "date": self.date.isoformat(),
            "miles": self.miles_traveled,
            "total_miles": TOTAL_MILES,
            "weather": self.weather,
            "pace": self.pace,
            "ration": self.ration,
            "supplies": {
                "food": self.supplies.food,
                "oxen": self.supplies.oxen,
                "clothing": self.supplies.clothing,
                "ammo": self.supplies.ammo,
                "wheels": self.supplies.wheels,
                "axles": self.supplies.axles,
                "tongues": self.supplies.tongues,
                "cash": round(self.supplies.cash, 2),
            },
            "party": [
                {"name": t.name, "health": t.health, "alive": t.alive,
                 "disease": t.disease, "is_leader": t.is_leader}
                for t in self.party
            ],
            "days": self.days_on_trail,
            "over": self.over,
            "victory": self.victory,
            "score": self.final_score,
            "current_landmark": self.current_landmark.name,
        }
