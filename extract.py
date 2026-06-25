"""
DZ Forge data extractor. `build_data()` scans the live DeerIsle server and returns the
map model (used by server.py's /api/data for always-fresh data). Run directly to also
write data.json (handy as a static fallback).

Coordinates normalised to world (X east, Z north). Every item carries its source file + line.
"""
import os, glob, json
import xml.etree.ElementTree as ET
import config

CFG      = config.load()
ROOT     = CFG["serverRoot"]
MISSION  = os.path.join(ROOT, "mpmissions", CFG["missionFolder"])
PROFILES = os.path.join(ROOT, "profiles")
EXP      = os.path.join(MISSION, "expansion")
QUESTS   = os.path.join(PROFILES, "ExpansionMod", "Quests")
ENV      = os.path.join(MISSION, "env")
OUT      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

OBJ_TYPE = {2:"Target",3:"Travel",4:"Collection",5:"Delivery",6:"TreasureHunt",
            7:"AIPatrol",8:"AICamp",9:"AIVIP",10:"Action",11:"Crafting"}


def loadj(p):
    with open(p, "r", encoding="utf-8-sig") as f: return json.load(f)
def jglob(d): return sorted(glob.glob(os.path.join(d, "*.json")))
def placed(x, z): return not (abs(x) < 0.01 and abs(z) < 0.01)
def fwd(p): return os.path.abspath(p).replace("\\", "/")
def find_line(path, needle, default=1):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for i, ln in enumerate(f, 1):
                if needle in ln: return i
    except Exception: pass
    return default
def wp_xz(wp):
    if isinstance(wp, (list, tuple)) and len(wp) >= 3: return [round(wp[0],2), round(wp[2],2)]
    if isinstance(wp, dict): return [wp.get("x",0), wp.get("z",0)]
    return None


