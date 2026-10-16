"""Particle systems and FX lists of the GeneralsX effects pack.

GeneralsX @feature Claude 16/10/2026 Each system is a dict of retail ParticleSystem INI fields plus
the GeneralsX FlipbookGrid / FlipbookRandom fields; write_ini() turns them into the INI the game
loads from Data\\INI\\GeneralsX, and preview.py simulates the same dicts for the preview video.
FX lists replace retail FXList definitions by name; they keep the retail sounds, view shake and
terrain scorch and only swap the particles. Everything here is client-side presentation: FX
lists and particle systems never feed back into game logic, so replays and multiplayer sync are
unaffected. Debris objects (ObjectCreationList) are logic objects and are not touched.

Units follow the retail INI: distances in world units, times in logic frames (30 per second),
rates per frame. Colours are 0..255 keyed on particle age in frames.
"""

DEFAULTS = {
    "Priority": "DEATH_EXPLOSION",
    "IsOneShot": "No",
    "Shader": "ALPHA",
    "Type": "PARTICLE",
    "AngleZ": (0.0, 6.28),
    "AngularRateZ": (0.0, 0.0),
    "AngularDamping": (1.0, 1.0),
    "VelocityDamping": (1.0, 1.0),
    "Gravity": 0.0,
    "Lifetime": (30.0, 30.0),
    "SystemLifetime": 1,
    "Size": (10.0, 10.0),
    "StartSizeRate": (0.0, 0.0),
    "SizeRate": (0.0, 0.0),
    "SizeRateDamping": (1.0, 1.0),
    "Alpha": [(1.0, 1.0, 0)],
    "Color": [((255, 255, 255), 0)],
    "BurstDelay": (99999.0, 99999.0),
    "BurstCount": (1.0, 1.0),
    "InitialDelay": (0.0, 0.0),
    "DriftVelocity": (0.0, 0.0, 0.0),
    "VelocityType": "SPHERICAL",
    "VelSpherical": (0.0, 0.0),
    "VolumeType": "POINT",
    "IsHollow": "No",
    "IsGroundAligned": "No",
    "IsEmitAboveGroundOnly": "No",
    "IsParticleUpTowardsEmitter": "No",
    "FlipbookGrid": 0,
    "FlipbookRandom": "No",
}


def system(**fields):
    s = dict(DEFAULTS)
    s.update(fields)
    return s


