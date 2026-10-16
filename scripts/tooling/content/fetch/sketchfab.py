"""Find and fetch openly licensed source models on Sketchfab for the detailed USA units.

GeneralsX @feature Claude 16/10/2026 Runs in CI, where Sketchfab is reachable.
  sketchfab.py search <out dir>   searches each unit's queries for downloadable CC0 / CC-BY / CC-BY-SA
                                  models, writes candidates.json and one labelled contact sheet per unit
  sketchfab.py fetch <picks.txt> <out dir>
                                  downloads the picked models as .glb (needs SKETCHFAB_TOKEN) and writes
                                  CREDITS.md with title, author, licence and link for each
  sketchfab.py probe <probe.txt> <out dir>
                                  downloads candidates for a closer look (needs SKETCHFAB_TOKEN): uid lines
                                  as they are, "q: <query>" lines as the best PBR-textured search hits, and
                                  writes probe.json with each one's texture maps and sizes
Search needs no token; downloads do. Licences that forbid commercial use or derivatives are skipped.
"""

import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw

API = "https://api.sketchfab.com/v3"
LICENCES = ("cc0", "by", "by-sa")
UNITS = {
    "crusader": ["M1 Abrams", "M1A2 Abrams tank", "main battle tank"],
    "paladin": ["M109 Paladin", "self-propelled howitzer"],
    "humvee": ["humvee", "HMMWV", "JLTV"],
    "ambulance": ["military ambulance", "humvee ambulance", "M997"],
    "tomahawk": ["HIMARS", "M270 MLRS", "missile launcher truck"],
    "microwave": ["M2 Bradley", "Stryker", "infantry fighting vehicle"],
    "avenger": ["Avenger air defense", "M1097 Avenger", "humvee stinger"],
    "bulldozer": ["military bulldozer", "D9 bulldozer", "bulldozer"],
}


def get(url, token=None, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "GeneralsX-content"})
    if token:
        req.add_header("Authorization", f"Token {token}")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data if raw else json.loads(data)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def search(out):
    os.makedirs(out, exist_ok=True)
    found = {}
    for unit, queries in UNITS.items():
        seen = {}
        for q in queries:
            for lic in LICENCES:
                params = {"type": "models", "q": q, "downloadable": "true", "license": lic, "count": 24,
                          "sort_by": "-likeCount"}
                res = get(f"{API}/search?{urllib.parse.urlencode(params)}")
                for m in res.get("results", []):
                    if m["uid"] in seen or m.get("faceCount", 0) > 400000:
                        continue
                    thumbs = sorted(m.get("thumbnails", {}).get("images", []), key=lambda t: t["width"])
                    thumb = next((t["url"] for t in thumbs if t["width"] >= 256), thumbs[-1]["url"] if thumbs else None)
                    seen[m["uid"]] = {
                        "uid": m["uid"], "name": m["name"], "author": m["user"]["username"],
                        "licence": lic, "faces": m.get("faceCount", 0), "likes": m.get("likeCount", 0),
                        "animations": m.get("animationCount", 0), "url": m.get("viewerUrl"), "thumb": thumb,
                    }
        ranked = sorted(seen.values(), key=lambda c: -c["likes"])[:24]
        found[unit] = ranked
        sheet(unit, ranked, os.path.join(out, f"{unit}.jpg"))
        for i, c in enumerate(ranked):
            print(f"{unit} #{i:02d} {c['uid']} {c['licence']:6s} {c['faces']:7d}f {c['likes']:5d}l  {c['name']} / {c['author']}")
    with open(os.path.join(out, "candidates.json"), "w") as f:
        json.dump(found, f, indent=1)


