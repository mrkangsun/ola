"""
🎂 Birthday Cake — versi web (Streamlit)

Satu file, responsif (HP / tablet / laptop), tanpa pygame.
Alur:  [Tirai opera tertutup]  --ketuk/sentuh-->  tirai terbuka  -->  [Animasi kue ASCII 3D]

Jalankan lokal :  streamlit run app.py
Hosting        :  push app.py + requirements.txt ke GitHub -> Streamlit Community Cloud

Link personal  :  https://<app>.streamlit.app/?untuk=Imi
"""

import base64
import io
import json
import re
import threading
import time
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ════════════════════════════════════════════════════════════════════════════
#  ⚙️  PENGATURAN — ubah bagian ini sesuai kebutuhan
# ════════════════════════════════════════════════════════════════════════════
CONFIG = {
    "page_title": "Pertunjukan Ulang Tahun",
    "page_icon": "🎂",
    "title": "Birthday Cake",                 # judul di atas animasi
    "sign": "@abin.zip · 2026",               # tanda tangan kecil di pojok animasi
    "lines": ["HAPPY", "BIRTHDAY", "TEH SINTAA"],      # 1–3 baris tulisan (A–Z, angka, . , ! ? ' & - :  maks 12 huruf)
    "curtain_title": "PERTUNJUKAN SPESIAL",   # tulisan emas di tirai
    "curtain_to": "Kamu",                     # "Untuk: ..." di tirai (kosongkan "" untuk menyembunyikan;
                                              #   bisa ditimpa lewat link ?untuk=Nama)
    "curtain_hint": "ketuk tirai untuk membuka",
    "music": "lagu.mp3",                      # file mp3 di folder yang sama dengan app.py (atau link https://...mp3)
                                              #   kosongkan "" kalau tidak mau ada musik
    "music_volume": 0.7,                      # 0.0 – 1.0
    "fps": 20,                                # frame/detik hasil render (15–24; makin besar makin berat)
}

TAU = np.pi * 2
LOOP = 18.0         # panjang satu putaran (detik)
BUILD = 3.4         # kue "tergambar" sampai detik ini

