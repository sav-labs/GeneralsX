# Model normal maps: notes for content authors

> [!NOTE]
> **AI-Generated Content Disclosure**: This document was written by an AI coding agent.

GeneralsX draws unit and building models with per-pixel lighting when their texture comes with a normal map.
Models without one render exactly as before.

## Naming

- The normal map sits next to the base texture and has the same name plus `_n`:
  `avtank.tga` (or `avtank.dds`) -> `avtank_n.dds` (preferred) or `avtank_n.tga`.
- It is found in the same places as any texture: `Art/Textures/` as loose files, or inside a `.big` archive.
- Only the texture of the first material pass, stage 0, is looked at. One normal map per base texture; every
  mesh that uses the base texture gets it.
- House colour (team colour) textures work: the recoloured copy finds the normal map of its base texture.

## Format

- Tangent space, **OpenGL orientation (Y+, green points up in the image)**, the Blender / Substance "OpenGL"
  default. A DirectX (Y-) map needs its green channel inverted.
- RGB = normal (128,128,255 is flat). **Alpha = gloss / specular strength**: 0 matte, 255 full highlight.
  A map without alpha (DXT1 / 24 bit TGA) counts as fully glossy everywhere, so always give it an alpha.
- Recommended: DDS **DXT5 (BC3)** with mip maps; or 32 bit TGA (loaded without compression).
- Power of two sizes. Up to 1024 x 1024 for vehicles and infantry, 2048 x 2048 for large buildings; the
  Options.ini texture reduction setting applies to normal maps too.
- Tangents come from UV set 0 of the mesh. Mirrored UVs are fine as long as the mirror seam has split
  vertices (it normally does in an exported W3D).

## Which meshes qualify

- Lit meshes with vertex normals, a texture on pass 0 stage 0, no second texture stage, plain "modulate"
  shading (the default W3D shader). Detail textures, environment mapped or UV-generated stages, sorted
  (alpha blended, depth sorted) meshes and prelit-only meshes stay on the original fixed function path.
- Skinned (infantry) meshes qualify when they have a single UV set.
- Alpha test (cut-out) and alpha blended, non-sorted passes, team colour, damage / selection tint, fog and
  scrolling UVs (tank treads) work as before.

## Lighting

- The map's sun and its first fill light are applied per pixel with the normal map, plus a highlight from the
  gloss in the sun's colour (exponent 16). Ambient, a third map light and nearby explosion / fire lights stay
  per vertex, with the same attenuation as before, so brightness matches unchanged models.
- Options.ini: `ModelNormalMaps = no` turns the feature off; `ModelSpecular = 0..2` (default 1) scales the
  highlight.

## Checking a model in game

- stderr shows one line per normal map found, e.g.
  `[NORMALMAP] loaded avtank_n.dds for mesh AVTANK.CHASSIS (texture avtank.tga)`.
- With the frame profiler on (`PerfOverlay = yes` or `-perf`), each `[PERF]` line has `normalmapped=N`, the
  draws per frame that used normal maps.
- A/B check: same camera, `ModelNormalMaps = yes` vs `no`. Flat parts should keep their brightness; panel
  lines, rivets and dents should catch the sun on the lit side and darken on the far side.
