#!/usr/bin/env python3
"""Build the GeneralsX content pack (GeneralsXContent.big).

GeneralsX @feature Claude 15/10/2026 Generates our own models and textures, renders their
command-bar cameos, copies the INI and string sources from content/ and packs everything into
one .big next to the game executable. Nothing from the retail game goes into the pack: the INI
only references retail names (sounds, effects, weapons), which load from the player's own copy.

Usage: build_content.py <repo root> <output dir> [--art] [--preview <dir>]

GeneralsX @tweak Claude 16/10/2026 The procedural USA models fell short of the art bar, so the pack ships
without them (and without their ArtRemap INI and cameos): the game draws the retail art. --art still
builds the models and cameos into the pack, for the self-test and for previews.
"""

import argparse
import os
import re
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "models"))

import textures  # noqa: E402
import w3d  # noqa: E402
from PIL import Image  # noqa: E402
from render import render  # noqa: E402
import gx_ambulance  # noqa: E402
import gx_apache  # noqa: E402
import gx_buildings  # noqa: E402
import gx_infantry  # noqa: E402
import gx_chinook  # noqa: E402
import gx_dozer  # noqa: E402
import gx_jets  # noqa: E402
import gx_jltv  # noqa: E402
import gx_mlrs  # noqa: E402
import gx_mbt  # noqa: E402
import gx_microwave  # noqa: E402

PACK_NAME = "GeneralsXContent.big"


def write_big(path, files):
    """files: list of (archive path with backslashes, bytes). Same layout as retail .big archives."""
    entries = sorted(files, key=lambda f: f[0].lower())
    header_size = 16 + sum(8 + len(name.encode("ascii")) + 1 for name, _ in entries)
    offset = header_size
    table = b""
    for name, data in entries:
        table += struct.pack(">II", offset, len(data)) + name.encode("ascii") + b"\0"
        offset += len(data)
    with open(path, "wb") as f:
        f.write(b"BIGF" + struct.pack("<I", offset) + struct.pack(">II", len(entries), header_size))
        f.write(table)
        for _, data in entries:
            f.write(data)


# Unit art: model name -> (builder, cameo name). Damaged models share geometry with scorched paint.
TAN = [(176, 160, 118), (128, 116, 82), (92, 86, 64)]
WOODLAND = [(98, 104, 74), (70, 64, 46), (44, 46, 38)]
HELI = [(92, 98, 88), (78, 84, 76), (64, 70, 64)]
JET = [(150, 156, 162), (128, 134, 140), (108, 114, 120)]
# Soldiers: uniform camouflage and the colour of their gear.
INFANTRY = {
    "GXIRNG": ([(150, 132, 100), (112, 104, 78), (92, 98, 74)], (150, 128, 92)),
    "GXISNP": ([(96, 100, 70), (74, 70, 48), (120, 114, 84)], (88, 92, 62)),
    "GXIBRT": ([(70, 72, 66), (52, 54, 50), (88, 86, 74)], (66, 68, 60)),
    "GXIMDF": ([(132, 128, 104), (104, 100, 80), (84, 88, 70)], (120, 110, 84)),
    "GXIPLT": ([(118, 122, 98), (112, 116, 94), (106, 110, 90)], (92, 98, 78)),
}


def build_textures(tex_dir):
    out = {}
    out["gxmbt_body.tga"] = textures.camo_atlas(1024, seed=11, palette=TAN)
    out["gxpal_body.tga"] = textures.camo_atlas(1024, seed=21, palette=WOODLAND)
    out["gxheli_body.tga"] = textures.camo_atlas(1024, seed=31, palette=HELI)
    out["gxjet_body.tga"] = textures.camo_atlas(1024, seed=51, palette=JET)
    for name in ("gxmbt_body", "gxpal_body", "gxheli_body", "gxjet_body"):
        out[name + "d.tga"] = textures.burnt(out[name + ".tga"], seed=12)
    out["gxmbt_tread.tga"] = textures.tread(256, 64, links=8, seed=13)
    out["gxteam.tga"] = textures.team_panel(128, seed=14)
    out["gxflash.tga"] = textures.flash(128)
    out["gxglass.tga"] = textures.glass(128, seed=15)
    for k, (name, (palette, gear)) in enumerate(INFANTRY.items()):
        out[name.lower() + ".tga"] = textures.infantry_atlas(256, seed=61 + k, palette=palette, gear=gear)
    out["gxbld_wall.tga"] = textures.building_atlas(1024, seed=41)
    out["gxbld_walld.tga"] = textures.burnt(out["gxbld_wall.tga"], seed=42)
    for name, img in out.items():
        textures.save_tga(img, os.path.join(tex_dir, name))
    disc_rgb, disc_alpha = textures.rotor_disc(256)
    textures.save_tga(disc_rgb, os.path.join(tex_dir, "gxrotor.tga"), alpha=disc_alpha)
    out["gxrotor.tga"] = disc_rgb
    return out


