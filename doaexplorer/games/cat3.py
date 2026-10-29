"""The newer .cat (dword0 = 1): every DOA3 costume and DOA2U's DOA3-era 'A#' costumes.

Header: 5 dwords, the version (1) and the offsets of sections A-D. 46 of DOA3's 69 obfuscate it: dword0 = key | 1, and
dwords 1-4 are XORed with key >> 5, each next key being the last * 5 // 7.
A (+0x14): 0x100, 1, offset of the mesh lists (relative to A), then (type, offset) pairs and flags. The lists are OBJ
  numbers after a marker byte: 0xFE high poly for bones 0-14, 0xFD the eyes (bones 17, 21), 0xFB a second forearm
  segment (bones 19, 20: same place and turn as the forearms), 0xF9 low poly, 0xF8 shadow, 0xF7/0xF6 a few extras;
  0xFF ends them. Materials follow (not used).
B: hair and cloth physics (spring chains rooted on bones). C: 'LNK' vertex links. Neither is used.
D: the joint meshes (neck, elbows, knees...): an offset table, then per joint the end and start of its float block
  (relative to D), the OBJ, bone a, bone b, flags. The float block starts with bone b's rotation into bone a's frame
  (rows interleaved with an identity's), two pivots (repeated), then ring vertices (position, normal); index blocks
  follow it: a weight in 16ths, then lists of joint-mesh vertex offsets. Weight-16 rings sit rigidly on bone b, so
  joint mesh vertex = R * ring + t gives t, bone b's origin in bone a's frame; partly weighted rings are relative to a
  pivot lerped from the first to the second, which gives t too.
The joint meshes are stored in bone a's frame. Chaining the rotations from the hips gives every bone's bind
orientation: DOA3 stores each limb along its own Z axis, so they are needed on top of the skeleton offsets."""
import struct
import numpy as np
from ..scene import trs
from .cat_skel import BONE_NAMES, bone_position

HIGH, EYES, FOREARM2, LOW, SHADOW = 0xFE, 0xFD, 0xFB, 0xF9, 0xF8
EYE_BONES, FOREARM2_BONES = (17, 21), (19, 20)
SAME_AS = {19: 4, 20: 10}          # the second forearm segments move with the forearms in the bind pose
# a wrist joint's bone b is the second segment on the hand's side; files whose joint flags are all 0 number it 20 for
# the left hand and 19 for the right, the others the other way round
WRIST = {5: 4, 11: 10}
# bind rotations (rows; bone frame -> character frame). The joints give exactly these in all 69 DOA3 costumes; they
# fill in bones a costume's joints don't reach. Unlisted bones (hips, chest, head, hands, feet, eyes) are not turned.
BIND = {4: ((0, 0, -1), (0, 1, 0), (1, 0, 0)), 8: ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
        10: ((0, 0, 1), (0, 1, 0), (-1, 0, 0)), 14: ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
        6: ((0, -1, 0), (0, 0, -1), (1, 0, 0)), 7: ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
        12: ((0, 1, 0), (0, 0, -1), (-1, 0, 0)), 13: ((0, 1, 0), (0, 0, 1), (1, 0, 0))}
# joint meshes are named after the joint; bone a is the one whose frame they are stored in
JOINT_NAMES = {1: "Neck", 0: "Waist", 3: "LeftAnkle", 8: "LeftShoulder", 4: "LeftElbow", 7: "LeftKnee", 6: "LeftHip",
               5: "LeftWrist", 9: "RightAnkle", 14: "RightShoulder", 10: "RightElbow", 13: "RightKnee",
               12: "RightHip", 11: "RightWrist"}
PART_NAMES = dict(enumerate(BONE_NAMES[:15]))
PART_NAMES.update({17: "LeftEyeBall", 21: "RightEyeBall", 19: "LeftForeArm 2", 20: "RightForeArm 2"})


class Cat3:
    def __init__(self):
        self.header = []
        self.groups = {}      # marker -> [OBJ]
        self.joints = []      # dict(obj, a, b, R, r0, r1, rings, blocks)


def plain_header(d):
    h = list(struct.unpack_from("<5I", d, 0))
    if h[0] == 1:
        return h
    key = (h[0] ^ 1) >> 5
    out = [1]
    for v in h[1:]:
        out.append(v ^ key)
        key = key * 5 // 7
    return out


