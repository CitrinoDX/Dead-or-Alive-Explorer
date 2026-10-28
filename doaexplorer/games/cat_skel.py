"""Limb placement from a costume's .cat (bone -> OBJ map) plus a per-character skeleton (bone offsets).
Ported from the 'XPR-EMP' Blender importer (xentax, 2013), which covers DOA2U, DOA3 and DOAX costumes.

.cat (decrypted, dword0 == 0x20): +8 physics table, +16 joints table, +0x14.. (pair1, pair2) section list.
  version: 1 = DOAX (no 0xFFFFFFFF marker), 2 = DOAU, 3 = DOA3 (from the marker's pair1).
Skeleton: 24 bones x (x, y, z, pad) local offsets, from the .cat itself (section type 8) or the importer's
skeletons/<code>.<ver> file (not shipped; the user points the viewer at their copy).
A limb sits at the sum of its bone's offsets up the fixed parent chain below."""
import math, os, struct
import numpy as np
from ..scene import trs

BONE_NAMES = ["Chest", "Head", "Hips", "LeftFoot", "LeftForeArm", "LeftHand", "LeftUpLeg", "LeftLeg",
              "LeftArm", "RightFoot", "RightForeArm", "RightHand", "RightUpLeg", "RightLeg", "RightArm", "Unknown0",
              "LeftShoulder", "LeftEyeBall", "LeftToe", "Neck", "RightShoulder", "RightEyeBall", "RightToe", "Waist",
              "LeftWingBase", "LeftWingMid", "LeftWingTip", "RightWingBase", "RightWingMid", "RightWingTip"]
PARENT = [0x17, 0x13, -1, 7, 8, 4, 2, 6, 0x10, 0xd, 0xe, 0xa, 2, 0xc, 0x14, -1, 0, 1, 3, 0, 0, 1, 9, 2, 0,
          0x18, 0x19, 0, 0x1b, 0x1c]
VERSION_EXT = {1: "doax", 2: "doau", 3: "doa3"}
SPECIAL_1 = {0x80: 4, 0x81: 0xa, 0x86: 8, 0x87: 0xe, 0x8b: 0x19, 0x8c: 0x1a, 0x8e: 0x1c, 0x8f: 0x1d}
SPECIAL_2 = {0: 0x17, 2: 0x10, 3: 0x14, 7: 0xc, 8: 7, 9: 0xd, 0xa: 0, 0xb: 2, 0xc: 0, 0xd: 0, 0xe: 2, 0xf: 0x13}
# kind of each map entry: 1 high poly, 2 DOAX high poly, 3 joint, 4 low poly, 5 shadow, 10 physics (hair, cloth)
GROUP = {1: "Character", 2: "Character", 3: "Character", 4: "Low poly", 5: "Shadow", 10: "Physics"}


class Cat:
    def __init__(self):
        self.version = 1
        self.links = []        # (kind, bone, obj)
        self.bones = None      # embedded skeleton: list of (x, y, z)
        self.physics = {}      # obj -> (bone, (x,y,z), (rx,ry,rz) radians)