def build_models(w3d_dir, tex):
    models = {}
    for suffix, d in (("", ""), ("_D", "d")):
        models["AVGXMBT" + suffix] = gx_mbt.build(
            "AVGXMBT" + suffix, f"gxmbt_body{d}.tga", "gxmbt_tread.tga", "gxteam.tga", "gxflash.tga")
        models["AVGXPAL" + suffix] = gx_mbt.build(
            "AVGXPAL" + suffix, f"gxpal_body{d}.tga", "gxmbt_tread.tga", "gxteam.tga", "gxflash.tga", variant="paladin")
        models["AVGXDOZ" + suffix] = gx_dozer.build("AVGXDOZ" + suffix, f"gxmbt_body{d}.tga", "gxteam.tga")
        models["AVGXJLTV" + suffix] = gx_jltv.build(
            "AVGXJLTV" + suffix, f"gxmbt_body{d}.tga", "gxteam.tga", "gxglass.tga", "gxflash.tga")
        models["AVGXMLRS" + suffix] = gx_mlrs.build("AVGXMLRS" + suffix, f"gxpal_body{d}.tga", "gxmbt_tread.tga", "gxteam.tga")
        models["AVGXCHINOOK" + suffix] = gx_chinook.build(
            "AVGXCHINOOK" + suffix, f"gxheli_body{d}.tga", "gxteam.tga", "gxglass.tga", "gxrotor.tga")
        models["AVGXAPACHE" + suffix] = gx_apache.build(
            "AVGXAPACHE" + suffix, f"gxheli_body{d}.tga", "gxteam.tga", "gxglass.tga", "gxflash.tga", "gxrotor.tga")
        models["AVGXMICRO" + suffix] = gx_microwave.build(
            "AVGXMICRO" + suffix, f"gxpal_body{d}.tga", "gxmbt_tread.tga", "gxteam.tga", "gxglass.tga")
        models["AVGXMEDIC" + suffix] = gx_ambulance.build("AVGXMEDIC" + suffix, f"gxmbt_body{d}.tga", "gxteam.tga", "gxglass.tga")
        for jet, variant in (("AVGXF35", "f35"), ("AVGXWING", "wing"), ("AVGXHYPER", "hyper")):
            models[jet + suffix] = gx_jets.build(
                jet + suffix, f"gxjet_body{d}.tga", "gxteam.tga", "gxglass.tga", "gxflash.tga", variant=variant)
    for name, builder in gx_buildings.BUILDERS.items():
        for variant, texture in (("", "gxbld_wall.tga"), ("D", "gxbld_walld.tga"), ("E", "gxbld_walld.tga")):
            full = name + (f"_{variant}" if variant else "")
            models[full] = builder(full, texture, "gxteam.tga", "gxglass.tga", variant=variant)
    for name, builder in gx_buildings.DOORS.items():
        for variant, texture in (("", "gxbld_wall.tga"), ("D", "gxbld_walld.tga")):
            full = name + (f"_{variant}" if variant else "")
            models[full] = builder(full, texture, "gxteam.tga", "gxglass.tga", variant=variant)
    for name, kit in gx_infantry.KITS.items():
        model, clips = gx_infantry.build(name, name.lower() + ".tga", "gxteam.tga", kit)
        models[name] = model
        model.stance = clips["AIM"][1]  # cameos and previews show the soldier aiming
        for clip, (frames, tracks) in clips.items():
            with open(os.path.join(w3d_dir, f"{name}_{clip}.w3d"), "wb") as f:
                f.write(w3d.pack_clip(name, f"{name}_{clip}", frames, tracks))
    models["ABGXSTRATGUN"] = gx_buildings.strategy_gun("ABGXSTRATGUN", "gxbld_wall.tga", "gxteam.tga", "gxglass.tga")
    for name, model in models.items():
        with open(os.path.join(w3d_dir, name + ".w3d"), "wb") as f:
            f.write(model.pack())
    return models