def sheet(unit, cands, path, cols=6, tw=320, th=200):
    rows = max(1, (len(cands) + cols - 1) // cols)
    img = Image.new("RGB", (cols * tw, rows * (th + 34)), (24, 24, 24))
    d = ImageDraw.Draw(img)
    for i, c in enumerate(cands):
        x, y = (i % cols) * tw, (i // cols) * (th + 34)
        try:
            t = Image.open(io.BytesIO(get(c["thumb"], raw=True))).convert("RGB")
            t.thumbnail((tw, th))
            img.paste(t, (x + (tw - t.width) // 2, y + (th - t.height) // 2))
        except Exception:
            pass
        d.text((x + 4, y + th + 2), f"#{i:02d} {c['licence']} {c['faces'] // 1000}k", fill=(255, 220, 120))
        d.text((x + 4, y + th + 17), c["name"][:44], fill=(230, 230, 230))
    img.save(path, quality=85)


def fetch(picks, out):
    token = os.environ.get("SKETCHFAB_TOKEN")
    if not token:
        sys.exit("SKETCHFAB_TOKEN is not set")
    os.makedirs(out, exist_ok=True)
    credits = ["# Third-party source models", ""]
    for line in open(picks):
        line = line.split("#")[0].strip()
        if not line:
            continue
        name, uid = line.split()
        info = get(f"{API}/models/{uid}")
        lic = info["license"]["slug"] if isinstance(info.get("license"), dict) else str(info.get("license"))
        if lic not in LICENCES:
            print(f"skip {name} {uid}: licence {lic}")
            continue
        links = get(f"{API}/models/{uid}/download", token=token)
        link = (links.get("glb") or links.get("gltf"))["url"]
        ext = "glb" if links.get("glb") else "zip"
        data = get(link, raw=True)
        with open(os.path.join(out, f"{name}.{ext}"), "wb") as f:
            f.write(data)
        credits.append(f"- {name}: \"{info['name']}\" by {info['user']['username']} ({info['user'].get('profileUrl', '')}), "
                       f"{info['license'].get('label', lic) if isinstance(info.get('license'), dict) else lic}, "
                       f"{info.get('viewerUrl')}")
        print(f"fetched {name} {uid} {len(data) // 1024} KB")
    with open(os.path.join(out, "CREDITS.md"), "w") as f:
        f.write("\n".join(credits) + "\n")


def glb_maps(data):
    """Texture maps a glb's materials use, with each image's size, from its JSON chunk and PNG/JPEG headers."""
    import struct
    length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + length])
    blob_at = 20 + length + 8
    sizes = []
    for img in gltf.get("images", []):
        view = gltf["bufferViews"][img["bufferView"]] if "bufferView" in img else None
        try:
            raw = data[blob_at + view.get("byteOffset", 0):blob_at + view.get("byteOffset", 0) + view["byteLength"]]
            sizes.append(Image.open(io.BytesIO(raw)).size)
        except Exception:
            sizes.append(None)
    maps = {}
    for m in gltf.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        for key, tex in (("base", pbr.get("baseColorTexture")), ("mr", pbr.get("metallicRoughnessTexture")),
                         ("normal", m.get("normalTexture")), ("ao", m.get("occlusionTexture"))):
            if tex:
                src = gltf["textures"][tex["index"]].get("source")
                maps.setdefault(key, set()).add(str(sizes[src]) if src is not None and src < len(sizes) else "?")
    return {k: sorted(v) for k, v in maps.items()}, len(gltf.get("materials", []))


def probe(listing, out):
    token = os.environ.get("SKETCHFAB_TOKEN")
    if not token:
        sys.exit("SKETCHFAB_TOKEN is not set")
    os.makedirs(out, exist_ok=True)
    uids = []
    for line in open(listing):
        line = line.split("#")[0].strip()
        if line.startswith("q:"):
            for lic in LICENCES:
                params = {"type": "models", "q": line[2:].strip(), "downloadable": "true", "license": lic,
                          "pbr_type": "true", "count": 12, "sort_by": "-likeCount"}
                for m in get(f"{API}/search?{urllib.parse.urlencode(params)}").get("results", [])[:3]:
                    if m.get("faceCount", 0) <= 300000:
                        uids.append(m["uid"])
        elif line:
            uids.append(line.split()[0])
    report = {}
    for uid in list(dict.fromkeys(uids))[:40]:
        try:
            info = get(f"{API}/models/{uid}")
            links = get(f"{API}/models/{uid}/download", token=token)
            if not links.get("glb"):
                continue
            data = get(links["glb"]["url"], raw=True)
            if len(data) > 150 * 1024 * 1024:
                continue
            maps, mats = glb_maps(data)
            with open(os.path.join(out, f"probe_{uid}.glb"), "wb") as f:
                f.write(data)
            report[uid] = {"name": info["name"], "author": info["user"]["username"],
                           "licence": info["license"]["slug"] if isinstance(info.get("license"), dict) else None,
                           "faces": info.get("faceCount"), "mb": len(data) // (1024 * 1024), "materials": mats,
                           "maps": maps, "url": info.get("viewerUrl")}
            print(uid, json.dumps(report[uid]), flush=True)
        except Exception as e:
            print(f"probe {uid} failed: {e}")
    with open(os.path.join(out, "probe.json"), "w") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "search":
        search(sys.argv[2])
    elif sys.argv[1] == "probe":
        probe(sys.argv[2], sys.argv[3])
    else:
        fetch(sys.argv[2], sys.argv[3])
