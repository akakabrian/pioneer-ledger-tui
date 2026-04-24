# Decisions — pioneer-ledger-tui

## Licensing / Clean-room (Stage 1)

**Decision: Clean-room Python reimplementation.** Binding strategy pattern
4 from the tui-game-build skill (SDL-coupled / asset-locked / IP-restricted).

The canonical Oregon Trail is owned by HMH (via the MECC catalogue acquired
through Brøderbund / The Learning Company / Houghton Mifflin Harcourt).
The DOS / Apple II / 1990 deluxe editions are **not** open source — binaries
float on abandonware sites but the IP is actively held. Several well-known
public ports exist (Westward, The Organ Trail parody, various browser
re-implementations) but nothing we can legally vendor.

Therefore:

- **No vendored code.** No assets, no binaries, no ROMs under `vendor/`.
- **No copied strings.** Prompts and flavor text are written from scratch
  here. We do preserve the **cultural easter egg** "You have died of
  dysentery." — that exact sentence is the phrase the public associates
  with the game and functions as the game's cultural signature (the
  equivalent of "It's a-me, Mario!" — a six-word quotation).
- **Public-domain facts only.** The 2000-mile Oregon Trail route, the
  1848 setting, the real landmarks (Fort Kearney, Chimney Rock, Fort
  Laramie, Independence Rock, South Pass, Fort Hall, Fort Boise, The
  Dalles, Willamette Valley), historical provisions (oxen, wagon, flour
  in lbs) are all historical record. 19th-century diseases (dysentery,
  cholera, typhoid, measles) are a matter of medical history.
- **Mechanics are generic turn-based survival/management.** Pick-
  profession + buy-supplies + daily-random-events + river-crossing +
  hunting-minigame are common to dozens of pioneer games and are not
  protectable expression.

See SKILL.md binding strategy tree — this slots in with karateka-tui,
ff1-tui, dragon-quest-tui, tetris, pacman (pattern 4).

## Architecture (Stage 2)

Single-process pure-Python simulation, driven by a deterministic
`Game` class that owns: RNG, party roster, supplies, mileage, date,
weather, events. Textual UI subscribes via a bus.

Game loop is **turn-based**, not real-time. The "tick" is one trail day.
The user presses `SPACE` to continue after each event, like the 1985
original. Timers are a non-issue — this is not a reflex game (except
the tiny hunting minigame, which uses a Textual `set_interval` for the
word timer).

## Journey model

Trail is a single linear integer `miles_traveled` counter, 0..2040.
Landmarks are `(name, mile, kind)` tuples in a list sorted by mile.
"Arrived at landmark" = `miles_traveled` crossed the landmark's mile
this step. Forts allow trading; rivers require a crossing decision;
ordinary landmarks just narrate.

18 landmarks:

```
    0  Independence, MO          (start)
  102  Kansas River Crossing     (river)
  185  Big Blue River Crossing   (river)
  304  Fort Kearney              (fort)
  554  Chimney Rock              (landmark)
  640  Fort Laramie              (fort)
  830  Independence Rock         (landmark)
  932  South Pass                (landmark)
  989  Green River Crossing      (river)
 1086  Soda Springs              (landmark)
 1151  Fort Hall                 (fort)
 1296  Snake River Crossing      (river)
 1395  Fort Boise                (fort)
 1534  Blue Mountains            (landmark)
 1660  Fort Walla Walla          (fort)
 1770  The Dalles                (landmark, choice)
 1930  Barlow Toll Road / Raft   (choice)
 2040  Willamette Valley         (end — victory)
```

## Party

5 travelers: leader (user-named) + 4 companions (user-named, random
defaults). Each has:
- `name`
- `health`: 0..100 (starts 100)
- `alive`: bool
- `disease`: str | None ("dysentery", "cholera", "typhoid", "measles",
  "exhaustion", "broken_leg", "snake_bite")

Dysentery is the famous one — preserved verbatim in the death message.

## Supplies