SYSTEMS = {
    # ---- Tank death explosion (FX_GenericTankDeathExplosion) ----------------------------------
    # Bright flash that lights everything for a few frames.
    "GXTankBlastFlash": system(
        Shader="ADDITIVE", ParticleName="gxfx_flash.tga",
        Lifetime=(9, 9), Size=(70, 70), SizeRate=(5, 5), SizeRateDamping=(0.7, 0.7),
        Color=[((255, 244, 220), 0), ((255, 150, 50), 4), ((0, 0, 0), 9)],
        BurstCount=(1, 1), AngleZ=(0, 6.28)),
    # Orange light pool on the ground under the blast.
    "GXTankBlastGroundGlow": system(
        Shader="ADDITIVE", ParticleName="gxfx_spark.tga", IsGroundAligned="Yes",
        Lifetime=(26, 26), Size=(90, 90), SizeRate=(1.0, 1.0), SizeRateDamping=(0.9, 0.9),
        Color=[((230, 120, 40), 0), ((120, 40, 10), 12), ((0, 0, 0), 26)],
        BurstCount=(1, 1)),
    # Main fireball: a cluster of billowing flipbook puffs that rise and cool into smoke.
    "GXTankBlastFireball": system(
        ParticleName="gxfx_fireball.tga", FlipbookGrid=4,
        Lifetime=(34, 46), Size=(16, 22), SizeRate=(2.4, 3.0), SizeRateDamping=(0.9, 0.92),
        AngularRateZ=(-0.02, 0.02),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 26), (0.0, 0.0, 46)],
        Color=[((255, 255, 255), 0)],
        BurstCount=(7, 7), Gravity=0.025, VelocityDamping=(0.84, 0.88),
        VelocityType="SPHERICAL", VelSpherical=(0.8, 1.6),
        VolumeType="SPHERE", VolSphereRadius=6.0),
    # Smaller secondary blasts a moment later, as fuel and ammunition go off.
    "GXTankBlastSecondary": system(
        ParticleName="gxfx_fireball.tga", FlipbookGrid=4,
        Lifetime=(26, 34), Size=(9, 13), SizeRate=(1.6, 2.0), SizeRateDamping=(0.9, 0.9),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 18), (0.0, 0.0, 34)],
        BurstDelay=(3, 6), BurstCount=(1, 1), SystemLifetime=18, InitialDelay=(5, 5),
        Gravity=0.02, VelocityDamping=(0.85, 0.85),
        VelocityType="SPHERICAL", VelSpherical=(0.6, 1.2),
        VolumeType="SPHERE", VolSphereRadius=12.0),
    # Dust ring racing out along the ground.
    "GXTankBlastShockwave": system(
        ParticleName="gxfx_ring.tga", IsGroundAligned="Yes", AngleZ=(0, 6.28),
        Lifetime=(24, 24), Size=(12, 12), SizeRate=(10, 10), SizeRateDamping=(0.86, 0.86),
        Alpha=[(0.9, 0.9, 0), (0.0, 0.0, 24)],
        Color=[((200, 182, 150), 0)],
        BurstCount=(1, 1)),
    # Brown dust thrown up and outwards around the hull.
    "GXTankBlastDust": system(
        ParticleName="gxfx_dust.tga", FlipbookGrid=4,
        Lifetime=(60, 85), Size=(10, 15), SizeRate=(0.9, 1.2), SizeRateDamping=(0.965, 0.97),
        AngularRateZ=(-0.01, 0.01),
        Alpha=[(0.0, 0.0, 0), (0.8, 0.8, 5), (0.0, 0.0, 85)],
        Color=[((170, 150, 120), 0), ((150, 136, 116), 60)],
        BurstCount=(14, 14), VelocityDamping=(0.9, 0.92), Gravity=0.004,
        VelocityType="OUTWARD", VelOutward=(1.6, 2.8), VelOutwardOther=(0.1, 0.5),
        VolumeType="CYLINDER", VolCylinderRadius=8.0, VolCylinderLength=1.0, IsHollow="Yes"),
    # Charred fragments flung out on arcs.
    "GXTankBlastDebris": system(
        ParticleName="gxfx_debris.tga", FlipbookGrid=2, FlipbookRandom="Yes",
        Lifetime=(36, 46), Size=(2.5, 4.5), AngularRateZ=(-0.35, 0.35),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 34), (0.0, 0.0, 46)],
        Color=[((255, 255, 255), 0)],
        BurstCount=(18, 18), Gravity=-0.17, VelocityDamping=(0.99, 0.99),
        VelocityType="OUTWARD", VelOutward=(1.2, 3.4), VelOutwardOther=(2.2, 4.4),
        VolumeType="CYLINDER", VolCylinderRadius=5.0, VolCylinderLength=4.0),
    # Fast glowing embers.
    "GXTankBlastEmbers": system(
        Shader="ADDITIVE", ParticleName="gxfx_spark.tga",
        Lifetime=(18, 40), Size=(1.0, 2.0), SizeRate=(-0.02, -0.02),
        Color=[((255, 230, 170), 0), ((255, 110, 30), 16), ((0, 0, 0), 40)],
        BurstCount=(40, 40), Gravity=-0.12, VelocityDamping=(0.95, 0.97),
        VelocityType="OUTWARD", VelOutward=(1.5, 5.0), VelOutwardOther=(1.5, 5.5),
        VolumeType="CYLINDER", VolCylinderRadius=4.0, VolCylinderLength=4.0),
    # Thick black smoke that rolls up from the fireball.
    "GXTankBlastSmoke": system(
        ParticleName="gxfx_smoke.tga", FlipbookGrid=4,
        Lifetime=(120, 160), Size=(16, 22), SizeRate=(0.7, 0.9), SizeRateDamping=(0.985, 0.988),
        AngularRateZ=(-0.008, 0.008),
        Alpha=[(0.0, 0.0, 0), (0.9, 0.9, 14), (0.6, 0.6, 80), (0.0, 0.0, 160)],
        Color=[((52, 46, 42), 0), ((96, 92, 88), 110)],
        BurstDelay=(2, 2), BurstCount=(2, 2), SystemLifetime=10, InitialDelay=(6, 6),
        DriftVelocity=(0.12, 0.05, 0.42), VelocityDamping=(0.92, 0.94),
        VelocityType="SPHERICAL", VelSpherical=(0.4, 0.9),
        VolumeType="SPHERE", VolSphereRadius=8.0),

    # ---- Burning wreck (about 6 s, until the retail hulk has sunk into the ground) -------------
    "GXWreckFire": system(
        Priority="WEAPON_EXPLOSION", Shader="ADDITIVE", ParticleName="gxfx_flame.tga", FlipbookGrid=4,
        Lifetime=(22, 30), Size=(8, 12), SizeRate=(0.05, 0.12), SizeRateDamping=(0.97, 0.97),
        AngleZ=(-0.15, 0.15),
        Color=[((0, 0, 0), 0), ((255, 225, 180), 4), ((210, 100, 36), 18), ((0, 0, 0), 30)],
        BurstDelay=(2, 3), BurstCount=(1, 1), SystemLifetime=170,
        DriftVelocity=(0.0, 0.0, 0.3),
        VolumeType="CYLINDER", VolCylinderRadius=6.0, VolCylinderLength=3.0),
    "GXWreckSmoke": system(
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_smoke.tga", FlipbookGrid=4,
        Lifetime=(140, 180), Size=(8, 12), SizeRate=(0.2, 0.26), SizeRateDamping=(0.995, 0.995),
        AngularRateZ=(-0.006, 0.006),
        Alpha=[(0.0, 0.0, 0), (0.8, 0.8, 18), (0.45, 0.45, 100), (0.0, 0.0, 180)],
        Color=[((40, 36, 33), 0), ((100, 96, 92), 130)],
        BurstDelay=(5, 8), BurstCount=(1, 1), SystemLifetime=200, InitialDelay=(20, 20),
        DriftVelocity=(0.14, 0.06, 0.5),
        VolumeType="CYLINDER", VolCylinderRadius=4.0, VolCylinderLength=2.0),
    "GXWreckEmbers": system(
        Priority="WEAPON_EXPLOSION", Shader="ADDITIVE", ParticleName="gxfx_spark.tga",
        Lifetime=(30, 50), Size=(0.7, 1.4),
        Color=[((255, 200, 120), 0), ((255, 90, 20), 24), ((0, 0, 0), 50)],
        BurstDelay=(4, 10), BurstCount=(1, 2), SystemLifetime=170,
        DriftVelocity=(0.08, 0.03, 0.0), Gravity=0.01, VelocityDamping=(0.97, 0.97),
        VelocityType="OUTWARD", VelOutward=(0.1, 0.4), VelOutwardOther=(0.6, 1.2),
        VolumeType="CYLINDER", VolCylinderRadius=6.0, VolCylinderLength=2.0),
    "GXWreckHeatGlow": system(
        Priority="WEAPON_EXPLOSION", Shader="ADDITIVE", ParticleName="gxfx_spark.tga", IsGroundAligned="Yes",
        Lifetime=(40, 40), Size=(34, 40),
        Color=[((0, 0, 0), 0), ((110, 50, 14), 10), ((110, 50, 14), 30), ((0, 0, 0), 40)],
        BurstDelay=(30, 30), BurstCount=(1, 1), SystemLifetime=160),
}

