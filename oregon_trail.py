"""CLI entry point — `python oregon_trail.py`."""
from __future__ import annotations

import argparse

from oregon_trail_tui.app import OregonTrailApp


def main() -> int:
    p = argparse.ArgumentParser(prog="oregon-trail-tui")
    p.add_argument("--seed", type=int, default=None, help="RNG seed")
    p.add_argument("--skip-setup", action="store_true",
                   help="Bypass shop / profession prompts (dev)")
    p.add_argument("--profession", choices=("banker", "carpenter", "farmer"),
                   default=None, help="Pre-pick a profession (with --skip-setup)")
    args = p.parse_args()
    OregonTrailApp(
        seed=args.seed,
        skip_setup=args.skip_setup,
        autotest_profession=args.profession,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