- `food` — lbs
- `oxen` — count (determines pace; breaks below threshold)
- `clothing` — sets (winter/terrain warmth)
- `ammo` — bullets (hunting + rare defense)
- `wheels`, `axles`, `tongues` — spare parts
- `cash` — $ (for forts)

## Setup flow

1. Pick profession: Banker ($1600, ×1), Carpenter ($800, ×2), Farmer
   ($400, ×3). Multiplier applies to final score.
2. Pick start month (March..July). April/May is the sweet spot;
   too-early = snow passes, too-late = winter in the Blues.
3. Name the party (leader + 4).
4. Buy at Matt's General Store. Starts with the profession's cash.
   Oxen $20/yoke, food $0.20/lb, clothing $10/set, ammo $2/box (20
   rounds), spare wheel/axle/tongue $10 each.

## Daily loop

1. Advance calendar day.
2. Advance miles by pace × terrain (15/day steady, 20 strenuous, 10
   grueling; modifiers for mountains, river crossings, weather).
3. Consume food by ration level × survivors (filling 3, meager 2,
   bare-bones 1 lb/person/day).
4. Roll a random event (60% nothing; 40% one of ~18 events).
5. Check arrival at next landmark; if so, narrate / trigger screen.
6. Health update — hunger, weather, disease progression.
7. Check game over (all dead, or reached Willamette).

## Events (15+)

- Illness: dysentery / cholera / typhoid / measles / exhaustion.
- Wagon breakdowns: wheel / axle / tongue.
- Oxen injury / ox dies.
- Bandits steal supplies.
- Thief in the night (ammo / food).
- Lose the trail (-1..-3 days).
- Heavy fog.
- Wrong trail → backtrack.
- Wild fruit (+food).
- Buffalo herd (hunting bonus).
- Snake bite.
- Broken limb.
- Bad water.
- Hailstorm.
- Friendly stranger (trade / cure / gift).
- Another wagon needs help.
- Found abandoned supplies.

## Hunting minigame

Enter the hunting screen → a target word appears → type it correctly
before timer expires. Hit = animal bagged (meat, 15..45 lbs depending
on animal × ammo). Miss = no meat, ammo spent. Limited by ammo.
Buffalo drops ~1000 lbs but only 100 is carryable (capacity cap). Lean
TUI version: 3 animals per hunt, 10 second timer each.

## River crossings

Four options:
- Ford (shallow water, safe if < 3 ft, else risk of losing supplies)
- Caulk and float (always available, 5-15% capsize risk)
- Ferry (costs $5, always safe, may have wait)
- Wait (advance 1 day, depth may drop)

Depth is 1..10 ft, random per river. Capsize = lose food + random
member health damage.

## Fort trading

At each fort the player can buy/sell supplies. Prices fluctuate:
Fort Laramie = baseline; Fort Hall / Boise cheaper per distance into
nowhere; Fort Walla Walla cheapest.

## Scoring

Final score on victory = survivors × profession_multiplier × (cash +
supply_value). Displayed on end screen with breakdown.

## Scope (v1 session)

**In:** Full Independence → Willamette run, 18 landmarks, hunting,
river crossings, fort trading, final score, dysentery easter egg,
QA harness, Textual TUI.

**Out (v2+):** Stranger events with deep branching, weather table
depth beyond 4 categories, Native American trade encounters, side-
quests (Barlow Road vs Columbia Raft is simplified to a single
choice).

## Randomness

Single `random.Random` on `Game`. `seed=42` in tests. All events
pull from this single RNG so replay is deterministic.

## Aesthetic

4-panel Textual layout inspired by simcity-tui but adjusted for
narrative turn-based flow:

```
┌ Title / Date / Mile counter ────────────────────────────────────┐
├──────────────────────────────────┬──────────────────────────────┤
│ Trail view (progress bar +       │ Party & supplies panel       │
│ mini-map with ~~~ landmarks)     │ (names, health, food lbs,    │
│                                  │  oxen, ammo, cash, weather)  │
├──────────────────────────────────┴──────────────────────────────┤
│ Event log (RichLog) / prompt area                               │
└─────────────────────────────────────────────────────────────────┘
```

Keyboard-first, single-letter hotkeys. No mouse required.
