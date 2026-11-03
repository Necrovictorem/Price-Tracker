# Hardware Price Tracker

Nov 3, 2026 · @Antonio

## Goal and scope

A Python service on your own machine checks prices for every Build Fund item once a day, keeps the full history, and alerts you when something crosses a buy target. It also watches a few leading signals, so a market shift shows up before resale prices fall.

**In scope**

- Prices for the items on the Build Fund list, new and used
- Market signals that move before those prices do (GPU rental rates, DDR5 server parts)
- A local price history you can chart and query
- Phone or Discord alerts

**Out of scope**

- Buying anything automatically
- Anything behind a login, like your Amazon or eBay account

It starts on your main PC and moves to the home server once that exists.

## What it watches

The tracker watches two kinds of things: the parts you plan to buy, and signals that move before those parts get cheaper. The signals matter because a market shift shows up in rental rates and newer server parts months before it reaches eBay prices for your list.

**Buy list**

| Item | Track | Starting price (Nov 3) |
| --- | --- | --- |
| EPYC 7B13 or 7713, unlocked | Used listings | $1,100–1,700 |
| Supermicro H12SSL-i | New and used | $600–900 |
| 512 GB DDR4-3200 RDIMM (8 × 64 GB) | Kits and single sticks × 8 | $1,928–3,999 |
| RTX PRO 6000 Blackwell, Workstation | New and used | $16,000 |
| RTX PRO 6000 Blackwell, Server Edition | Used | not yet priced |
| WD Red Plus 12 TB | New | $533.81 each |
| Bambu Lab H3C AMS Combo | Store price, sales | $2,499 |
| UniFormation S10 | Retail launch after Kickstarter | $1,299 MSRP |

**Leading signals**

| Signal | Why it matters |
| --- | --- |
| RTX PRO 6000 rental rate per hour (Runpod, Vast.ai) | Rates fall when cloud providers have spare capacity. That happens months before used cards get cheaper. |
| 64 GB DDR5-4800 RDIMM price | Neocloud servers use DDR5. A liquidation drops these prices first, and could make a DDR5 build cheaper than DDR4. |
| Used EPYC Genoa (9004) CPU prices | Same reason as DDR5: it is the platform a liquidation would release. |
| DDR4 RDIMM price trend | Shows whether the memory shortage is easing, which also drives GPU prices. |

## Data sources

Use official APIs wherever a store offers one, and parse web pages only where it doesn't. APIs keep working when a store redesigns its site; page parsers break and need fixing.

| Source | Covers | Method | Notes |
| --- | --- | --- | --- |
| eBay Browse API | Used CPUs, boards, RAM, GPUs | Official API, free developer account | Returns current listings. Sold-price history is a restricted API, so the tracker builds its own history from daily snapshots. |
| Keepa API | Amazon prices and history | Paid API | Covers drives and RAM kits sold on Amazon. Optional; decide after phase 2. |
| Bambu Lab, Newegg, Micro Center, B&H | Printers, new parts | Page parsing | Check each site's terms first. One request per item per day is enough. Some pages need a headless browser (Playwright). |
| Runpod, Vast.ai | GPU rental rates | Public pricing pages or APIs | Confirm in phase 2 which ones expose pricing without an account. |
| UniFormation store | S10 retail launch | Page check | Until retail opens, the tracker only needs to notice when a buy button appears. |

Two filtering problems will come up early. Used listings mix in parts you don't want (vendor-locked EPYCs, "for parts" cards, bulk lots), so each item needs keyword rules. And one item shows up as many listings, so the tracker should record the lowest valid price per item per day, not every listing.

## Architecture

&#91;embedded content: tracker architecture · 7 parts\]

Every part reads from or writes to the price history, so collectors, alerts and the dashboard can each change without touching the others. Adding a new store means adding one collector.

## Alerts and buy targets

Each item gets a target price you choose, and the tracker alerts on three kinds of events. Alerts go to your phone through ntfy (free, self-hostable) or to a Discord channel.

| Rule | Fires when | Example |
| --- | --- | --- |
| Below target | Lowest valid price drops under your target | RTX PRO 6000 under your number |
| Sharp drop | Price falls a set percent within a set window | WD Red Plus down 15% in 7 days, like a Black Friday sale |
| New low | Price is the lowest the tracker has ever recorded | Any item, after the history is a few weeks long |
| Signal shift | A leading signal moves past a threshold | GPU rental rates down 15% over 30 days |

Targets start blank. Fill them in once the tracker has collected a few weeks of history, so they're based on real price swings rather than a guess.

## Build phases with Claude Code

Build one working slice first, then widen it. Each phase ends with something you can run and check, which is where Claude Code is most useful: it writes the code, runs it, reads the errors, and fixes them while you watch.

1. **Set up the project.** Create a git repo with a Python environment, plus a CLAUDE.md file that describes the project and its rules for Claude Code. Done when Claude Code can run an empty test suite.
2. **One source, end to end.** Pull used EPYC 7B13 listings from the eBay API, filter them, and save the lowest valid price to SQLite. Run it by hand. Done when a second run adds a new row instead of overwriting.
   - Before the first run, write down what you expect the lowest price to be. Compare it with what comes back.
3. **The rest of the list.** Add a collector per source and per-item filter rules. Done when every item on the list gets a price each run, or a logged reason why not.
4. **Schedule and alerts.** Run daily on its own (Task Scheduler on Windows, cron or systemd on Linux) and send ntfy or Discord alerts from the rules. Done when a test alert reaches your phone.
5. **Dashboard.** A local web page with a price chart per item and the signals. Done when you can see a week of history.
6. **Move to the home server.** Package it in a Docker container and run it on the server. Done when it keeps running through a reboot.

**Optional phase 7: a local model for unclear listings.** Keyword rules should handle most listings. A few titles stay ambiguous, like "EPYC 7B13 tested, pulled from server". Your local Qwen or Gemma could judge only those leftovers through Ollama and log its answer next to the listing. Prices and alerts stay rule-based, so results are exact and repeatable.

**When to build it.** Phases 1 and 2 are worth starting soon, alongside the LLM starter work, because price history only grows with time. A tracker started now has months of data when you're ready to buy. Phases 3 to 7 can wait until after the Gmail cleanup project.

## Open questions

- [ ] Which machine runs it first, and on which OS (Windows on the main PC, or WSL)?
- [ ] Alerts through ntfy, Discord, or both?
- [ ] Is a paid Keepa plan worth it for Amazon history, or is eBay plus store pages enough?
- [ ] Should the tracker also update the Build Fund page, or replace it with its own dashboard?
- [ ] Which DDR5 threshold would make you switch the server plan from DDR4 to DDR5?

## Sources

- [Thunder Compute – RTX PRO 6000 prices and rental rates](https://www.thundercompute.com/blog/nvidia-rtx-pro-6000-pricing)
- [ComputingForGeeks – hard drive price tracker](https://computingforgeeks.com/hard-drive-prices/)
- [PC Server & Parts – DDR4 RDIMM kits](https://pcserverandparts.com/generic/?page=22)
- [Central Computers – NEMIX 512 GB kit](https://www.centralcomputer.com/nemix-512gb-8x64gb-1-2v-ddr4-3200mhz-pc4-25600rdimm-2rx4-mr25600-924k8-g.html)
- [3Dnatives – Bambu Lab H3C launch](https://www.3dnatives.com/en/bambu-lab-h3c-03112026/)
- [3Dnatives – UniFormation S10](https://www.3dnatives.com/en/uniformation-s10-resin-3d-printer-07102026/)
