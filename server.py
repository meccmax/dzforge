"""
DZ Forge local backend — serves the map viewer AND handles edits.
Runs under the trusted python.exe, so Smart App Control doesn't block it.

- GET  /<file>          static files (index.html, tiles, vendor, data.json)
- POST /api/read        {path}              -> {content}
- POST /api/save        {path, content}     -> {backup, bytes}   (backup + atomic write)
- POST /api/new_entity  {kind, x, z}        -> new objective/NPC file (server allocates ID)

Writes are restricted to EDIT_ROOT for safety. Run: python server.py
"""
import json, os, re, shutil, sys, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import extract
import config
import sftpsrc

if getattr(sys, "frozen", False):                                 # PyInstaller build
    ROOT = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))             # static files (map-viewer)
EDIT_ROOT = QUESTS_DIR = MISSION_DIR = None  # set by apply_config()


def set_roots(root):
    global EDIT_ROOT, QUESTS_DIR, MISSION_DIR
    EDIT_ROOT = os.path.abspath(root)  # only area we may write
    QUESTS_DIR = os.path.join(EDIT_ROOT, "profiles", "ExpansionMod", "Quests")
    MISSION_DIR = os.path.join(EDIT_ROOT, "mpmissions", config.load()["missionFolder"])


def apply_config():
    set_roots(config.load()["serverRoot"])


apply_config()
PORT = 8777

RUNTIME_DIRS = {"storage_1", "ATM", "DataCache", "Users", "terje_storage", ".dzforge-backups", "bku"}
RUNTIME_EXT = {".bak", ".log", ".rpt", ".db", ".bin", ".tmp"}
EDITABLE_EXT = {".json", ".xml", ".cfg", ".txt", ".c", ".map"}
SFTP_STATE = {"conn": None, "cache": None}  # active SFTP connection + local cache dir (remote mode)


def in_edit_root(path: str):
    ap = os.path.abspath(path)
    try:
        if os.path.commonpath([ap, EDIT_ROOT]) == EDIT_ROOT:
            return ap
    except ValueError:
        pass
    return None


def fwd(p):
    return os.path.abspath(p).replace("\\", "/")


def max_id_in(dirs):
    mx = 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.lower().endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fn), "r", encoding="utf-8-sig") as f:
                    v = json.load(f).get("ID")
                if isinstance(v, int) and v > mx:
                    mx = v
            except Exception:
                pass
    return mx


def find_line(path, needle):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for i, ln in enumerate(f, 1):
                if needle in ln:
                    return i
    except Exception:
        pass
    return 1


def write_new(folder, fname, obj):
    os.makedirs(folder, exist_ok=True)
    base, ext = os.path.splitext(fname)
    fp = os.path.join(folder, fname)
    k = 1
    while os.path.exists(fp):
        fp = os.path.join(folder, f"{base}_{k}{ext}")
        k += 1
    with open(fp, "w", encoding="utf-8", newline="") as f:
        json.dump(obj, f, indent=4)
    return fp