def build_data(root_override=None):
    cfg = config.load()
    ROOT = root_override or cfg["serverRoot"]
    MISSION = os.path.join(ROOT, "mpmissions", cfg["missionFolder"])
    PROFILES = os.path.join(ROOT, "profiles")
    EXP = os.path.join(MISSION, "expansion")
    QUESTS = os.path.join(PROFILES, "ExpansionMod", "Quests")
    ENV = os.path.join(MISSION, "env")
    errors = []
    data = {"map": {"name": cfg["mapName"], "worldSize": cfg["worldSize"]}, "layers": {}, "stats": {}}
    L = data["layers"]
    for k in ("traderZones","traderObjects","questNPCs","questObjectives","aiObjectives",
              "airdrops","contaminated","eventSpawns","territories","turrets","dna"):
        L[k] = []
    unplaced = {"questNPCs": 0, "questObjectives": 0}

    for p in jglob(os.path.join(EXP, "traderzones")):
        try:
            d = loadj(p); pos = d.get("Position", [0,0,0])
            L["traderZones"].append({"id": os.path.splitext(os.path.basename(p))[0],
                "name": d.get("m_DisplayName") or os.path.basename(p), "x": pos[0], "z": pos[2],
                "radius": d.get("Radius", 0), "buy": d.get("BuyPricePercent"), "sell": d.get("SellPricePercent"),
                "stock": len(d.get("Stock", {})), "file": fwd(p), "line": find_line(p, '"Position"')})
        except Exception as e: errors.append(f"{p}: {e}")

    for sub in ("traders", "objects"):
        for p in glob.glob(os.path.join(EXP, sub, "*.map")):
            try:
                with open(p, "r", encoding="utf-8-sig") as f:
                    for n, line in enumerate(f, 1):
                        line = line.strip()
                        if not line or "|" not in line: continue
                        parts = line.split("|")
                        cls = parts[0].split(".")[0]; grp = parts[0].split(".")[1] if "." in parts[0] else ""
                        xyz = parts[1].replace(",", " ").split()
                        ypr = parts[2].replace(",", " ").split() if len(parts) > 2 else []
                        L["traderObjects"].append({"class": cls, "group": grp,
                            "x": float(xyz[0]), "z": float(xyz[2]), "yaw": float(ypr[0]) if ypr else 0.0,
                            "file": fwd(p), "line": n})
            except Exception as e: errors.append(f"{p}: {e}")

    for p in jglob(os.path.join(QUESTS, "NPCs")):
        try:
            d = loadj(p); pos = d.get("Position", [0,0,0]); ori = d.get("Orientation", [0,0,0])
            if not placed(pos[0], pos[2]): unplaced["questNPCs"] += 1; continue
            L["questNPCs"].append({"id": d.get("ID"), "name": d.get("NPCName") or "NPC",
                "className": d.get("ClassName"), "x": pos[0], "z": pos[2], "yaw": ori[0],
                "active": d.get("Active", 1), "file": fwd(p), "line": find_line(p, '"Position"')})
        except Exception as e: errors.append(f"{p}: {e}")

    for tdir in glob.glob(os.path.join(QUESTS, "Objectives", "*")):
        if not os.path.isdir(tdir): continue
        for p in jglob(tdir):
            try:
                d = loadj(p); t = d.get("ObjectiveType", 0); name = OBJ_TYPE.get(t, str(t))
                text = d.get("ObjectiveText", ""); oid = d.get("ID"); pos = d.get("Position")
                if isinstance(pos, list) and len(pos) >= 3 and placed(pos[0], pos[2]):
                    L["questObjectives"].append({"id": oid, "type": t, "typeName": name, "text": text,
                        "x": pos[0], "z": pos[2], "radius": d.get("MaxDistance", 0),
                        "file": fwd(p), "line": find_line(p, '"Position"')})
                elif isinstance(pos, list):
                    unplaced["questObjectives"] += 1
                ai = d.get("AISpawn")
                if isinstance(ai, dict):
                    pts = [w for w in (wp_xz(x) for x in ai.get("Waypoints", [])) if w and placed(w[0], w[1])]
                    if pts:
                        L["aiObjectives"].append({"id": oid, "type": t, "typeName": name, "text": text,
                            "name": ai.get("Name", ""), "count": ai.get("NumberOfAI", 0), "waypoints": pts,
                            "file": fwd(p), "line": find_line(p, '"Waypoints"')})
            except Exception as e: errors.append(f"{p}: {e}")

    for p in jglob(os.path.join(EXP, "missions")):
        try:
            d = loadj(p)
            if "DropLocation" in d:
                dl = d["DropLocation"]
                L["airdrops"].append({"name": d.get("MissionName") or dl.get("Name"),
                    "x": dl.get("x", 0), "z": dl.get("z", 0), "radius": dl.get("Radius", 100),
                    "enabled": d.get("Enabled", 1), "file": fwd(p), "line": find_line(p, '"DropLocation"')})
            elif isinstance(d.get("Data"), dict) and "Pos" in d["Data"]:
                dd = d["Data"]
                L["contaminated"].append({"name": d.get("MissionName"), "x": dd["Pos"][0], "z": dd["Pos"][2],
                    "radius": dd.get("Radius", 100), "enabled": d.get("Enabled", 1),
                    "file": fwd(p), "line": find_line(p, '"Pos"')})
        except Exception as e: errors.append(f"{p}: {e}")

    tc = os.path.join(PROFILES, "AutomatedTurrets", "AutomatedTurretsConfig.json")
    if os.path.isfile(tc):
        try:
            d = loadj(tc)
            for t in d.get("Turrets", []):
                pos = t.get("m_vTurretPosition", [0, 0, 0])
                if isinstance(pos, list) and len(pos) >= 3 and placed(pos[0], pos[2]):
                    L["turrets"].append({"class": t.get("m_sTurretClassName", ""),
                        "ammo": t.get("m_sTurretAmmoClassName", ""), "x": pos[0], "z": pos[2],
                        "guard": t.get("m_fTurretGuardRadius", 0), "rpm": t.get("m_nTurretShootingRPM", 0),
                        "hit": t.get("m_nTurretHitChance", 0), "group": t.get("_group", ""),
                        "file": fwd(tc), "line": 1})
        except Exception as e:
            errors.append(f"{tc}: {e}")

    dna_main = os.path.join(PROFILES, "DNA_Keycards", "System", "Main", "KeyCard_Main_System_Config.json")
    if os.path.isfile(dna_main):
        try:
            d = loadj(dna_main)
            for color in ("Yellow", "Green", "Blue", "Purple", "Red"):
                for kind, key in (("crate", "m_DNA%s_Crate_Locations" % color), ("strongroom", "m_DNA%s_Strongroom_Locations" % color)):
                    for i, slot in enumerate(d.get(key, [])):
                        loc = str(slot.get("dna_Location") or "").split()
                        if len(loc) >= 3:
                            try: x, y, z = float(loc[0]), float(loc[1]), float(loc[2])
                            except ValueError: continue
                            if placed(x, z):
                                L["dna"].append({"color": color, "kind": kind, "idx": i, "key": key,
                                                 "x": x, "y": y, "z": z, "file": fwd(dna_main), "line": 1})
        except Exception as e:
            errors.append(f"{dna_main}: {e}")

    evs = os.path.join(MISSION, "cfgeventspawns.xml")
    try:
        for ev in ET.parse(evs).getroot().findall("event"):
            pts = [[float(ps.get("x")), float(ps.get("z"))] for ps in ev.findall("pos")]
            if pts:
                L["eventSpawns"].append({"event": ev.get("name"), "points": pts,
                    "file": fwd(evs), "line": find_line(evs, f'name="{ev.get("name")}"')})
    except Exception as e: errors.append(f"cfgeventspawns.xml: {e}")

    for p in sorted(glob.glob(os.path.join(ENV, "*_territories.xml"))):
        try:
            species = os.path.basename(p).replace("_territories.xml", "")
            zones = [[float(z.get("x")), float(z.get("z")), float(z.get("r", 0))]
                     for z in ET.parse(p).getroot().iter("zone")]
            if zones:
                L["territories"].append({"species": species, "zones": zones,
                    "file": fwd(p), "line": find_line(p, "<zone")})
        except Exception as e: errors.append(f"{p}: {e}")

    data["stats"] = {k: len(v) for k, v in L.items()}
    data["stats"]["territoryZones"] = sum(len(t["zones"]) for t in L["territories"])
    data["stats"]["eventPoints"] = sum(len(e["points"]) for e in L["eventSpawns"])
    data["stats"]["unplaced"] = unplaced
    data["stats"]["errors"] = len(errors)
    data["_errors"] = errors[:50]
    return data


if __name__ == "__main__":
    data = build_data()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    print("Wrote", OUT)
    for k, v in data["stats"].items():
        print(f"  {k}: {v}")
    for e in data["_errors"]:
        print("  ERR", e)
