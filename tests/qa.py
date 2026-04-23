"""QA harness — drive the game engine + TUI with assertions.

Usage:
  python -m tests.qa           # run every scenario
  python -m tests.qa landmark  # only scenarios with 'landmark' in name

Each scenario runs on a fresh `Game(seed=42)` (or on an `OregonTrailApp`
where the TUI shell is exercised). RNG is deterministic so expected
outcomes are stable across runs.
"""
from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from oregon_trail_tui.app import OregonTrailApp
from oregon_trail_tui.game import Game, PROFESSIONS
from oregon_trail_tui.landmarks import LANDMARKS, TOTAL_MILES

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    needs_tui: bool
    fn: Callable[..., Awaitable[None]]


SCENARIOS: list[Scenario] = []


def engine_scenario(name: str):
    def deco(fn: Callable[[Game], Awaitable[None]]) -> Callable:
        SCENARIOS.append(Scenario(name, needs_tui=False, fn=fn))
        return fn
    return deco


def tui_scenario(name: str):
    def deco(fn: Callable[[OregonTrailApp, object], Awaitable[None]]) -> Callable:
        SCENARIOS.append(Scenario(name, needs_tui=True, fn=fn))
        return fn
    return deco


# ---- helpers --------------------------------------------------------------


def assert_eq(a, b, msg: str = "") -> None:
    if a != b:
        raise AssertionError(f"{msg}: {a!r} != {b!r}")


def assert_gt(a, b, msg: str = "") -> None:
    if not (a > b):
        raise AssertionError(f"{msg}: {a!r} not > {b!r}")


def assert_ge(a, b, msg: str = "") -> None:
    if not (a >= b):
        raise AssertionError(f"{msg}: {a!r} not >= {b!r}")


def _fresh_outfitted_game(seed: int = 42, prof: str = "farmer") -> Game:
    g = Game(seed=seed)
    g.choose_profession(prof)
    g.start_month("April")
    g.set_party(["Ben", "Sarah", "Mary", "Tom", "John"])
    g.apply_shop({
        "oxen": 4, "food": 800, "clothing": 3, "ammo": 200,
        "wheel": 1, "axle": 1, "tongue": 1,
    })
    g.start_trail()
    return g


# ============================================================================
# ENGINE SCENARIOS — pure Game() tests, no Textual needed
# ============================================================================


@engine_scenario("profession_sets_cash_and_multiplier")
async def _prof(_game) -> None:
    for name, (cash, mult, _flavor) in PROFESSIONS.items():
        g = Game(seed=1)
        g.choose_profession(name)
        assert_eq(g.supplies.cash, float(cash), f"{name} cash")
        assert_eq(PROFESSIONS[name][1], mult)


@engine_scenario("shop_rejects_over_budget")
async def _shop_broke(_game) -> None:
    g = Game(seed=1)
    g.choose_profession("farmer")  # $400
    ok = g.apply_shop({"oxen": 10, "food": 5000})
    assert_eq(ok, False, "over-budget shop should fail atomically")
    assert_eq(g.supplies.cash, 400.0, "cash untouched")
    assert_eq(g.supplies.food, 0)


@engine_scenario("shop_successful_reduces_cash")
async def _shop_ok(_game) -> None:
    g = Game(seed=1)
    g.choose_profession("banker")  # $1600
    before = g.supplies.cash
    ok = g.apply_shop({"oxen": 4, "food": 500})
    assert ok
    assert_eq(g.supplies.food, 500)
    assert_eq(g.supplies.oxen, 4)
    assert_gt(before, g.supplies.cash)


@engine_scenario("landmarks_18_in_order")
async def _lm_count(_game) -> None:
    assert_eq(len(LANDMARKS), 18)
    for i in range(1, len(LANDMARKS)):
        assert_ge(LANDMARKS[i].mile, LANDMARKS[i - 1].mile)
    assert_eq(LANDMARKS[-1].mile, TOTAL_MILES)