st.set_page_config(
    page_title=CONFIG["page_title"],
    page_icon=CONFIG["page_icon"],
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ════════════════════════════════════════════════════════════════════════════
#  ENGINE 3D → HURUF  (dari kode asli, tanpa pygame)
# ════════════════════════════════════════════════════════════════════════════
POOLS = ["1il!;:", "rtfjcvxz=+", "aeoun0{}[]<>", "08B$#&%Q"]   # gelap -> terang
CHARS = " .,:~+*^01|/\\-_#()x" + "".join(POOLS)
AT = {c: i for i, c in enumerate(CHARS)}
FILL = np.array([[AT[p[k % len(p)]] for k in range(12)] for p in POOLS])

(SPONGE, CRUST, CREAM, FROST, RED, RED_HI, PLATE, GOLD, CORE, FLAME, GLOW, WICK,
 LIT_S, LIT_F, HAPPY, BDAY) = range(16)
DOTS = np.arange(16, 22)    # warna taburan / konfeti


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def rot_y(p, a):
    c, s = np.cos(a), np.sin(a)
    return np.stack([c * p[:, 0] + s * p[:, 2], p[:, 1], -s * p[:, 0] + c * p[:, 2]], 1)


# kamera

def camera(eye, target):
    eye, target = np.asarray(eye, float), np.asarray(target, float)
    fwd = (target - eye) / np.linalg.norm(target - eye)
    right = np.cross(fwd, [0, 1.0, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)

    def look(P):
        rel = P - eye
        return rel @ right, rel @ up, rel @ fwd, -fwd
    return look


look = camera(eye=(1.0, 2.6, 7.9), target=(1.0, 1.85, 0))
F = 2.9     # lensa

# irisan kue: dua lapis bolu dengan krim di tengah

R, FT, TOP = 1.6, 0.08, 0.98        # radius, tebal frosting, tinggi
A0, A1 = np.radians(-28), np.radians(30)
CANDLE = np.array([0.62 * R, 0.0, 0.0])


def ring(a):
    return np.stack([np.cos(a), 0 * a, -np.sin(a)], -1)


def frosting(x, z):
    # tinggi permukaan atas: gelombang di tepi + pusaran di sekitar lilin
    r, a = np.hypot(x, z), np.arctan2(-z, x)
    edge = 0.15 * np.exp(-((r - 1.3) / 0.26) ** 2) * (0.55 + 0.45 * np.sin(a * 22 - r * 14))
    d = np.hypot(x - CANDLE[0], z - CANDLE[2])
    swirl = 0.2 * np.exp(-(d / 0.34) ** 2) * (0.6 + 0.4 * np.sin(np.arctan2(z, x - CANDLE[0]) * 3 + d * 30))
    return TOP + 0.04 + edge + swirl


def cake():
    rng = np.random.default_rng(7)
    P, N, T, K = [], [], [], []

    def add(p, n, t, k):
        P.append(p)
        N.append(n)
        T.append(np.broadcast_to(t, len(p)))
        K.append(np.broadcast_to(k, len(p)))

    # sisi potongan
    for a, side in ((A0, 1), (A1, -1)):
        n = 9000
        r, y = rng.uniform(0, R + FT, n), rng.uniform(0, TOP, n)
        p = r[:, None] * ring(np.full(n, a)) + y[:, None] * [0, 1, 0]
        crust = (y < 0.05) | ((y > 0.37) & (y < 0.42)) | ((y > 0.56) & (y < 0.6)) | ((y > 0.9) & (y < 0.95))
        cream = (y > 0.42) & (y < 0.56)
        frost = (y >= 0.95) | (r > R)
        t = np.where(frost, FROST, np.where(cream, CREAM, np.where(crust, CRUST, SPONGE)))
        k = np.where(frost, 3, np.where(cream, 2, 1))
        add(p, np.tile(side * np.array([np.sin(a), 0, np.cos(a)]), (n, 1)), t, k)

    # sisi luar
    n = 9000
    a, y = rng.uniform(A0, A1, n), rng.uniform(0, TOP + 0.04, n)
    p = (R + FT + 0.025 * np.sin(a * 40 + y * 9))[:, None] * ring(a) + y[:, None] * [0, 1, 0]
    add(p, ring(a), FROST, 3)

    # atas
    n = 12000
    r, a = (R + FT) * np.sqrt(rng.uniform(0, 1, n)), rng.uniform(A0, A1, n)
    xz = r[:, None] * ring(a)
    x, z, e = xz[:, 0], xz[:, 2], 0.01
    y = frosting(x, z)
    nr = np.stack([-(frosting(x + e, z) - y) / e, np.ones(n), -(frosting(x, z + e) - y) / e], 1)
    add(np.stack([x, y, z], 1), nr / np.linalg.norm(nr, axis=1, keepdims=True), FROST, 3)

    # lilin (belang berpilin) dan sumbu
    base = frosting(CANDLE[0], CANDLE[2]) - 0.05
    n = 2500
    a, y = rng.uniform(0, TAU, n), rng.uniform(0, 0.62, n)
    rad = np.stack([np.cos(a), 0 * a, np.sin(a)], 1)
    add(CANDLE + 0.075 * rad + (base + y)[:, None] * [0, 1, 0], rad,
        np.where(np.sin(a + y * 16) > 0.45, RED_HI, RED), 4)
    w = np.linspace(0, 0.07, 30)
    add(CANDLE + (base + 0.62 + w)[:, None] * [0, 1, 0], np.tile([0, 0, 1.0], (30, 1)), WICK, 4)

    # piring dengan tepi emas bergelombang
    n, rp = 9000, 1.3
    a, u = rng.uniform(0, TAU, n), np.sqrt(rng.uniform(0, 1, n))
    rim = rp + 0.06 * np.sin(a * 12)
    r = u * rim
    p = np.stack([1.0 + r * np.cos(a), -0.02 + 0.06 * u ** 4, r * np.sin(a)], 1)
    add(p, np.tile([0, 1.0, 0], (n, 1)), np.where(u > 0.93, GOLD, PLATE), 0)
    a, y = rng.uniform(0, TAU, 3000), rng.uniform(-0.1, 0.04, 3000)
    rim = rp + 0.06 * np.sin(a * 12)
    add(np.stack([1.0 + rim * np.cos(a), y, rim * np.sin(a)], 1),
        np.stack([np.cos(a), 0 * a, np.sin(a)], 1), GOLD, 0)

    # taburan: di atas kue, sebagian di piring
    for i in range(110):
        if i < 90:
            r, a = rng.uniform(0.25, R, 1), rng.uniform(A0 + 0.05, A1 - 0.05, 1)
            c = (r[:, None] * ring(a))[0]
            if np.hypot(*(c - CANDLE)[[0, 2]]) < 0.12:
                continue
            c[1] = frosting(c[0], c[2]) + 0.02
        else:
            a, r = rng.uniform(1.2, 4.6), rng.uniform(0.95, 1.2)
            c = np.array([1.0 + r * np.cos(a), 0.0, r * np.sin(a)])
        d = rng.normal(size=3) * [1, 0.3, 1]
        s = np.linspace(-0.06, 0.06, 10)[:, None]
        add(c + s * d / np.linalg.norm(d), np.tile([0, 1.0, 0], (10, 1)), rng.choice(DOTS), 5)

    P, N, T, K = (np.concatenate(v) for v in (P, N, T, K))
    order = (P[:, 1] + 0.12) / 2.3 + rng.uniform(0, 0.1, len(P))            # dibangun dari bawah ke atas
    fly = np.where(rng.uniform(0, 1, len(P))[:, None] < 1 / 30, rng.normal(size=(len(P), 3)) * 2.2, 0)
    return P, N, T.astype(int), K.astype(int), order, fly, base + 0.69


@st.cache_resource(show_spinner=False)
def _geometry():
    return cake()          # dibuat sekali saja, dipakai ulang oleh semua pengunjung


P0, N0, T0, K0, ORDER, FLY, WICK_TOP = _geometry()
GRAIN = np.where(np.isin(T0, (SPONGE, CRUST)), np.random.default_rng(5).uniform(0.6, 1.0, len(T0)), 1.0)
CENTER = np.array([1.0, 0, 0])


# nyala api lilin

def flicker(t):
    return 0.82 + 0.1 * np.sin(t * 13) + 0.06 * np.sin(t * 29 + 1) + 0.04 * np.sin(t * 47 + 2)


def flame(t, tip, grow, f):
    rng = np.random.default_rng(3)
    u, v = rng.uniform(-1, 1, 900), rng.uniform(0, 1, 900)
    width = 0.15 * np.sin(np.pi * v ** 0.75) * (1 - 0.35 * v)
    lean = 0.05 * np.sin(t * 2.3) + 0.02 * np.sin(t * 7)
    hgt = 0.6 * f * grow
    p = tip + np.stack([u * width * grow + lean * v ** 2, (v - 0.12) * hgt, 0 * u + 0.05], 1)
    core = (np.abs(u) < 0.5) & (v < 0.62)
    return p, np.where(core, CORE, FLAME), np.where(core, 1.0, 0.82)


def project(p, cols, rows, aspect):
    x, y, z, _ = look(p[None])
    return int((0.5 - y[0] / z[0] * F * 0.5 * aspect) * rows), int((0.5 + x[0] / z[0] * F * 0.5) * cols)


# tulisan besar

# Font tebal mini (DejaVu Sans Bold, hanya A–Z 0–9 dan tanda baca dasar) — ikut di dalam file ini
# supaya tulisan besar tampil sama di semua server, tanpa perlu font sistem.
EMBEDDED_FONT = (
    "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"
)
FONTS = ["seguibl.ttf", "C:/Windows/Fonts/seguibl.ttf", "ariblk.ttf", "Arial Black.ttf",
         "/System/Library/Fonts/Supplemental/Arial Black.ttf", "DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
ALLOWED = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?'&-:"


def heavy_font(px):
    """Kembalikan (font, tipis?) — pakai font tebal yang ikut di file; cadangan: font sistem."""
    try:
        data = zlib.decompress(base64.b64decode(EMBEDDED_FONT))
        return ImageFont.truetype(io.BytesIO(data), px), False
    except Exception:       # noqa: BLE001
        pass
    for name in FONTS:
        try:
            return ImageFont.truetype(name, px), False
        except OSError:
            pass
    try:
        return ImageFont.load_default(px), True
    except TypeError:
        return ImageFont.load_default(), True


def word(TEXT, text, cols, rows, scale, cy, hrows):
    # cakupan tiap sel huruf, 0..1
    key = (text, cols, rows, round(scale, 2), cy, hrows)
    if key not in TEXT:
        ref, thin = heavy_font(100)
        sw = 6 if thin else 0                       # font tipis diberi garis tepi; ukurannya ikut dihitung
        cap = ref.getbbox("H", stroke_width=sw)[3] - ref.getbbox("H", stroke_width=sw)[1]
        px_w = 100 * 0.90 * cols * 9 / (ref.getlength(text) + 2 * sw)
        px_h = 100 * hrows * 14 / cap
        px = max(8, int(min(px_w, px_h) * scale))
        font, _ = heavy_font(px)
        im = Image.new("L", (cols * 9, rows * 14), 0)
        ImageDraw.Draw(im).text((cols * 4.5, cy * 14), text, font=font, fill=255, anchor="mm",
                                stroke_width=round(px * sw / 100), stroke_fill=255)
        TEXT[key] = np.asarray(im, np.float32).reshape(rows, 14, cols, 9).mean((1, 3)) / 255
    return TEXT[key]


def pop(p):
    # ease-out dengan sedikit overshoot
    c1 = 1.70158
    q = p - 1
    return 1 + (c1 + 1) * q ** 3 + c1 * q ** 2


# titik -> huruf

def outline_letter(gx, gy):
    ax, ay = np.abs(gx), np.abs(gy)
    c = np.where(ax > 2 * ay, AT["|"], np.where(ay > 2 * ax, np.where(gy > 0, AT["_"], AT["-"]),
                 np.where(gx * gy > 0, AT["/"], AT["\\"])))
    return np.where((ax + ay) == 0, AT["+"], c)


def raster(t, cols, rows, aspect, P, shade, T, K):
    x, y, z, _ = look(P)
    zz = np.maximum(z, 0.2)
    sx = (0.5 + x / zz * F * 0.5) * cols
    sy = (0.5 - y / zz * F * 0.5 * aspect) * rows
    order = np.argsort(-z)                              # jauh -> dekat
    sx, sy, z, shade, T, K = sx[order], sy[order], z[order], shade[order], T[order], K[order]
    ix, iy = sx.astype(int), sy.astype(int)
    ok = (ix >= 0) & (ix < cols) & (iy >= 0) & (iy < rows) & (z > 0.2)

    part = np.full((rows, cols), -1)
    depth = np.full((rows, cols), 99.0)
    lum = np.zeros((rows, cols))
    tag = np.zeros((rows, cols), int)
    part[iy[ok], ix[ok]], depth[iy[ok], ix[ok]] = K[ok], z[ok]
    lum[iy[ok], ix[ok]], tag[iy[ok], ix[ok]] = shade[ok], T[ok]
    body = part >= 0

    # garis tepi: sel di sebelah ruang kosong atau bagian lain yang lebih jauh
    pp = np.pad(part, 1, constant_values=-1)
    pd = np.pad(depth, 1, constant_values=99)
    edge = np.zeros_like(body)
    gx = np.zeros((rows, cols))
    gy = np.zeros((rows, cols))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == dy == 0:
                continue
            nb = pp[1 + dy:rows + 1 + dy, 1 + dx:cols + 1 + dx]
            nz = pd[1 + dy:rows + 1 + dy, 1 + dx:cols + 1 + dx]
            out = body & ((nb < 0) | ((nb != part) & (nz > depth + 0.035)))
            gx += dx * out
            gy += dy * out
            if dx == 0 or dy == 0:
                edge |= out

    r, c = np.mgrid[0:rows, 0:cols]
    h = (r * 7919 + c * 104729) % 9973                  # hash tetap per sel
    level = np.clip((lum * 3.2).astype(int), 0, 3)
    fill = FILL[level, (h + (t * 4 + h % 11).astype(int)) % 12]
    char = np.where(body, np.where(edge, outline_letter(gx, gy), fill), 0)
    lum = np.where(body, np.where(edge, np.maximum(0.5, lum), np.clip(lum, 0, 1)), 0)
    return SimpleNamespace(char=char, lum=lum, tag=tag, body=body, h=h, rows=rows, cols=cols, count=int(body.sum()))


def rays(g, cy, cx, reach, glint_tag, diag=0.7):
    # bintang empat sudut
    char, lum, tag, rows, cols = g.char, g.lum, g.tag, g.rows, g.cols
    for dist in range(1, reach + 1):
        fade = 1 - dist / (reach + 1)
        for (dy, dx, ch) in ((0, 1, "-"), (0, -1, "-"), (1, 0, "|"), (-1, 0, "|")):
            yy, xx = cy + dy * dist, cx + dx * dist * 2
            if 0 <= yy < rows and 0 <= xx < cols and lum[yy, xx] < fade:
                char[yy, xx], lum[yy, xx], tag[yy, xx] = AT[ch], fade, glint_tag
        if dist <= reach // 2:
            for (dy, dx, ch) in ((1, 1, "\\"), (-1, -1, "\\"), (1, -1, "/"), (-1, 1, "/")):
                yy, xx = cy + dy * dist, cx + dx * dist
                if 0 <= yy < rows and 0 <= xx < cols and lum[yy, xx] < fade * diag:
                    char[yy, xx], lum[yy, xx], tag[yy, xx] = AT[ch], fade * diag, glint_tag
    char[cy, cx], lum[cy, cx] = AT["*"], 1.0


# posisi baris tulisan (pusat baris, dalam satuan sel) menurut jumlah baris
WORD_ROWS = {1: [13.5], 2: [9.5, 17.5], 3: [5.5, 13.5, 22.0]}


# satu frame

def frame(t, cols, rows, aspect, lines, TEXT):
    turn = 0.95 + 0.08 * np.sin(t * 0.5)
    P = rot_y(P0 - CENTER, turn) + CENTER
    N = rot_y(N0, turn)
    head = (t - 0.2) / (BUILD - 0.2) * 1.25
    rev = smooth((head - ORDER) / 0.12)
    P = P + (1 - rev)[:, None] * FLY

    on = smooth((t - 4.4) / 0.8)
    f = flicker(t)
    tip = rot_y((CANDLE + [0, WICK_TOP, 0] - CENTER)[None], turn)[0] + CENTER
    light = tip + [0.03 * np.sin(t * 2.3), 0.18, 0.05]

    # cahaya utama + cahaya lilin hangat yang hanya menjangkau yang dekat
    view = look(P)[3]
    key = np.array([-0.5, 0.8, 0.6]) / np.linalg.norm([-0.5, 0.8, 0.6])
    rim = np.array([0.8, 0.3, -0.5])
    diff = np.clip(N @ key, 0, 1)
    half_k = (key + view) / np.linalg.norm(key + view)
    half_r = (rim + view) / np.linalg.norm(rim + view)
    spec = np.clip(N @ half_k, 0, 1) ** 24 + 0.7 * np.clip(N @ half_r, 0, 1) ** 18
    d = light - P
    dist = np.linalg.norm(d, axis=1)
    glow = on * f * (0.3 + 0.7 * np.clip((N * d).sum(1) / dist, 0, 1)) * np.exp(-(dist / 1.6) ** 2) * 1.3
    shade = (0.3 + 0.45 * diff + 0.12 * spec + 0.45 * glow) * rev * GRAIN * np.where(K0 == 0, 0.6, 1.0)
    T = np.where(glow > 0.3, np.where(np.isin(T0, (SPONGE, CRUST)), LIT_S,
                                      np.where(T0 == FROST, LIT_F, T0)), T0)
    keep = rev > 0.01
    P, shade, T, K = P[keep], shade[keep], T[keep], K0[keep]

    grow = smooth((t - 4.3) / 0.7)
    if grow > 0:
        fp, ft, fs = flame(t, tip, grow, f)
        P, shade = np.concatenate([P, fp]), np.concatenate([shade, fs * (0.6 + 0.4 * grow)])
        T, K = np.concatenate([T, ft]), np.concatenate([K, np.full(len(fp), 6)])

    g = raster(t, cols, rows, aspect, P, shade, T, K)
    char, lum, tag = g.char, g.lum, g.tag
    r, c = np.mgrid[0:rows, 0:cols]
    h = g.h

    # tekstur: remah di bolu, gelombang di krim
    inner = g.body & ~np.isin(char, [AT[x] for x in "/|\\-_+"])
    crumb = np.array([AT[x] for x in "o0ae.:o0"])[(h + int(t * 2) * (h % 3 == 0)) % 8]
    wave = np.where(h % 5 == 0, AT["^"], AT["~"])
    texture = {SPONGE: crumb, LIT_S: crumb, CRUST: AT["="], CREAM: AT["~"], FROST: wave, LIT_F: wave,
               PLATE: np.where(h % 4 == 0, AT[":"], AT["."]), GOLD: AT["="]}
    for k, ch in texture.items():
        char = np.where(inner & (tag == k), ch, char)
    lum = np.where(inner & (tag == CREAM), np.maximum(lum, 0.85), lum)
    lum = np.where(g.body & (tag == PLATE), lum * 0.8, lum)

    # halo di sekitar api
    cy, cx = project(light, cols, rows, aspect)
    if on > 0:
        rg = (6 + 1.5 * f) * on
        fall = 1 - np.hypot(r - cy, (c - cx) * 9 / 14) / rg
        halo = (char == 0) & (fall > 0) & ((h + int(t * 9)) % 3 != 0)
        char = np.where(halo, np.where(fall < 0.4, AT["."], np.where(fall < 0.7, AT[":"], AT["+"])), char)
        lum = np.where(halo, 0.6 * fall * on * f, lum)
        tag = np.where(halo, GLOW, tag)

    # percikan saat lilin menyala
    if 4.3 < t < 5.4:
        k = (t - 4.3) / 1.1
        for i in range(14):
            a = i * 2.4 + k * 3
            sy, sx = int(cy + 2 - k * 7 * (0.6 + 0.4 * (i % 3)) + np.sin(a) * 2), int(cx + np.cos(a) * (2 + k * 9))
            if 0 <= sy < rows and 0 <= sx < cols and char[sy, sx] == 0:
                char[sy, sx], lum[sy, sx], tag[sy, sx] = AT["*" if i % 2 else "+"], 1 - k, CORE

    # konfeti
    pieces = 0
    rng = np.random.default_rng(11)
    for i in range(110):
        x0, speed, delay = rng.uniform(0, cols), rng.uniform(4, 9), rng.uniform(0, 5)
        amp, w, ph, col = rng.uniform(1, 4), rng.uniform(1, 2.5), rng.uniform(0, TAU), rng.choice(DOTS)
        age = t - 6.2 - delay
        if age < 0:
            continue
        y = int(age * speed % (rows + 4)) - 2
        x = int(x0 + amp * np.sin(w * t + ph))
        if 0 <= y < rows and 0 <= x < cols and (char[y, x] == 0 or tag[y, x] == GLOW):
            spin = "-/|\\"[int(t * w * 3 + ph) % 4] if i % 7 else "o"
            char[y, x], lum[y, x], tag[y, x] = AT[spin], 0.85, col
            pieces += 1

    # tulisan besar
    n_lines = len(lines)
    for k, text in enumerate(lines):
        ts, cyr = 8.0 + 0.4 * k, WORD_ROWS[n_lines][k]
        tg = HAPPY if k < n_lines - 1 else BDAY
        p = np.clip((t - ts) / 0.5, 0, 1)
        if p <= 0:
            continue
        cov = word(TEXT, text, cols, rows, 1.55 - 0.55 * pop(p), cyr, 7.0)
        on_t = (cov > 0.45) & ((h % 997) / 997 < smooth(p * 1.6))
        gx = -(np.roll(cov, -1, 1) - np.roll(cov, 1, 1))
        gy = -(np.roll(cov, -1, 0) - np.roll(cov, 1, 0))
        edge = on_t & ((np.roll(cov, 1, 0) < 0.45) | (np.roll(cov, -1, 0) < 0.45) |
                       (np.roll(cov, 1, 1) < 0.45) | (np.roll(cov, -1, 1) < 0.45))
        fill = FILL[3, (h + int(t * 4) + h % 11) % 12]
        char = np.where(on_t, np.where(edge, outline_letter(gx * 10, gy * 10), fill), char)
        shine = 0.8 + 0.2 * np.sin(t * 3 - c * 0.12)
        lum = np.where(on_t, np.clip(shine * (1 + 0.5 * (1 - p)), 0, 1), lum)
        tag = np.where(on_t, tg, tag)

    g.char, g.lum, g.tag = char, lum, tag
    if t > 9.6:
        lit = np.argwhere(tag == HAPPY)
        for n in range(2):
            q = int(t * 1.3 + n * 0.5)
            if len(lit):
                sy, sx = lit[(q * 7919 + n * 104729) % len(lit)]
                rays(g, int(sy), int(sx), int(2 + 4 * np.sin((t * 1.3 + n * 0.5) % 1 * np.pi)), CORE)

    info = {"candle": "lit" if on > 0.5 else "off", "flame": float(f * on), "confetti": pieces}
    return g.char, g.lum, g.tag, info, g.count


# ════════════════════════════════════════════════════════════════════════════
#  RENDER DI SERVER (sekali, di thread latar, di-cache untuk semua pengunjung)
# ════════════════════════════════════════════════════════════════════════════
CW, CH = 9, 14                      # ukuran satu sel huruf (px)
W, H = 1080, 960
COLS, ROWS = W // CW, H // CH       # 120 x 68
ASPECT = (COLS * CW) / (ROWS * CH)
COLORS = [
    [236, 160, 52], [150, 84, 36], [255, 250, 238], [255, 246, 232],     # bolu, kerak, krim, frosting
    [240, 50, 70], [255, 140, 150], [232, 222, 206], [228, 176, 84],     # lilin x2, piring, emas
    [255, 250, 228], [255, 158, 52], [255, 184, 96], [90, 70, 60],       # inti api, api, cahaya, sumbu
    [255, 184, 72], [255, 226, 168], [255, 212, 138], [255, 176, 204],   # bolu terang, frosting terang, tulisan
    [255, 96, 160], [70, 160, 255], [60, 200, 110], [255, 214, 50], [255, 128, 40], [245, 245, 255],
]


class Renderer:
    """Merender semua frame di thread latar supaya halaman undangan langsung tampil."""

    def __init__(self, lines, fps):
        self.lines, self.fps = list(lines), int(fps)
        self.total = int(LOOP * self.fps)
        self.done_frames = 0
        self.ready = False
        self.error = None
        self.payload = None          # dict siap dikirim ke browser
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def progress(self):
        return min(1.0, self.done_frames / max(1, self.total))

    def _run(self):
        try:
            TEXT = {}
            cells = COLS * ROWS
            arr = np.zeros((3, self.total, cells), np.uint8)       # [char | warna | terang]
            info = []
            for i in range(self.total):
                char, lum, tag, inf, count = frame(i / self.fps, COLS, ROWS, ASPECT, self.lines, TEXT)
                arr[0, i] = char.ravel()
                arr[1, i] = np.clip(tag, 0, len(COLORS) - 1).ravel()
                arr[2, i] = (np.clip(lum, 0, 1) * 31 + 0.5).astype(np.uint8).ravel()
                info.append([1 if inf["candle"] == "lit" else 0, round(inf["flame"], 2), inf["confetti"], count])
                self.done_frames = i + 1
            delta = arr.copy()
            delta[:, 1:] = arr[:, 1:] ^ arr[:, :-1]                # selisih antar frame -> kompres kecil
            blob = zlib.compress(delta.tobytes(), 9)
            self.payload = {
                "b64": base64.b64encode(blob).decode(),
                "info": info,
            }
            self.ready = True
        except Exception as exc:        # noqa: BLE001
            self.error = repr(exc)


@st.cache_resource(show_spinner=False, max_entries=2)
def get_renderer(lines, fps):
    return Renderer(lines, fps)


# ════════════════════════════════════════════════════════════════════════════
#  PANGGUNG + TIRAI OPERA (HTML + JS) — canvas responsif, jalan di browser
# ════════════════════════════════════════════════════════════════════════════
PLAYER_HTML = r"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;800&family=Press+Start+2P&display=swap" rel="stylesheet">
<style>
  :root{--bg:#0b0714;--gold:#e0b441;--wine:#5a0a12;--pink:#ff7ab6;--dim:#6e6878;
        --val:clamp(56px,13vh,120px)}
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;color:#fff;overflow:hidden;-webkit-tap-highlight-color:transparent;
    background:radial-gradient(ellipse at 50% 35%,#2a0c18 0%,#120812 55%,var(--bg) 100%);
    font-family:'Press Start 2P',consolas,menlo,monospace}

  /* ── panggung ── */
  .wrap{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
    gap:clamp(8px,2vh,18px);padding:var(--val) 10px 10px}
  .title{font:800 clamp(11px,3vw,20px)/1.2 'Cinzel',Georgia,serif;letter-spacing:.14em;color:var(--gold);
    text-align:center;text-shadow:0 2px 0 #000,0 0 18px rgba(224,180,65,.35)}
  .stage{position:relative;width:min(100%,calc((100vh - 150px - var(--val)) * 1.134),1100px);min-width:240px;
    aspect-ratio:1080/952;background:#000;overflow:hidden;container-type:inline-size;cursor:pointer;
    box-shadow:0 0 0 3px var(--gold),0 0 0 7px var(--wine),0 0 60px rgba(255,200,120,.22)}
  canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
  #g1,#g2{mix-blend-mode:screen;pointer-events:none}
  #g1{opacity:.75} #g2{opacity:.45}
  .hud{position:absolute;left:5.5%;bottom:4%;pointer-events:none;
    font:clamp(7px,1.5vw,14px)/1.9 consolas,menlo,'DejaVu Sans Mono',monospace;color:#6e6878;white-space:pre}
  .hud{font-size:1.45cqw;line-height:1.7}
  .timer{position:absolute;right:5.5%;top:3%;pointer-events:none;color:var(--pink);
    font:clamp(7px,1.5vw,14px)/1 consolas,menlo,'DejaVu Sans Mono',monospace;font-size:1.65cqw}
  .loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    font-size:clamp(8px,2.2cqw,13px);color:var(--gold);background:#000;text-align:center;line-height:2;
    animation:blink 1s steps(2) infinite}
  @keyframes blink{50%{opacity:.3}}
  .bar{display:flex;gap:clamp(6px,1.6vw,12px);flex-wrap:wrap;justify-content:center}
  button{font:inherit;font-size:clamp(7px,1.9vw,10px);color:#fff;background:#3a0c18;border:0;cursor:pointer;
    padding:10px 12px;box-shadow:0 0 0 2px var(--gold),3px 3px 0 2px #000;transition:transform .08s steps(2)}
  button[hidden]{display:none}
  button:hover{background:#561222;transform:translate(-1px,-1px)}
  button:active{transform:translate(2px,2px);box-shadow:0 0 0 2px var(--gold)}
  .hint{font-size:clamp(6px,1.6vw,8px);color:var(--dim);text-align:center;line-height:1.8}

  /* ── tirai opera ── */
  .curtain{position:fixed;inset:0;z-index:50;cursor:pointer;overflow:hidden;outline:none}
  .curtain.done{pointer-events:none}
  .panel{position:absolute;top:0;bottom:0;width:50.5%;will-change:transform;
    transition:transform 3s cubic-bezier(.68,0,.22,1);
    background:
      linear-gradient(180deg,rgba(0,0,0,.55) 0%,rgba(0,0,0,0) 22%,rgba(0,0,0,0) 70%,rgba(0,0,0,.5) 100%),
      repeating-linear-gradient(90deg,rgba(0,0,0,.50) 0,rgba(0,0,0,0) 3.6%,rgba(255,90,90,.20) 6.4%,
        rgba(0,0,0,0) 8.4%,rgba(0,0,0,.50) 11.5%),
      linear-gradient(90deg,#7d1020,#92162a 50%,#6a0c19)}
  .panel::after{content:"";position:absolute;left:0;right:0;bottom:0;height:clamp(10px,2.4vh,20px);
    background:repeating-linear-gradient(90deg,#f1cf6b 0 3px,#8a6a1c 3px 5px,transparent 5px 9px);
    border-top:3px solid var(--gold)}
  .left{left:0;transform-origin:0 50%;box-shadow:inset -10px 0 18px rgba(0,0,0,.55),4px 0 0 var(--gold)}
  .right{right:0;transform-origin:100% 50%;box-shadow:inset 10px 0 18px rgba(0,0,0,.55),-4px 0 0 var(--gold)}
  .open .left,.open .right{transform:scaleX(.1)}      /* tirai menggulung ke tepi */
  .valance{position:absolute;left:0;top:0;width:100%;height:var(--val);z-index:3;
    filter:drop-shadow(0 6px 8px rgba(0,0,0,.6))}
  .plaque{position:absolute;left:50%;top:52%;transform:translate(-50%,-50%);z-index:2;text-align:center;
    width:min(86vw,560px);transition:opacity .6s;font-family:'Cinzel',Georgia,serif;color:var(--gold)}
  .open .plaque{opacity:0}
  .plaque .t{font-weight:800;font-size:clamp(15px,4.6vw,30px);letter-spacing:.18em;text-shadow:0 2px 0 #3a050b,0 0 22px rgba(0,0,0,.7)}
  .plaque .orn{margin:.7em auto;width:60%;height:3px;background:linear-gradient(90deg,transparent,var(--gold),transparent)}
  .plaque .to{font-weight:600;font-size:clamp(11px,3vw,18px);letter-spacing:.12em;color:#ffe9b0;text-shadow:0 2px 0 #3a050b}
  .plaque .h{margin-top:1.8em;font-weight:600;font-size:clamp(9px,2.4vw,14px);letter-spacing:.2em;color:#fff3cf;
    text-shadow:0 2px 0 #3a050b;animation:blink 1.4s ease-in-out infinite}
</style></head>
<body>
<div class="wrap">
  <div class="title" id="title"></div>
  <div class="stage" id="stage">
    <canvas id="art"></canvas><canvas id="g1"></canvas><canvas id="g2"></canvas>
    <div class="hud" id="hud"></div><div class="timer" id="timer"></div>
    <div class="loading" id="loading">MEMANGGANG KUE...</div>
  </div>
  <div class="bar">
    <button id="bPlay">JEDA</button><button id="bRe">ULANG</button>
    <button id="bMusic" hidden>MUSIK: ON</button><button id="bSave">SIMPAN</button><button id="bFs">LAYAR PENUH</button>
  </div>
  <div class="hint">ketuk gambar = jeda &middot; spasi = jeda &middot; R = ulang &middot; S = simpan</div>
</div>

<div class="curtain" id="curtain" role="button" tabindex="0" aria-label="Buka tirai">
  <div class="panel left"></div><div class="panel right"></div>
  __VALANCE__
  <div class="plaque">
    <div class="t" id="cTitle"></div><div class="orn"></div>
    <div class="to" id="cTo"></div><div class="h" id="cHint"></div>
  </div>
</div>

<script>
(function(){
"use strict";
const CFG = __CFG__;
const COLS=CFG.cols, ROWS=CFG.rows, N=COLS*ROWS, FPS=CFG.fps, LOOP=CFG.loop;
const F=Math.floor(LOOP*FPS), MONO="consolas,menlo,'DejaVu Sans Mono','Courier New',monospace";
const $=id=>document.getElementById(id);
const stage=$('stage'), art=$('art'), g1=$('g1'), g2=$('g2'), curtain=$('curtain');
const actx=art.getContext('2d'), c1=g1.getContext('2d'), c2=g2.getContext('2d');
$('title').textContent = CFG.title;
$('cTitle').textContent = CFG.curtainTitle;
$('cTo').textContent = CFG.curtainTo;
$('cHint').textContent = CFG.ready ? CFG.hint : CFG.waitText;

// warna: LUT[tag*32 + terang]
const LUT=[];
CFG.colors.forEach(c=>{for(let l=0;l<32;l++){const k=l/31;
  LUT.push('rgb('+Math.round(c[0]*k)+','+Math.round(c[1]*k)+','+Math.round(c[2]*k)+')');}});
const GL=Array.from(CFG.chars);

let D=null, paused=false, t=0, last=0, lastFi=-1, curFi=0, opened=false, started=false;

/* ── musik (mp3, loop) ── */
let audio=null, musicOn=true;
if(CFG.ready && CFG.music){
  audio=new Audio(); audio.loop=true; audio.preload='auto'; audio.volume=CFG.volume; audio.src=CFG.music;
  $('bMusic').hidden=false;
}
function playMusic(){ if(audio&&musicOn){ const p=audio.play(); if(p&&p.catch) p.catch(()=>{}); } }
function toggleMusic(){
  if(!audio) return;
  musicOn=!musicOn; $('bMusic').textContent='MUSIK: '+(musicOn?'ON':'OFF');
  if(musicOn){ if(opened) playMusic(); } else audio.pause();
}
document.addEventListener('visibilitychange',()=>{ if(!audio||!opened||!musicOn) return;
  if(document.hidden) audio.pause(); else playMusic(); });

/* ── tirai ── */
function openCurtain(){
  if(opened||!CFG.ready) return;
  opened=true; curtain.classList.add('open'); playMusic();   // klik pengguna = izin memutar suara
  setTimeout(()=>curtain.classList.add('done'),3100);
}
curtain.addEventListener('click',openCurtain);
curtain.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openCurtain();}});

function loadScript(src){return new Promise((ok,no)=>{const s=document.createElement('script');
  s.src=src;s.onload=ok;s.onerror=no;document.head.appendChild(s);});}

async function inflate(u8){
  if (typeof DecompressionStream!=='undefined'){
    const ds=new DecompressionStream('deflate');
    const out=new Blob([u8]).stream().pipeThrough(ds);
    return new Uint8Array(await new Response(out).arrayBuffer());
  }
  await loadScript('https://cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako.min.js');
  return window.pako.inflate(u8);
}

async function load(){
  const bin=atob(CFG.b64), u8=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++) u8[i]=bin.charCodeAt(i);
  D=await inflate(u8);
  for(let p=0;p<3;p++) for(let f=1;f<F;f++){            // kembalikan selisih -> frame utuh
    const b=(p*F+f)*N, a=b-N;
    for(let i=0;i<N;i++) D[b+i]^=D[a+i];
  }
}

function resize(){
  const dpr=Math.min(window.devicePixelRatio||1,2);
  const iw=Math.max(240,Math.min(Math.round(stage.clientWidth*dpr),1500));
  const ih=Math.round(iw*(ROWS*CFG.ch)/(COLS*CFG.cw));
  art.width=iw; art.height=ih;
  g1.width=Math.max(8,iw>>2); g1.height=Math.max(8,ih>>2);
  g2.width=Math.max(8,iw>>3); g2.height=Math.max(8,ih>>3);
  const w=stage.clientWidth;
  g1.style.filter='blur('+Math.max(2,w*0.006).toFixed(1)+'px)';
  g2.style.filter='blur('+Math.max(6,w*0.022).toFixed(1)+'px)';
  clearTrail(); if(D) draw(curFi);
}
function clearTrail(){actx.globalCompositeOperation='source-over';actx.fillStyle='#000';
  actx.fillRect(0,0,art.width,art.height);}

function draw(fi){
  curFi=fi;
  const w=art.width, h=art.height, cw=w/COLS, chh=h/ROWS;
  actx.globalCompositeOperation='source-over';
  actx.fillStyle='rgba(0,0,0,0.62)';                    // frame sebelumnya memudar (trail)
  actx.fillRect(0,0,w,h);
  actx.globalCompositeOperation='lighten';
  actx.font=(chh*15/14).toFixed(1)+'px '+MONO;
  actx.textAlign='center'; actx.textBaseline='middle';
  const bc=fi*N, bt=(F+fi)*N, bl=(2*F+fi)*N;
  for(let r=0;r<ROWS;r++){
    const y=(r+0.52)*chh;
    for(let c=0;c<COLS;c++){
      const i=r*COLS+c, ch=D[bc+i]; if(!ch) continue;
      const lq=D[bl+i]; if(!lq) continue;
      actx.fillStyle=LUT[D[bt+i]*32+lq];
      actx.fillText(GL[ch],(c+0.5)*cw,y);
    }
  }
  actx.globalCompositeOperation='source-over';
  c1.drawImage(art,0,0,g1.width,g1.height);             // cahaya lembut (diburam lewat CSS)
  c2.drawImage(art,0,0,g2.width,g2.height);
  const inf=CFG.info[fi];
  $('hud').textContent=CFG.sign+'\ncandle '+(inf[0]?'lit':'off')+'\nflame '+inf[1].toFixed(2)+
    '\nconfetti '+inf[2]+'\nletters '+String(inf[3]).padStart(5,'0');
}

function tick(now){
  requestAnimationFrame(tick);
  if(!D) return;
  const dt=last?(now-last)/1000:0; last=now;
  if(opened && !started){started=true;t=0;lastFi=-1;clearTrail();}   // pertunjukan mulai saat tirai dibuka
  if(started && !paused){
    t+=Math.min(dt,1/15);
    if(t>LOOP){t=0;clearTrail();lastFi=-1;}
  }
  const fi=Math.min(F-1,Math.floor(t*FPS));
  if(fi!==lastFi){lastFi=fi;draw(fi);}
  if(started) $('timer').textContent=((Math.floor(t*2)%2===0)?'\u25CF':' ')+' t '+t.toFixed(2).padStart(5,'0')+'s';
}

function setPaused(p){paused=p;$('bPlay').textContent=p?'LANJUT':'JEDA';}
function restart(){t=0;lastFi=-1;clearTrail();}
function save(){try{art.toBlob(b=>{const a=document.createElement('a');a.href=URL.createObjectURL(b);
  a.download='cake_'+Date.now()+'.png';document.body.appendChild(a);a.click();a.remove();});}catch(e){}}
function fs(){try{const el=document.documentElement;
  if(document.fullscreenElement) document.exitFullscreen(); else (el.requestFullscreen||el.webkitRequestFullscreen).call(el);}catch(e){}}

stage.addEventListener('click',()=>{if(opened) setPaused(!paused);});
$('bPlay').onclick=()=>setPaused(!paused);
$('bMusic').onclick=toggleMusic; $('bRe').onclick=restart; $('bSave').onclick=save; $('bFs').onclick=fs;
window.addEventListener('keydown',e=>{
  if(!opened){ if(e.code==='Space'||e.key==='Enter'){e.preventDefault();openCurtain();} return; }
  if(e.code==='Space'){e.preventDefault();setPaused(!paused);}
  else if(e.key==='r'||e.key==='R') restart();
  else if(e.key==='s'||e.key==='S') save();
});
new ResizeObserver(resize).observe(stage);
window.addEventListener('resize',resize);
try{curtain.focus({preventScroll:true});}catch(e){}

if(CFG.ready){
  load().then(()=>{$('loading').remove();resize();requestAnimationFrame(tick);})
   .catch(err=>{$('loading').textContent='Gagal memuat animasi. Muat ulang halaman.';console.error(err);});
}
})();
</script></body></html>"""


def valance_svg():
    """Kain penutup atas (pelmet) bergelombang dengan rumbai emas."""
    gold = "#e0b441"
    n, wdt = 8, 1000 / 8
    d = "M0,0 H1000 V78"
    for i in range(n):
        x1 = 1000 - wdt * i
        d += f" Q{x1 - wdt / 2:.1f},132 {x1 - wdt:.1f},78"
    d += " Z"
    parts = [
        '<defs><linearGradient id="vg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#a11a30"/><stop offset="1" stop-color="#4a060e"/></linearGradient></defs>',
        f'<path d="{d}" fill="url(#vg)" stroke="{gold}" stroke-width="3" vector-effect="non-scaling-stroke"/>',
        f'<rect x="0" y="0" width="1000" height="14" fill="{gold}"/>',
        '<rect x="0" y="14" width="1000" height="3" fill="#7a5a12"/>',
    ]
    for i in range(n + 1):
        x = wdt * i
        parts.append(f'<path d="M{x:.1f},17 L{x:.1f},78" stroke="rgba(0,0,0,.28)" stroke-width="2" '
                     f'vector-effect="non-scaling-stroke"/>')
        parts.append(f'<rect x="{x - 3:.1f}" y="78" width="6" height="22" fill="{gold}"/>')
    for i in range(n):                                  # lipatan di tengah tiap gelombang
        xm = wdt * i + wdt / 2
        parts.append(f'<path d="M{xm:.1f},17 Q{xm:.1f},80 {xm:.1f},112" stroke="rgba(255,120,120,.25)" '
                     f'stroke-width="2" fill="none" vector-effect="non-scaling-stroke"/>')
    return ('<svg class="valance" viewBox="0 0 1000 135" preserveAspectRatio="none" aria-hidden="true">'
            + "".join(parts) + "</svg>")


def clean(text, default="", limit=24):
    text = re.sub(r"[^\w .,'\-]", "", str(text or default), flags=re.UNICODE).strip()
    return text[:limit]


@st.cache_resource(show_spinner=False, max_entries=2)
def load_music(path):
    """mp3 -> data URI (atau link https apa adanya). Kosong kalau tidak ada/terlalu besar."""
    path = (path or "").strip()
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    f = Path(__file__).resolve().with_name(path)
    if not f.is_file():
        return ""
    data = f.read_bytes()
    if len(data) > 12 * 1024 * 1024:
        return ""
    return "data:audio/mpeg;base64," + base64.b64encode(data).decode()


def build_player_html(payload, to):
    ready = payload is not None
    cfg = {
        "ready": ready,
        "cols": COLS, "rows": ROWS, "cw": CW, "ch": CH,
        "fps": payload["fps"] if ready else 20, "loop": LOOP,
        "chars": CHARS, "colors": COLORS,
        "info": payload["info"] if ready else [], "b64": payload["b64"] if ready else "",
        "title": "🎂 " + CONFIG["title"], "sign": CONFIG["sign"],
        "curtainTitle": CONFIG["curtain_title"],
        "curtainTo": ("Untuk: " + to) if to else "",
        "music": load_music(CONFIG["music"]) if ready else "",
        "volume": float(min(1.0, max(0.0, CONFIG["music_volume"]))),
        "hint": CONFIG["curtain_hint"], "waitText": "menyiapkan panggung...",
    }
    data = json.dumps(cfg, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return PLAYER_HTML.replace("__VALANCE__", valance_svg()).replace("__CFG__", data)


def page_css():
    return """
<style>
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"]{
  background:#0b0714 !important}
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer{display:none !important}
[data-testid="stMainBlockContainer"], .block-container{padding:0 !important;max-width:100% !important}
iframe{height:calc(100vh - 8px) !important;height:calc(100dvh - 8px) !important;min-height:520px;border:0 !important}
</style>"""


def show_iframe(html_str):
    if hasattr(st, "iframe"):                       # Streamlit baru
        st.iframe(html_str, height=780)
    else:                                           # Streamlit lama
        import streamlit.components.v1 as components
        components.html(html_str, height=780, scrolling=False)


# ════════════════════════════════════════════════════════════════════════════
#  HALAMAN
# ════════════════════════════════════════════════════════════════════════════
def main():
    lines = [re.sub(r"[^A-Z0-9 .,!?'&:\-]", "", str(x).upper()).strip()[:12] for x in CONFIG["lines"]]
    lines = [x for x in lines if x][:3] or ["HAPPY"]
    fps = int(min(24, max(12, CONFIG["fps"])))
    renderer = get_renderer(tuple(lines), fps)          # mulai merender di latar begitu halaman dibuka
    to = clean(st.query_params.get("untuk"), CONFIG["curtain_to"])

    st.markdown(page_css(), unsafe_allow_html=True)
    m = (CONFIG["music"] or "").strip()
    if m and not load_music(m):
        st.warning(f"Musik '{m}' tidak ditemukan / lebih dari 12 MB. Taruh file mp3 di folder yang sama dengan app.py.")
    slot = st.empty()

    if not renderer.ready and not renderer.error:       # tirai tampil dulu selagi panggung disiapkan
        with slot.container():
            show_iframe(build_player_html(None, to))
        while not renderer.ready and not renderer.error:
            time.sleep(0.25)

    if renderer.error:
        slot.error("Maaf, animasi gagal dibuat: " + renderer.error)
        return
    with slot.container():
        show_iframe(build_player_html({**renderer.payload, "fps": renderer.fps}, to))


main()