def backup_name(bdir, base, ts, tag=""):
    fp = os.path.join(bdir, f"{base}.{ts}{tag}.bak")
    k = 1
    while os.path.exists(fp):
        fp = os.path.join(bdir, f"{base}.{ts}_{k}{tag}.bak")
        k += 1
    return fp


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def _json(self, code, obj):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if urlparse(self.path).path == "/api/data":
            try:
                return self._json(200, extract.build_data(EDIT_ROOT))
            except Exception as e:
                return self._json(500, {"error": str(e)})
        return super().do_GET()

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            body = self._body()
        except Exception as e:
            return self._json(400, {"error": f"bad request: {e}"})

        if route == "/api/read":
            fp = in_edit_root(body.get("path", ""))
            if not fp:
                return self._json(403, {"error": "path outside editable root"})
            try:
                with open(fp, "r", encoding="utf-8-sig") as f:
                    return self._json(200, {"content": f.read()})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/save":
            fp = in_edit_root(body.get("path", ""))
            if not fp:
                return self._json(403, {"error": "path outside editable root"})
            content = body.get("content", "")
            try:
                backup = "(new file)"
                if os.path.exists(fp):
                    bdir = os.path.join(os.path.dirname(fp), ".dzforge-backups")
                    os.makedirs(bdir, exist_ok=True)
                    backup = backup_name(bdir, os.path.basename(fp), int(time.time()))
                    shutil.copy2(fp, backup)
                tmp = fp + ".dzforge.tmp"
                with open(tmp, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
                os.replace(tmp, fp)
                conn, cache = SFTP_STATE["conn"], SFTP_STATE["cache"]
                if conn and cache:  # remote mode: also push the changed file back over SFTP
                    try:
                        rel = os.path.relpath(fp, cache).replace("\\", "/")
                        conn.write(f"{conn.base.rstrip('/')}/{rel}", content)
                    except Exception as e:
                        return self._json(200, {"backup": backup, "bytes": len(content), "pushWarn": str(e)})
                return self._json(200, {"backup": backup, "bytes": len(content)})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/new_entity":
            kind = body.get("kind")
            try:
                x, z = round(float(body.get("x", 0)), 2), round(float(body.get("z", 0)), 2)
            except Exception:
                return self._json(400, {"error": "bad coordinates"})
            try:
                if kind == "npc":
                    folder = os.path.join(QUESTS_DIR, "NPCs")
                    nid = max_id_in([folder]) + 1
                    obj = {
                        "ConfigVersion": 6, "ID": nid, "ClassName": "ExpansionQuestNPCDenis",
                        "Position": [x, 0.0, z], "Orientation": [0.0, 0.0, 0.0],
                        "NPCName": "New NPC", "DefaultNPCText": "Hmm?", "Waypoints": [],
                        "NPCEmoteID": 46, "NPCEmoteIsStatic": 0, "NPCLoadoutFile": "",
                        "NPCInteractionEmoteID": 1, "NPCQuestCancelEmoteID": 60,
                        "NPCQuestStartEmoteID": 58, "NPCQuestCompleteEmoteID": 39,
                        "NPCFaction": "InvincibleObservers", "NPCType": 0, "Active": 1,
                    }
                    fp = write_new(folder, f"QuestNPC_{nid}.json", obj)
                    return self._json(200, {"id": nid, "name": "New NPC",
                        "className": "ExpansionQuestNPCDenis", "x": x, "z": z,
                        "file": fwd(fp), "line": find_line(fp, '"Position"')})

                if kind == "objective":
                    otype = int(body.get("type", 3))
                    specs = {
                        3: ("Travel", "T", {
                            "ConfigVersion": 28, "ID": 0, "ObjectiveType": 3,
                            "ObjectiveText": "New travel objective", "TimeLimit": -1, "Active": 1,
                            "Position": [x, 0.0, z], "MaxDistance": 50.0, "MarkerName": "New objective",
                            "ShowDistance": 1, "TriggerOnEnter": 1, "TriggerOnExit": 0}),
                        2: ("Target", "TA", {
                            "ConfigVersion": 28, "ID": 0, "ObjectiveType": 2,
                            "ObjectiveText": "New target objective", "TimeLimit": -1, "Active": 1,
                            "Position": [x, 0.0, z], "MaxDistance": 50.0, "MinDistance": -1.0,
                            "Amount": 10, "ClassNames": [], "CountSelfKill": 0, "AllowedWeapons": [],
                            "ExcludedClassNames": [], "CountAIPlayers": 0, "AllowedTargetFactions": [],
                            "AllowedDamageZones": []}),
                    }
                    if otype not in specs:
                        return self._json(400, {"error": f"unsupported objective type {otype}"})
                    folder_name, abbr, tmpl = specs[otype]
                    objs_root = os.path.join(QUESTS_DIR, "Objectives")
                    all_dirs = [os.path.join(objs_root, d) for d in os.listdir(objs_root)] if os.path.isdir(objs_root) else []
                    nid = max_id_in(all_dirs) + 1
                    tmpl["ID"] = nid
                    fp = write_new(os.path.join(objs_root, folder_name), f"Objective_{abbr}_{nid}.json", tmpl)
                    return self._json(200, {"id": nid, "type": otype, "typeName": folder_name,
                        "text": tmpl["ObjectiveText"], "x": x, "z": z, "radius": 50.0,
                        "file": fwd(fp), "line": find_line(fp, '"Position"')})

                if kind == "traderzone":
                    tzdir = os.path.join(MISSION_DIR, "expansion", "traderzones")
                    tmpl = {"m_Version": 6, "m_DisplayName": "New Trader", "Position": [x, 0.0, z],
                            "Radius": 100.0, "BuyPricePercent": 100.0, "SellPricePercent": -1.0, "Stock": {}}
                    fp = write_new(tzdir, "NewTrader.json", tmpl)
                    return self._json(200, {"id": os.path.splitext(os.path.basename(fp))[0],
                        "name": "New Trader", "x": x, "z": z, "radius": 100.0, "buy": 100.0,
                        "sell": -1.0, "stock": 0, "file": fwd(fp), "line": find_line(fp, '"Position"')})

                return self._json(400, {"error": f"unknown kind: {kind}"})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/delete":
            fp = in_edit_root(body.get("path", ""))
            if not fp:
                return self._json(403, {"error": "path outside editable root"})
            try:
                if not os.path.exists(fp):
                    return self._json(404, {"error": "file not found"})
                bdir = os.path.join(os.path.dirname(fp), ".dzforge-backups")
                os.makedirs(bdir, exist_ok=True)
                backup = backup_name(bdir, os.path.basename(fp), int(time.time()), ".deleted")
                shutil.copy2(fp, backup)
                os.remove(fp)
                return self._json(200, {"backup": backup})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/backups":
            fp = in_edit_root(body.get("path", ""))
            if not fp:
                return self._json(403, {"error": "path outside editable root"})
            bdir = os.path.join(os.path.dirname(fp), ".dzforge-backups")
            base = os.path.basename(fp)
            items = []
            if os.path.isdir(bdir):
                for fn in os.listdir(bdir):
                    if not (fn.startswith(base + ".") and fn.endswith(".bak")):
                        continue
                    full = os.path.join(bdir, fn)
                    kind = "deleted" if fn.endswith(".deleted.bak") else ("prerestore" if fn.endswith(".prerestore.bak") else "edit")
                    mid = fn[len(base) + 1:].rsplit(".bak", 1)[0].replace(".deleted", "").replace(".prerestore", "")
                    try:
                        ts = int(mid)
                    except ValueError:
                        ts = int(os.path.getmtime(full))
                    items.append({"name": fn, "path": fwd(full), "ts": ts, "kind": kind})
            items.sort(key=lambda x: x["ts"], reverse=True)
            return self._json(200, {"backups": items})

        if route == "/api/restore":
            bak = in_edit_root(body.get("backup", ""))
            tgt = in_edit_root(body.get("target", ""))
            if not bak or not tgt:
                return self._json(403, {"error": "path outside editable root"})
            if not os.path.exists(bak):
                return self._json(404, {"error": "backup not found"})
            try:
                if os.path.exists(tgt):
                    bdir = os.path.join(os.path.dirname(tgt), ".dzforge-backups")
                    os.makedirs(bdir, exist_ok=True)
                    shutil.copy2(tgt, backup_name(bdir, os.path.basename(tgt), int(time.time()), ".prerestore"))
                shutil.copy2(bak, tgt)
                return self._json(200, {"restored": fwd(tgt)})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/all_backups":
            PRUNE = {"storage_1", "ATM", "DataCache", "Users", "terje_storage", "bku", "tiles"}
            rx = re.compile(r"^(.*)\.(\d+)(?:_\d+)?(\.deleted|\.prerestore)?\.bak$")
            items = []
            for rootd, dirs, files in os.walk(EDIT_ROOT):
                if os.path.basename(rootd) == ".dzforge-backups":
                    origdir = os.path.dirname(rootd)
                    for fn in files:
                        m = rx.match(fn)
                        if not m:
                            continue
                        kind = "deleted" if m.group(3) == ".deleted" else ("prerestore" if m.group(3) == ".prerestore" else "edit")
                        target = os.path.join(origdir, m.group(1))
                        items.append({"backup": fwd(os.path.join(rootd, fn)), "target": fwd(target),
                            "name": m.group(1), "ts": int(m.group(2)), "kind": kind, "targetExists": os.path.exists(target)})
                    dirs[:] = []
                    continue
                dirs[:] = [d for d in dirs if d not in PRUNE]
            items.sort(key=lambda x: x["ts"], reverse=True)
            return self._json(200, {"backups": items[:300]})

        if route == "/api/sftp/connect":
            try:
                conn = sftpsrc.SftpConn(body.get("host"), body.get("port"), body.get("user"), body.get("key"), body.get("base"))
                conn.listdir(conn.base)  # verify auth + base path
                # pull the read-heavy folders into a local cache (per-file SFTP reads are too slow)
                cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".dzforge-cache")
                shutil.rmtree(cache, ignore_errors=True)
                mission = config.load()["missionFolder"]
                base = conn.base.rstrip("/")
                mrem = f"{base}/mpmissions/{mission}"
                mcache = os.path.join(cache, "mpmissions", mission)
                os.makedirs(mcache, exist_ok=True)
                for sub in ("db", "expansion", "expansion_ce", "env", "EditorFiles"):
                    try: conn.pull(f"{mrem}/{sub}", mcache)
                    except Exception: pass
                for f in conn.listdir(mrem):  # root config files (globbing breaks on quoted paths with spaces)
                    if not f["dir"] and f["name"].lower().endswith((".xml", ".json")):
                        conn.get_into(f'{mrem}/{f["name"]}', mcache)
                erem = f"{base}/profiles/ExpansionMod"
                ecache = os.path.join(cache, "profiles", "ExpansionMod")
                os.makedirs(ecache, exist_ok=True)
                for sub in ("Quests", "Settings"):
                    try: conn.pull(f"{erem}/{sub}", ecache)
                    except Exception: pass
                SFTP_STATE["conn"] = conn
                SFTP_STATE["cache"] = cache
                set_roots(cache)  # all read routes now use the cache; saves also push (see /api/save)
                return self._json(200, {"ok": True, "base": conn.base, "cache": fwd(cache)})
            except Exception as e:
                SFTP_STATE["conn"] = None; SFTP_STATE["cache"] = None
                return self._json(500, {"error": str(e)})

        if route == "/api/sftp/disconnect":
            SFTP_STATE["conn"] = None; SFTP_STATE["cache"] = None
            apply_config()  # back to local serverRoot
            return self._json(200, {"ok": True})

        if route in ("/api/sftp/tree", "/api/sftp/read", "/api/sftp/save"):
            conn = SFTP_STATE["conn"]
            if not conn:
                return self._json(400, {"error": "no active SFTP connection"})
            try:
                if route == "/api/sftp/tree":
                    base = body.get("path") or conn.base
                    entries = []
                    for e in conn.listdir(base):
                        ext = os.path.splitext(e["name"])[1].lower()
                        entries.append({"name": e["name"], "path": base.rstrip("/") + "/" + e["name"],
                            "dir": e["dir"], "runtime": (e["name"] in RUNTIME_DIRS) or (ext in RUNTIME_EXT),
                            "editable": (not e["dir"]) and ext in EDITABLE_EXT, "ext": ext})
                    entries.sort(key=lambda x: (not x["dir"], x["runtime"], x["name"].lower()))
                    return self._json(200, {"path": base, "root": conn.base, "entries": entries})
                if route == "/api/sftp/read":
                    return self._json(200, {"content": conn.read(body.get("path"))})
                if route == "/api/sftp/save":
                    return self._json(200, {"backup": conn.write(body.get("path"), body.get("content", ""))})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/economy":
            core = os.path.join(MISSION_DIR, "cfgeconomycore.xml")
            rows, issues, registered = [], [], []
            try:
                if os.path.exists(core):
                    for ce in ET.parse(core).getroot().findall("ce"):
                        folder = ce.get("folder", "")
                        for fl in ce.findall("file"):
                            if fl.get("type") == "types":
                                registered.append((folder, fl.get("name")))
                if os.path.exists(os.path.join(MISSION_DIR, "db", "types.xml")) and "types.xml" not in {n for _, n in registered}:
                    registered.insert(0, ("db", "types.xml"))  # vanilla loot is loaded by default
                for folder, fname in registered:
                    fp = os.path.join(MISSION_DIR, folder, fname)
                    if not os.path.exists(fp):
                        issues.append({"kind": "missing", "file": fname}); continue
                    try:
                        for t in ET.parse(fp).getroot().findall("type"):
                            g = lambda tag: (t.find(tag).text or "").strip() if t.find(tag) is not None else ""
                            cat = t.find("category")
                            rows.append({"file": fwd(fp), "name": t.get("name"),
                                "nominal": g("nominal"), "min": g("min"), "lifetime": g("lifetime"),
                                "restock": g("restock"), "quantmin": g("quantmin"), "quantmax": g("quantmax"),
                                "cost": g("cost"), "category": cat.get("name") if cat is not None else "",
                                "usage": [u.get("name") for u in t.findall("usage")],
                                "tier": [v.get("name") for v in t.findall("value")],
                                "tag": [tg.get("name") for tg in t.findall("tag")]})
                    except Exception as e:
                        issues.append({"kind": "parse", "file": fname, "err": str(e)})
                regnames = {n for _, n in registered}
                dbdir = os.path.join(MISSION_DIR, "db")
                if os.path.isdir(dbdir):
                    for fn in os.listdir(dbdir):
                        if fn.endswith(".xml") and fn not in regnames and fn.lower() not in ("types.xml", "expansion_types.xml"):
                            try:
                                rt = ET.parse(os.path.join(dbdir, fn)).getroot()
                                if rt.tag == "types" and rt.find("type") is not None:
                                    issues.append({"kind": "orphan", "file": fn})
                            except Exception:
                                pass
                return self._json(200, {"rows": rows, "issues": issues, "count": len(rows)})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/validate":
            md = MISSION_DIR
            out = {"badFlags": [], "duplicates": [], "spawnMissing": [], "orphanFiles": [], "missingFiles": []}
            try:
                def attrset(path, child):
                    s = set()
                    if os.path.exists(path):
                        try:
                            for el in ET.parse(path).getroot().iter(child):
                                if el.get("name"): s.add(el.get("name").lower())
                        except Exception: pass
                    return s
                ld = os.path.join(md, "cfglimitsdefinition.xml")
                cats, tags = attrset(ld, "category"), attrset(ld, "tag")
                usages, values = attrset(ld, "usage"), attrset(ld, "value")
                ldu = os.path.join(md, "cfglimitsdefinitionuser.xml")
                if os.path.exists(ldu):
                    try:
                        r = ET.parse(ldu).getroot()
                        for uf in r.findall("usageflags"):
                            for u in uf.findall("user"):
                                if u.get("name"): usages.add(u.get("name").lower())
                        for vf in r.findall("valueflags"):
                            for u in vf.findall("user"):
                                if u.get("name"): values.add(u.get("name").lower())
                    except Exception: pass
                core = os.path.join(md, "cfgeconomycore.xml")
                reg_types, reg_spawn = [], []
                if os.path.exists(core):
                    for ce in ET.parse(core).getroot().findall("ce"):
                        folder = ce.get("folder", "")
                        for fl in ce.findall("file"):
                            (reg_types if fl.get("type") == "types" else reg_spawn if fl.get("type") == "spawnabletypes" else []).append((folder, fl.get("name")))
                if os.path.exists(os.path.join(md, "db", "types.xml")) and "types.xml" not in {n for _, n in reg_types}:
                    reg_types.insert(0, ("db", "types.xml"))
                name_files = {}
                for folder, fname in reg_types:
                    fp = os.path.join(md, folder, fname)
                    if not os.path.exists(fp): out["missingFiles"].append(fname); continue
                    try:
                        for t in ET.parse(fp).getroot().findall("type"):
                            nm = t.get("name")
                            if not nm: continue
                            name_files.setdefault(nm.lower(), set()).add(fname)
                            for tag, allowed in (("category", cats), ("usage", usages), ("value", values), ("tag", tags)):
                                if not allowed: continue
                                for el in t.findall(tag):
                                    val = el.get("name")
                                    if val and val.lower() not in allowed:
                                        out["badFlags"].append({"type": nm, "file": fwd(fp), "bad": f"{tag}={val}"})
                    except Exception: pass
                econ = set(name_files.keys())
                out["duplicates"] = [{"name": k, "files": sorted(v)} for k, v in name_files.items() if len(v) > 1]
                for sp in [os.path.join(md, f, n) for f, n in reg_spawn] + [os.path.join(md, "cfgspawnabletypes.xml")]:
                    if not os.path.exists(sp): continue
                    try:
                        for t in ET.parse(sp).getroot().findall("type"):
                            nm = t.get("name")
                            if nm and nm.lower() not in econ:
                                out["spawnMissing"].append({"name": nm, "file": fwd(sp)})
                    except Exception: pass
                regnames = {n for _, n in reg_types}
                dbdir = os.path.join(md, "db")
                if os.path.isdir(dbdir):
                    for fn in os.listdir(dbdir):
                        if fn.endswith(".xml") and fn not in regnames and fn.lower() not in ("types.xml", "expansion_types.xml"):
                            try:
                                rt = ET.parse(os.path.join(dbdir, fn)).getroot()
                                if rt.tag == "types" and rt.find("type") is not None:
                                    out["orphanFiles"].append(fn)
                            except Exception: pass
                out["summary"] = {k: len(v) for k, v in out.items() if isinstance(v, list)}
                return self._json(200, out)
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/loadouts":
            d = os.path.join(EDIT_ROOT, "profiles", "ExpansionMod", "Loadouts")
            files = []
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if fn.lower().endswith(".json"):
                        files.append({"name": fn, "path": fwd(os.path.join(d, fn))})
            return self._json(200, {"files": files, "dir": fwd(d)})

        if route == "/api/quests":
            base = os.path.join(EDIT_ROOT, "profiles", "ExpansionMod", "Quests")
            qdir, ndir, odir = (os.path.join(base, x) for x in ("Quests", "NPCs", "Objectives"))
            quests, npcs, objectives = [], [], {}
            def _loadj(p):
                with open(p, "r", encoding="utf-8-sig") as f:
                    return json.load(f)
            if os.path.isdir(qdir):
                for fn in sorted(os.listdir(qdir)):
                    if not fn.lower().endswith(".json"):
                        continue
                    p = os.path.join(qdir, fn)
                    try:
                        d = _loadj(p)
                        quests.append({"file": fwd(p), "name": fn, "id": d.get("ID"),
                                       "title": d.get("Title", ""), "objText": d.get("ObjectiveText", ""),
                                       "active": d.get("Active", 1), "objectives": d.get("Objectives", []),
                                       "givers": d.get("QuestGiverIDs", []), "turnIns": d.get("QuestTurnInIDs", []),
                                       "pre": d.get("PreQuestIDs", []), "followUp": d.get("FollowUpQuest", -1),
                                       "rewards": [r.get("ClassName") for r in d.get("Rewards", []) if isinstance(r, dict)]})
                    except Exception:
                        quests.append({"file": fwd(p), "name": fn, "id": None, "title": "(unreadable)", "objText": "", "active": 1})
            if os.path.isdir(ndir):
                for fn in sorted(os.listdir(ndir)):
                    if not fn.lower().endswith(".json"):
                        continue
                    p = os.path.join(ndir, fn)
                    try:
                        d = _loadj(p)
                        npcs.append({"file": fwd(p), "id": d.get("ID"), "name": d.get("NPCName") or fn})
                    except Exception:
                        pass
            if os.path.isdir(odir):
                for sub in sorted(os.listdir(odir)):
                    sp = os.path.join(odir, sub)
                    if not os.path.isdir(sp):
                        continue
                    for fn in sorted(os.listdir(sp)):
                        if not fn.lower().endswith(".json"):
                            continue
                        p = os.path.join(sp, fn)
                        try:
                            d = _loadj(p)
                            objectives.setdefault(str(d.get("ObjectiveType")), []).append(
                                {"file": fwd(p), "id": d.get("ID"), "text": d.get("ObjectiveText", ""),
                                 "type": d.get("ObjectiveType"), "folder": sub})
                        except Exception:
                            pass
            return self._json(200, {"dir": fwd(qdir), "quests": quests, "npcs": npcs, "objectives": objectives})

        if route == "/api/turrets":
            tdir = os.path.join(EDIT_ROOT, "profiles", "AutomatedTurrets")
            fp = os.path.join(tdir, "AutomatedTurretsConfig.json")
            return self._json(200, {"file": fwd(fp), "exists": os.path.isfile(fp), "dir": fwd(tdir)})

        if route == "/api/events":
            # dynamic events economy (db/events.xml); also report the cfglimits-derived nothing here.
            fp = os.path.join(MISSION_DIR, "db", "events.xml")
            return self._json(200, {"file": fwd(fp), "exists": os.path.isfile(fp)})

        if route == "/api/spawnable":
            tf = os.path.join(MISSION_DIR, "cfgspawnabletypes.xml")
            pf = os.path.join(MISSION_DIR, "cfgrandompresets.xml")
            return self._json(200, {"typesFile": fwd(tf), "presetsFile": fwd(pf),
                                    "typesExist": os.path.isfile(tf), "presetsExist": os.path.isfile(pf)})

        if route == "/api/dnakeycards":
            base = os.path.join(EDIT_ROOT, "profiles", "DNA_Keycards")
            files = []
            if os.path.isdir(base):
                for rootd, dirs, fs in os.walk(base):
                    for fn in sorted(fs):
                        if fn.lower().endswith(".json"):
                            p = os.path.join(rootd, fn)
                            rel = os.path.relpath(os.path.dirname(p), base).replace("\\", "/")
                            files.append({"name": fn, "path": fwd(p), "group": "" if rel == "." else rel})
            files.sort(key=lambda f: (f["group"], f["name"]))
            return self._json(200, {"dir": fwd(base), "exists": os.path.isdir(base), "files": files})

        if route == "/api/gentiles":
            src = (body.get("image") or "").strip()
            if not src or not os.path.isfile(src):
                return self._json(400, {"error": "Map image not found: " + (src or "(blank)")})
            try:
                world = int(body.get("worldSize") or config.load().get("worldSize") or 15360)
                import tiler  # lazy (also makes PyInstaller bundle Pillow)
                res = tiler.build_tiles(src, os.path.join(ROOT, "tiles"), world)
                cfg = config.load()
                cfg["mapImage"] = src
                if body.get("worldSize"):
                    cfg["worldSize"] = world
                config.save(cfg)
                return self._json(200, {"ok": True, **res})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if route == "/api/limits":
            # valid category/usage/value/tag flag values from cfglimitsdefinition.xml
            out = {"category": [], "usage": [], "value": [], "tag": []}
            ld = os.path.join(MISSION_DIR, "cfglimitsdefinition.xml")
            if os.path.exists(ld):
                try:
                    r = ET.parse(ld).getroot()
                    for path, key in (("categories/category", "category"), ("usageflags/usage", "usage"),
                                      ("valueflags/value", "value"), ("tags/tag", "tag")):
                        for e in r.findall(path):
                            if e.get("name"):
                                out[key].append(e.get("name"))
                except Exception:
                    pass
            for k in out:
                out[k] = sorted(set(out[k]))
            return self._json(200, out)

        if route == "/api/coordscan":
            ws = float(config.load().get("worldSize", 16384) or 16384)
            # Skip already-plotted sources, runtime/backup dirs, and the giant economy/mapgroup files.
            EXCLUDE = (".dzforge-backups", "/bku", "/storage_", "groupdata", "playerdata", "/logs",
                       "expansion/traders", "expansion/traderzones", "expansion/objects", "expansion/missions",
                       "expansionmod/quests", "automatedturrets", "_territories.xml", "cfgeventspawns",
                       "/db", "types.xml", "cfgspawnabletypes", "cfglimits", "cfgeconomycore",
                       "cfgrandompresets", "mapgrouppos", "mapgroupproto", "mapgroupcluster", "mapclusterproto",
                       "roadcache", "roadnetwork", "navmesh", "cfgeventgroups")
            POS = re.compile(r"pos|coord|location|spawn|origin|waypoint|point", re.I)
            pts, CAP, scanned, capped = [], 4000, [0], [False]

            def okxz(x, z):
                try:
                    x, z = float(x), float(z)
                except (TypeError, ValueError):
                    return None
                if abs(x) < 1 and abs(z) < 1:
                    return None
                if 0 <= x <= ws * 1.05 and 0 <= z <= ws * 1.05:
                    return (round(x, 2), round(z, 2))
                return None

            def add(x, z, label, fp):
                if len(pts) >= CAP:
                    capped[0] = True
                    return
                pts.append({"x": x, "z": z, "label": str(label)[:60], "file": fwd(fp)})

            def walk_json(o, key, fp):
                if len(pts) >= CAP:
                    return
                if isinstance(o, dict):
                    if "x" in o and "z" in o:
                        r = okxz(o.get("x"), o.get("z"))
                        if r:
                            add(r[0], r[1], key or o.get("name") or "point", fp)
                    for k, v in o.items():
                        walk_json(v, k, fp)
                elif isinstance(o, list):
                    if key and POS.search(key) and len(o) >= 3 and all(isinstance(n, (int, float)) for n in o[:3]):
                        r = okxz(o[0], o[2])
                        if r:
                            add(r[0], r[1], key, fp)
                    else:
                        for it in o:
                            walk_json(it, key, fp)

            for base in (MISSION_DIR, os.path.join(EDIT_ROOT, "profiles")):
                for root, dirs, files in os.walk(base):
                    rl = root.replace("\\", "/").lower()
                    dirs[:] = [d for d in dirs if not any(e in (rl + "/" + d.lower()) for e in EXCLUDE)]
                    for fn in files:
                        fp = os.path.join(root, fn)
                        fpl = fp.replace("\\", "/").lower()
                        ext = os.path.splitext(fn)[1].lower()
                        if ext not in (".json", ".map", ".xml") or any(e in fpl for e in EXCLUDE):
                            continue
                        try:
                            if os.path.getsize(fp) > 3 * 1024 * 1024:
                                continue
                        except OSError:
                            continue
                        scanned[0] += 1
                        try:
                            if ext == ".json":
                                with open(fp, "r", encoding="utf-8-sig") as f:
                                    walk_json(json.load(f), None, fp)
                            elif ext == ".map":
                                with open(fp, "r", encoding="utf-8-sig") as f:
                                    for line in f:
                                        line = line.strip()
                                        if not line or "|" not in line:
                                            continue
                                        p = line.split("|")
                                        xyz = p[1].replace(",", " ").split() if len(p) > 1 else []
                                        if len(xyz) >= 3:
                                            r = okxz(xyz[0], xyz[2])
                                            if r:
                                                add(r[0], r[1], p[0].split(".")[0], fp)
                                        if len(pts) >= CAP:
                                            break
                            else:
                                for el in ET.parse(fp).getroot().iter():
                                    a = el.attrib
                                    if "x" in a and "z" in a:
                                        r = okxz(a["x"], a["z"])
                                        if r:
                                            add(r[0], r[1], el.tag, fp)
                                    elif "pos" in a:
                                        parts = a["pos"].replace(",", " ").split()
                                        if len(parts) >= 3:
                                            r = okxz(parts[0], parts[2])
                                            if r:
                                                add(r[0], r[1], el.tag, fp)
                                    if len(pts) >= CAP:
                                        break
                        except Exception:
                            pass
                        if len(pts) >= CAP:
                            break
                    if len(pts) >= CAP:
                        break
            return self._json(200, {"points": pts, "scanned": scanned[0], "capped": capped[0]})

        if route == "/api/expansion_settings":
            locs = [("Profile settings", os.path.join(EDIT_ROOT, "profiles", "ExpansionMod", "Settings")),
                    ("Mission settings", os.path.join(MISSION_DIR, "expansion", "settings"))]
            files = []
            for group, sdir in locs:
                if os.path.isdir(sdir):
                    for fn in sorted(os.listdir(sdir)):
                        if fn.lower().endswith(".json"):
                            files.append({"name": fn, "path": fwd(os.path.join(sdir, fn)), "group": group})
            return self._json(200, {"files": files})

        if route == "/api/huntermods":
            base = os.path.join(EDIT_ROOT, "profiles", "Hunter_Mods")
            files = []
            if os.path.isdir(base):
                for rootd, dirs, fs in os.walk(base):
                    # skip runtime/player data + backup-copy folders; only mod settings remain
                    dirs[:] = [d for d in dirs if d.lower() not in ("playerdatabase", "players", "bases", "data", "cache", "logs") and " - copy" not in d.lower()]
                    for fn in sorted(fs):
                        if fn.lower().endswith(".json") and fn.lower().startswith("hm_settings"):
                            p = os.path.join(rootd, fn)
                            files.append({"name": fn, "path": fwd(p), "group": os.path.basename(os.path.dirname(p))})
            files.sort(key=lambda f: f["group"].lower())
            return self._json(200, {"dir": fwd(base), "exists": os.path.isdir(base), "files": files})

        if route == "/api/classnames":
            names = set()
            md = MISSION_DIR
            tfiles, sfiles = [], []
            core = os.path.join(md, "cfgeconomycore.xml")
            if os.path.exists(core):
                for ce in ET.parse(core).getroot().findall("ce"):
                    folder = ce.get("folder", "")
                    for fl in ce.findall("file"):
                        ft = fl.get("type")
                        if ft == "types":
                            tfiles.append(os.path.join(md, folder, fl.get("name")))
                        elif ft == "spawnabletypes":
                            sfiles.append(os.path.join(md, folder, fl.get("name")))
            vt = os.path.join(md, "db", "types.xml")
            if os.path.exists(vt):
                tfiles.append(vt)
            sfiles.append(os.path.join(md, "cfgspawnabletypes.xml"))
            for fp in tfiles:
                if not os.path.exists(fp):
                    continue
                try:
                    for t in ET.parse(fp).getroot().findall("type"):
                        if t.get("name"):
                            names.add(t.get("name"))
                except Exception:
                    pass
            # spawnabletypes add many attachment/ammo classes not in types.xml
            for fp in sfiles:
                if not os.path.exists(fp):
                    continue
                try:
                    for t in ET.parse(fp).getroot().findall("type"):
                        if t.get("name"):
                            names.add(t.get("name"))
                        for grp in ("attachments", "cargo"):
                            for g in t.findall(grp):
                                for it in g.findall("item"):
                                    if it.get("name"):
                                        names.add(it.get("name"))
                except Exception:
                    pass
            return self._json(200, {"names": sorted(names), "count": len(names)})

        if route == "/api/config":
            def _valid(c):
                r = c.get("serverRoot", "")
                return bool(r) and os.path.isdir(r) and (os.path.isdir(os.path.join(r, "mpmissions")) or os.path.isdir(os.path.join(r, "profiles")))
            def _missions(r):
                mp = os.path.join(r or "", "mpmissions")
                return sorted([d for d in os.listdir(mp) if os.path.isdir(os.path.join(mp, d))]) if os.path.isdir(mp) else []
            if body.get("detectRoot") is not None:  # inspect a candidate folder without saving (first-run helper)
                rp = body.get("detectRoot") or ""
                return self._json(200, {"rootExists": os.path.isdir(rp),
                                        "hasMpmissions": os.path.isdir(os.path.join(rp, "mpmissions")),
                                        "missions": _missions(rp)})
            if body.get("serverRoot") is not None:
                cfg = config.load()
                for k in ("serverRoot", "missionFolder", "mapName", "mapImage", "worldSize"):
                    if k in body:
                        cfg[k] = body[k]
                config.save(cfg)
                apply_config()
                return self._json(200, {"saved": True, "config": cfg, "editRoot": fwd(EDIT_ROOT), "valid": _valid(cfg)})
            cfg = config.load()
            return self._json(200, {"config": cfg, "editRoot": fwd(EDIT_ROOT), "valid": _valid(cfg), "missions": _missions(cfg.get("serverRoot", ""))})

        if route == "/api/cfgfiles":
            found = []
            for rootd, dirs, files in os.walk(EDIT_ROOT):
                dirs[:] = [d for d in dirs if d not in RUNTIME_DIRS]
                for fn in files:
                    if fn.lower().endswith(".cfg"):
                        found.append(fwd(os.path.join(rootd, fn)))
                if len(found) >= 300:
                    break
            return self._json(200, {"files": found[:300], "root": fwd(EDIT_ROOT)})

        if route == "/api/tree":
            base = in_edit_root(body.get("path") or EDIT_ROOT) or EDIT_ROOT
            try:
                entries = []
                for name in os.listdir(base):
                    full = os.path.join(base, name)
                    isdir = os.path.isdir(full)
                    ext = os.path.splitext(name)[1].lower()
                    runtime = (name in RUNTIME_DIRS) or (ext in RUNTIME_EXT)
                    entries.append({"name": name, "path": fwd(full), "dir": isdir,
                        "runtime": runtime, "editable": (not isdir) and ext in EDITABLE_EXT, "ext": ext})
                entries.sort(key=lambda e: (not e["dir"], e["runtime"], e["name"].lower()))
                return self._json(200, {"path": fwd(base), "root": fwd(EDIT_ROOT), "entries": entries})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        self._json(404, {"error": "no route"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}/app.html"
    print(f"DZ Forge server: {url}")
    print(f"  static : {ROOT}")
    print(f"  edits  : {EDIT_ROOT}")
    if getattr(sys, "frozen", False):  # packaged .exe: open the app automatically
        import webbrowser, threading
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    httpd.serve_forever()