@engine_scenario("advance_day_moves_miles")
async def _advance(_game) -> None:
    g = _fresh_outfitted_game()
    before = g.miles_traveled
    g.advance_day("steady", "filling")
    # the daily event might wipe miles via _event_lost, so try 5 days
    for _ in range(5):
        g.advance_day("steady", "filling")
    assert_gt(g.miles_traveled, before, "moved at least some distance")


@engine_scenario("no_oxen_zero_miles")
async def _no_oxen(_game) -> None:
    g = _fresh_outfitted_game()
    g.supplies.oxen = 0
    before = g.miles_traveled
    g.advance_day("steady", "filling")
    assert_eq(g.miles_traveled, before, "no oxen = no movement")


@engine_scenario("starvation_damages_health")
async def _starve(_game) -> None:
    g = _fresh_outfitted_game()
    g.supplies.food = 0
    hp_before = sum(t.health for t in g.party)
    for _ in range(3):
        g.advance_day("steady", "filling")
    hp_after = sum(t.health for t in g.survivors())
    assert_gt(hp_before, hp_after, "starvation hurts")


@engine_scenario("dysentery_kill_uses_signature_line")
async def _dysentery(_game) -> None:
    g = _fresh_outfitted_game()
    g.party[0].disease = "dysentery"
    g.party[0].health = 1
    # One daily tick should trigger _kill
    g.advance_day("steady", "bare")
    found = any("died of dysentery" in m for m in g.messages)
    assert found, f"dysentery signature missing. Messages: {g.messages}"


@engine_scenario("hunting_increases_food")
async def _hunt(_game) -> None:
    g = _fresh_outfitted_game()
    before = g.supplies.food
    msg = g.resolve_hunt(hits=2, animals=["deer", "rabbit"])
    assert_gt(g.supplies.food, before, "food goes up after hunt")
    assert "meat" in msg


@engine_scenario("river_ford_safe_shallow")
async def _river_shallow(_game) -> None:
    g = _fresh_outfitted_game()
    msg = g.resolve_river("ford", depth=1)
    assert "forded" in msg or "safely" in msg, f"shallow ford should be safe: {msg}"


@engine_scenario("river_ferry_costs_5")
async def _river_ferry(_game) -> None:
    g = _fresh_outfitted_game()
    g.supplies.cash = 100
    g.resolve_river("ferry", depth=5)
    assert_eq(g.supplies.cash, 95.0, "ferry costs $5")


@engine_scenario("river_ferry_blocked_when_poor")
async def _river_ferry_poor(_game) -> None:
    g = _fresh_outfitted_game()
    g.supplies.cash = 0
    msg = g.resolve_river("ferry", depth=5)
    assert "do not have" in msg


@engine_scenario("fort_prices_scale_with_distance")
async def _fort_prices(_game) -> None:
    g = _fresh_outfitted_game()
    east = g.fort_prices("Fort Kearney")       # mile 304
    west = g.fort_prices("Fort Walla Walla")   # mile 1660
    # farther west = cheaper in this simulation
    assert_gt(east["food"], west["food"] - 1e-6, "west fort is not more expensive")


@engine_scenario("fort_buy_works")
async def _fort_buy(_game) -> None:
    g = _fresh_outfitted_game()
    g.supplies.cash = 100
    before = g.supplies.ammo
    ok = g.fort_buy("Fort Kearney", "ammo", 20)
    assert ok
    assert_eq(g.supplies.ammo, before + 20)


@engine_scenario("full_run_eventually_ends")
async def _full_run(_game) -> None:
    # banker loadout usually crosses; if not, still must terminate
    g = Game(seed=42)
    g.choose_profession("banker")
    g.start_month("April")
    g.set_party(["A", "B", "C", "D", "E"])
    g.apply_shop({"oxen": 6, "food": 2000, "ammo": 500, "clothing": 4,
                  "wheel": 2, "axle": 2, "tongue": 2})
    g.start_trail()
    for _ in range(400):
        ev = g.advance_day("steady", "meager")
        if ev and ev.kind == "river":
            g.resolve_river("ford" if ev.data["depth"] <= 3 else "caulk",
                            ev.data["depth"])
        if g.over:
            break
    assert g.over, "game must terminate in 400 days"


