"""Binary FBX 7.4 writer: a tree of nodes with typed properties, wrapped in the header, settings and definitions that
Autodesk's SDK and Blender expect.
Property values: str -> S, bytes -> R, bool -> C, float -> D, int -> I (int32), L(n) -> int64,
numpy arrays by dtype (f8 -> d, f4 -> f, i4 -> i, i8 -> l)."""
import collections, itertools, struct, time, zlib
import numpy as np

VERSION = 7400
HEAD = b"Kaydara FBX Binary  \x00\x1a\x00"
NULL = b"\0" * 13
# Readers check the footer against FileId and CreationTime; this fixed triple is the one Blender's exporter writes.
FILE_ID = bytes.fromhex("28b32aebb624ccc2bfc8b02aa92bfcf1")
CREATION_TIME = "1970-01-01 10:00:00:000"
FOOT_ID = bytes.fromhex("fabcab09d0c8d466b176fb831cf7267e")
FOOT_MAGIC = bytes.fromhex("f85a8c6adef5d97eece90ce3758f290b")
ARRAYS = {"f8": b"d", "f4": b"f", "i4": b"i", "i8": b"l"}


class L(int):
    """int64 property (object ids)"""


def prop(v):
    if isinstance(v, bool):
        return b"C" + struct.pack("?", v)
    if isinstance(v, L):
        return b"L" + struct.pack("<q", v)
    if isinstance(v, int):
        return b"I" + struct.pack("<i", v)
    if isinstance(v, float):
        return b"D" + struct.pack("<d", v)
    if isinstance(v, str):
        v = v.encode("utf-8")
        return b"S" + struct.pack("<I", len(v)) + v
    if isinstance(v, (bytes, bytearray)):
        return b"R" + struct.pack("<I", len(v)) + bytes(v)
    if isinstance(v, np.ndarray):
        dt = v.dtype.kind + str(v.dtype.itemsize)
        raw = np.ascontiguousarray(v.reshape(-1), v.dtype.newbyteorder("<")).tobytes()
        enc = 0
        if len(raw) > 128:
            raw, enc = zlib.compress(raw), 1
        return ARRAYS[dt] + struct.pack("<III", v.size, enc, len(raw)) + raw
    raise TypeError("no FBX property type for %r" % type(v))


class Node:
    def __init__(self, name, *props):
        self.name, self.props, self.children = name, props, []

    def add(self, name, *props):
        n = Node(name, *props)
        self.children.append(n)
        return n

    def P(self, name, ptype, label, flags, *values):
        """one Properties70 entry"""
        return self.add("P", name, ptype, label, flags, *values)


def _write(node, out):
    start = len(out)
    props = b"".join(prop(v) for v in node.props)
    name = node.name.encode("ascii")
    out += struct.pack("<IIIB", 0, len(node.props), len(props), len(name)) + name + props
    for c in node.children:
        _write(c, out)
    if node.children or not node.props:
        out += NULL
    struct.pack_into("<I", out, start, len(out))   # end offset, counted from the start of the file


def encode(nodes):
    out = bytearray(HEAD + struct.pack("<I", VERSION))
    for n in nodes:
        _write(n, out)
    out += NULL + FOOT_ID + b"\0" * 4
    out += b"\0" * (16 - len(out) % 16)            # align to 16, a full 16 when already aligned
    out += struct.pack("<I", VERSION) + b"\0" * 120 + FOOT_MAGIC
    return bytes(out)


class Document:
    """Objects and their connections. Y up, right-handed; unit_cm = centimetres per unit (100 for metres)."""
    def __init__(self, creator, unit_cm=100.0):
        self.creator, self.unit_cm = creator, float(unit_cm)
        self.objects = Node("Objects")
        self.links = []
        self.counts = collections.Counter()
        self._ids = itertools.count(1000000)

    def add(self, kind, label, sub):
        """new object -> (id, node); kind is Model, Geometry, Material, Texture, Video, NodeAttribute..."""
        oid = next(self._ids)
        self.counts[kind] += 1
        return oid, self.objects.add(kind, L(oid), label + "\x00\x01" + kind, sub)

    def link(self, child, parent=0, prop=None):
        """parent 0 is the scene root; prop connects to a property (a texture to a material's DiffuseColor)"""
        self.links.append((child, parent, prop))

    def to_bytes(self):
        now = time.localtime()
        head = Node("FBXHeaderExtension")
        head.add("FBXHeaderVersion", 1003)
        head.add("FBXVersion", VERSION)
        head.add("EncryptionType", 0)
        ts = head.add("CreationTimeStamp")
        for k, v in (("Version", 1000), ("Year", now.tm_year), ("Month", now.tm_mon), ("Day", now.tm_mday),
                     ("Hour", now.tm_hour), ("Minute", now.tm_min), ("Second", now.tm_sec), ("Millisecond", 0)):
            ts.add(k, v)
        head.add("Creator", self.creator)

        settings = Node("GlobalSettings")
        settings.add("Version", 1000)
        p = settings.add("Properties70")
        for k, v in (("UpAxis", 1), ("UpAxisSign", 1), ("FrontAxis", 2), ("FrontAxisSign", 1), ("CoordAxis", 0),
                     ("CoordAxisSign", 1), ("OriginalUpAxis", 1), ("OriginalUpAxisSign", 1)):
            p.P(k, "int", "Integer", "", v)
        p.P("UnitScaleFactor", "double", "Number", "", self.unit_cm)
        p.P("OriginalUnitScaleFactor", "double", "Number", "", self.unit_cm)
        p.P("AmbientColor", "ColorRGB", "Color", "", 0.0, 0.0, 0.0)
        p.P("DefaultCamera", "KString", "", "", "Producer Perspective")
        p.P("TimeMode", "enum", "", "", 11)
        p.P("TimeSpanStart", "KTime", "Time", "", L(0))
        p.P("TimeSpanStop", "KTime", "Time", "", L(46186158000))
        p.P("CustomFrameRate", "double", "Number", "", 24.0)

        docs = Node("Documents")
        docs.add("Count", 1)
        d = docs.add("Document", L(next(self._ids)), "", "Scene")
        p = d.add("Properties70")
        p.P("SourceObject", "object", "", "")
        p.P("ActiveAnimStackName", "KString", "", "", "")
        d.add("RootNode", L(0))

        defs = Node("Definitions")
        defs.add("Version", 100)
        defs.add("Count", sum(self.counts.values()) + 1)
        defs.add("ObjectType", "GlobalSettings").add("Count", 1)
        for kind, n in self.counts.items():
            defs.add("ObjectType", kind).add("Count", n)

        conns = Node("Connections")
        for child, parent, pr in self.links:
            if pr:
                conns.add("C", "OP", L(child), L(parent), pr)
            else:
                conns.add("C", "OO", L(child), L(parent))
        takes = Node("Takes")
        takes.add("Current", "")
        return encode([head, Node("FileId", FILE_ID), Node("CreationTime", CREATION_TIME), Node("Creator", self.creator),
                       settings, docs, Node("References"), defs, self.objects, conns, takes])
