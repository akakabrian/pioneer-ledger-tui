"""Modal screens — setup, shop, landmark, river, fort, hunting, end.

Rule from the skill: modal screens MUST NOT use keys claimed by priority
App bindings (SPACE/arrow keys). We use letters + digits for dialog
buttons.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from .game import Game, PendingEvent, PROFESSIONS, MONTHS, PRICES, RATION


class _Box(ModalScreen[None]):
    """Base class — renders a single content widget, waits for a key."""

    BOX_ID = "box"

    def compose(self) -> ComposeResult:
        with Vertical(id=self.BOX_ID):
            yield Static("", id="content")


# --- setup ------------------------------------------------------------------


class SetupScreen(_Box):
    BOX_ID = "setup-box"
    BINDINGS = [
        Binding("1", "pick_profession('banker')",    "banker"),
        Binding("2", "pick_profession('carpenter')", "carpenter"),
        Binding("3", "pick_profession('farmer')",    "farmer"),
        Binding("m", "cycle_month",                  "month"),
        Binding("enter", "next_step",                "next"),
        Binding("escape", "dismiss_screen",          "abort"),
    ]

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self._step = "profession"  # profession → month → shop
        self._month_idx = 1   # April default
        self._names = ["Ben", "Sarah", "Mary", "Tom", "John"]

    def on_mount(self) -> None:
        self._redraw()

    def action_pick_profession(self, name: str) -> None:
        self.game.choose_profession(name)
        self._step = "month"
        self._redraw()

    def action_cycle_month(self) -> None:
        if self._step != "month":
            return
        self._month_idx = (self._month_idx + 1) % len(MONTHS)
        self._redraw()

    def action_next_step(self) -> None:
        if self._step == "profession":
            if self.game.profession is None:
                return
            self._step = "month"
        elif self._step == "month":
            self.game.start_month(MONTHS[self._month_idx])
            self.game.set_party(self._names)
            self._step = "shop"
            # Hand off to the shop screen. Dismiss self with a sentinel so
            # the app knows to push ShopScreen next (not enter trail yet).
            self.dismiss("needs_shop")
            return
        self._redraw()

    def action_dismiss_screen(self) -> None:
        self.dismiss()

    def _redraw(self) -> None:
        c = self.query_one("#content", Static)
        t = Text()
        t.append("THE OREGON TRAIL\n", style="bold #ffbb44")
        t.append("Independence, Missouri — March 1848\n\n", style="dim")

        if self._step == "profession":
            t.append("Choose your profession:\n\n", style="bold")
            for i, (name, (cash, mult, flavor)) in enumerate(PROFESSIONS.items(), 1):
                mark = " *" if self.game.profession == name else "  "
                t.append(f"  [{i}]{mark}{name.title():<10} ${cash:>4}  "
                         f"×{mult}   {flavor}\n")
            t.append("\nPress 1 / 2 / 3 to pick, then ENTER.\n",
                     style="dim")
        elif self._step == "month":
            t.append("Choose starting month:\n\n", style="bold")
            for i, m in enumerate(MONTHS):
                mark = " *" if i == self._month_idx else "  "
                t.append(f"  {mark}{m}\n")
            t.append("\nM to cycle, ENTER to continue.\n", style="dim")
            t.append("(April / May usually arrive before winter.)\n",
                     style="dim")
        c.update(t)


# --- shop -------------------------------------------------------------------


SHOP_ITEMS = [
    # (item, step, label)
    ("oxen",     2, "oxen (pair)"),
    ("food",     50, "food (50 lbs)"),
    ("clothing", 1, "clothing"),
    ("ammo",     20, "ammo (20 bullets)"),
    ("wheel",    1, "spare wheel"),
    ("axle",     1, "spare axle"),
    ("tongue",   1, "spare tongue"),
]


class ShopScreen(_Box):
    BOX_ID = "shop-box"
    BINDINGS = [
        Binding("1", "buy(0)",  "oxen"),
        Binding("2", "buy(1)",  "food"),
        Binding("3", "buy(2)",  "clothing"),
        Binding("4", "buy(3)",  "ammo"),
        Binding("5", "buy(4)",  "wheel"),
        Binding("6", "buy(5)",  "axle"),
        Binding("7", "buy(6)",  "tongue"),
        Binding("enter", "depart", "depart"),
        Binding("escape", "depart", "depart"),
    ]

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game

    def on_mount(self) -> None:
        self._redraw()

    def action_buy(self, idx: int) -> None:
        item, step, _label = SHOP_ITEMS[idx]
        if self.game.buy(item, step):
            self.game.log(f"Bought {step} {item}.")
        else:
            self.game.log(f"Not enough cash for {item}.")
        self._redraw()

    def action_depart(self) -> None:
        # don't let the player leave with zero oxen
        if self.game.supplies.oxen < 2:
            self.game.log("You need at least 2 oxen to pull the wagon.")
            self._redraw()
            return
        self.dismiss()

    def _redraw(self) -> None:
        c = self.query_one("#content", Static)
        t = Text()
        t.append("MATT'S GENERAL STORE — Independence, MO\n", style="bold #ffbb44")
        t.append(f"Cash on hand: ${self.game.supplies.cash:.2f}\n\n")
        s = self.game.supplies
        owned = {
            "oxen": s.oxen, "food": s.food, "clothing": s.clothing,
            "ammo": s.ammo, "wheel": s.wheels, "axle": s.axles,
            "tongue": s.tongues,
        }
        for i, (item, step, label) in enumerate(SHOP_ITEMS, 1):
            cost = self.game.price(item, step)
            have = owned[item]
            t.append(f"  [{i}] {label:<22} ${cost:5.2f}  have {have}\n")
        t.append("\nENTER: hit the trail.   ESC: leave.\n", style="dim")
        t.append(
            "Tip: 4 oxen, 500+ lbs food, 200 bullets, 1 of each spare.\n",
            style="dim",
        )
        c.update(t)


# --- landmark / event -------------------------------------------------------


class LandmarkScreen(_Box):
    BOX_ID = "lm-box"
    BINDINGS = [
        Binding("enter", "ack", "ok", priority=True),
        Binding("space", "ack", "ok", priority=True),
        Binding("escape", "ack", "ok"),
    ]

    def __init__(self, ev: PendingEvent) -> None:
        super().__init__()
        self.ev = ev

    def on_mount(self) -> None:
        c = self.query_one("#content", Static)
        t = Text()
        t.append(self.ev.title + "\n\n", style="bold #ffbb44")
        t.append(self.ev.body + "\n\n")
        t.append("Press ENTER to continue.", style="dim")
        c.update(t)

    def action_ack(self) -> None:
        self.dismiss()


# --- river ------------------------------------------------------------------


class RiverScreen(_Box):
    BOX_ID = "river-box"
    BINDINGS = [
        Binding("1", "choose('ford')",   "ford"),
        Binding("2", "choose('caulk')",  "caulk and float"),
        Binding("3", "choose('ferry')",  "ferry"),
        Binding("4", "choose('wait')",   "wait"),
        Binding("escape", "dismiss_screen", "dismiss"),
    ]

    def __init__(self, game: Game, ev: PendingEvent) -> None:
        super().__init__()
        self.game = game
        self.ev = ev

    def on_mount(self) -> None:
        self._redraw()

    def action_choose(self, choice: str) -> None:
        depth = int(self.ev.data.get("depth", 3))
        msg = self.game.resolve_river(choice, depth)
        self.game.log(msg)
        # `resolve_river` may have set a new pending "wait" event
        if self.game.pending and self.game.pending.kind == "river":
            self.ev = self.game.pending
            self._redraw()
        else:
            self.dismiss()

    def action_dismiss_screen(self) -> None:
        self.dismiss()

    def _redraw(self) -> None:
        c = self.query_one("#content", Static)
        depth = self.ev.data.get("depth", 3)
        width = self.ev.data.get("width", 400)
        t = Text()
        t.append(self.ev.title + "\n\n", style="bold #ffbb44")
        t.append(f"Width: {width} ft   Depth: {depth} ft\n\n")
        t.append("  [1] Ford — drive straight across (safe if shallow)\n")
        t.append("  [2] Caulk and float — seal the wagon; some capsize risk\n")
        t.append("  [3] Ferry — $5, always safe\n")
        t.append("  [4] Wait a day — river may drop\n")
        c.update(t)


# --- fort -------------------------------------------------------------------


FORT_ITEMS = [
    ("food",     100, "food (100 lbs)"),
    ("clothing", 1,   "clothing"),
    ("ammo",     20,  "ammo (20 bullets)"),
    ("wheel",    1,   "wheel"),
    ("axle",     1,   "axle"),
    ("tongue",   1,   "tongue"),
    ("oxen",     1,   "ox"),
]


class FortScreen(_Box):
    BOX_ID = "fort-box"
    BINDINGS = [
        Binding("1", "buy(0)", "food"),
        Binding("2", "buy(1)", "clothing"),
        Binding("3", "buy(2)", "ammo"),
        Binding("4", "buy(3)", "wheel"),
        Binding("5", "buy(4)", "axle"),
        Binding("6", "buy(5)", "tongue"),
        Binding("7", "buy(6)", "oxen"),
        Binding("enter", "depart", "depart"),
        Binding("escape", "depart", "depart"),
    ]

    def __init__(self, game: Game, ev: PendingEvent) -> None:
        super().__init__()
        self.game = game
        self.ev = ev
        self.fort = ev.data.get("landmark", "Fort Kearney")

    def on_mount(self) -> None:
        self._redraw()

    def action_buy(self, idx: int) -> None:
        item, step, _label = FORT_ITEMS[idx]
        if self.game.fort_buy(self.fort, item, step):
            self.game.log(f"Bought {step} {item} at {self.fort}.")
        else:
            self.game.log(f"Couldn't afford {item} at {self.fort}.")
        self._redraw()

    def action_depart(self) -> None:
        self.dismiss()

    def _redraw(self) -> None:
        c = self.query_one("#content", Static)
        prices = self.game.fort_prices(self.fort)
        t = Text()
        t.append(f"{self.fort}\n", style="bold #ffbb44")
        t.append(f"Cash: ${self.game.supplies.cash:.2f}\n\n")
        for i, (item, step, label) in enumerate(FORT_ITEMS, 1):
            unit = prices.get(item, 0.0)
            cost = unit * step
            t.append(f"  [{i}] {label:<22} ${cost:6.2f}\n")
        t.append("\nENTER: leave the fort.\n", style="dim")
        c.update(t)


# --- hunting ----------------------------------------------------------------

# small pool; weights: rabbit is common, buffalo rare. Words chosen to be
# typeable on a standard keyboard — no tricky characters.
HUNT_POOL = [
    ("rabbit",   "rabbit",   0.40),
    ("deer",     "deer",     0.30),
    ("squirrel", "squirrel", 0.15),
    ("buffalo",  "buffalo",  0.10),
    ("bear",     "bear",     0.05),
]


class HuntScreen(_Box):
    BOX_ID = "hunt-box"
    BINDINGS = [
        Binding("enter", "submit", "shoot", priority=True),
        Binding("escape", "leave", "leave"),
    ]

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.target_idx = 0
        self.targets: list[tuple[str, str]] = []  # (word, animal)
        self.hits: list[str] = []
        self.typed = ""
        self._make_targets()

    def _make_targets(self) -> None:
        words = [a for a, _, _ in HUNT_POOL]
        weights = [w for _, _, w in HUNT_POOL]
        for _ in range(3):
            name = self.game.rng.choices(words, weights=weights)[0]
            self.targets.append((name, name))

    def on_mount(self) -> None:
        self._redraw()

    def on_key(self, event) -> None:
        if event.key == "enter":
            return
        if event.key == "escape":
            return
        if event.key == "backspace":
            self.typed = self.typed[:-1]
        elif len(event.key) == 1 and event.key.isalpha():
            self.typed += event.key
        self._redraw()

    def action_submit(self) -> None:
        if self.target_idx >= len(self.targets):
            return
        word, animal = self.targets[self.target_idx]
        self.game.supplies.ammo = max(0, self.game.supplies.ammo - 3)
        if self.typed.strip().lower() == word:
            self.hits.append(animal)
            self.game.log(f"You bagged a {animal}.")
        else:
            self.game.log(f"You missed the {animal}. (typed {self.typed!r})")
        self.target_idx += 1
        self.typed = ""
        if self.target_idx >= len(self.targets) or self.game.supplies.ammo < 3:
            msg = self.game.resolve_hunt(len(self.hits), self.hits)
            self.game.log(msg)
            self.dismiss()
            return
        self._redraw()

    def action_leave(self) -> None:
        if self.hits:
            msg = self.game.resolve_hunt(len(self.hits), self.hits)
            self.game.log(msg)
        self.dismiss()

    def _redraw(self) -> None:
        c = self.query_one("#content", Static)
        t = Text()
        t.append("HUNTING\n", style="bold #ffbb44")
        t.append(f"Ammo: {self.game.supplies.ammo}   Bagged: {len(self.hits)}\n\n")
        if self.target_idx < len(self.targets):
            word, _animal = self.targets[self.target_idx]
            t.append(f"An animal appears.  Type: ", style="white")
            t.append(f"{word.upper()}\n", style="bold #ffbb44")
            t.append(f"\nYour shot: {self.typed}_\n\n")
            t.append("ENTER = fire   ESC = leave the woods\n", style="dim")
        else:
            t.append("Hunt complete.\n")
        c.update(t)


# --- end --------------------------------------------------------------------


class EndScreen(_Box):
    BOX_ID = "end-box"
    BINDINGS = [
        Binding("enter", "ok", "ok", priority=True),
        Binding("space", "ok", "ok", priority=True),
        Binding("q",     "ok", "ok"),
    ]

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game

    def on_mount(self) -> None:
        c = self.query_one("#content", Static)
        t = Text()
        if self.game.victory:
            t.append("THE WILLAMETTE VALLEY\n\n", style="bold green")
            t.append("Green, wet, and waiting. You have reached Oregon.\n\n")
        else:
            t.append("THE END OF THE TRAIL\n\n", style="bold red")
            t.append("Your party did not make it.\n\n")
        alive = self.game.alive()
        t.append(f"Survivors: {alive}/5\n")
        t.append(f"Days on trail: {self.game.days_on_trail}\n")
        t.append(f"Miles traveled: {self.game.miles_traveled}\n")
        t.append(f"Profession multiplier: ×{PROFESSIONS[self.game.profession][1]}\n")
        t.append(f"Supply value: ${self.game.supplies.value():.2f}\n")
        t.append(f"Final score: {self.game.final_score}\n\n", style="bold")
        t.append("Press ENTER to exit.\n", style="dim")
        c.update(t)

    def action_ok(self) -> None:
        self.dismiss()