# Particle systems of one FX list entry: (system, offset x y z).
FXLISTS = {
    "FX_GenericTankDeathExplosion": {
        "particles": [
            ("GXTankBlastFlash", (0, 0, 10)),
            ("GXTankBlastGroundGlow", (0, 0, 1)),
            ("GXTankBlastFireball", (0, 0, 8)),
            ("GXTankBlastSecondary", (0, 0, 8)),
            ("GXTankBlastShockwave", (0, 0, 1)),
            ("GXTankBlastDust", (0, 0, 2)),
            ("GXTankBlastDebris", (0, 0, 6)),
            ("GXTankBlastEmbers", (0, 0, 6)),
            ("GXTankBlastSmoke", (0, 0, 12)),
            ("GXWreckFire", (0, 0, 6)),
            ("GXWreckSmoke", (0, 0, 12)),
            ("GXWreckEmbers", (0, 0, 6)),
            ("GXWreckHeatGlow", (0, 0, 1)),
        ],
        # Retail nuggets kept as they are.
        "extra": """  LightPulse
    Color = R:255 G:150 B:70
    Radius = 90
    IncreaseTime = 0
    DecreaseTime = 900
  End
  ViewShake
    Type = STRONG
  End
  TerrainScorch
    Type = RANDOM
    Radius = 15
  End
  Sound
    Name = TankDie
  End
""",
    },
}


