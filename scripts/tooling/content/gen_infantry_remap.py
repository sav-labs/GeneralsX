"""Write the ArtRemap block that puts the pack's soldiers on the retail USA infantry.

GeneralsX @feature Claude 16/10/2026 Reads the unmodified retail Object INI (not shipped; any ZH 1.04
copy, e.g. TheSuperHackers/GeneralsGamePatch GameFilesOriginalZH/Data/INI/Object/AmericaInfantry.ini),
finds every animation the soldiers' Draw modules play and maps it to the clip of gx_infantry that fits
the condition or transition it plays in. The output is committed as
content/Data/INI/GeneralsX/AmericaInfantryArt.ini; rerun this when retail names change.

Usage: gen_infantry_remap.py <AmericaInfantry.ini> <output .ini>
"""

import re
import sys

# Retail skin -> pack model (gx_infantry.KITS).
MODELS = {
    "AIRngr_SKN": "GXIRNG",
    "AIRngr_F_SKN": "GXIRNG",
    "AIPFDR_SKN": "GXISNP",
    "AIHERO_SKN": "GXIBRT",
    "AIRPlt_SKN": "GXIPLT",
    "NITHNT_SKN": "GXIMDF",  # despite the name, only the USA Missile Defenders use it
}
# Played only by the generals' variants (AirforceGeneral.ini and friends), which reuse the same skins.
EXTRA = {
    "AIHERO_SKL.AIHERO_CLMST": ("GXIBRT", "CLIMB"),
    "AIRPlt_SKL.AIRPlt_POP": ("GXIPLT", "CHUTEOPN"),
}
OBJECTS = ["AmericaInfantryRanger", "AmericaInfantryPathfinder", "AmericaInfantryColonelBurton", "AmericaInfantryPilot",
           "AmericaInfantryMissileDefender"]


def classify(kind, flags, keys, anim):
    """Clip for an animation from where it plays: kind is 'state' or 'transition', flags the condition
    flags (state) and keys the transition keys (from, to)."""
    tail = anim.split(".")[-1].upper()
    if re.search(r"ADT\w*1$", tail):
        return "FLAIL"  # first part of a blown-off death, before the flailing loop
    if kind == "transition":
        a, b = (k.upper() for k in keys)
        if "FALLING" in a and "CHUTE" in b:
            return "CHUTEOPN"
        if "CHUTE" in a or "RAPPEL" in a:
            return "LAND"
        if "RAISING" in a or "PACK" in b:
            return "WORK"
        fire_a = any(w in a for w in ("FIRING", "ATTACK", "AIM"))
        fire_b = any(w in b for w in ("FIRING", "ATTACK", "AIM"))
        if fire_b and not fire_a:
            return "AIMIN"
        if fire_a and not fire_b:
            return "AIMOUT"
        if fire_a and fire_b:
            return "AIM"
        return "SHIFT"
    f = set(flags)
    if "DYING" in f:
        if "EXPLODED_FLAILING" in f:
            return "FLAIL"
        if "EXPLODED_BOUNCING" in f or "SPLATTED" in f:
            return "TUMBLE"
        return "DIEFWD" if tail.endswith("B") else "DIEBACK"
    if "FREEFALL" in f:
        return "FREEFALL"
    if "PARACHUTING" in f:
        return "HANG"
    if "RAPPELLING" in f:
        return "RAPPEL"
    if "CLIMBING" in f or tail.startswith(("AIHERO_CLM",)):
        return "CLIMB"
    if f & {"UNPACKING", "PACKING", "RAISING_FLAG", "PREPARING"} or "_IDT" in tail:
        return "WORK"
    if "SPECIAL_CHEERING" in f:
        return "CHEER"
    if any(x.startswith("FIRING_") for x in f):
        return "FIRE"
    if any(x.startswith("BETWEEN_FIRING_SHOTS_") or x.startswith("RELOADING_") for x in f):
        return "FIRE"
    if any(x.startswith("PREATTACK_") for x in f):
        return "AIMIN"
    if any(x.startswith("USING_WEAPON_") or x.startswith("ATTACKING") for x in f):
        return "AIM"
    if "MOVING" in f:
        return "RUN"
    if kind == "idle":
        return "STAND" if re.search(r"ST[A-Z]?$", tail) else "IDLE"
    return "STAND"


def scan(text):
    """(model, kind, flags, keys, animation) for each animation line of the wanted objects."""
    out = []
    for obj in OBJECTS:
        m = re.search(rf"^Object {obj}\s*$(.*?)^End\s*$", text, re.M | re.S)
        if not m:
            raise SystemExit(f"{obj} not found")
        model = None
        kind, flags, keys = "state", [], ()
        for raw in m.group(1).splitlines():
            line = raw.split(";")[0].strip()
            if not line:
                continue
            head = line.split("=")[0].strip()
            val = line.split("=", 1)[1].split() if "=" in line else []
            if head == "DefaultConditionState":
                kind, flags, keys = "state", [], ()
            elif head == "ConditionState":
                kind, flags, keys = "state", val, ()
            elif head == "TransitionState":
                kind, flags, keys = "transition", [], tuple(val[:2])
            elif head == "Model" and val:
                if val[0] in MODELS:
                    model = val[0]
            elif head in ("Animation", "IdleAnimation") and val and model:
                out.append((model, "idle" if head == "IdleAnimation" else kind, flags, keys, val[0]))
    return out


def main():
    text = open(sys.argv[1], encoding="latin-1").read()
    mapped = {}
    for model, kind, flags, keys, anim in scan(text):
        key = anim.upper()
        if key not in mapped:
            mapped[key] = (anim, MODELS[model], classify(kind, flags, keys, anim))
    for anim, (model, clip) in EXTRA.items():
        mapped.setdefault(anim.upper(), (anim, model, clip))
    lines = [
        "; GeneralsX content: modern art for USA infantry. Generated by scripts/tooling/content/gen_infantry_remap.py",
        "; from the retail AmericaInfantry.ini. Display-only like AmericaVehicleArt.ini: the soldiers are the pack's",
        "; own rigid models with their own skeleton, and every retail animation plays the pack clip that matches",
        "; the condition it is used in. Logic keeps the retail bones.",
        "",
        "ArtRemap",
    ]
    for retail, pack in MODELS.items():
        lines.append(f"  Model     = {retail:<14} {pack}")
    for anim, model, clip in sorted(mapped.values(), key=lambda v: v[0].upper()):
        lines.append(f"  Animation = {anim:<26} {model}.{model}_{clip}")
    lines.append("End")
    with open(sys.argv[2], "w", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(mapped)} animations")


if __name__ == "__main__":
    main()