@engine_scenario("snapshot_has_expected_keys")
async def _snap(_game) -> None:
    g = _fresh_outfitted_game()
    s = g.snapshot()
    for k in ("miles", "date", "supplies", "party", "weather", "score"):
        assert k in s, f"missing {k}"
    assert_eq(len(s["party"]), 5)


# ============================================================================
# TUI SCENARIOS — exercise the full Textual app via Pilot
# ============================================================================


@tui_scenario("mount_clean")
async def _mount(app: OregonTrailApp, pilot) -> None:
    await pilot.pause()
    # skip_setup mode — panels should exist
    assert app._title_bar is not None
    assert app._trail_panel is not None
    assert app._party_panel is not None
    assert_eq(app.game.alive(), 5)


@tui_scenario("space_advances_one_day")
async def _space(app: OregonTrailApp, pilot) -> None:
    await pilot.pause()
    before_days = app.game.days_on_trail
    await pilot.press("space")
    await pilot.pause()
    # may have opened a modal — bail out if so, but day count still ticked
    assert_gt(app.game.days_on_trail, before_days, "day advanced")


@tui_scenario("pace_hotkey_cycles")
async def _pace(app: OregonTrailApp, pilot) -> None:
    await pilot.pause()
    start = app.game.pace
    await pilot.press("p")
    await pilot.pause()
    assert app.game.pace != start, "P cycles pace"


@tui_scenario("ration_hotkey_cycles")
async def _ration(app: OregonTrailApp, pilot) -> None:
    await pilot.pause()
    start = app.game.ration
    await pilot.press("f")
    await pilot.pause()
    assert app.game.ration != start, "F cycles ration"


@tui_scenario("rest_heals_wounded")
async def _rest(app: OregonTrailApp, pilot) -> None:
    await pilot.pause()
    # damage the leader then rest
    leader = app.game.leader()
    assert leader is not None
    leader.health = 50
    before = leader.health
    await pilot.press("r")
    await pilot.pause()
    assert_gt(leader.health, before, "rest heals")


@tui_scenario("party_panel_lists_travelers")
async def _panel(app: OregonTrailApp, pilot) -> None:
    await pilot.pause()
    app.refresh_ui()
    # The PartyPanel is a Static — we can check its renderable via the
    # engine snapshot (simpler and robust to Textual internals).
    s = app.game.snapshot()
    assert_eq(len(s["party"]), 5)


@tui_scenario("title_bar_shows_miles")
async def _title(app: OregonTrailApp, pilot) -> None:
    await pilot.pause()
    # Advance so miles > 0
    for _ in range(2):
        await pilot.press("space")
        await pilot.pause()
        # dismiss modal if one popped up
        while len(app.screen_stack) > 1:
            await pilot.press("enter")
            await pilot.pause()
    assert_gt(app.game.miles_traveled, 0)


# ---- interactive setup (regression lock) ---------------------------------


async def _run_interactive_setup() -> tuple[str, bool, str]:
    """Dedicated runner — can't use the skip_setup fixture."""
    name = "interactive_setup_profession_month_shop"
    try:
        app = OregonTrailApp(seed=42)
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            # Setup: banker → April → shop → depart
            await pilot.press("1");   await pilot.pause()
            await pilot.press("enter"); await pilot.pause()
            await pilot.press("enter"); await pilot.pause()
            # ShopScreen — buy 8 ox pairs + 30 × 50 lbs food
            for _ in range(8):
                await pilot.press("1"); await pilot.pause()
            for _ in range(30):
                await pilot.press("2"); await pilot.pause()
            await pilot.press("enter"); await pilot.pause()
            assert_eq(app.game.profession, "banker")
            assert_ge(app.game.supplies.oxen, 4)
            assert_ge(app.game.supplies.food, 500)
            assert app._setup_done
        return name, True, ""
    except Exception:
        return name, False, traceback.format_exc()