def _pair(v):
    return "%.2f %.2f" % (float(v[0]), float(v[1]))


def write_system(name, s):
    out = ["ParticleSystem %s" % name]
    for key in ("Priority", "IsOneShot", "Shader", "Type", "ParticleName"):
        out.append("  %s = %s" % (key, s[key]))
    for key in ("AngleZ", "AngularRateZ", "AngularDamping", "VelocityDamping"):
        out.append("  %s = %s" % (key, _pair(s[key])))
    out.append("  Gravity = %.3f" % s["Gravity"])
    out.append("  Lifetime = %s" % _pair(s["Lifetime"]))
    out.append("  SystemLifetime = %d" % s["SystemLifetime"])
    for key in ("Size", "StartSizeRate", "SizeRate", "SizeRateDamping"):
        out.append("  %s = %s" % (key, _pair(s[key])))
    alpha = list(s["Alpha"]) + [(0.0, 0.0, 0)] * (8 - len(s["Alpha"]))
    for i, (lo, hi, frame) in enumerate(alpha):
        out.append("  Alpha%d = %.2f %.2f %d" % (i + 1, lo, hi, frame))
    color = list(s["Color"]) + [((0, 0, 0), 0)] * (8 - len(s["Color"]))
    for i, ((r, g, b), frame) in enumerate(color):
        out.append("  Color%d = R:%d G:%d B:%d %d" % (i + 1, r, g, b, frame))
    out.append("  ColorScale = 0.00 0.00")
    for key in ("BurstDelay", "BurstCount", "InitialDelay"):
        out.append("  %s = %s" % (key, _pair(s[key])))
    d = s["DriftVelocity"]
    out.append("  DriftVelocity = X:%.2f Y:%.2f Z:%.2f" % d)
    out.append("  VelocityType = %s" % s["VelocityType"])
    vt = s["VelocityType"]
    if vt == "SPHERICAL":
        out.append("  VelSpherical = %s" % _pair(s["VelSpherical"]))
    elif vt == "HEMISPHERICAL":
        out.append("  VelHemispherical = %s" % _pair(s["VelHemispherical"]))
    elif vt == "OUTWARD":
        out.append("  VelOutward = %s" % _pair(s["VelOutward"]))
        out.append("  VelOutwardOther = %s" % _pair(s["VelOutwardOther"]))
    out.append("  VolumeType = %s" % s["VolumeType"])
    if s["VolumeType"] == "SPHERE":
        out.append("  VolSphereRadius = %.2f" % s["VolSphereRadius"])
    elif s["VolumeType"] == "CYLINDER":
        out.append("  VolCylinderRadius = %.2f" % s["VolCylinderRadius"])
        out.append("  VolCylinderLength = %.2f" % s["VolCylinderLength"])
    for key in ("IsHollow", "IsGroundAligned", "IsEmitAboveGroundOnly", "IsParticleUpTowardsEmitter"):
        out.append("  %s = %s" % (key, s[key]))
    out.append("  WindMotion = Unused")
    if s["FlipbookGrid"]:
        out.append("  FlipbookGrid = %d" % s["FlipbookGrid"])
        out.append("  FlipbookRandom = %s" % s["FlipbookRandom"])
    out.append("End")
    return "\n".join(out) + "\n"


def write_fxlist(name, fx):
    out = ["FXList %s" % name]
    for sys_name, (x, y, z) in fx["particles"]:
        out += ["  ParticleSystem", "    Name = %s" % sys_name,
                "    Offset = X:%.1f Y:%.1f Z:%.1f" % (x, y, z), "  End"]
    return "\n".join(out) + "\n" + fx["extra"] + "End\n"


def write_ini():
    """Returns {archive path: INI text}. Particle systems come first so the FX lists find them."""
    header = "; GeneralsX effects pack: generated by scripts/tooling/effects/build_effects.py, do not edit.\n\n"
    systems = header + "\n".join(write_system(n, s) for n, s in SYSTEMS.items())
    fx = header + "\n".join(write_fxlist(n, f) for n, f in FXLISTS.items())
    return {
        "Data\\INI\\GeneralsX\\EffectsParticles.ini": systems,
        "Data\\INI\\GeneralsX\\EffectsFXList.ini": fx,
    }
