#!/usr/bin/env python3
# GeneralsX @feature Claude 16/10/2026 Minimal Direct3D pixel shader 1.x assembler.
# GeneralsX @feature Claude 16/10/2026 Also assembles vs.1.1 vertex shaders (model normal maps).
#
# The 64-bit and non-Windows builds have no D3DXAssembleShader (CompatLib stubs it),
# so shaders that are not shipped as .pso files are embedded as token arrays.
# This tool turns ps.1.1 - ps.1.4 assembly into those tokens, so the C++ arrays can
# be regenerated from the assembly kept next to them.
#
# Usage: assemble_ps1x.py shader.psh [--name kTokens] [--bin out.bin]
# Prints a C++ "static const DWORD name[] = {...};" array; --bin also writes the
# raw little-endian token stream (for validation with an external DXSO compiler).
#
# Supported: ps.1.x version line, texld/texcrd (1.4), tex (1.1-1.3), mov, add, sub,
# mul, mad, lrp, dp3, dp4, cnd, cmp, nop, phase; instruction modifiers _x2 _x4 _x8
# _d2 _d4 _d8 _sat; co-issue prefix "+"; destination write masks; source negate,
# 1-x complement, _bias, _bx2, _x2 and single channel or full swizzles.
#
# vs.1.1: mov, add, mul, mad, rcp, rsq, dp3, dp4, min, max, slt, sge; registers r, v, c,
# oPos, oFog, oPts, oD0-1, oT0-7; write masks, negate and 1 to 4 channel swizzles (a short
# swizzle repeats its last channel, as in the D3D assembler).

import argparse
import re
import struct
import sys

OPCODES = {
    "nop": (0, 0), "mov": (1, 1), "add": (2, 2), "sub": (3, 2), "mad": (4, 3),
    "mul": (5, 2), "dp3": (8, 2), "dp4": (9, 2), "lrp": (18, 3),
    "texcrd": (64, 1), "texcoord": (64, 0), "tex": (66, 0), "texld": (66, 1),
    "cnd": (80, 3), "cmp": (88, 3), "phase": (0xFFFD, -1),
}

VS_OPCODES = {
    "mov": (1, 1), "add": (2, 2), "mad": (4, 3), "mul": (5, 2), "rcp": (6, 1),
    "rsq": (7, 1), "dp3": (8, 2), "dp4": (9, 2), "min": (10, 2), "max": (11, 2),
    "slt": (12, 2), "sge": (13, 2),
}

# vertex shader output registers: name -> (register type, number)
VS_OUTPUTS = {"opos": (4, 0), "ofog": (4, 1), "opts": (4, 2)}

REGTYPES = {"r": 0, "v": 1, "c": 2, "t": 3}
CHANNELS = {"r": 0, "g": 1, "b": 2, "a": 3, "x": 0, "y": 1, "z": 2, "w": 3}
SHIFTS = {"x2": 1, "x4": 2, "x8": 3, "d2": 0xF, "d4": 0xE, "d8": 0xD}
SRCMODS = {None: 0, "neg": 1, "bias": 2, "biasneg": 3, "bx2": 4, "bx2neg": 5,
           "comp": 6, "x2": 7, "x2neg": 8}

END_TOKEN = 0x0000FFFF


class AsmError(Exception):
    pass


def reg_bits(text):
    low = text.lower()
    m = re.fullmatch(r"([rvct])(\d+)", text)
    if low in VS_OUTPUTS:
        rtype, num = VS_OUTPUTS[low]
    elif re.fullmatch(r"od[01]", low):
        rtype, num = 5, int(low[2])
    elif re.fullmatch(r"ot[0-7]", low):
        rtype, num = 6, int(low[2])
    elif m:
        rtype = REGTYPES[m.group(1)]
        num = int(m.group(2))
    else:
        raise AsmError(f"bad register '{text}'")
    return 0x80000000 | ((rtype & 7) << 28) | ((rtype & 0x18) << 8) | (num & 0x7FF)


def dest_token(text, mods):
    reg, _, mask = text.partition(".")
    tok = reg_bits(reg)
    if mask:
        bits = 0
        for ch in mask:
            bits |= 1 << CHANNELS[ch]
    else:
        bits = 0xF
    tok |= bits << 16
    for mod in mods:
        if mod == "sat":
            tok |= 1 << 20
        elif mod in SHIFTS:
            tok |= SHIFTS[mod] << 24
        else:
            raise AsmError(f"bad instruction modifier '_{mod}'")
    return tok