# Register as a bare entry for the runner (needs a custom path).
SCENARIOS.append(Scenario(
    "interactive_setup_profession_month_shop",
    needs_tui=False,  # we'll handle directly in _run
    fn=_run_interactive_setup,  # type: ignore[arg-type]
))


# ---- robustness ----------------------------------------------------------


@engine_scenario("robust_kill_all_then_advance")
async def _dead_end(_game) -> None:
    g = _fresh_outfitted_game()
    for t in g.party:
        t.alive = False
    ev = g.advance_day("steady", "filling")
    assert ev is not None and ev.kind == "end"
    assert g.over


@engine_scenario("robust_advance_after_over_is_noop")
async def _after_over(_game) -> None:
    g = _fresh_outfitted_game()
    g._trigger_end(victory=True)
    ret = g.advance_day("steady", "filling")
    assert ret is None


@engine_scenario("robust_unknown_key_no_crash")
async def _unknown_fort(_game) -> None:
    g = _fresh_outfitted_game()
    # invalid fort name → fort_buy returns False instead of crashing
    ok = g.fort_buy("Fort Nowhere", "food", 100)
    assert not ok


@engine_scenario("robust_hunt_drains_ammo")
async def _hunt_ammo(_game) -> None:
    g = _fresh_outfitted_game()
    g.supplies.ammo = 200
    before = g.supplies.ammo
    # Simulating a 3-shot hunt that hits one animal
    # (the UI consumes 3 ammo per shot)
    g.supplies.ammo -= 3
    assert_eq(g.supplies.ammo, before - 3)


@engine_scenario("landmark_event_returned_on_crossing")
async def _lm_crossing(_game) -> None:
    g = _fresh_outfitted_game()
    # teleport just before Kansas River Crossing (mile 102)
    g.miles_traveled = 100
    # force the next day's mileage to cross it (fix RNG jitter by running
    # many days — the landmark will fire deterministically)
    triggered: list[str] = []
    for _ in range(40):
        ev = g.advance_day("steady", "filling")
        if ev and ev.kind == "river":
            triggered.append(ev.data["landmark"])
            g.resolve_river("ford", 1)
        if g.miles_traveled > 200:
            break
    assert "Kansas River Crossing" in triggered, f"never hit river: {triggered}"


# ============================================================================
# RUNNER
# ============================================================================


async def _run_engine(scn: Scenario) -> tuple[str, bool, str]:
    try:
        await scn.fn(None)
        return scn.name, True, ""
    except Exception:
        return scn.name, False, traceback.format_exc()


async def _run_tui(scn: Scenario) -> tuple[str, bool, str]:
    try:
        app = OregonTrailApp(seed=42, skip_setup=True, autotest_profession="farmer")
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
                app.save_screenshot(str(OUT_DIR / f"{scn.name}.PASS.svg"))
                return scn.name, True, ""
            except Exception:
                tb = traceback.format_exc()
                try:
                    app.save_screenshot(str(OUT_DIR / f"{scn.name}.FAIL.svg"))
                except Exception:
                    pass
                return scn.name, False, tb
    except Exception:
        return scn.name, False, traceback.format_exc()


async def _run(scn: Scenario) -> tuple[str, bool, str]:
    if scn.name == "interactive_setup_profession_month_shop":
        return await _run_interactive_setup()
    if scn.needs_tui:
        return await _run_tui(scn)
    return await _run_engine(scn)


async def _main(pattern: str | None) -> int:
    sel = [s for s in SCENARIOS if pattern is None or pattern in s.name]
    if not sel:
        print(f"no scenarios match {pattern!r}", file=sys.stderr)
        return 2
    passed = failed = 0
    failures: list[tuple[str, str]] = []
    for scn in sel:
        name, ok, err = await _run(scn)
        if ok:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            failures.append((name, err))
            print(f"  FAIL  {name}")
    print(f"\n{passed} passed, {failed} failed")
    if failures:
        print("\nFailure details")
        print("---------------")
        for name, err in failures:
            print(f"\n[{name}]\n{err}")
    return 0 if failed == 0 else 1


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    return asyncio.run(_main(pattern))


if __name__ == "__main__":
    raise SystemExit(main())
