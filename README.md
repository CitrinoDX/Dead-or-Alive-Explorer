# Dead or Alive Explorer

A local viewer for the models and textures of the Xbox and Xbox 360 Dead or Alive games. A small Python server reads the game
archives directly (CRI AFS archives, Xbox disc images) and a WebGL2 page shows the assembled characters, stages and
textures, with OBJ, GLB, FBX and PNG export.

**No game data is included.** Use your own copies of the games. The viewer only ever reads them: nothing is modified,
and the only file it writes is its own `config.json`.

## Quick start
1. Install Python 3.8 or newer and numpy (`python -m pip install numpy`).
2. Start it: on Windows double-click **`Dead or Alive Explorer.bat`**, elsewhere run `python run_explorer.py`. Your browser
   opens the viewer (it runs at http://127.0.0.1:8765/ and works offline).
3. On first run the **Setup** panel opens. Click *Add folder…* or *Add disc image…* (or paste a path) and point it at
   your game files; the viewer works out which game it is and remembers it. Setup is always one click away in the sidebar.

| Game | Point it at | Notes |
|---|---|---|
| Dead or Alive 2 Ultimate (Xbox) | the game folder (or its `DOA2` subfolder) with `datahdd2.afs` / `datadvd.afs` / `datahdd.afs` | adding the game folder also finds DOA1 Ultimate |
| Dead or Alive 1 Ultimate (Xbox) | the DOA2U game folder, or its `DOA1/data` folder | |
| Dead or Alive Xtreme Beach Volleyball (Xbox) | the disc image (`.iso`), or an extracted folder with `datadvd.afs` / `datahdd.afs` | read straight from the image, nothing to extract |
| Dead or Alive Xtreme 2 (Xbox 360) | the disc image (`.iso`), or an extracted folder with `chr.afs`, `werone.afs`, ... and `default.xex` | read straight from the image; assembles without extra data |
| Dead or Alive 4 (Xbox 360) | the disc image (`.iso`), or an extracted folder with `chrone.afs` / `chrtwo.afs` / `chrthree.afs` | read straight from the image; assembles without extra data |

### Optional: limb assembly data
DOA2U, DOA1U and DOAX store costumes as loose limbs. To assemble them, the viewer reads third-party data you may already
have; it is not included in this project. Add either folder in Setup:
- your **GreedXplorer** folder (its `doau2data`, `doau1data`, `doa3data`, `doaxdata` layout folders): DOA2U, DOA1U and the
  DOA3-era DOA2U costumes;
- the **Team Ninja Blender importer** (2013) folder or its `skeletons` subfolder: DOAX bodies and swimsuits, and the
  skeleton view for DOA2U.

Without them every model still loads with its textures, but the limbs sit at their stored origins.

### Command line (optional)
```
python run_explorer.py "D:\Games\Dead or Alive 2 Ultimate"     # add any folder or disc image it recognises
python run_explorer.py --doax2 DIR --doa4 ISO --greedxplorer DIR --skeletons DIR
options: --port 8765  --no-browser  --forget KEY  --version
```
`names.json` (optional, next to `run_explorer.py`): `{"tra": "Trainer"}` display-name overrides for character codes.

## What it does
- Sidebar: game switcher, then characters > costumes / stages / other resources. Search, ←/→ for prev/next.
- 3D view: assembled model, shading modes, wireframe, parts panel (toggle/hover), OBJ, GLB or FBX export of what is
  visible. The FBX embeds its textures and carries the skeleton too (not skinned).
  Culling button / **Alt+C** cycles GreedXplorer's four modes in its order: none, CW (back faces), CCW (front faces),
  per material (default, remembered between visits). The parts panel's ▾ shrinks it to its header (remembered per game).
- Character picker (DOAX2, right side above the parts panel): choose a girl, a head and a swimsuit and they load as one
  model, ready for the export buttons; ←/→ step through the swimsuits. Heads: her hairstyles (dry and wet), or any other
  girl's head as a head swap. Swimsuits: hers first, then every other girl's that has a fit for her body type. The parts
  panel starts minimised in DOAX2 to make room.
- Skeleton view (dropdown or `B`): off, drawn on top of the model, or the skeleton alone. The **Bones** tab in the parts
  panel lists the hierarchy; hovering a bone or a joint names it, clicking centres the view on it. A bone that belongs to
  a part shows only while that part does. Available wherever the limbs are assembled from bone data: DOA2U and DOAX
  (the importer's skeleton files, or one embedded in the `.cat`), DOAX2 and DOA4 (the file's node tree). DOA1U has none yet.
- Texture browser (button or `T`): every texture with size and format, a lightbox with zoom, an alpha toggle and Save PNG,
  "Ignore alpha" for normal/specular maps, and "Download all" as a zip. Texture-only files (UI, sprites) open here directly.
- Links: `#game/id` in the URL opens that entry; back/forward work.

## Status
| Game | Status |
|---|---|
| DOA2U | 418/418 entries load. Costumes assemble with GreedXplorer layouts (258 exact); the 25 `A#` costumes are DOA3 models and use GreedXplorer's DOA3 layouts, matched by mesh and texture count |
| DOA1U | 135/135 load. Only gen00/jan00/jan01 have layouts and there are no `.cat` files, so the rest show unassembled. Stages are texture-only |
| DOAX | 2593/2593 load. Bodies (`v<code>NN`) and ~2000 swimsuits/accessories (`md<item><wearer>`) placed from each `.cat` bone map + the wearer's skeleton. 19 items use a newer `.cat` variant and show unassembled |
| DOAX2 | 1016/1016 load. Bodies, heads, swimsuits, items, boats, stages; placed from the file's own node tree. Heads are listed by hairstyle, each with its wet version. Swimsuits are listed by their shop names and show the owner's fit; the fits for the other body types are toggles in the parts panel. The character picker dresses any girl in any head and fitting swimsuit |
| DOA4 | 854/854 load and every texture on the disc decodes (19,952). 23 characters plus a cutscene cast (117 costumes, 25 heads, 17 colour variants listed with their base), 24 stages, effects, menus and 635 online-lobby avatar parts; placed from the file's own node tree. Head-swap characters get their `AA` head, the other hairstyles are toggles in the parts panel |

## Versions
Numbered MAJOR.MINOR.PATCH; 0.x while it is a work in progress. The version shows in the Setup panel, at startup and
with `--version`.
- **0.3.0**: DOAX2 read straight from the disc image. DOAX2 swimsuits are named after their shop names and fitted to
  each body type (the owner's fit shows; the other fits are toggles in the parts panel); heads are named by hairstyle,
  each with its wet version. Skeleton view, sphere-mapped reflection textures, game picker dropdown. Fixes: every DOA2U /
  DOA1U / DOAX material is read, TPR alpha blending comes from the material flag, Kokoro's hair is no longer white
  (DOAX2, DOA4).
- **0.2.0**: Dead or Alive 4 (Xbox 360), read straight from the disc image. Low-detail, shadow and prop objects start
  hidden; head-swap characters get their head attached, with alternate hairstyles in the parts panel.
- **0.1.0**: first public release. DOA2U, DOA1U, DOAX and DOAX2; Setup panel; OBJ/GLB/PNG export.

## Code layout
- `run_explorer.py`: command line. `doaexplorer/server.py`: HTTP API (`/api/games`, `/api/setup`, `/api/library/<game>`,
  `/api/model/<game>/<id>`, `/api/tex/<game>/<id>/<n>.png[?opaque=1]`, `/api/textures/<game>/<id>.zip`,
  `/api/export/<game>/<id>.obj.zip|.glb|.fbx?parts=`) plus the Setup endpoints, which only answer pages served from this machine.
- `doaexplorer/config.py`: `config.json` (per machine, not committed). `doaexplorer/sources.py`: the optional GreedXplorer and
  skeleton folders.
- `doaexplorer/scene.py`: the common model every game produces (meshes, parts with 4x4 matrices, textures, bones for the
  skeleton view, orientation basis).
- `doaexplorer/texture.py`: DXT1/3/5, BC5, Xbox swizzled/linear formats (incl. P8 + palette, V8U8), Xbox 360 tiling + byte swaps, PNG.
- `doaexplorer/export.py`: OBJ zip, GLB, FBX, texture zip. `doaexplorer/fbx.py`: binary FBX 7.4 writer.
  `doaexplorer/afs.py`: AFS reader. `doaexplorer/vfs.py`: folder or Xbox disc image (XDVDFS).
- `doaexplorer/games/`: `doa2u.py`, `doa1u.py`, `doax.py`, `doax2.py`, `doa4.py`, plus format modules `xbox_crypt.py`, `xpr_mdl.py`,
  `gx_layout.py`, `cat_skel.py` (.cat bone map + skeleton placement), `tpr.py`.
  A new game is one module with `find_root`, `tree`, `load` and an entry in `games/__init__.py`.
- `tools/`: standalone AFS survey/extract and memory-dump helper scripts.

## Format notes
Verified unless marked otherwise.
- AFS: `AFS\0`, count, (offset,size) TOC, then a pointer to 48-byte name records (32-byte name + 16 meta).
- DOA2U scramble: XPR if `(dword0 & 0xffffff00)==0x306ea300`: seed=dword0^0x30525058, XOR dwords from 12 with MT19937+0x31415926, restore 'XPR0'.
  CAT if `0x003cf300`: seed=dword0^0x20, count=dword@16>>2, data from 20. (Vectorised; byte-exact with the original.)
- XPR0 resources: user blocks (bit 31, size follows; 'MDL\0' is Team Ninja's), textures (20 bytes), VB/IB/palette (12 bytes).
  **Texture width = 1<<((fmt>>20)&15), height = 1<<((fmt>>24)&15)** (swapping them garbles non-square textures: 161 of 174
  decode cleanly this way, and the XPR-EMP importer agrees). P8 palettes are the palette resource right after the texture.
- MDL OBJ (regular): 'OBJ\0', weight count, 4, ?, bound, 4 slots (vtxnum, vtxofs, idxnum, idxofs) at +0x20, materials at +0xA0.
  **Every vertex is pos(3), then one float per blend weight, then the slot's attributes** (slot 0: normal(3) uv(2)); the main
  UV is always the last pair. DOA2U uses 0-1 weights, DOAX up to 3. Reading the weight as part of the normal breaks
  UVs on joint meshes. Materials draw `indices[start : start+tris+2]` as one strip.
- DOAX costume XPRs are plain: only the magic dword is overwritten. Their `.cat` files are plain too (DOA2U's are scrambled).
- `.cat` placement (DOAX, DOA2U regular): (offset, type) sections after +0x14; type 1 = bone list of (id, bone, OBJ) triples
  (type 9 = low poly), 5 = shadow, 8 = embedded skeleton; +8 physics table, +16 joints. A limb sits at the sum of its skeleton
  bone offsets up a fixed 24-bone parent chain; this reproduces DOAX2's node positions exactly (Ayane's head at y = 0.507).
  A newer variant (dword0 = 1; DOA2U `A#`, 19 DOAX items) has a different section layout and is not decoded.
- The importer's skeleton files (`<code>.doau/.doa3/.doax`: 24 bones of x, y, z, pad; Tengu has 30 with wings) put DOA2U's
  joints within a few millimetres of GreedXplorer's limb positions, so layout-placed costumes get that skeleton too.
  Slot 15 ("Unknown0") is zero in every file and is left out.
- MDL OBJ (compact; DOA2U `A#`, DOA1U; inferred): slots at +0x10, bound at +0x50, materials at +0x60. Each material has a header,
  colours, ntex texture refs `(unit, type, flags, texture id)`, then strip records `(slot, (n+2)*32, start, n)`. The index
  buffer is one stitched strip, so a record covers `indices[start : start+n+4]`. Materials are only dword-aligned.
- GX layouts: limbs are stored around their own pivots; `tx/ty/tz` place them, and mirror meshes go at -tx **with mirrored
  rotation (rx, -ry, -rz)**, which fixes the missing left forearm on DOA1U. DOA2U layouts never rotate mirrored parts.
- XPR2/TPR (360, big-endian): USER chunks (header, MdlGeo, MdlInfo, Hie), TX2D/VBUF/IBUF into the data block. Chunk tables:
  count at +0x14, offsets at +0x20. Vertex decls are D3DDECLTYPE layers (FLOAT3, HEND3N, FLOAT16_2, ...). Strips use 0xFFFF
  restarts. Hie nodes are row-vector 4x4 matrices with parent node indices, one per object (node index = object index);
  that tree is the skeleton view. DOAX2 swimsuits carry ~150 extra nodes with no mesh (bare bones).
  DOAX2 bodies have no head: heads and hair are the `<code><style><wet>` files. The first letter is the hairstyle
  (Kasumi A-D, Ayane, Hitomi, Lei Fang and Helena A-B), the second A dry or B wet: the same hairstyle lying 5-20 mm
  flatter, bangs reaching up to 40 mm less far forward. Two exceptions: `vhtAB` has exactly `vhtAA`'s shapes (no real wet
  headband head), and `vcoBA` is Kokoro's dry head with a different face texture (ears painted in; use unknown).
  Head files are stored around their own root node, not in body space. The root goes on the body's head node (object 1:
  meshless, or a 3-vertex stub in Hitomi's body). Then the head's eyes land on the body's eye nodes (objects 8 and 27)
  within 3 mm for eight girls; Lisa is 13 mm off because her eye nodes are Helena's. Bodies of one type differ only in
  object 21, the neck piece, so a head swap within a body type also brings the head owner's neck and joins seamlessly.
  Across body types the join and the skin tone can show.
  A colour map on UV set 1 multiplies the UV-set-0 one; it is usually a 1x1 to 32x32 white stand-in. Where the UV-set-0
  map is plain white with the shape in its alpha (Kokoro's hair in DOAX2 and DOA4, Brad's torn cloth in DOA4 `bra01`, a
  few stage pieces), the viewer bakes one texture: the two maps multiplied where both UV sets are the same (Brad), else
  the mask filled with the colour map's mean colour (Kokoro's runs along the strands on its own UVs).
  Texture headers are 0x34 bytes in DOAX2 and 0x28 in DOA4; both end with the 6-dword GPU fetch constant, so it is read
  from the end. DOA4 also uses format 0x0A (8_8, stage water-ripple frames).
  Material alpha blending is the dword at +0x50: it is set on every material whose texture has alpha (DOA4 characters
  1124/1124, DOAX2 699/699). The dword at +0x04 only ever appears on opaque textures and is not the transparency flag.
- DOAX2 body types: the nine girls share five skeletons (joint positions identical to 0.0000): Kasumi + Ayane, Helena +
  Lisa, Hitomi + Kokoro + Lei Fang, Christie, Tina. Bodies of the same type differ only in the neck piece. Swimsuits
  (`<owner>_<type>_<letter>_m` in werone/wertwo) hold the outfit once per body type, each a separate 37-node tree that
  repeats that type's joints exactly (290 of 340 files; the nearest other type is 7 mm off). 49 files hold one fit: the
  14 gifts from Zack, the only character-specific swimsuits (every `cs_` file plus Kasumi's three `vks_hn_i`), and 35
  per-body-type files of Leifang's five qipao (`vks_on_p`, `vle_on_i`, `vhe_on_r`, `vtn_on_s`, `vcr_on_u`) and Kasumi's two
  sailor fuku (`vks_sk_f`, `vht_sk_k`, `vhe_sk_i`, `vtn_sk_j`, `vcr_sk_l`), whose prefix names the body type, not the
  owner. All 308 shop swimsuits (the wiki's nine lists) are named in the viewer, matched by texture; the file name stays
  in the info line. Some sets sit under another girl's prefix: Lisa's butterfly bikinis (`vay_dl_i`) and Venus
  (`vcr_vs_b`), Tina's G-string bikinis (`vco_dl_g`), Christie's bunny suits (`vtn_on_m`). Kokoro's three crop tops
  (`vco_sh_e`) are stored twice; the second copy, with a see-through shirt, is listed as the wet one. Same-name repeats are design
  variants (textures always differ, geometry usually). Loose objects outside the trees: a fit's objects form one run of
  object indices, and its loose pieces (rigid cups and bows) sit at the same offset in or just before every run; a loose
  tree split off a fit (Tina's bottom in `vht_ch_a`) keeps its other nodes inside that fit's run. Pieces stored once (bead
  rows, tassel chains, helper quads, ornaments kept with the middle fit only) are shared props. Node list order is not
  object order in these files.
- DOA4 character files hold the model three times: full detail, a low-detail copy, and an untextured shadow copy built from
  the low one (its objects have the low copy's exact bounds). The viewer pairs each shadow object with the same-bounds
  textured object closest in vertex count; the hierarchy root those partners belong to is the low-detail set. Both start
  hidden, as do "extras": single quads (shadow planes) and props reaching 0.5 past the body (Zack's rope runs 500 units out).
- DOA4 head swaps: characters whose shadow copy has 14 objects instead of 15 (Kasumi, Helena, Lei Fang, Ayane, Kokoro,
  Hitomi, Ein, Jann Lee, Eliot, La Mariposa, Christie) stop at the neck; `<code>AA/BA/...` are faces and hair. Each head
  file is stored relative to a different body node (hips, chest or neck), so it is placed by the eyes both files carry:
  meshes under the face that match a body mesh, most common offset (hair ornaments some bodies share hang off other roots
  and would mislead). Helena's eyes differ; there the head file's low-detail head, which is stored in body space, gives
  the offset, and it puts her eyes exactly on her body's eye nodes. Some alternate hairstyles mix conventions per piece,
  so they take the candidate offset that puts their face where the `AA` face went. All 25 heads land at head height
  (y 0.55-0.63) on every body of their character.
- DOA4 colour variants (Lei Fang `CA`-`CG`, Kokoro `AA`-`AG`, ...) store the same `.tpr` again next to a different `.cat`;
  the `.cat` differences are material colour floats (tints). Listed once, with the variant names in the note.
- Orientation: basis diag(-1,1,-1), camera yaw = pi; matches GreedXplorer's view. Exports use the same transform.
  Front faces are **counter-clockwise**: the winding agrees with the stored vertex normals on 99.5-100% of triangles in
  DOA2U, DOAX and DOAX2. Treating them as clockwise hides the outside of single-sided materials and flips the lighting.
  The compact format's strip parity is unreliable, so its triangles are oriented by their normals instead (100% after).
- Culling, read from GreedXplorer's code (memory dump of GX_003D.exe): Alt+C cycles a variable 1 -> 2 -> 3 -> 4 -> 1 (1-3 =
  D3DCULL_NONE/CW/CCW set globally; 4 = per material, the default). Per material it sets the cull mode from the material
  dword at +0x0C: regular OBJ `0` or `0x900` -> CW, `0x901` -> CCW, anything else -> none (0x48EBB0); compact OBJ the same
  without the `0` case (0x48EBD4). So only flag 0 is single-sided: thin cloth with bit 0 (Ayane's bow, aprons, sleeves) and
  hair (bit 3) render double-sided. GreedXplorer's view is mirrored, so its CW hides back faces (CULL_BACK here).
  GreedXplorer blends with depth writes left on, so hair layers drawn first hide the ones behind; that is a layering
  problem, not culling, and the viewer's two-pass alpha drawing (below) avoids it.
  DOA1U/`A#` (compact) and DOAX2 materials carry no cull flag, so per-material mode leaves them double-sided.
- Transparency: the material "transparent" bit (id 0x80000001) is often set on fully opaque textures (Ayane's bow is DXT1
  with alpha 255 everywhere). Blending those without depth writes showed their inside, so each flagged material is drawn by
  its texture's real alpha: opaque -> solid, only clear/solid pixels -> alpha-tested cut-out (still writes depth), real
  translucency (hair) -> two passes: the solid core (alpha >= 0.85) is drawn with depth writes so front layers hide back
  ones, then the soft edges are blended on top without depth writes. GLB export uses the same classes (OPAQUE / MASK / BLEND).
- FBX export: binary 7.4, Y up, metres with `UnitScaleFactor` 100 (Blender and Unity import it at the GLB's size), one
  mesh per part in world space like the GLB. Textures are embedded. Importers take alpha from any RGBA diffuse texture
  (Blender checks only the image depth), so opaque materials embed an RGB copy and only alpha-tested / blended ones get
  the RGBA texture, also linked as `TransparentColor`. Bones are a `LimbNode` tree under a `skeleton` null, positions only
  (the data has no joint orientations, so Blender points them all one way unless *Automatic Bone Orientation* is ticked).
  Checked against both Blender 5.0 FBX importers (positions, UVs, normals, materials and bone positions match the GLB and
  the viewer); not tried in Autodesk software.

## Open items
- DOA1U: 48 costumes have no layout and there are no `.cat` files, so they need more layouts or another skeleton source.
  It has no skeleton view: its proportions differ from the DOA2U skeleton files (Gen Fu's DOA1U layout puts each
  shoulder 5 cm further in than `gen.doau`).
- Skeleton view: TPR node trees have no bone names (bones are named after their objects). The FBX skeleton is not bound
  to the meshes (blend weights are not decoded); OBJ and GLB carry no bones.
- The newer `.cat` variant (dword0 = 1) is not decoded. One `A#` material references texture 190 of 41 (unknown shared table).
- DOAX: no "wear swimsuit on body" combination yet (each file is shown on its own); stages show at their stored origins.
- DOAX2: LOD/shadow meshes are not separated (the `.cat` "long way" isn't decoded); no skinning or morphs; small textures that
  live in a packed mip tail may decode wrong.
- DOA4: `.cat` material tints are not applied, so colour variants look like their base. Which head goes with which costume in-game isn't known; `AA` is always the default.
  Stages show the first colour map of each material (no lightmaps), and some frame wide because of distant scenery
  cards. No skinning or animation.
- DOA2U: env-map layers are still guesses; `.mot` animations not parsed.
- Unnamed codes: DOA1U `tra`; DOAX `vun`. Use names.json.

## License
Dead or Alive Explorer © 2026 by CitrinoDX is licensed under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) (Attribution-NonCommercial-ShareAlike 4.0
International); the full text is in [LICENSE](LICENSE). It covers this project's own code and documentation only. It
grants no rights to the games' content, to GreedXplorer's layouts, or to the Team Ninja importer's files.

## Credits
- **GreedXplorer** and the layout authors credited in its files (Kaz, Dony & Kaz): the per-costume limb layouts and
  signature tables the viewer can read from your copy, and the reference for culling behaviour.
- The **Team Ninja Blender importers** (TMC / TPR / XPR-EMP, 2013): format notes for TPR and XPR-EMP, and the skeleton files
  the viewer can read from your copy.
- The wider Xbox modding community's documentation of XPR, XDVDFS and Xbox 360 texture tiling.

Not affiliated with or endorsed by Koei Tecmo or Team Ninja. Dead or Alive is a trademark of Koei Tecmo. This project
contains no game assets.
