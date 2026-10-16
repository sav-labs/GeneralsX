"""Writer and strict reader for Zero Hour .map files (DataChunk format).

GeneralsX @feature Claude 16/10/2026 Lets the content tools produce skirmish maps without
WorldBuilder. The writer emits the same chunks, in the same order and at the same versions,
as WorldBuilder's save (GeneralsMD/Code/Tools/WorldBuilder/src/WorldBuilderDoc.cpp Serialize,
WHeightMapEdit.cpp saveToFile, SidesList::WriteSidesDataChunk, PolygonTrigger::
WritePolygonTriggersDataChunk). The reader parses a map with the rules of the engine readers
(DataChunk.cpp, WorldHeightMap.cpp, SidesList.cpp, PolygonTrigger.cpp, Scripts.cpp,
TerrainLogic.cpp, MapUtil.cpp) and raises MapError on anything those readers would reject,
assert on, or silently patch. It also reads WorldBuilder maps (RefPack compressed or not),
which is how it is checked against real data.
"""

import struct

# Chunk versions (Core/GameEngine/Include/Common/MapReaderWriterInfo.h, SidesList.cpp, Scripts.cpp)
K_HEIGHT_MAP_VERSION_4 = 4
K_BLEND_TILE_VERSION_8 = 8
K_OBJECTS_VERSION_3 = 3
K_WAYPOINTS_VERSION_1 = 1
K_TRIGGERS_VERSION_4 = 4
K_LIGHTING_VERSION_3 = 3
K_WORLDDICT_VERSION_1 = 1
K_SIDES_DATA_VERSION_3 = 3
K_SCRIPTS_DATA_VERSION_1 = 5  # enum value in Scripts.cpp (follows K_SCRIPT_CONDITION_VERSION_4 = 4)
K_SCRIPT_LIST_DATA_VERSION_1 = 1

FLAG_VAL = 0x7ADA0000  # WorldHeightMap.h, closes every blended tile record
NUM_SOURCE_TILES = 1024  # TileData.h; WorldBuilder refuses more bitmap tiles than this
NUM_BLEND_TILES = 16192  # WorldHeightMap.h
NUM_CLIFF_INFO = 32384  # WorldHeightMap.h
MAX_TEXTURE_CLASSES = 200  # assert in ParseBlendTileData
MAP_XY_FACTOR = 10.0
MAP_HEIGHT_SCALE = MAP_XY_FACTOR / 16.0
MAX_PLAYER_COUNT = 16  # GameCommon.h

# Dict::DataType (Core/GameEngine/Include/Common/Dict.h)
DICT_BOOL, DICT_INT, DICT_REAL, DICT_ASCIISTRING, DICT_UNICODESTRING = range(5)

# MapObject flags (Core/GameEngine/Include/Common/MapObject.h)
FLAG_DRAWS_IN_MIRROR = 0x001
FLAG_ROAD_POINT1 = 0x002
FLAG_ROAD_POINT2 = 0x004
FLAG_BRIDGE_POINT1 = 0x010
FLAG_BRIDGE_POINT2 = 0x020

# Time of day (GameType.h): TIME_OF_DAY_MORNING = 1 .. TIME_OF_DAY_NIGHT = 4
TIME_OF_DAY_AFTERNOON = 2


class MapError(Exception):
    pass


class Real(float):
    """A float the Dict writer stores as DICT_REAL (plain Python floats are also accepted)."""


class Unicode(str):
    """A string the Dict writer stores as DICT_UNICODESTRING."""


def _dict_type(value):
    if isinstance(value, bool):
        return DICT_BOOL
    if isinstance(value, int):
        return DICT_INT
    if isinstance(value, float):
        return DICT_REAL
    if isinstance(value, Unicode):
        return DICT_UNICODESTRING
    if isinstance(value, str):
        return DICT_ASCIISTRING
    raise TypeError(f"unsupported Dict value {value!r}")


# ---------------------------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------------------------

