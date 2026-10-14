#!/usr/bin/env python3
"""Convert the Real-ESRGAN x4plus PyTorch weights to ONNX without PyTorch.

The upscaler then runs through ONNX Runtime with DirectML (any DirectX 12 GPU)
or on the CPU. The ncnn Vulkan builds of Real-ESRGAN fail vkAllocateMemory on
the Radeon 780M while loading the model, so hdpack uses this path on Windows.

The .pth file is a zip with a pickled state dict; tensors are rebuilt from the
raw storages with numpy. The graph mirrors RRDBNet from xinntao/Real-ESRGAN
(BSD-3-Clause): 23 RRDB blocks, 64 features, 32 growth channels, 4x output.
"""

# GeneralsX @feature sav-labs 14/10/2026 Torch-free Real-ESRGAN x4plus to ONNX export for the HD pack builder.

import argparse
import pickle
import zipfile

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

STORAGE_DTYPES = {
    "FloatStorage": np.float32,
    "HalfStorage": np.float16,
    "DoubleStorage": np.float64,
    "LongStorage": np.int64,
}


def load_state_dict(path):
    archive = zipfile.ZipFile(path)
    root = archive.namelist()[0].split("/")[0]

    def rebuild_tensor(storage, offset, size, stride, *_):
        if not size:
            return storage[offset:offset + 1].reshape(())
        itemsize = storage.itemsize
        return np.lib.stride_tricks.as_strided(
            storage[offset:], shape=tuple(size), strides=tuple(s * itemsize for s in stride)).copy()

    class Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            if name == "_rebuild_tensor_v2":
                return rebuild_tensor
            if module == "collections" and name == "OrderedDict":
                import collections
                return collections.OrderedDict
            if name in STORAGE_DTYPES:
                return name
            raise pickle.UnpicklingError(f"unexpected global {module}.{name}")

        def persistent_load(self, pid):
            _, storage_type, key, _location, _numel = pid
            data = archive.read(f"{root}/data/{key}")
            return np.frombuffer(data, dtype=STORAGE_DTYPES[storage_type])

    state = Unpickler(archive.open(f"{root}/data.pkl")).load()
    for key in ("params_ema", "params"):
        if key in state:
            return state[key]
    return state


class GraphBuilder:
    def __init__(self, weights):
        self.weights = weights
        self.nodes = []
        self.initializers = []
        self.count = 0

    def name(self, prefix):
        self.count += 1
        return f"{prefix}_{self.count}"

    def const(self, value):
        n = self.name("const")
        self.initializers.append(numpy_helper.from_array(np.asarray(value, dtype=np.float32), n))
        return n

    def op(self, op_type, inputs, **attrs):
        out = self.name(op_type.lower())
        self.nodes.append(helper.make_node(op_type, inputs, [out], **attrs))
        return out

    def conv(self, x, layer):
        w = self.weights[f"{layer}.weight"].astype(np.float32)
        b = self.weights[f"{layer}.bias"].astype(np.float32)
        self.initializers.append(numpy_helper.from_array(w, f"{layer}.weight"))
        self.initializers.append(numpy_helper.from_array(b, f"{layer}.bias"))
        return self.op("Conv", [x, f"{layer}.weight", f"{layer}.bias"], kernel_shape=[3, 3], pads=[1, 1, 1, 1])

    def lrelu(self, x):
        return self.op("LeakyRelu", [x], alpha=0.2)

    def residual(self, x, out):
        """out * 0.2 + x, as in RRDBNet."""
        return self.op("Add", [self.op("Mul", [out, self.const(0.2)]), x])

    def rdb(self, x, prefix):
        feats = [x]
        for i in range(1, 5):
            inp = feats[0] if len(feats) == 1 else self.op("Concat", feats, axis=1)
            feats.append(self.lrelu(self.conv(inp, f"{prefix}.conv{i}")))
        x5 = self.conv(self.op("Concat", feats, axis=1), f"{prefix}.conv5")
        return self.residual(x, x5)

    def upsample2(self, x):
        scales = self.const([1.0, 1.0, 2.0, 2.0])
        return self.op("Resize", [x, "", scales], mode="nearest")


def build_model(weights, num_blocks):
    g = GraphBuilder(weights)
    feat = g.conv("input", "conv_first")
    body = feat
    for i in range(num_blocks):
        out = body
        for j in range(1, 4):
            out = g.rdb(out, f"body.{i}.rdb{j}")
        body = g.residual(body, out)
    feat = g.op("Add", [feat, g.conv(body, "conv_body")])
    feat = g.lrelu(g.conv(g.upsample2(feat), "conv_up1"))
    feat = g.lrelu(g.conv(g.upsample2(feat), "conv_up2"))
    out = g.conv(g.lrelu(g.conv(feat, "conv_hr")), "conv_last")
    g.nodes.append(helper.make_node("Identity", [out], ["output"]))

    graph = helper.make_graph(
        g.nodes, "realesrgan_x4plus",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, "height", "width"])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3, "height4", "width4"])],
        g.initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pth", help="RealESRGAN_x4plus.pth")
    ap.add_argument("onnx", help="Output .onnx")
    args = ap.parse_args()
    weights = load_state_dict(args.pth)
    num_blocks = 1 + max(int(k.split(".")[1]) for k in weights if k.startswith("body."))
    onnx.save(build_model(weights, num_blocks), args.onnx)
    print(f"wrote {args.onnx} ({num_blocks} RRDB blocks)")


if __name__ == "__main__":
    main()
