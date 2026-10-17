"""Small 3D gas solver for baking fire, smoke and explosion flipbooks.

GeneralsX @feature Claude 16/10/2026 Blender's pip module ships a Mantaflow that cannot bake, so the
simulation runs here in numpy: semi-Lagrangian MacCormack advection, buoyancy from temperature, smoke
weight, vorticity confinement, a Jacobi pressure projection, and a fuel -> flame -> heat + soot
combustion step. blender_flipbook.py renders the result with Cycles.

Axes: arrays are [x, y, z] with z up; one cell is `dx` world units.
"""

import numpy as np


class Gas:
    def __init__(self, shape, dx, seed=1):
        self.shape = tuple(shape)
        self.dx = dx
        self.rng = np.random.default_rng(seed)
        z = np.zeros(self.shape, np.float32)
        self.u, self.v, self.w = z.copy(), z.copy(), z.copy()
        self.density = z.copy()
        self.temp = z.copy()
        self.fuel = z.copy()
        self.flame = z.copy()
        self.pressure = z.copy()
        # target divergence (1/s): gas expanding from combustion or a blast
        self.expand = z.copy()
        nx, ny, nz = self.shape
        self.gx, self.gy, self.gz = np.meshgrid(
            np.arange(nx, dtype=np.float32), np.arange(ny, dtype=np.float32),
            np.arange(nz, dtype=np.float32), indexing="ij")
        # parameters (per second, world units)
        self.buoyancy = 2.0
        self.weight = 0.4
        self.vorticity = 0.3
        self.cooling = 1.2
        self.burn_rate = 2.5
        self.heat = 3.0
        self.soot = 0.8
        self.density_decay = 0.0
        self.drag = 0.02
        self.expansion = 0.6
        self.flame_decay = 6.0
        self.glow_temp = 1.4
        self.flame_gain = 0.25
        self.wind = (0.0, 0.0)

    # --- sampling ---------------------------------------------------------------------------------

    def sample(self, f, x, y, z):
        nx, ny, nz = self.shape
        x = np.clip(x, 0, nx - 1.001)
        y = np.clip(y, 0, ny - 1.001)
        z = np.clip(z, 0, nz - 1.001)
        x0 = x.astype(np.int32)
        y0 = y.astype(np.int32)
        z0 = z.astype(np.int32)
        fx, fy, fz = x - x0, y - y0, z - z0
        c00 = f[x0, y0, z0] * (1 - fx) + f[x0 + 1, y0, z0] * fx
        c10 = f[x0, y0 + 1, z0] * (1 - fx) + f[x0 + 1, y0 + 1, z0] * fx
        c01 = f[x0, y0, z0 + 1] * (1 - fx) + f[x0 + 1, y0, z0 + 1] * fx
        c11 = f[x0, y0 + 1, z0 + 1] * (1 - fx) + f[x0 + 1, y0 + 1, z0 + 1] * fx
        return (c00 * (1 - fy) + c10 * fy) * (1 - fz) + (c01 * (1 - fy) + c11 * fy) * fz

    def advect(self, fields, dt):
        k = dt / self.dx
        bx = self.gx - self.u * k
        by = self.gy - self.v * k
        bz = self.gz - self.w * k
        fx = self.gx + self.u * k
        fy = self.gy + self.v * k
        fz = self.gz + self.w * k
        out = []
        for f in fields:
            a = self.sample(f, bx, by, bz)
            b = self.sample(a, fx, fy, fz)
            m = a + 0.5 * (f - b)
            # MacCormack limiter: keep within the neighbourhood the back trace touched.
            lo = np.minimum(a, f)
            hi = np.maximum(a, f)
            out.append(np.clip(m, lo - 0.05 * np.abs(hi - lo), hi + 0.05 * np.abs(hi - lo)))
        return out

    # --- forces -----------------------------------------------------------------------------------

    def confine(self, dt):
        u, v, w = self.u, self.v, self.w
        du = np.gradient(u)
        dv = np.gradient(v)
        dw = np.gradient(w)
        ox = dw[1] - dv[2]
        oy = du[2] - dw[0]
        oz = dv[0] - du[1]
        mag = np.sqrt(ox * ox + oy * oy + oz * oz)
        g = np.gradient(mag)
        n = np.sqrt(g[0] ** 2 + g[1] ** 2 + g[2] ** 2) + 1e-6
        nx_, ny_, nz_ = g[0] / n, g[1] / n, g[2] / n
        e = self.vorticity
        self.u += dt * e * (ny_ * oz - nz_ * oy)
        self.v += dt * e * (nz_ * ox - nx_ * oz)
        self.w += dt * e * (nx_ * oy - ny_ * ox)

    def project(self, iters=40):
        dx = self.dx
        u, v, w = self.u, self.v, self.w
        div = np.zeros(self.shape, np.float32)
        div[1:-1, :, :] += (u[2:, :, :] - u[:-2, :, :]) * 0.5
        div[:, 1:-1, :] += (v[:, 2:, :] - v[:, :-2, :]) * 0.5
        div[:, :, 1:-1] += (w[:, :, 2:] - w[:, :, :-2]) * 0.5
        div /= dx
        div -= self.expand
        p = self.pressure
        h2 = dx * dx
        for _ in range(iters):
            s = np.zeros_like(p)
            s[1:, :, :] += p[:-1, :, :]
            s[:-1, :, :] += p[1:, :, :]
            s[:, 1:, :] += p[:, :-1, :]
            s[:, :-1, :] += p[:, 1:, :]
            s[:, :, 1:] += p[:, :, :-1]
            s[:, :, :-1] += p[:, :, 1:]
            # Open top and sides (p = 0 outside), closed floor (mirror).
            s[:, :, 0] += p[:, :, 0]
            p = (s - div * h2) / 6.0
        self.pressure = p
        gp = np.gradient(p, dx)
        self.u -= gp[0]
        self.v -= gp[1]
        self.w -= gp[2]
        self.w[:, :, 0] = np.maximum(self.w[:, :, 0], 0)

    # --- step -------------------------------------------------------------------------------------

    def step(self, dt):
        self.density, self.temp, self.fuel, self.flame, u, v, w = self.advect(
            [self.density, self.temp, self.fuel, self.flame, self.u, self.v, self.w], dt)
        self.u, self.v, self.w = u, v, w
        # combustion: fuel above ignition burns into flame, heat and soot
        burn = np.minimum(self.fuel, self.fuel * self.burn_rate * dt + 0.0) * (self.temp > 0.3)
        self.fuel -= burn
        self.temp += burn * self.heat
        self.expand = self.expand * 0.5 + burn / max(dt, 1e-6) * self.expansion
        self.density += burn * self.soot
        self.flame = np.maximum(self.flame * np.exp(-self.flame_decay * dt), np.clip(burn / max(dt, 1e-6) * self.flame_gain, 0, 1.5))
        self.flame = np.maximum(self.flame, np.clip((self.temp - self.glow_temp) * 0.5, 0, 1.0))
        # forces
        self.w += dt * (self.buoyancy * self.temp - self.weight * self.density)
        self.u += dt * self.wind[0]
        self.v += dt * self.wind[1]
        self.confine(dt)
        damp = 1.0 - self.drag
        self.u *= damp
        self.v *= damp
        self.w *= damp
        self.project()
        self.temp *= np.exp(-self.cooling * dt)
        if self.density_decay:
            self.density *= np.exp(-self.density_decay * dt)
        np.clip(self.density, 0, 20, out=self.density)

    # --- sources ----------------------------------------------------------------------------------

    def blob(self, centre, radius, noise=0.4):
        """Soft lumpy sphere mask around a world-space centre (cells)."""
        cx, cy, cz = centre
        d = np.sqrt((self.gx - cx) ** 2 + (self.gy - cy) ** 2 + (self.gz - cz) ** 2)
        n = self.lumps(noise)
        return np.clip(1.0 - d / (radius * (1.0 + n)), 0, 1) ** 0.7

    def lumps(self, amount):
        if not amount:
            return 0.0
        if not hasattr(self, "_lumps"):
            # low-frequency value noise, made once per sim
            nx, ny, nz = self.shape
            c = self.rng.random((nx // 6 + 2, ny // 6 + 2, nz // 6 + 2)).astype(np.float32) * 2 - 1
            self._lumps = self.sample(c, self.gx / 6, self.gy / 6, self.gz / 6)
        return amount * self._lumps

    def radial(self, centre, mask, speed, up=0.0):
        cx, cy, cz = centre
        rx, ry, rz = self.gx - cx, self.gy - cy, self.gz - cz
        r = np.sqrt(rx * rx + ry * ry + rz * rz) + 1e-3
        jitter = 1.0 + 0.6 * self.rng.standard_normal(self.shape).astype(np.float32) * 0.5
        self.u += mask * speed * rx / r * jitter
        self.v += mask * speed * ry / r * jitter
        self.w += mask * (speed * rz / r * jitter + up)

    def turbulence(self, mask, strength):
        """Random swirl inside a source so plumes break up instead of rising as one bubble."""
        s = self.shape
        for f in (self.u, self.v, self.w):
            coarse = self.rng.standard_normal((s[0] // 4 + 2, s[1] // 4 + 2, s[2] // 4 + 2)).astype(np.float32)
            f += mask * strength * self.sample(coarse, self.gx / 4, self.gy / 4, self.gz / 4)
