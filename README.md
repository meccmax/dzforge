# 🛠️ DZ Forge

**A graphical, all-in-one editor for DayZ modded servers.** Point it at your server files and edit the economy, quests, traders, loadouts, events, turrets, Expansion settings and `serverDZ.cfg` through friendly forms and a live map — no hand-editing XML/JSON/CFG, and every save makes a backup.

DZ Forge is **config-editing only**. It assumes you already manage your server with a host/GSP (CFTools, Nitrado, a VPS, etc.); it does not start, stop, or host your server.

> Runs as a tiny local web app: a Python standard-library server + your browser. No accounts, no telemetry, nothing leaves your machine — except optional SFTP to your own server, and the optional OCR import (see [Privacy & security](#-privacy--security)).

---

## ✨ Features

| Area | What you can do |
|---|---|
| 📁 **Files** | Browse the whole server tree; graphical editors for JSON, XML and CFG. Runtime/log files hidden by default. |
| 🗺️ **Map & quests** | Live map of trader zones, quest NPCs, objectives, AI patrols, airdrops, contaminated areas, event spawns, territories, turrets and DNA keycard crates/vaults. Drag markers to move, place new entities (incl. keycard crates/vaults by tier), edit or clear them in popups. Plus a **"scan all files for coordinates"** layer with a per-file filter. |
| 💰 **Economy** | Search 11k+ loot types, edit nominal/min/lifetime/restock/cost inline, detect orphan/missing files, and a **flag fixer** (category/usage/value/tag via dropdowns of valid values from `cfglimitsdefinition`). |
| 🪙 **Traders** | Per-zone health **Verify**, plus a stock & price editor (buy/sell %, radius, searchable item list with autocomplete). |
| 🎖️ **Loadouts** | DayZ Expansion loadouts via a visual paper-doll slot editor, copy/paste items, search, verify. |
| 📜 **Quests** | Full Expansion quest editor — story/dialogue, rewards, reputation, prerequisites, NPC givers, objectives — plus dedicated **Objective** and **NPC** editors and a server-wide **clickable audit**. |
| 🧩 **Expansion** | Friendly forms for every `ExpansionMod` settings file (Market, Hardline, Airdrop, AI, Quests, General…). |
| 🔫 **Turrets** | Meccmax's AutomatedTurrets editor, wired to load/save from the server with backups, plus a turret Verify. |
| 🎲 **Events** | `db/events.xml` dynamic events: counts, lifetime, restock, flags and the spawn-mix (children). |
| 📦 **Spawnable** | `cfgspawnabletypes.xml` + `cfgrandompresets.xml` — what cargo/attachments spawn inside/on each item. |
| 🔑 **Keycards** | The **DNA Keycards** mod, organised by tier (Yellow→Red): per-tier spawn settings and full loot tables — weapons (with magazine/ammo/optic/attachments), clothing (every outfit slot) and general items — each field with an item picker that browses your types.xml, plus crate/strongroom locations, small-crate loot sets, door alarms, and place/drag crates & vaults on the map. |
| 🏹 **Hunter Mods** | Friendly forms for every Hunter mod config under `profiles/Hunter_Mods` (one per mod) — booleans as checkboxes, loot lists, spawn settings and nested options, all with backups. |
| 🛡️ **Validation** | One-click scan for the usual server-breakers: bad flags, duplicate classnames, missing/orphan files, spawnable types missing from the economy. |
| ⚙️ **Server cfg** | `serverDZ.cfg` as a grouped, typed form with official wiki tooltips (or a raw view). |
| 🔌 **Connections** | Edit local files, or connect to a live server over **SFTP** (key-based). |

Every save is written atomically and the previous version is copied to a timestamped `.bak` — with browse & restore built in throughout.

---

## 🚀 Getting started

### Option A — Standalone (no Python needed)
1. Copy the **`DZForge`** folder (built into `dist/`).
2. Run **`DZForge.exe`** — your browser opens to the app automatically.
3. It ships **blank** — on first launch the **setup screen** asks for your server folder (the one containing `mpmissions` and `profiles`), auto-detects your mission folder, and lets you pick your **map** (Chernarus, Livonia, DeerIsle, Namalsk, Sakhal, or a custom one). Nobody's files come preloaded.

> ⚠️ **Windows Smart App Control / SmartScreen:** the exe is unsigned, so SAC (if enabled) will block it and SmartScreen may warn. Run it on a machine without SAC, or use Option B. (This is exactly why DZ Forge also runs as plain Python.)

### Option B — From source (works even with Smart App Control on)
Requires **Python 3.8+** (standard library only — no pip packages needed to run).
```bat
:: point dzforge.config.json at your server (or use the in-app setup), then:
start.bat
```
`start.bat` launches the local server and opens `http://localhost:8777/app.html`. It runs through the Microsoft-signed `python.exe`, so SAC allows it.

### Option C — Manual
```bat
python server.py
```
then open `http://localhost:8777/app.html`.

---

## ⚙️ Pointing it at your server

DZ Forge reads `dzforge.config.json` (copy `dzforge.config.example.json` to start):
```json
{
  "serverRoot": "C:\\path\\to\\your\\server",
  "missionFolder": "dayzOffline.chernarusplus",
  "mapName": "Chernarus",
  "mapImage": "C:\\path\\to\\map.jpg",
  "worldSize": 15360
}
```
- `serverRoot` — the folder that contains `mpmissions` and `profiles`.
- You can set all of this in-app (**Connections**, or the first-run setup screen) — no JSON editing required.
- `worldSize` is your map's size in metres (Chernarus 15360, DeerIsle 16384, Livonia 12800…).
- **Remote servers:** in **Connections**, connect over SFTP with an SSH **private key** (password auth isn't supported). Files are pulled to a local cache, edited, and pushed back with backups.

---

## 🗺️ Map tiles

The map view shows your map image as a background. Tiles aren't shipped (they're large and map-specific) — but you don't need Python to make them:

- **In‑app (easiest):** on the first‑run setup screen (or **Connections**), enter the path to a square render of your map and click **🗺️ Generate map tiles**. The bundled exe slices it for you — no Python required.
- **From source / CLI:** `pip install pillow` then `python tiler.py` (reads `mapImage`/`worldSize` from your config).

Either way it writes `tiles/{z}/{x}/{y}.jpg`, sized so the top zoom matches your map's world size. Without tiles the map still works — markers just sit on a plain background.

---

## 📦 Building the standalone .exe

```bat
build_exe.bat
```
Produces `dist\DZForge\DZForge.exe` (a one-folder bundle — ship the **entire** `dist\DZForge` folder, ~15 MB zipped). It ships **clean**: no config and no map tiles are bundled, so a fresh copy shows the first-run setup screen. For map background imagery, generate tiles for your map with `tiler.py` (see **Map tiles** above) and drop the `tiles/` folder next to the exe; without them the map still works (markers on a plain background), just no satellite image.

---

## 🔒 Privacy & security

- The server binds to **`127.0.0.1` only** — it is not reachable from your network.
- Nothing is uploaded anywhere, except: SFTP to **your own** server (Connections), and the **optional** OCR import in the Turret editor (which sends images to Google's Gemini API using a key you provide).
- Every edit keeps a timestamped backup; deletes and restores are reversible.

See **[SECURITY.md](SECURITY.md)** for the full security analysis, threat model and how to report a vulnerability.

---

## 🗂️ Project layout

```
server.py        local HTTP server + all /api endpoints (stdlib only)
extract.py       builds the map data model from your server
config.py        loads/saves dzforge.config.json
sftpsrc.py       remote editing via Windows' signed sftp.exe (key auth)
tiler.py         slices a map image into web tiles (needs Pillow)
app.html         the main app (shell + all editors)
index.html       the Leaflet map editor (embedded)
turrets.html     the AutomatedTurrets editor (embedded)
vendor/          Leaflet (bundled locally)
start.bat        launcher (source)
build_exe.bat    PyInstaller packaging
```

---

## 🙏 Credits

- Built by **Meccmax**.
- Map rendering by [Leaflet](https://leafletjs.com/) (bundled).
- Turret editor: *Meccmax's Turret Editor for AutomatedTurrets*.
- Field definitions cross-referenced against the official [Bohemia DayZ wiki](https://community.bistudio.com/wiki/DayZ:Server_Configuration) and the [DayZ-Central-Economy](https://github.com/BohemiaInteractive/DayZ-Central-Economy) repo.

DayZ is a trademark of Bohemia Interactive. DZ Forge is an unofficial community tool, not affiliated with or endorsed by Bohemia Interactive.

## 📄 License

[MIT](LICENSE) — free to use, modify and share.