# Cameo name -> model it is rendered from.
CAMEOS = {
    "GXCameo_MBT": "AVGXMBT",
    "GXCameo_Paladin": "AVGXPAL",
    "GXCameo_Dozer": "AVGXDOZ",
    "GXCameo_Apache": "AVGXAPACHE",
    "GXCameo_JLTV": "AVGXJLTV",
    "GXCameo_MLRS": "AVGXMLRS",
    "GXCameo_Chinook": "AVGXCHINOOK",
    "GXCameo_Microwave": "AVGXMICRO",
    "GXCameo_Medic": "AVGXMEDIC",
    "GXCameo_F35": "AVGXF35",
    "GXCameo_Wing": "AVGXWING",
    "GXCameo_Hyper": "AVGXHYPER",
    "GXCameo_PowerPlant": "ABGXPWR",
    "GXCameo_Barracks": "ABGXBARRACKS",
    "GXCameo_WarFactory": "ABGXWARFACT",
    "GXCameo_Supply": "ABGXSUPPLY",
    "GXCameo_CommandCenter": "ABGXCMDHQ",
    "GXCameo_Patriot": "ABGXPATRIOT",
    "GXCameo_FireBase": "ABGXFIREBASE",
    "GXCameo_DropZone": "ABGXDROPZONE",
    "GXCameo_Strategy": "ABGXSTRATCTR",
    "GXCameo_Airfield": "ABGXAIRFIELD",
    "GXCameo_Uplink": "ABGXUPLINK",
    "GXCameo_Ranger": "GXIRNG",
    "GXCameo_Sniper": "GXISNP",
    "GXCameo_Burton": "GXIBRT",
    "GXCameo_Pilot": "GXIPLT",
    "GXCameo_MissileDef": "GXIMDF",
}
# Retail command bar images redrawn with our cameos. The retail MappedImages load from TextureSize_*
# before HandCreated, so redefining them here swaps the picture on every button and portrait that uses
# them, the generals' variants included, without overriding any Object or CommandButton.
RETAIL_CAMEOS = {
    "GXCameo_MBT": ["SACLeopard"],
    "GXCameo_Paladin": ["SAPaladin"],
    "GXCameo_Dozer": ["SACDozer"],
    "GXCameo_Apache": ["SACCommanche"],
    "GXCameo_JLTV": ["SAHummer"],
    "GXCameo_MLRS": ["SACTomahawk"],
    "GXCameo_Chinook": ["SAChinook", "SAComChinok"],
    "GXCameo_Microwave": ["SAThunderBolt"],
    "GXCameo_Medic": ["SAAmbulance"],
    "GXCameo_F35": ["SACRaptor", "SAKingRap"],
    "GXCameo_Wing": ["SAStealth"],
    "GXCameo_Hyper": ["SAAurora", "SAFulArAurora"],
    "GXCameo_PowerPlant": ["SAPowerPlant"],
    "GXCameo_Barracks": ["SABarracks"],
    "GXCameo_WarFactory": ["SACWeaponsfact"],
    "GXCameo_Supply": ["SASupplyCntr"],
    "GXCameo_CommandCenter": ["SAComCentr"],
    "GXCameo_Patriot": ["SAPatriot"],
    "GXCameo_FireBase": ["SAFirebase"],
    "GXCameo_DropZone": ["SADropZone"],
    "GXCameo_Strategy": ["SAStrategyCenter"],
    "GXCameo_Airfield": ["SAACommand"],
    "GXCameo_Uplink": ["SAUplink"],
    "GXCameo_Ranger": ["SARanger"],
    "GXCameo_Sniper": ["SAPathfinder1"],
    "GXCameo_Burton": ["SABurton"],
    "GXCameo_Pilot": ["SAPilot"],
    "GXCameo_MissileDef": ["SAMissleDefender"],
}
# Sub-objects the Draw module hides in the default state (upgrades), left out of cameos and previews.
DEFAULT_HIDDEN = {"TURRETUP01", "HOUSECOLOR03", "MISSILEUPGRADE"}
CELL_W, CELL_H = 352, 184