class ChunkWriter:
    """DataChunkOutput: a table of contents ("CkMp", count, then len/name/id per symbol, newest
    first) followed by chunks of id (u32), version (u16), size (i32) and payload. Symbols are
    allocated in the order they are first used, chunk labels and Dict keys alike."""

    def __init__(self):
        self.ids = {}
        self.body = bytearray()
        self.stack = []

    def symbol(self, name):
        if name not in self.ids:
            if not name or len(name) > 255:
                raise MapError(f"bad symbol name {name!r}")
            self.ids[name] = len(self.ids) + 1
        return self.ids[name]

    def open(self, name, version):
        self.body += struct.pack("<IH", self.symbol(name), version)
        self.stack.append(len(self.body))
        self.body += struct.pack("<i", 0xFFFF)

    def close(self):
        pos = self.stack.pop()
        struct.pack_into("<i", self.body, pos, len(self.body) - pos - 4)

    def int(self, v):
        self.body += struct.pack("<i", v)

    def real(self, v):
        self.body += struct.pack("<f", v)

    def byte(self, v):
        self.body += struct.pack("<b", v)

    def bytes(self, data):
        self.body += data

    def ascii(self, s):
        data = s.encode("ascii")
        self.body += struct.pack("<H", len(data)) + data

    def unicode(self, s):
        data = s.encode("utf-16-le")
        self.body += struct.pack("<H", len(data) // 2) + data

    def dict(self, d):
        self.body += struct.pack("<H", len(d))
        for key, value in d.items():
            t = _dict_type(value)
            self.int((self.symbol(key) << 8) | t)
            if t == DICT_BOOL:
                self.byte(1 if value else 0)
            elif t == DICT_INT:
                self.int(value)
            elif t == DICT_REAL:
                self.real(value)
            elif t == DICT_ASCIISTRING:
                self.ascii(value)
            else:
                self.unicode(value)

    def finish(self):
        if self.stack:
            raise MapError("unclosed chunk")
        toc = bytearray(b"CkMp" + struct.pack("<i", len(self.ids)))
        for name, sid in sorted(self.ids.items(), key=lambda kv: -kv[1]):
            data = name.encode("ascii")
            toc += struct.pack("<B", len(data)) + data + struct.pack("<I", sid)
        return bytes(toc + self.body)


# Script chunk versions (Scripts.cpp): Script 2, OrCondition 1, Condition 4, ScriptAction 2.
K_SCRIPT_DATA_VERSION_2 = 2
K_SCRIPT_OR_CONDITION_DATA_VERSION_1 = 1
K_SCRIPT_CONDITION_VERSION_4 = 4
K_SCRIPT_ACTION_VERSION_2 = 2
PARAM_COORD3D = 16  # Parameter::COORD3D (Scripts.h)


def _write_name_key(w, name):
    """DataChunkOutput::writeNameKey: a table-of-contents symbol tagged as an ascii string."""
    w.int((w.symbol(name) << 8) | DICT_ASCIISTRING)


def _write_parameters(w, parms):
    w.int(len(parms))
    for ptype, value in parms:
        w.int(ptype)
        if ptype == PARAM_COORD3D:
            for v in value:
                w.real(v)
        else:
            ival, rval, sval = 0, 0.0, ""
            if isinstance(value, bool) or isinstance(value, int):
                ival = int(value)
            elif isinstance(value, float):
                rval = value
            else:
                sval = value
            w.int(ival)
            w.real(rval)
            w.ascii(sval)


def _write_script(w, script):
    """script: dict with name, conditions [[(type id, internal name, [(param type, value)])]]
    (an OR of ANDs), actions [(type id, internal name, params)] and optional one_shot/active."""
    w.open("Script", K_SCRIPT_DATA_VERSION_2)
    w.ascii(script["name"])
    w.ascii(script.get("comment", ""))
    w.ascii("")
    w.ascii("")
    w.byte(1 if script.get("active", True) else 0)
    w.byte(1 if script.get("one_shot", True) else 0)
    for _ in range(3):  # easy, normal, hard
        w.byte(1)
    w.byte(0)  # subroutine
    w.int(script.get("delay", 0))
    for and_list in script["conditions"]:
        w.open("OrCondition", K_SCRIPT_OR_CONDITION_DATA_VERSION_1)
        for ctype, cname, parms in and_list:
            w.open("Condition", K_SCRIPT_CONDITION_VERSION_4)
            w.int(ctype)
            _write_name_key(w, cname)
            _write_parameters(w, parms)
            w.close()
        w.close()
    for atype, aname, parms in script["actions"]:
        w.open("ScriptAction", K_SCRIPT_ACTION_VERSION_2)
        w.int(atype)
        _write_name_key(w, aname)
        _write_parameters(w, parms)
        w.close()
    w.close()


def write_map(m):
    """m is a dict with: width, height, border, heights (bytes, width*height), tiles (list of
    Short, width*height), blend (list), extra_blend (list), cliff_info (list), cliff_state
    (bytes, height*((width+7)//8)), num_bitmap_tiles, texture_classes [(firstTile, numTiles,
    width, name)], blended_tiles [dict], world (dict), sides [(dict, build list)], teams
    [dict], objects [(x, y, z, angle, flags, name, dict)], triggers [dict], lighting (dict),
    waypoint_links [(id1, id2)]."""
    w = ChunkWriter()
    width, height = m["width"], m["height"]
    size = width * height

    w.open("HeightMapData", K_HEIGHT_MAP_VERSION_4)
    w.int(width)
    w.int(height)
    w.int(m["border"])
    w.int(1)
    w.int(width - 2 * m["border"])
    w.int(height - 2 * m["border"])
    w.int(size)
    w.bytes(m["heights"])
    w.close()

    w.open("BlendTileData", K_BLEND_TILE_VERSION_8)
    w.int(size)
    for array in ("tiles", "blend", "extra_blend", "cliff_info"):
        w.bytes(struct.pack(f"<{size}h", *m[array]))
    w.bytes(m["cliff_state"])
    w.int(m["num_bitmap_tiles"])
    w.int(len(m["blended_tiles"]) + 1)
    w.int(1)  # numCliffInfo: only the default entry 0
    w.int(len(m["texture_classes"]))
    for first, count, cls_width, name in m["texture_classes"]:
        w.int(first)
        w.int(count)
        w.int(cls_width)
        w.int(0)  # legacy GDF flag
        w.ascii(name)
    w.int(0)  # numEdgeTiles
    w.int(0)  # numEdgeTextureClasses
    for b in m["blended_tiles"]:
        w.int(b["blendNdx"])
        for key in ("horiz", "vert", "rightDiagonal", "leftDiagonal", "inverted", "longDiagonal"):
            w.byte(b[key])
        w.int(b.get("customBlendEdgeClass", -1))
        w.int(FLAG_VAL)
    w.close()

    w.open("WorldInfo", K_WORLDDICT_VERSION_1)
    w.dict(m["world"])
    w.close()

    w.open("SidesList", K_SIDES_DATA_VERSION_3)
    w.int(len(m["sides"]))
    for side, build_list in m["sides"]:
        w.dict(side)
        w.int(len(build_list))
        if build_list:
            raise MapError("build lists are not supported by this writer")
    w.int(len(m["teams"]))
    for team in m["teams"]:
        w.dict(team)
    w.open("PlayerScriptsList", K_SCRIPTS_DATA_VERSION_1)
    side_scripts = m.get("scripts", {})
    for i in range(len(m["sides"])):
        w.open("ScriptList", K_SCRIPT_LIST_DATA_VERSION_1)
        for script in side_scripts.get(i, []):
            _write_script(w, script)
        w.close()
    w.close()
    w.close()

    w.open("ObjectsList", K_OBJECTS_VERSION_3)
    for x, y, z, angle, flags, name, props in m["objects"]:
        w.open("Object", K_OBJECTS_VERSION_3)
        w.real(x)
        w.real(y)
        w.real(z)
        w.real(angle)
        w.int(flags)
        w.ascii(name)
        w.dict(props)
        w.close()
    w.close()

    w.open("PolygonTriggers", K_TRIGGERS_VERSION_4)
    w.int(len(m["triggers"]))
    for t in m["triggers"]:
        w.ascii(t["name"])
        w.ascii(t.get("layer", ""))
        w.int(t["id"])
        w.byte(1 if t.get("water") else 0)
        w.byte(1 if t.get("river") else 0)
        w.int(t.get("river_start", 0))
        w.int(len(t["points"]))
        for px, py, pz in t["points"]:
            w.int(px)
            w.int(py)
            w.int(pz)
    w.close()

    lighting = m["lighting"]
    w.open("GlobalLighting", K_LIGHTING_VERSION_3)
    w.int(lighting["time_of_day"])
    for tod in lighting["times"]:  # morning, afternoon, evening, night
        terrain, objects = tod["terrain"], tod["objects"]
        for light in (terrain[0], objects[0], objects[1], objects[2], terrain[1], terrain[2]):
            for v in light["ambient"] + light["diffuse"] + light["pos"]:
                w.real(v)
    w.bytes(struct.pack("<I", lighting["shadow_color"]))
    w.close()

    w.open("WaypointsList", K_WAYPOINTS_VERSION_1)
    w.int(len(m["waypoint_links"]))
    for a, b in m["waypoint_links"]:
        w.int(a)
        w.int(b)
    w.close()
    return w.finish()


# ---------------------------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------------------------

def refpack_decode(src):
    """RefPack, as wrapped by the CompressionManager 'EAR\\0' header (WorldBuilder saves)."""
    pos = 0
    flags = (src[0] << 8) | src[1]
    pos = 2
    nbytes = 4 if flags & 0x8000 else 3
    if flags & 0x0100:
        pos += nbytes
    size = int.from_bytes(src[pos:pos + nbytes], "big")
    pos += nbytes
    out = bytearray()
    while True:
        b0 = src[pos]
        pos += 1
        if not b0 & 0x80:
            b1 = src[pos]
            pos += 1
            plain, length, offset = b0 & 3, ((b0 & 0x1C) >> 2) + 3, ((b0 & 0x60) << 3) + b1 + 1
        elif not b0 & 0x40:
            b1, b2 = src[pos], src[pos + 1]
            pos += 2
            plain, length, offset = b1 >> 6, (b0 & 0x3F) + 4, ((b1 & 0x3F) << 8) + b2 + 1
        elif not b0 & 0x20:
            b1, b2, b3 = src[pos], src[pos + 1], src[pos + 2]
            pos += 3
            plain, length, offset = b0 & 3, ((b0 & 0x0C) << 6) + b3 + 5, ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        else:
            if b0 >= 0xFC:
                out += src[pos:pos + (b0 & 3)]
                break
            n = ((b0 & 0x1F) << 2) + 4
            out += src[pos:pos + n]
            pos += n
            continue
        out += src[pos:pos + plain]
        pos += plain
        for _ in range(length):
            out.append(out[-offset])
    if len(out) != size:
        raise MapError(f"RefPack size mismatch {len(out)} != {size}")
    return bytes(out)


def decompress(data):
    if data[:4] == b"EAR\0":
        size = struct.unpack_from("<I", data, 4)[0]
        out = refpack_decode(data[8:])
        if len(out) != size:
            raise MapError("EAR size mismatch")
        return out
    if data[:4] in (b"ZL1\0", b"ZL2\0", b"ZL3\0", b"ZL4\0", b"ZL5\0", b"ZL6\0", b"ZL7\0", b"ZL8\0", b"ZL9\0"):
        import zlib
        return zlib.decompress(data[8:])
    return data


class Chunk:
    def __init__(self, reader, label, version, start, size):
        self.r, self.label, self.version, self.start, self.size, self.pos = reader, label, version, start, size, start

    @property
    def left(self):
        return self.start + self.size - self.pos

    def take(self, n):
        if n < 0 or n > self.left:
            raise MapError(f"{self.label}: read of {n} bytes past the end of the chunk ({self.left} left)")
        data = self.r.data[self.pos:self.pos + n]
        self.pos += n
        return data

    def int(self):
        return struct.unpack("<i", self.take(4))[0]

    def uint(self):
        return struct.unpack("<I", self.take(4))[0]

    def real(self):
        return struct.unpack("<f", self.take(4))[0]

    def byte(self):
        return struct.unpack("<b", self.take(1))[0]

    def shorts(self, n):
        return list(struct.unpack(f"<{n}h", self.take(2 * n)))

    def ascii(self):
        n = struct.unpack("<H", self.take(2))[0]
        return self.take(n).decode("latin-1")

    def unicode(self):
        n = struct.unpack("<H", self.take(2))[0]
        return self.take(2 * n).decode("utf-16-le")

    def dict(self):
        n = struct.unpack("<H", self.take(2))[0]
        d = {}
        for _ in range(n):
            kt = self.int()
            t, key = kt & 0xFF, self.r.name(kt >> 8)
            if t == DICT_BOOL:
                d[key] = bool(self.byte())
            elif t == DICT_INT:
                d[key] = self.int()
            elif t == DICT_REAL:
                d[key] = self.real()
            elif t == DICT_ASCIISTRING:
                d[key] = self.ascii()
            elif t == DICT_UNICODESTRING:
                d[key] = Unicode(self.unicode())
            else:
                raise MapError(f"{self.label}: Dict value type {t} (readDict throws)")
        return d

    def children(self):
        """DataChunkInput::parse inside this chunk: stops when fewer than a header is left."""
        out = []
        while self.left > 0:
            if self.left < 10:
                raise MapError(f"{self.label}: {self.left} stray bytes after the last sub-chunk")
            out.append(self.r.open_chunk(self))
        return out

    def end(self):
        if self.left != 0:
            raise MapError(f"{self.label}: {self.left} unread bytes at the end of the chunk")


class MapReader:
    def __init__(self, data):
        self.data = decompress(data)
        if self.data[:4] != b"CkMp":
            raise MapError("missing CkMp table of contents (DataChunkTableOfContents::read)")
        count = struct.unpack_from("<i", self.data, 4)[0]
        if count <= 0:
            raise MapError("empty table of contents: isOpenedForRead() is false and parse() fails")
        pos = 8
        self.names = {}
        for _ in range(count):
            n = self.data[pos]
            name = self.data[pos + 1:pos + 1 + n].decode("latin-1")
            sid = struct.unpack_from("<I", self.data, pos + 1 + n)[0]
            pos += 5 + n
            if sid in self.names:
                raise MapError(f"duplicate symbol id {sid}")
            if name in self.names.values():
                raise MapError(f"duplicate symbol name {name}")
            self.names[sid] = name
        self.first = pos
        if pos >= len(self.data):
            raise MapError("no chunks after the table of contents")

    def name(self, sid):
        if sid not in self.names:
            raise MapError(f"symbol id {sid} not in the table of contents")
        return self.names[sid]

    def open_chunk(self, parent):
        pos = parent.pos if parent else self.pos
        if pos + 10 > len(self.data):
            raise MapError("truncated chunk header")
        sid, version, size = struct.unpack_from("<IHi", self.data, pos)
        label = self.name(sid)
        if size < 0:
            raise MapError(f"{label}: negative size")
        start = pos + 10
        if parent:
            parent.pos = start
            if size > parent.left:
                raise MapError(f"{label}: chunk of {size} bytes overruns its parent {parent.label}")
            parent.pos += size
        else:
            if start + size > len(self.data):
                raise MapError(f"{label}: chunk of {size} bytes overruns the file")
            self.pos = start + size
        return Chunk(self, label, version, start, size)

    def top_chunks(self):
        self.pos = self.first
        out = []
        while self.pos < len(self.data):
            out.append(self.open_chunk(None))
        return out


def _need_version(c, supported):
    if c.version not in supported:
        raise MapError(f"{c.label}: version {c.version} not in the versions the engine reads {sorted(supported)}")


def parse_height_map(c):
    _need_version(c, {4})
    width, height, border = c.int(), c.int(), c.int()
    boundaries = [(c.int(), c.int()) for _ in range(c.int())]
    size = c.int()
    if size <= 0 or size != width * height:
        raise MapError("HeightMapData: dataSize != width*height (throws ERROR_CORRUPT_FILE_FORMAT)")
    heights = c.take(size)
    c.end()
    return {"width": width, "height": height, "border": border, "boundaries": boundaries, "heights": heights}


def parse_blend_tiles(c, hm):
    _need_version(c, {7, 8})
    size = c.int()
    if size != hm["width"] * hm["height"]:
        raise MapError("BlendTileData: length != height map dataSize (throws)")
    out = {"tiles": c.shorts(size), "blend": c.shorts(size), "extra_blend": c.shorts(size), "cliff_info": c.shorts(size)}
    flip_width = (hm["width"] + 7) // 8
    if c.version == 7:
        out["cliff_state"] = c.take(hm["height"] * ((hm["width"] + 1) // 8))
    else:
        out["cliff_state"] = c.take(hm["height"] * flip_width)
    out["num_bitmap_tiles"] = c.int()
    out["num_blended_tiles"] = c.int()
    out["num_cliff_info"] = c.int()
    if not 0 < out["num_bitmap_tiles"] < 2048:
        raise MapError("BlendTileData: numBitmapTiles out of range (asserts)")
    if not 0 < out["num_blended_tiles"] < NUM_BLEND_TILES + 1:
        raise MapError("BlendTileData: numBlendedTiles out of range (asserts)")
    if not 0 < out["num_cliff_info"] <= NUM_CLIFF_INFO:
        raise MapError("BlendTileData: numCliffInfo out of range")
    ncls = c.int()
    if not 0 < ncls < MAX_TEXTURE_CLASSES:
        raise MapError("BlendTileData: numTextureClasses out of range (asserts)")
    out["texture_classes"] = []
    for _ in range(ncls):
        first, count, width, _legacy = c.int(), c.int(), c.int(), c.int()
        out["texture_classes"].append((first, count, width, c.ascii()))
    out["num_edge_tiles"] = c.int()
    out["edge_classes"] = []
    for _ in range(c.int()):
        first, count, width = c.int(), c.int(), c.int()
        out["edge_classes"].append((first, count, width, c.ascii()))
    out["blended_tiles"] = []
    for _ in range(out["num_blended_tiles"] - 1):
        b = {"blendNdx": c.int()}
        for key in ("horiz", "vert", "rightDiagonal", "leftDiagonal", "inverted", "longDiagonal"):
            b[key] = c.byte()
        b["customBlendEdgeClass"] = c.int()
        if c.uint() != FLAG_VAL:
            raise MapError("BlendTileData: blended tile record without FLAG_VAL (throws)")
        out["blended_tiles"].append(b)
    out["cliff_infos"] = []
    for _ in range(out["num_cliff_info"] - 1):
        info = [c.int()] + [c.real() for _ in range(8)] + [c.byte(), c.byte()]
        out["cliff_infos"].append(info)
    c.end()
    return out


def parse_world(c):
    _need_version(c, {1})
    d = c.dict()
    c.end()
    return d


def parse_sides(c):
    _need_version(c, {1, 2, 3})
    sides = []
    for _ in range(c.int()):
        side = c.dict()
        builds = []
        for _ in range(c.int()):
            b = {"building": c.ascii(), "template": c.ascii(), "loc": (c.real(), c.real(), c.real()),
                 "angle": c.real(), "built": c.byte(), "rebuilds": c.int()}
            if c.version >= 3:
                b.update(script=c.ascii(), health=c.int(), whiner=c.byte(), unsellable=c.byte(), repairable=c.byte())
            builds.append(b)
        sides.append((side, builds))
    if len(sides) > MAX_PLAYER_COUNT:
        raise MapError("SidesList: more sides than MAX_PLAYER_COUNT")
    teams = [c.dict() for _ in range(c.int())] if c.version >= 2 else []
    scripts = []
    for sub in c.children():
        if sub.label != "PlayerScriptsList":
            continue
        for lst in sub.children():
            if lst.label == "ScriptList":
                scripts.append([_parse_script_entry(s) for s in lst.children()])
        if len(scripts) >= MAX_PLAYER_COUNT:
            raise MapError("PlayerScriptsList: too many script lists")
    return {"sides": sides, "teams": teams, "scripts": scripts}


def _parse_parameter(c):
    ptype = c.int()
    if ptype == PARAM_COORD3D:
        return (ptype, (c.real(), c.real(), c.real()))
    return (ptype, c.int(), c.real(), c.ascii())


def _parse_template(c, keyed_from):
    ttype = c.int()
    name = c.r.name(c.uint() >> 8) if c.version >= keyed_from else None
    return (ttype, name, [_parse_parameter(c) for _ in range(c.int())])


def _parse_script(c):
    s = {"name": c.ascii(), "comment": c.ascii(), "condition_comment": c.ascii(), "action_comment": c.ascii()}
    s["active"], s["one_shot"], s["easy"], s["normal"], s["hard"], s["subroutine"] = (c.byte() for _ in range(6))
    s["delay"] = c.int() if c.version >= 2 else 0
    s["conditions"], s["actions"], s["actions_false"] = [], [], []
    for sub in c.children():
        if sub.label == "OrCondition":
            ands = []
            for cond in sub.children():
                ands.append(_parse_template(cond, 4))
                cond.end()
            s["conditions"].append(ands)
        elif sub.label in ("ScriptAction", "ScriptActionFalse"):
            s["actions" if sub.label == "ScriptAction" else "actions_false"].append(_parse_template(sub, 2))
            sub.end()
    return s


def _parse_script_entry(c):
    if c.label == "Script":
        return ("Script", _parse_script(c))
    if c.label == "ScriptGroup":
        name, active = c.ascii(), c.byte()
        if c.version >= 2:
            c.byte()
        return ("ScriptGroup", name, active, [_parse_script(s) for s in c.children() if s.label == "Script"])
    return (c.label,)


def parse_objects(c):
    _need_version(c, {1, 2, 3})
    objects = []
    for o in c.children():
        if o.label != "Object":
            continue
        x, y, z, angle, flags = o.real(), o.real(), o.real(), o.real(), o.int()
        name = o.ascii()
        props = o.dict() if o.version >= 2 else {}
        if o.left:
            # ParseObjectData leaves the rest unread; WorldBuilder never writes more.
            raise MapError(f"Object {name}: {o.left} trailing bytes")
        if o.version <= 2:
            z = 0.0
        objects.append({"x": x, "y": y, "z": z, "angle": angle, "flags": flags, "name": name, "props": props})
    return objects


def parse_triggers(c):
    _need_version(c, {1, 2, 3, 4})
    triggers = []
    for _ in range(c.int()):
        t = {"name": c.ascii()}
        t["layer"] = c.ascii() if c.version >= 4 else ""
        t["id"] = c.int()
        t["water"] = bool(c.byte()) if c.version >= 2 else False
        if c.version >= 3:
            t["river"], t["river_start"] = bool(c.byte()), c.int()
        t["points"] = [(c.int(), c.int(), c.int()) for _ in range(c.int())]
        triggers.append(t)
    c.end()
    return triggers


def parse_lighting(c):
    _need_version(c, {1, 2, 3})
    out = {"time_of_day": c.int(), "times": []}
    def light():
        return {"ambient": [c.real() for _ in range(3)], "diffuse": [c.real() for _ in range(3)], "pos": [c.real() for _ in range(3)]}
    for _ in range(4):
        terrain, objects = [light()], [light()]
        if c.version >= 2:
            objects += [light(), light()]
        if c.version >= 3:
            terrain += [light(), light()]
        out["times"].append({"terrain": terrain, "objects": objects})
    out["shadow_color"] = c.uint() if c.left else None
    c.end()
    return out


def parse_waypoint_links(c):
    _need_version(c, {1})
    links = [(c.int(), c.int()) for _ in range(c.int())]
    c.end()
    return links


def read_map(data):
    """Parse every chunk the engine reads. Returns a dict; raises MapError on any problem."""
    r = MapReader(data)
    out = {"chunks": []}
    for c in r.top_chunks():
        out["chunks"].append((c.label, c.version))
        if c.label == "HeightMapData":
            out["height_map"] = parse_height_map(c)
        elif c.label == "BlendTileData":
            if "height_map" not in out:
                raise MapError("BlendTileData before HeightMapData (needs m_dataSize)")
            out["blend_tiles"] = parse_blend_tiles(c, out["height_map"])
        elif c.label == "WorldInfo":
            out["world"] = parse_world(c)
        elif c.label == "SidesList":
            out.update(parse_sides(c))
        elif c.label == "ObjectsList":
            out["objects"] = parse_objects(c)
        elif c.label == "PolygonTriggers":
            out["triggers"] = parse_triggers(c)
        elif c.label == "GlobalLighting":
            out["lighting"] = parse_lighting(c)
        elif c.label == "WaypointsList":
            out["waypoint_links"] = parse_waypoint_links(c)
    for key in ("height_map", "blend_tiles", "world", "sides", "objects", "triggers", "lighting"):
        if key not in out:
            raise MapError(f"map has no {key} chunk")
    return out
