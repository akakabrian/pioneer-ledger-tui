"""Textual UI — shell + panels + modal screens.

Layout:

    ┌ Title bar — date, miles, weather ─────────────────────┐
    ├──────────────────────────────┬────────────────────────┤
    │ Trail panel (progress map,   │ Party + supplies panel │
    │  landmarks, status)          │                        │
    ├──────────────────────────────┴────────────────────────┤
    │ Event log (RichLog)                                   │
    ├───────────────────────────────────────────────────────┤
    │ Prompt bar (hotkeys)                                  │
    └───────────────────────────────────────────────────────┘

Modal screens for setup, shop, landmarks, river, fort, hunt, end.
"""
from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, RichLog, Static

from .game import Game, PACE, RATION, PROFESSIONS, MONTHS
from .landmarks import LANDMARKS, TOTAL_MILES
from .screens import (
    EndScreen,
    FortScreen,
    HuntScreen,
    LandmarkScreen,
    RiverScreen,
    SetupScreen,
    ShopScreen,
)


class TitleBar(Static):
    def refresh_bar(self, game: Game) -> None:
        t = Text()
        miles = game.miles_traveled
        pct = int(100 * miles / TOTAL_MILES)
        t.append(" THE OREGON TRAIL  ", style="bold #ffbb44")
        t.append(f" {game.date.strftime('%b %d, %Y')}  ", style="white")
        t.append(f" Mile {miles}/{TOTAL_MILES} ({pct}%)  ", style="bold")
        t.append(f" {game.weather}  ", style="cyan")
        t.append(f" pace:{game.pace}  ration:{game.ration} ", style="dim")
        self.update(t)


class TrailPanel(Static):
    """Main panel — trail progress bar, landmark list, and journey flavor."""

    def refresh_panel(self, game: Game) -> None:
        t = Text()
        t.append("The Trail West\n\n", style="bold #ffbb44")

        # Progress bar: 40 cells mapping 0..TOTAL_MILES
        bar_w = 40
        fill = int(bar_w * game.miles_traveled / TOTAL_MILES)
        t.append("  Independence ")
        t.append("█" * fill, style="bold #ffbb44")
        t.append("░" * (bar_w - fill), style="#5a3d12")
        t.append(" Oregon\n\n")

        # Landmark list; mark passed / current / upcoming
        t.append("  Landmarks:\n", style="bold")
        for lm in LANDMARKS:
            if lm.mile <= game.miles_traveled:
                marker = "✓"
                style = "dim"
            elif lm == self._next_upcoming(game):
                marker = "►"
                style = "bold #ffbb44"
            else:
                marker = " "
                style = ""
            kind_tag = {
                "river":    "[river]",
                "fort":     "[fort]",
                "landmark": "[landmark]",
                "choice":   "[choice]",
                "start":    "[start]",
                "end":      "[end]",
            }.get(lm.kind, "")
            line = f"  {marker} {lm.mile:>5} mi  {lm.name:<26} {kind_tag}\n"
            t.append(line, style=style)

        self.update(t)

    @staticmethod
    def _next_upcoming(game: Game):
        for lm in LANDMARKS:
            if lm.mile > game.miles_traveled:
                return lm
        return None


class PartyPanel(Static):
    def refresh_panel(self, game: Game) -> None:
        t = Text()
        t.append("Party\n", style="bold underline")
        for tr in game.party:
            if not tr.alive:
                t.append(f"  ☠ {tr.name:<14} DEAD\n", style="dim red")
                continue
            hp_color = "green" if tr.health > 70 else "yellow" if tr.health > 35 else "red"
            marker = "★" if tr.is_leader else "·"
            disease = f"  ({tr.disease})" if tr.disease else ""
            t.append(f"  {marker} {tr.name:<14} ", style="white")
            t.append(f"{tr.health:>3} HP", style=f"bold {hp_color}")
            if disease:
                t.append(disease, style="red")
            t.append("\n")

        t.append("\nSupplies\n", style="bold underline")
        s = game.supplies
        rows = [
            ("food", f"{s.food} lbs"),
            ("oxen", f"{s.oxen}"),
            ("clothing", f"{s.clothing}"),
            ("ammo", f"{s.ammo} bullets"),
            ("wheels", f"{s.wheels}"),
            ("axles", f"{s.axles}"),
            ("tongues", f"{s.tongues}"),
            ("cash", f"${s.cash:.2f}"),
        ]
        for name, val in rows:
            t.append(f"  {name:<10} ", style="white")
            t.append(f"{val}\n", style="bold")

        self.update(t)