def fit(img, size, pad=3, top=1.0):
    """Crop a render to its silhouette (its upper `top` part: soldiers show head and shoulders) and scale
    it to fill size."""
    img = img.crop(img.getbbox())
    img = img.crop((0, 0, img.width, max(1, round(img.height * top))))
    scale = min((size[0] - 2 * pad) / img.width, (size[1] - 2 * pad) / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.alpha_composite(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    return out


CELLS_PER_SHEET = 10


def build_cameos(stage, tex_dir, models, tex, hd_cameos=None):
    """Sheets of command bar art (1024x1024, ten cells each: gxcameos.tga, gxcameos2.tga ...): per unit a
    button (120x96) and a selection portrait (216x178), plus the MappedImage INI that cuts them out
    (Name for the button, Name_L for the portrait)."""
    sheets = []
    ini = ["; GeneralsX content: command bar cameos rendered from our own models. Generated by build_content.py.", ""]

    def mapped(name, texture, left, top, right, bottom):
        ini.extend([f"MappedImage {name}", f"  Texture = {texture}", "  TextureWidth = 1024", "  TextureHeight = 1024",
                    f"  Coords = Left:{left} Top:{top} Right:{right} Bottom:{bottom}", "  Status = NONE", "End", ""])

    for i, (cameo, model_name) in enumerate(CAMEOS.items()):
        page, cell = divmod(i, CELLS_PER_SHEET)
        if page == len(sheets):
            sheets.append(Image.new("RGB", (1024, 1024), (20, 24, 28)))
        sheet = sheets[page]
        texture = "gxcameos.tga" if page == 0 else f"gxcameos{page + 1}.tga"
        x, y = (cell % 2) * (CELL_W + 8), (cell // 2) * (CELL_H + 8)
        model = models[model_name]
        top = 0.5 if getattr(model, "stance", None) else 1.0
        hd = hd_cameos and os.path.join(hd_cameos, f"{model_name}_button.png")
        if hd and os.path.exists(hd):
            # Detailed models come with their own Blender renders (blend/render_hd.py --cameo).
            shots = [Image.open(hd).convert("RGBA"),
                     Image.open(os.path.join(hd_cameos, f"{model_name}_portrait.png")).convert("RGBA")]
        else:
            shots = [render(model, tex, size=(480, 480), yaw=35, pitch=24, hide=DEFAULT_HIDDEN),
                     render(model, tex, size=(640, 640), yaw=30, pitch=20, hide=DEFAULT_HIDDEN)]
        button = textures.cameo_frame(fit(shots[0], (120, 96), top=top), (120, 96))
        portrait = textures.cameo_frame(fit(shots[1], (216, 178), top=top), (216, 178))
        sheet.paste(button, (x, y))
        sheet.paste(portrait, (x + 128, y))
        for name in [cameo] + RETAIL_CAMEOS.get(cameo, []):
            mapped(name, texture, x, y, x + 120, y + 96)
            mapped(name + "_L", texture, x + 128, y, x + 344, y + 178)
    for page, sheet in enumerate(sheets):
        textures.save_tga(sheet, os.path.join(tex_dir, "gxcameos.tga" if page == 0 else f"gxcameos{page + 1}.tga"))
    ini_dir = os.path.join(stage, "Data", "INI", "MappedImages", "HandCreated")
    os.makedirs(ini_dir, exist_ok=True)
    with open(os.path.join(ini_dir, "GeneralsXCameos.ini"), "w", newline="\r\n") as f:
        f.write("\n".join(ini))
    return sheets


def collect(root):
    files = []
    for dirpath, _, names in os.walk(root):
        for name in names:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("/", "\\")
            with open(full, "rb") as f:
                files.append((rel, f.read()))
    return files


# GeneralsX @feature Claude 16/10/2026 Reviewed detailed models (blend/build_src.py) replace retail models one unit at a
# time: the pack carries only the models present in the --hd folder, their textures and _n.dds normal maps, and an
# ArtRemap that draws them where the retail INI names the retail model. Logic keeps reading the retail model's bones.
# GeneralsX @feature Claude 18/10/2026 Retail model names read from the untouched ZH 1.04 Object/AmericaVehicle.ini
# (DefaultConditionState / REALLYDAMAGED Model=), the same source the infantry remap uses.
# GeneralsX @bugfix Claude 19/10/2026 The black upper surfaces were the convex-hull shadow shells the bake emitted as
# visible opaque meshes (fixed in import_src.py), not the normal map. Six of these (Abrams, Paladin, MLRS, JLTV, ambulance,
# dozer) were confirmed clean by an in-game PC frame (usa6-*.jpg) and shipped in #107. The Stryker (AVGXMICRO) and Avenger
# (AVGXAVNG) missed that first lineup on wrong template names; the -camtest usa keyword fallback put them back in frame and
# they are now confirmed clean too (usa8-*.jpg), so all eight ship.
HD_REMAP = {
    "AVGXMBT": ("AVLeopard", "Crusader -> M1A2 Abrams"),
    "AVGXMBT_D": ("AVLeopard_D", None),
    "AVGXMICRO": ("AVTHUNDRBLT", "Microwave Tank -> Stryker M1126"),
    "AVGXMICRO_D": ("AVTHUNDRBLT_D", None),
    "AVGXAVNG": ("AVAVNGER", "Avenger -> M1097 Avenger"),
    "AVGXAVNG_D": ("AVAVNGER_D", None),
    "AVGXPAL": ("AVPaladin", "Paladin -> M109 self-propelled howitzer"),
    "AVGXPAL_D": ("AVPaladin_D", None),
    "AVGXMLRS": ("AVTomahawk", "Tomahawk -> M270 MLRS"),
    "AVGXMLRS_D": ("AVTomahawk_D", None),
    "AVGXJLTV": ("AVHUMMER", "Humvee -> JLTV"),
    "AVGXJLTV_D": ("AVHUMMER_d", None),
    "AVGXMEDIC": ("AVAmbulance", "Medic -> M1133 ambulance"),
    "AVGXMEDIC_D": ("AVAmbulance_D", None),
    "AVGXDOZ": ("AVCONSTDOZ_A", "Dozer -> armoured bulldozer"),
    "AVGXDOZ_D": ("AVCONSTDOZ_AD", None),
}


def add_hd(hd, stage, w3d_dir, tex_dir):
    lines, used = [], set()
    for name in sorted(os.listdir(os.path.join(hd, "w3d"))):
        model = name[:-4]
        if not name.endswith(".w3d") or model not in HD_REMAP:
            continue
        shutil.copy(os.path.join(hd, "w3d", name), os.path.join(w3d_dir, name))
        with open(os.path.join(hd, "w3d", name), "rb") as f:
            used.update(t.decode().lower() for t in re.findall(rb"[\w-]+\.tga", f.read()))
        retail, note = HD_REMAP[model]
        if note:
            lines.append(f"  ; {note}")
        lines.append(f"  Model = {retail} {model}")
    for name in sorted(os.listdir(os.path.join(hd, "tex"))):
        stem = name[:-6] if name.endswith("_n.dds") else name[:-4] if name.endswith(".tga") else None
        if stem and stem.lower() + ".tga" in used:
            shutil.copy(os.path.join(hd, "tex", name), os.path.join(tex_dir, name))
    if lines:
        ini_dir = os.path.join(stage, "Data", "INI", "GeneralsX")
        os.makedirs(ini_dir, exist_ok=True)
        with open(os.path.join(ini_dir, "DetailedModels.ini"), "w", newline="\r\n") as f:
            f.write("; GeneralsX content: reviewed detailed models (generated by build_content.py --hd).\n"
                    "; Only what is drawn changes; logic reads bones from the retail model.\n\n"
                    "ArtRemap\n" + "\n".join(lines) + "\nEnd\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("out")
    parser.add_argument("--art", action="store_true", help="also build the procedural models and cameos")
    parser.add_argument("--preview")
    parser.add_argument("--hd", help="output of blend/build_src.py (w3d/, tex/): reviewed detailed models, drawn "
                                     "in place of the retail ones listed in HD_REMAP")
    args = parser.parse_args()

    stage = os.path.join(args.out, "stage")
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(os.path.join(args.repo, "content"), stage)
    tex_dir = os.path.join(stage, "Art", "Textures")
    w3d_dir = os.path.join(stage, "Art", "W3D")
    os.makedirs(tex_dir, exist_ok=True)
    os.makedirs(w3d_dir, exist_ok=True)

    models, tex = {}, None
    if args.art or args.preview:
        tex = build_textures(tex_dir)
        models = build_models(w3d_dir, tex)
        build_cameos(stage, tex_dir, models, tex)
    if args.hd:
        add_hd(args.hd, stage, w3d_dir, tex_dir)

    write_big(os.path.join(args.out, PACK_NAME), collect(stage))

    if args.preview:
        os.makedirs(args.preview, exist_ok=True)
        for name, model in models.items():
            if name.endswith("_D") or name.endswith("_E") or name == "ABGXSTRATGUN" or name in gx_buildings.DOORS:
                continue
            for yaw in (35, 150):
                render(model, tex, size=(960, 720), yaw=yaw, pitch=26, background=(70, 78, 70, 255), hide=DEFAULT_HIDDEN).save(
                    os.path.join(args.preview, f"{name}_{yaw}.png"))
    print(f"wrote {os.path.join(args.out, PACK_NAME)}")


if __name__ == "__main__":
    main()
