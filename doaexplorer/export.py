"""OBJ (+MTL+PNG, zipped), GLB and texture-zip export of a Scene.
Geometry goes through basis * part matrix - exactly what the viewer shows. Winding is kept as stored
(materials are double-sided), matching the original DOA2U exporter."""
import io, json, struct, zipfile
import numpy as np


def flatten(scene, part_ids):
    B = np.array(scene.basis["m"], float).reshape(4, 4).T
    out = []
    for pi in part_ids:
        if pi < 0 or pi >= len(scene.parts):
            continue
        p = scene.parts[pi]
        g = scene.meshes[p["mesh"]] if 0 <= p["mesh"] < len(scene.meshes) else None
        if g is None:
            continue
        M = B @ np.asarray(p["m"], float)
        pos = g["pos"].astype(np.float64) @ M[:3, :3].T + M[:3, 3]
        nrm = g["nrm"].astype(np.float64) @ np.linalg.inv(M[:3, :3])  # inverse-transpose for normals
        ln = np.linalg.norm(nrm, axis=1, keepdims=True)
        nrm = np.divide(nrm, ln, out=np.zeros_like(nrm), where=ln > 0)
        subs = []
        for s in g["subs"]:
            tris = g["idx"][s["start"]:s["start"] + s["count"]].reshape(-1, 3).astype(np.int64)
            subs.append(dict(tex=s["tex"], blend=scene.sub_blend(s), tris=tris))
        out.append(dict(name=p["name"].replace(" ", "_"), group=p["group"], pos=pos, nrm=nrm, uv=g["uv"], subs=subs))
    return out


def mat_key(s):
    return (s["tex"], s["blend"])


def mat_name(k):
    return ("tex%03d" % k[0] if k[0] >= 0 else "untextured") + {"blend": "_alpha", "mask": "_cutout"}.get(k[1], "")


def safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def export_obj_zip(scene, part_ids, name):
    name = safe(name)
    flat = flatten(scene, part_ids)
    obj = io.StringIO()
    obj.write("# Dead or Alive Explorer export: %s\nmtllib %s.mtl\n" % (name, name))
    base = 1
    mats = {}
    for f in flat:
        obj.write("o %s\n" % f["name"])
        obj.write("".join("v %.6f %.6f %.6f\n" % tuple(v) for v in f["pos"]))
        obj.write("".join("vt %.6f %.6f\n" % (v[0], 1.0 - v[1]) for v in f["uv"]))
        obj.write("".join("vn %.6f %.6f %.6f\n" % tuple(v) for v in f["nrm"]))
        for s in f["subs"]:
            k = mat_key(s)
            mats[k] = True
            obj.write("usemtl %s\n" % mat_name(k))
            obj.write("".join("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a, a, a, b, b, b, c, c, c) for a, b, c in s["tris"] + base))
        base += len(f["pos"])
    mtl = io.StringIO()
    used_tex = set()
    for k in mats:
        mtl.write("newmtl %s\nKd 1 1 1\nKa 0 0 0\nKs 0 0 0\n" % mat_name(k))
        if k[0] >= 0:
            mtl.write("map_Kd textures/tex%03d.png\n" % k[0])
            used_tex.add(k[0])
            if k[1] != "opaque":
                mtl.write("map_d textures/tex%03d.png\n" % k[0])
        mtl.write("\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name + ".obj", obj.getvalue())
        z.writestr(name + ".mtl", mtl.getvalue())
        for t in sorted(used_tex):
            z.writestr("textures/tex%03d.png" % t, scene.texture_png(t))
    return buf.getvalue()


def export_textures_zip(scene, name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, t in enumerate(scene.textures):
            z.writestr("%s_%03d_%s.png" % (safe(name), i, safe(t["name"])), scene.texture_png(i))
    return buf.getvalue()


def export_glb(scene, part_ids, name):
    flat = flatten(scene, part_ids)
    bin_ = bytearray()
    views, accs, meshes, nodes = [], [], [], []

    def add_view(data, target=None):
        while len(bin_) % 4:
            bin_.append(0)
        v = {"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data)}
        if target:
            v["target"] = target
        bin_.extend(data)
        views.append(v)
        return len(views) - 1

    def add_acc(arr, ctype, typ, target, minmax=False):
        vi = add_view(arr.tobytes(), target)
        a = {"bufferView": vi, "componentType": ctype, "count": int(len(arr)), "type": typ}
        if minmax:
            a["min"] = [float(x) for x in arr.min(0)]
            a["max"] = [float(x) for x in arr.max(0)]
        accs.append(a)
        return len(accs) - 1

    mat_ids, materials = {}, []
    tex_ids, images, textures = {}, [], []

    def get_mat(k):
        if k in mat_ids:
            return mat_ids[k]
        m = {"name": mat_name(k), "doubleSided": True,
             "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 1.0}}
        if k[0] >= 0:
            if k[0] not in tex_ids:
                vi = add_view(scene.texture_png(k[0]))
                images.append({"bufferView": vi, "mimeType": "image/png", "name": "tex%03d" % k[0]})
                textures.append({"source": len(images) - 1, "sampler": 0})
                tex_ids[k[0]] = len(textures) - 1
            m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex_ids[k[0]]}
        m["alphaMode"] = {"blend": "BLEND", "mask": "MASK"}.get(k[1], "OPAQUE")
        if k[1] == "mask":
            m["alphaCutoff"] = 0.5
        materials.append(m)
        mat_ids[k] = len(materials) - 1
        return mat_ids[k]

    for f in flat:
        if not f["subs"]:
            continue
        pa = add_acc(f["pos"].astype("<f4"), 5126, "VEC3", 34962, True)
        na = add_acc(f["nrm"].astype("<f4"), 5126, "VEC3", 34962)
        ua = add_acc(np.asarray(f["uv"]).astype("<f4"), 5126, "VEC2", 34962)
        prims = []
        for s in f["subs"]:
            if not len(s["tris"]):
                continue
            ia = add_acc(s["tris"].reshape(-1).astype("<u4"), 5125, "SCALAR", 34963)
            prims.append({"attributes": {"POSITION": pa, "NORMAL": na, "TEXCOORD_0": ua}, "indices": ia,
                          "material": get_mat(mat_key(s))})
        if not prims:
            continue
        meshes.append({"name": f["name"], "primitives": prims})
        nodes.append({"name": f["name"], "mesh": len(meshes) - 1})
    gltf = {"asset": {"version": "2.0", "generator": "Dead or Alive Explorer"},
            "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
            "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(bin_)}],
            "materials": materials, "images": images, "textures": textures,
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    while len(bin_) % 4:
        bin_.append(0)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js +
            struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_))
