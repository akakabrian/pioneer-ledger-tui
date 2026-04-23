"""Perf recheck — engine throughput + TUI boot latency.

Usage: python -m tests.perf

Thresholds are intentionally conservative so the check passes on a loaded
ProDesk but still flags real regressions.
"""
from __future__ import annotations

import asyncio
import sys
import time

from oregon_trail_tui.app import OregonTrailApp
from oregon_trail_tui.game import Game


ENGINE_TURNS = 50_000           # advance_day calls across fresh games
ENGINE_BUDGET_S = 8.0           # ≥ 6k turns / s on this box
BOOT_ITERS = 5                  # how many boots to average
BOOT_BUDGET_MS = 500.0          # per-boot upper bound


def _bench_engine() -> tuple[float, float]:
    """Return (elapsed_s, turns_per_sec)."""
    turns = 0
    t0 = time.perf_counter()
    while turns < ENGINE_TURNS:
        g = Game(seed=turns & 0xFFFF)
        g.choose_profession("farmer")
        g.start_month("April")
        g.set_party(["A", "B", "C", "D", "E"])
        g.apply_shop({"oxen": 4, "food": 1000, "ammo": 200,
                      "wheel": 1, "axle": 1, "tongue": 1})
        g.start_trail()
        for _ in range(200):
            turns += 1
            ev = g.advance_day("steady", "meager")
            if ev and ev.kind == "river":
                g.resolve_river("ford", ev.data.get("depth", 1))
            if g.over:
                break
            if turns >= ENGINE_TURNS:
                break
    dt = time.perf_counter() - t0
    return dt, turns / dt


async def _bench_boot_once() -> float:
    t0 = time.perf_counter()
    app = OregonTrailApp(seed=7, skip_setup=True, autotest_profession="farmer")
    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.pause()
        assert app._setup_done
    return (time.perf_counter() - t0) * 1000.0


async def _bench_boot() -> tuple[float, float]:
    samples = [await _bench_boot_once() for _ in range(BOOT_ITERS)]
    return sum(samples) / len(samples), max(samples)


def main() -> int:
    print("== engine throughput ==")
    dt, tps = _bench_engine()
    print(f"  {ENGINE_TURNS} turns in {dt:.2f} s   ({tps:,.0f} turns / s)")
    engine_ok = dt < ENGINE_BUDGET_S
    print(f"  budget {ENGINE_BUDGET_S}s   -> {'OK' if engine_ok else 'SLOW'}")

    print("\n== TUI boot latency ==")
    mean_ms, max_ms = asyncio.run(_bench_boot())
    print(f"  {BOOT_ITERS} boots   mean {mean_ms:.1f} ms   max {max_ms:.1f} ms")
    boot_ok = max_ms < BOOT_BUDGET_MS
    print(f"  budget {BOOT_BUDGET_MS} ms   -> {'OK' if boot_ok else 'SLOW'}")

    ok = engine_ok and boot_ok
    print("\n" + ("PERF PASS" if ok else "PERF FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
