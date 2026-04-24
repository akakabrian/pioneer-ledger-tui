"""Scripted end-to-end playtest — boot → setup → shop → advance → river → quit.

Drives the Textual app via Pilot the way a human would on first run. Saves
a screenshot at each checkpoint to tests/out/playtest-*.svg for visual
regression.

Usage: python -m tests.playtest
"""
from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

from pioneer_ledger_tui.app import OregonTrailApp
from pioneer_ledger_tui.screens import RiverScreen

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)


async def _shot(app: OregonTrailApp, tag: str) -> None:
    app.save_screenshot(str(OUT_DIR / f"playtest-{tag}.svg"))


async def _drain_modals(pilot, max_iter: int = 6) -> None:
    """Dismiss any stray modal by pressing enter up to max_iter times."""
    app = pilot.app
    for _ in range(max_iter):
        if len(app.screen_stack) <= 1:
            return
        await pilot.press("enter")
        await pilot.pause()


async def _playtest() -> tuple[bool, str]:
    app = OregonTrailApp(seed=42)
    try:
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            await _shot(app, "01-boot")

            # --- Setup: banker (1) → April default → advance to shop ----
            await pilot.press("1");     await pilot.pause()   # banker
            await _shot(app, "02-profession")
            await pilot.press("enter"); await pilot.pause()   # profession -> month
            await pilot.press("enter"); await pilot.pause()   # month -> shop
            await _shot(app, "03-shop-open")

            # --- Shop: load enough to survive ---------------------------
            # Keys: 1=oxen pair, 2=food, 3=clothing, 4=ammo,
            #       5=wheel, 6=axle, 7=tongue (from screens.py SHOP_KEYS).
            for _ in range(6):
                await pilot.press("1"); await pilot.pause()   # 6 yoke → 12 oxen
            for _ in range(30):
                await pilot.press("2"); await pilot.pause()   # 30×50 lb = 1500 lb food
            for _ in range(4):
                await pilot.press("3"); await pilot.pause()   # clothing
            for _ in range(6):
                await pilot.press("4"); await pilot.pause()   # ammo
            await pilot.press("5"); await pilot.pause()       # wheel
            await pilot.press("6"); await pilot.pause()       # axle
            await pilot.press("7"); await pilot.pause()       # tongue
            await _shot(app, "04-shop-stocked")
            assert app.game.supplies.oxen >= 4, "no oxen"
            assert app.game.supplies.food >= 500, "no food"

            await pilot.press("enter"); await pilot.pause()   # depart
            await _drain_modals(pilot)
            assert app._setup_done, "trail never started"
            await _shot(app, "05-on-trail")

            # --- Advance 3 days ----------------------------------------
            start_days = app.game.days_on_trail
            start_miles = app.game.miles_traveled
            advanced = 0
            safety = 0
            while advanced < 3 and safety < 40:
                safety += 1
                if app.game.over:
                    break
                await pilot.press("space"); await pilot.pause()
                # Handle any modal that popped — river gets dedicated flow
                if len(app.screen_stack) > 1:
                    top = app.screen_stack[-1]
                    if isinstance(top, RiverScreen):
                        # default to ford for shallow, ferry otherwise
                        depth = int(top.ev.data.get("depth", 3))
                        key = "1" if depth <= 2 else "3"
                        # ensure we have cash for ferry; fall back to caulk
                        if key == "3" and app.game.supplies.cash < 5:
                            key = "2"
                        await pilot.press(key); await pilot.pause()
                        await _drain_modals(pilot)
                        await _shot(app, f"06-river-handled-{advanced}")
                    else:
                        await _drain_modals(pilot)
                advanced += 1
            await _shot(app, "07-after-3-days")
            assert app.game.days_on_trail >= start_days + 1, \
                f"day counter never ticked ({start_days} → {app.game.days_on_trail})"
            assert app.game.miles_traveled >= start_miles, "miles went backwards"

            # --- Force a river crossing if none yet --------------------
            # Teleport within range of Kansas River (mile 102) and advance
            # until a RiverScreen appears.
            if app.game.miles_traveled < 100:
                app.game.miles_traveled = 95
            saw_river = False
            for _ in range(30):
                if app.game.over:
                    break
                await pilot.press("space"); await pilot.pause()
                if len(app.screen_stack) > 1:
                    top = app.screen_stack[-1]
                    if isinstance(top, RiverScreen):
                        saw_river = True
                        await pilot.press("1"); await pilot.pause()   # ford
                        await _drain_modals(pilot)
                        await _shot(app, "08-river-forded")
                        break
                    await _drain_modals(pilot)
            # Not a hard failure if RNG doesn't hit a river — the engine
            # scenario landmark_event_returned_on_crossing already locks
            # that behavior. Just record it.
            if not saw_river:
                print("  note: no river fired in 30 ticks (non-fatal)")

            # --- Quit --------------------------------------------------
            await pilot.press("q"); await pilot.pause()
            await _shot(app, "09-quit")
        return True, ""
    except Exception:
        try:
            app.save_screenshot(str(OUT_DIR / "playtest-FAIL.svg"))
        except Exception:
            pass
        return False, traceback.format_exc()


def main() -> int:
    ok, err = asyncio.run(_playtest())
    if ok:
        print("PLAYTEST PASS — screenshots in tests/out/playtest-*.svg")
        return 0
    print("PLAYTEST FAIL\n" + err, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