class PromptBar(Static):
    def set_prompt(self, txt: str) -> None:
        self.update(Text(txt, style="bold #ffbb44"))


# --- main app ---------------------------------------------------------------


class OregonTrailApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "The Oregon Trail — TUI"

    BINDINGS = [
        Binding("space", "next_day", "Next day", priority=True),
        Binding("h", "hunt", "Hunt"),
        Binding("r", "rest", "Rest"),
        Binding("p", "change_pace", "Pace"),
        Binding("f", "change_ration", "Food"),
        Binding("s", "shop", "Shop"),
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, seed: int | None = None, skip_setup: bool = False,
                 autotest_profession: str | None = None) -> None:
        super().__init__()
        self.game = Game(seed=seed)
        self._skip_setup = skip_setup
        self._autotest_profession = autotest_profession
        self._setup_done = False
        self._title_bar: TitleBar | None = None
        self._trail_panel: TrailPanel | None = None
        self._party_panel: PartyPanel | None = None
        self._log: RichLog | None = None
        self._prompt_bar: PromptBar | None = None
        self._logged_count = 0

    # --- compose ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield TitleBar("", id="title-bar")
        with Horizontal(id="main"):
            yield TrailPanel("", id="trail-panel")
            yield PartyPanel("", id="party-panel")
        yield RichLog(id="log-panel", max_lines=500, highlight=False, markup=False)
        yield PromptBar("", id="prompt-bar")

    def on_mount(self) -> None:
        self._title_bar = self.query_one("#title-bar", TitleBar)
        self._trail_panel = self.query_one("#trail-panel", TrailPanel)
        self._party_panel = self.query_one("#party-panel", PartyPanel)
        self._log = self.query_one("#log-panel", RichLog)
        self._prompt_bar = self.query_one("#prompt-bar", PromptBar)
        if self._skip_setup:
            self._fast_setup()
            self._begin_trail()
        else:
            self.push_screen(SetupScreen(self.game), self._setup_done_cb)

    # --- setup -----------------------------------------------------------

    def _fast_setup(self) -> None:
        """Bypass interactive setup — used in tests."""
        prof = self._autotest_profession or "farmer"
        self.game.choose_profession(prof)
        self.game.start_month("April")
        self.game.set_party(["Ben", "Sarah", "Mary", "Tom", "John"])
        # minimum viable outfit
        self.game.apply_shop({
            "oxen": 4, "food": 800, "clothing": 3,
            "ammo": 200, "wheel": 1, "axle": 1, "tongue": 1,
        })

    def _setup_done_cb(self, result) -> None:
        # SetupScreen dismisses with "needs_shop" when profession+month
        # have been picked but the player still has to outfit the wagon.
        if result == "needs_shop":
            self.push_screen(ShopScreen(self.game), self._shop_done_cb)
            return
        self._begin_trail()

    def _shop_done_cb(self, _result) -> None:
        self._begin_trail()

    def _begin_trail(self) -> None:
        self._setup_done = True
        self.game.start_trail()
        self.refresh_ui()
        self._prompt_bar.set_prompt(
            "SPACE next day  H hunt  R rest  P pace  F food  S shop  Q quit  ? help"
        )

    # --- actions ---------------------------------------------------------

    def action_next_day(self) -> None:
        if not self._setup_done or self.game.over:
            return
        ev = self.game.advance_day(self.game.pace, self.game.ration)
        self.refresh_ui()
        if ev is None:
            return
        if ev.kind == "landmark" or ev.kind == "event":
            self.push_screen(LandmarkScreen(ev), self._after_modal)
        elif ev.kind == "river":
            self.push_screen(RiverScreen(self.game, ev), self._after_river)
        elif ev.kind == "fort":
            self.push_screen(FortScreen(self.game, ev), self._after_modal)
        elif ev.kind == "choice":
            self.push_screen(LandmarkScreen(ev), self._after_modal)
        elif ev.kind == "end":
            self.push_screen(EndScreen(self.game), self._after_end)

    def _after_modal(self, _r) -> None:
        self.refresh_ui()
        if self.game.over:
            self.push_screen(EndScreen(self.game), self._after_end)

    def _after_river(self, _r) -> None:
        # If pending is still a river (player picked "wait"), re-enter.
        if self.game.pending and self.game.pending.kind == "river":
            self.push_screen(RiverScreen(self.game, self.game.pending), self._after_river)
            return
        self._after_modal(_r)

    def _after_end(self, _r) -> None:
        self.exit()

    def action_hunt(self) -> None:
        if not self._setup_done or self.game.over:
            return
        if self.game.supplies.ammo < 3:
            self.game.log("You do not have enough ammo to hunt.")
            self.refresh_ui()
            return
        self.push_screen(HuntScreen(self.game), self._after_modal)

    def action_rest(self) -> None:
        if not self._setup_done or self.game.over:
            return
        # resting ≈ 1 day, no miles, +5 HP, eat food at current ration
        from datetime import timedelta
        self.game.date += timedelta(days=1)
        self.game.days_on_trail += 1
        for t in self.game.survivors():
            t.health = min(100, t.health + 5)
        per, _ = RATION[self.game.ration]
        need = per * self.game.alive()
        if self.game.supplies.food >= need:
            self.game.supplies.food -= need
        self.game.log("You rest for a day. The party recovers a little.")
        self.refresh_ui()

    def action_change_pace(self) -> None:
        order = ["steady", "strenuous", "grueling"]
        i = order.index(self.game.pace)
        self.game.pace = order[(i + 1) % len(order)]
        self.game.log(f"Pace set to {self.game.pace}.")
        self.refresh_ui()

    def action_change_ration(self) -> None:
        order = ["filling", "meager", "bare"]
        i = order.index(self.game.ration)
        self.game.ration = order[(i + 1) % len(order)]
        self.game.log(f"Ration set to {self.game.ration}.")
        self.refresh_ui()

    def action_shop(self) -> None:
        # Re-open Matt's store at any time during the trail. (Meta action;
        # tests and speedrunners will love it.)
        if not self._setup_done or self.game.over:
            return
        self.push_screen(ShopScreen(self.game), self._after_modal)

    def action_help(self) -> None:
        from .screens import LandmarkScreen
        from .game import PendingEvent
        help_ev = PendingEvent(
            kind="landmark",
            title="HELP",
            body=(
                "SPACE — advance one day\n"
                "H — hunt (spend ammo, gain food)\n"
                "R — rest one day (heal)\n"
                "P — cycle pace (steady/strenuous/grueling)\n"
                "F — cycle ration (filling/meager/bare)\n"
                "S — reopen Matt's store\n"
                "Q — quit\n\n"
                "Events pop up as modal screens. Press ENTER to continue."
            ),
        )
        self.push_screen(LandmarkScreen(help_ev), self._after_modal)

    # --- refresh ---------------------------------------------------------

    def refresh_ui(self) -> None:
        if self._title_bar is not None:
            self._title_bar.refresh_bar(self.game)
        if self._trail_panel is not None:
            self._trail_panel.refresh_panel(self.game)
        if self._party_panel is not None:
            self._party_panel.refresh_panel(self.game)
        # flush new messages to log
        if self._log is not None:
            while self._logged_count < len(self.game.messages):
                self._log.write(self.game.messages[self._logged_count])
                self._logged_count += 1
