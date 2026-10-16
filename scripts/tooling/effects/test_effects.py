#!/usr/bin/env python3
"""Checks for the GeneralsX effects pack sources.

GeneralsX @feature Claude 16/10/2026 Every FX list names existing systems, every system names a
generated texture, flipbook grids are ones the engine supports, key frames rise, and the INI
parses back into the same number of blocks.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fx_systems  # noqa: E402
import fx_textures  # noqa: E402


def main():
    errors = []
    for fx_name, fx in fx_systems.FXLISTS.items():
        for sys_name, _ in fx["particles"]:
            if sys_name not in fx_systems.SYSTEMS:
                errors.append("%s: unknown system %s" % (fx_name, sys_name))
    for name, s in fx_systems.SYSTEMS.items():
        tex = s.get("ParticleName")
        if tex not in fx_textures.TEXTURES:
            errors.append("%s: texture %s is not generated" % (name, tex))
        elif s["FlipbookGrid"] not in (0, 1) and s["FlipbookGrid"] != fx_textures.TEXTURES[tex][1]:
            errors.append("%s: FlipbookGrid %d does not match %s" % (name, s["FlipbookGrid"], tex))
        if s["FlipbookGrid"] not in (0, 1, 2, 4, 8, 16):
            errors.append("%s: unsupported FlipbookGrid %d" % (name, s["FlipbookGrid"]))
        for keys in ([k[2] for k in s["Alpha"]], [k[1] for k in s["Color"]]):
            if len(keys) > 8 or any(b <= a for a, b in zip(keys, keys[1:])):
                errors.append("%s: key frames must rise and number at most 8: %s" % (name, keys))
        if s["Lifetime"][0] < 1 or s["Lifetime"][1] < s["Lifetime"][0]:
            errors.append("%s: bad Lifetime %s" % (name, s["Lifetime"]))
    ini = fx_systems.write_ini()
    text = "".join(ini.values())
    blocks = sum(1 for line in text.splitlines() if line.startswith(("ParticleSystem ", "FXList ")))
    if blocks != len(fx_systems.SYSTEMS) + len(fx_systems.FXLISTS):
        errors.append("INI has %d blocks, expected %d" % (blocks, len(fx_systems.SYSTEMS) + len(fx_systems.FXLISTS)))
    if not text.isascii():
        errors.append("INI is not ASCII")
    for e in errors:
        print("error: " + e)
    print("effects: %d systems, %d FX lists, %d textures" % (
        len(fx_systems.SYSTEMS), len(fx_systems.FXLISTS), len(fx_textures.TEXTURES)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