def src_token(text):
    neg = text.startswith("-")
    if neg:
        text = text[1:]
    comp = False
    if text.startswith("1-"):
        comp = True
        text = text[2:]
    reg, _, swz = text.partition(".")
    mod = None
    if "_" in reg:
        reg, mod = reg.split("_", 1)
    tok = reg_bits(reg)
    if swz:
        chans = [CHANNELS[c] for c in swz]
        if not 1 <= len(chans) <= 4:
            raise AsmError(f"unsupported swizzle '.{swz}'")
        chans = chans + [chans[-1]] * (4 - len(chans))
    else:
        chans = [0, 1, 2, 3]
    tok |= (chans[0] | chans[1] << 2 | chans[2] << 4 | chans[3] << 6) << 16
    if comp:
        if mod or neg:
            raise AsmError("1-x cannot be combined with other source modifiers")
        key = "comp"
    else:
        key = mod
        if neg:
            key = (mod or "") + "neg" if mod else "neg"
    if key not in SRCMODS:
        raise AsmError(f"bad source modifier in '{text}'")
    tok |= SRCMODS[key] << 24
    return tok


def assemble(source):
    tokens = []
    version = None
    for lineno, raw in enumerate(source.splitlines(), 1):
        line = raw.split(";", 1)[0].split("//", 1)[0].strip()
        if not line:
            continue
        try:
            if version is None:
                if line == "vs.1.1":
                    version = "vs"
                    tokens.append(0xFFFE0101)
                    continue
                m = re.fullmatch(r"ps\.1\.([1-4])", line)
                if not m:
                    raise AsmError("first statement must be ps.1.x or vs.1.1")
                version = int(m.group(1))
                tokens.append(0xFFFF0100 | version)
                continue
            if version == "vs":
                parts = line.split(None, 1)
                name = parts[0].lower()
                args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []
                if name not in VS_OPCODES:
                    raise AsmError(f"unknown vs.1.1 instruction '{name}'")
                opcode, nsrc = VS_OPCODES[name]
                if len(args) != 1 + nsrc:
                    raise AsmError(f"{name} takes {1 + nsrc} operands")
                consts = {a.lstrip("-").split(".")[0] for a in args[1:] if a.lstrip("-").startswith("c")}
                if len(consts) > 1:
                    raise AsmError("vs.1.1 reads at most one constant register per instruction")
                tokens.append(opcode)
                tokens.append(dest_token(args[0], []))
                for src in args[1:]:
                    if src.lstrip("-").startswith("1-") or "_" in src:
                        raise AsmError(f"vs.1.1 sources only take negate: '{src}'")
                    tokens.append(src_token(src))
                continue
            coissue = line.startswith("+")
            if coissue:
                line = line[1:].strip()
            parts = line.split(None, 1)
            name, *mods = parts[0].lower().split("_")
            args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []
            if name not in OPCODES:
                raise AsmError(f"unknown instruction '{name}'")
            opcode, nsrc = OPCODES[name]
            if name == "phase":
                if version != 4:
                    raise AsmError("phase needs ps.1.4")
                tokens.append(0x0000FFFD)
                continue
            if name in ("texld", "texcrd") and version != 4:
                raise AsmError(f"{name} needs ps.1.4")
            if name == "tex" and version == 4:
                raise AsmError("use texld in ps.1.4")
            expect = (1 + nsrc) if name != "nop" else 0
            if len(args) != expect:
                raise AsmError(f"{name} takes {expect} operands")
            tok = opcode | (0x40000000 if coissue else 0)
            tokens.append(tok)
            if name == "nop":
                continue
            tokens.append(dest_token(args[0], mods))
            for src in args[1:]:
                tokens.append(src_token(src))
        except (AsmError, KeyError) as exc:
            raise AsmError(f"line {lineno}: {exc}: {raw.strip()}") from None
    if version is None:
        raise AsmError("empty shader")
    tokens.append(END_TOKEN)
    return tokens


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("--name", default="kShaderTokens")
    ap.add_argument("--bin")
    args = ap.parse_args()
    with open(args.source, encoding="utf-8") as fh:
        tokens = assemble(fh.read())
    if args.bin:
        with open(args.bin, "wb") as fh:
            fh.write(struct.pack(f"<{len(tokens)}I", *tokens))
    print(f"static const DWORD {args.name}[] =\n{{")
    for i in range(0, len(tokens), 6):
        print("\t" + ", ".join(f"0x{t:08x}" for t in tokens[i:i + 6]) + ",")
    print("};")


if __name__ == "__main__":
    try:
        main()
    except AsmError as exc:
        sys.exit(f"assemble_ps1x: {exc}")