def parse(d):
    c = Cat3()
    c.header = h = plain_header(d)
    if h[1] != 0x14 or not all(0x14 <= o <= len(d) for o in h[2:]):
        raise ValueError("not a DOA3-style .cat")
    u = lambda o: struct.unpack_from("<I", d, o)[0]
    q = h[1] + u(h[1] + 8)
    cur = None
    while q < min(len(d), h[2]):
        b = d[q]
        q += 1
        if b == 0xFF:
            break
        if b >= 0xE0:
            cur = c.groups.setdefault(b, [])
        elif cur is not None:
            cur.append(b)
    jo = h[4]
    offs = []
    q = jo
    while q + 4 <= len(d) and u(q) and len(offs) < 64:
        offs.append(u(q))
        q += 4
    for o in offs:
        e = jo + o
        if e + 12 > len(d):
            continue
        fend, frow = jo + u(e), jo + u(e + 4)
        if not e < frow < fend <= len(d) or (fend - frow - 160) % 32:
            continue
        obj, a, b, fl = d[e + 8:e + 12]
        rows = np.frombuffer(d, "<f4", 24, frow).reshape(6, 4)[:, :3].astype(np.float64)
        piv = np.frombuffer(d, "<f4", 8, frow + 96).reshape(2, 4)[:, :3].astype(np.float64)
        rings = np.frombuffer(d, "<f4", (fend - frow - 160) // 4, frow + 160).reshape(-1, 8)[:, :3].astype(np.float64)
        blocks = []
        q = fend
        while q + 4 <= len(d):
            w = u(q)
            q += 4
            if w == 0 or w > 16:
                break
            lists = []
            while q + 4 <= len(d):
                lst = []
                while q + 4 <= len(d) and u(q) != 0xFFFFFFFF:
                    lst.append(u(q) // 32)
                    q += 4
                q += 4
                if not lst:
                    break
                lists.append(lst)
            blocks.append((w, lists))
        c.joints.append(dict(obj=obj, a=a, b=b, flags=fl, R=rows[1::2], r0=piv[0], r1=piv[1], rings=rings,
                             blocks=blocks))
    return c


def joint_offset(j, pos):
    """bone b's origin in bone a's frame from the joint's rings and its mesh (positions in bone a's frame), or None"""
    ts = []
    n = 0
    for w, lists in j["blocks"]:
        a = w / 16
        for lst in lists:
            if n >= len(j["rings"]):
                return None
            p = j["rings"][n]
            n += 1
            if not 0 <= lst[0] < len(pos):
                continue
            v = pos[lst[0]]
            ts.append(v - j["R"] @ p if w == 16 else (v - p - (1 - a) * j["r0"] - a * (j["R"] @ j["r1"])) / a)
    return np.median(ts, axis=0) if ts else None


def joint_bones(j):
    """(a, b) with a wrist joint's b resolved to the forearm on the hand's side"""
    a, b = j["a"], j["b"]
    return a, (WRIST[a] if a in WRIST and b in FOREARM2_BONES else b)


def bone_rotations(c):
    """bone -> 3x3 bind rotation (bone frame -> character frame), chained from the hips (not turned) through the
    joints, then BIND for the bones they don't reach; the second forearm segments take the forearm's."""
    W = {2: np.eye(3)}
    for _ in range(len(c.joints) + 1):
        grew = False
        for j in c.joints:
            (a, b), R = joint_bones(j), j["R"]
            if b in W and a not in W:
                W[a] = W[b] @ R.T
                grew = True
            elif a in W and b not in W:
                W[b] = W[a] @ R
                grew = True
        if not grew:
            break
    for b in list(range(15)) + list(EYE_BONES):
        W.setdefault(b, np.array(BIND[b], float) if b in BIND else np.eye(3))
    W.update({b: W[same] for b, same in SAME_AS.items()})
    return W


def skeleton_positions(bones):
    """bone -> position from a skeleton of per-bone offsets (cat_skel.PARENT chain)"""
    P = {b: bone_position(bones, b) for b in list(range(15)) + list(EYE_BONES) if b < len(bones)}
    P.update({b: P[same] for b, same in SAME_AS.items() if same in P})
    return P


def joint_skeleton(c, positions):
    """bone -> position from the joints alone (no hands without wrist joints, no eyes): the fallback when there is no
    skeleton table. positions: OBJ -> vertex positions."""
    W = bone_rotations(c)
    P = {2: np.zeros(3)}
    for _ in range(len(c.joints) + 1):
        grew = False
        for j in c.joints:
            a, b = joint_bones(j)
            if (a in P) == (b in P) or j["obj"] not in positions:
                continue
            t = joint_offset(j, positions[j["obj"]])
            if t is None:
                continue
            if b in P:
                P[a] = P[b] - W[a] @ t
            else:
                P[b] = P[a] + W[a] @ t
            grew = True
        if not grew:
            break
    P.update({b: P[same] for b, same in SAME_AS.items() if same in P})
    return P


def place(scene, c, P, nobjs):
    """One part per OBJ the .cat names, turned and moved to its bone (P: bone -> position). Returns the meshes it
    placed; the others are left to the caller."""
    W = bone_rotations(c)
    placed = set()

    def add(obj, bone, name, group, visible):
        if obj in placed or obj >= nobjs or scene.meshes[obj] is None or bone not in P:
            return
        m = trs(P[bone])
        m[:3, :3] = W.get(bone, np.eye(3))
        scene.add_part(name, obj, m, group, visible)
        placed.add(obj)
    for marker, bones, group, visible in ((HIGH, range(15), "Character", True), (EYES, EYE_BONES, "Character", True),
                                          (FOREARM2, FOREARM2_BONES, "Character", True),
                                          (LOW, range(15), "Low poly", False), (SHADOW, range(15), "Shadow", False)):
        for obj, bone in zip(c.groups.get(marker, ()), bones):
            add(obj, bone, PART_NAMES[bone], group, visible)
    for j in c.joints:
        add(j["obj"], j["a"], JOINT_NAMES.get(j["a"], PART_NAMES.get(j["a"], "bone %d" % j["a"]) + " joint"),
            "Character", True)
    return placed