def parse_cat(d):
    c = Cat()
    if len(d) < 0x1C or struct.unpack_from("<I", d, 0)[0] != 0x20:
        raise ValueError("not a decrypted CAT file")
    u = lambda o: struct.unpack_from("<I", d, o)[0]
    b = lambda o: d[o] if o < len(d) else 0
    p = 0x14
    while p + 8 <= len(d):
        pair1, pair2 = u(p), u(p + 4)
        p += 8
        if pair1 == 0:
            break
        if pair2 == 0xFFFFFFFF:
            c.version = 2 if pair1 == 2 else 3
        elif (c.version != 1 and pair2 in (1, 9)) or (c.version == 1 and pair1 == 4):
            q = pair1 + 0x14
            if c.version == 1:   # DOAX: shadow list first (0xFE-delimited), then the bone list
                q = pair2 + 0x14
                while q < len(d) and b(q) != 0xFE:
                    q += 1
                q += 1
                i = 0
                while q < len(d) and b(q) != 0xFE:
                    if b(q) != 0xFF:
                        c.links.append((5, i, b(q)))
                    i += 1
                    q += 1
                q += 1
                while q < len(d) and b(q) != 0xFE:
                    q += 1
                q += 1
            while q + 3 <= len(d):
                bid, bone, obj = b(q), b(q + 1), b(q + 2)
                if bid == 0:
                    break
                if bid == 0xA:
                    q += 2
                    continue
                if bid == 0xB:
                    q += 1
                    continue
                q += 3
                if bid == 1:
                    bone = SPECIAL_1.get(bone, bone)
                elif bid == 2:
                    bone = SPECIAL_2.get(bone, bone)
                else:
                    continue
                c.links.append((4 if pair2 == 9 else bid, bone, obj))
        elif c.version != 1 and pair2 == 5:          # DOAU/DOA3 shadow shapes
            q = pair1 + 0x14
            if b(q) == 0xF0:
                for i in range(0xF):
                    c.links.append((5, i, b(q + 1 + i)))
        elif c.version != 1 and pair2 == 8:          # skeleton embedded in the cat
            q = pair1 + 0x14
            c.bones = [struct.unpack_from("<3f", d, q + 16 * i) for i in range(0x18)]
    jo = u(16)
    if jo and jo < len(d):
        offs = []
        q = jo
        while q + 4 <= len(d) and u(q) != 0:
            offs.append(u(q))
            q += 4
        for j in offs:
            if j < 4 or jo + j + 11 > len(d):
                continue
            obj, bone = b(jo + j + 8), b(jo + j + 9)
            if bone <= 0x17:
                c.links.append((3, bone, obj))
    po = u(8)
    if po and po < len(d):
        q = po
        while q + 8 <= len(d):
            kind, off = u(q), u(q + 4)
            q += 8
            if kind == 0xFF:
                break
            if kind == 0 and po + off + 52 <= len(d):
                bone = b(po + off + 1)
                px, py, pz, _ = struct.unpack_from("<4f", d, po + off + 28)
                rx, ry, rz, obj = struct.unpack_from("<4H", d, po + off + 44)
                to_rad = lambda v: (v - 0x10000 if v & 0x8000 else v) / 0x8000 * math.pi
                c.physics[obj] = (bone, (px, py, pz), (to_rad(rx), to_rad(ry), to_rad(rz)))
                c.links.append((10, bone, obj))
    return c


def load_skeleton(code, version, skeleton_dir):
    """skeleton_dir: the user's Team Ninja importer 'skeletons' folder (or None)"""
    if not skeleton_dir:
        return None
    path = os.path.join(skeleton_dir, "%s.%s" % (code, VERSION_EXT.get(version, "doax")))
    if not os.path.exists(path):
        return None
    d = open(path, "rb").read()
    return [struct.unpack_from("<3f", d, 16 * i) for i in range(len(d) // 16)]


def bone_position(bones, bone):
    pos = np.zeros(3)
    n = 0
    while bone != -1 and bone < len(bones) and n < 32:
        pos += bones[bone]
        bone = PARENT[bone] if bone < len(PARENT) else -1
        n += 1
    return pos


def add_skeleton(scene, bones, source):
    """Fill scene.bones for the skeleton view: one joint per bone at the sum of its offsets. 'Unknown0' is an empty
    slot (zero offset, no parent) in every skeleton file, so it is left out."""
    keep = [b for b in range(min(len(bones), len(PARENT))) if BONE_NAMES[b] != "Unknown0"]
    at = {b: k for k, b in enumerate(keep)}
    for b in keep:
        scene.bones.append(dict(name=BONE_NAMES[b], parent=at.get(PARENT[b], -1), pos=bone_position(bones, b), part=None))
    scene.info["skeleton"] = source


def place(scene, cat, bones, nobjs):
    """Add one part per placed OBJ. Returns the number of objects that found a bone."""
    placed = {}
    for kind, bone, obj in cat.links:            # first link per object wins; high poly/joints before LOD/shadow
        if obj < nobjs and obj not in placed and scene.meshes[obj] is not None:
            placed[obj] = (kind, bone)
    for obj, (kind, bone) in sorted(placed.items()):
        if kind == 10 and obj in cat.physics:
            b, xyz, rot = cat.physics[obj]
            base = bone_position(bones, b) if bones and b < len(bones) else np.zeros(3)
            m = trs(base + np.array(xyz), tuple(math.degrees(a) for a in rot))
        else:
            m = trs(bone_position(bones, bone) if bones and bone < len(bones) else (0, 0, 0))
        name = BONE_NAMES[bone] if bone < len(BONE_NAMES) else "bone %d" % bone
        scene.add_part("%s%s" % (name, " (joint)" if kind == 3 else ""), obj, m, GROUP.get(kind, "Misc"),
                       visible=kind in (1, 2, 3, 10))
    for i, g in enumerate(scene.meshes):
        if g is not None and i not in placed:
            scene.add_part(g.get("name") or "OBJ_%d" % i, i, None, "Unassigned", visible=False)
    return len(placed)
