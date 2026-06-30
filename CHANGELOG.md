# Changelog

All notable changes to DZ Forge are documented here.
This project adheres to [Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Quest Wizard** — guided quest creation: answer a few plain-English questions
  (title, who gives it, what to do, reward) and DZ Forge writes the quest, its
  objective and — if needed — the NPC, all linked together, with a live preview.
  Hides the three-file / numeric-ID complexity that makes quest setup confusing.
- **Plain-language quest summaries** — every quest shows a one-line
  "Talk to X → kill 8 wolves → return to X 🎁 reward" summary in the editor and as
  a tooltip in the list.
- **Per-mod coordinate scanner** — the map's "scan for coordinates" now groups,
  colour-codes and names markers per mod, parses coordinate-strings (e.g. AirborneAI
  safe zones), and labels points by mission name. Surfaces AI missions, patrols and
  spawners that weren't shown before.
- **Section deep-links** — jump straight to a view via URL hash (e.g. `#economy`,
  `#dna=Weapons`); shareable and used to render the docs screenshots.

## [1.0.0] — 2026-06-24

First public release. A graphical, all-in-one editor for DayZ modded servers —
a local web app (Python standard-library server + your browser). Config-editing
only; every save writes a timestamped backup.

### Added
- **Files** — browse the whole server tree with graphical editors for JSON, XML
  and CFG. Runtime/log files hidden by default.
- **Map & quests** — live Leaflet map of trader zones, quest NPCs, objectives,
  AI patrols, airdrops, contaminated areas, event spawns, territories, turrets
  and DNA keycard crates/vaults. Drag to move, place new entities, edit or clear
  in popups, plus a "scan all files for coordinates" layer with a per-file filter.
- **Economy** — search 11k+ loot types; inline-edit nominal/min/lifetime/restock/
  cost; orphan/missing-file detection; a flag fixer (category/usage/value/tag from
  `cfglimitsdefinition`).
- **Traders** — per-zone health Verify plus a stock & price editor (buy/sell %,
  radius, searchable item list with autocomplete).
- **Loadouts** — DayZ Expansion loadouts via a visual paper-doll slot editor with
  copy/paste, search and verify.
- **Quests** — full Expansion quest editor (story/dialogue, rewards, reputation,
  prerequisites, NPC givers, objectives) with dedicated Objective and NPC editors
  and a server-wide clickable audit.
- **Expansion** — friendly forms for every `ExpansionMod` settings file (Market,
  Hardline, Airdrop, AI, Quests, General…).
- **Turrets** — the AutomatedTurrets editor, wired to load/save from the server
  with backups, plus a turret Verify.
- **Events** — `db/events.xml` dynamic events: counts, lifetime, restock, flags
  and the spawn-mix.
- **Spawnable** — `cfgspawnabletypes.xml` + `cfgrandompresets.xml` cargo/attachments.
- **Keycards** — the DNA Keycards mod by tier (Yellow→Red): per-tier spawn
  settings and full loot tables for weapons (magazine/ammo/optic/attachments),
  clothing (every outfit slot) and general items — each field with an item picker
  that browses your types.xml — plus crate/strongroom locations, small-crate loot
  sets, door alarms, and place/drag crates & vaults on the map.
- **Hunter Mods** — friendly forms for every Hunter mod config under
  `profiles/Hunter_Mods`.
- **Validation** — one-click scan for bad flags, duplicate classnames,
  missing/orphan files and spawnable types missing from the economy.
- **Server cfg** — `serverDZ.cfg` as a grouped, typed form with official wiki
  tooltips, or a raw view.
- **Connections** — edit local files, or connect to a live server over SFTP
  (key-based; pulled to a local cache, edited, pushed back with backups).
- Backups, browse & restore throughout; first-run setup screen (pick server
  folder + map); in-app map-tile generation; standalone `.exe` build.

### Security
- HTML-escaping of all file-derived text rendered into the DOM (XSS hardening).
- SFTP host-key verification (trust-on-first-use; refuses on key change).
- Localhost-only binding, path confinement on all file endpoints, no shell
  execution. See [SECURITY.md](SECURITY.md).

[1.0.0]: https://github.com/meccmax/dzforge/releases/tag/v1.0
