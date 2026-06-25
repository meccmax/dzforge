"""Shared config for DZ Forge. Edit dzforge.config.json to point at YOUR server."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

# Blank by default so a fresh copy shows the first-run setup screen instead of
# pointing at anyone's machine. Users set these via the setup screen / Connections.
DEFAULTS = {
    "serverRoot": "",
    "missionFolder": "",
    "mapName": "",
    "mapImage": "",
    "worldSize": 15360,
}


def load():
    cfg = dict(DEFAULTS)
    p = os.path.join(HERE, "dzforge.config.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print("WARN: could not read dzforge.config.json:", e)
    return cfg


def save(cfg):
    p = os.path.join(HERE, "dzforge.config.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return cfg
