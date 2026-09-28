"""枠付き文字画像の描画エンジン（GUI からも、スクリプトからも使える）"""
import math
import os
import re

from PIL import Image, ImageDraw, ImageFont

SS = 4  # 4倍で描いて縮小（アンチエイリアス）

DEFAULTS = {
    # 内容
    "mode": "range",          # "range"（数字の範囲） / "list"（文字リスト）
    "start": 1, "end": 99, "step": 1,
    "digits": 2,              # 桁数
    "pad": "0",               # "" なし / "0" 0で埋める(07) / " " 空白で埋める(ゼロサプレス)
    "prefix": "", "suffix": "",
    "items": "A\nB\nC",
    # 文字
    "font_path": r"C:\Windows\Fonts\ARIALNB.TTF", "font_index": 0,
    "text_height": 44.0,      # 文字の高さ（数字「0」の高さ, 画像の短辺に対する%）
    "max_width": 58.0,        # 文字の最大幅（画像の幅に対する%）
    "min_scale": 82.0,        # 幅が収まらない時、等比縮小してよい下限（%）。残りは横方向だけ縮める
    "bold": 0.0,              # 太さ補正（文字の高さに対する%）
    "valign": "ref",          # "ref" 数字の高さ基準で揃える / "ink" 文字ごとに中央
    "offset_x": 0.0, "offset_y": 0.0,
    # 枠
    "frame_on": True,         # 枠線を描くか（外すと線なし。内側の塗りは残る）
    "shape": "circle", "line_width": 6.0, "margin": 3.0, "radius": 20.0,
    "shape_image": "",        # 任意の形状：形を表す画像（透過PNGなら不透明部分、そうでなければ暗い部分が形）
    # 色
    "text_color": "#000000", "frame_color": "#000000",
    "fill_color": "#FFFFFF", "fill_transparent": False,
    "bg_color": "#FFFFFF", "bg_transparent": False,
    # 出力
    "width": 1200, "height": 1200, "dpi": 600,
    "fmt": "PNG", "jpeg_quality": 95,
    "out_dir": os.path.join(os.path.expanduser("~"), "Downloads", "数字画像"),
    "filename": "{text}",
}

SHAPES = {
    "circle": "円",
    "ellipse": "楕円",
    "square": "正方形",
    "rect": "長方形",
    "rounded": "角丸正方形",
    "rrect": "角丸長方形",
    "hexagon": "六角形",
    "octagon": "八角形",
    "diamond": "ひし形",
    "triangle": "三角形",
    "custom": "任意の形状（画像から）",
}
# "none"（枠なし＝画像全体が内側）は古い設定の読み込み用に残している
# 正方形系（画像が長方形でも、短辺に合わせた正方形の枠を中央に描く）
SQUARE_SHAPES = {"circle", "square", "rounded"}
# 形状ごとのおすすめ値：(文字の高さ%, 文字の最大幅%, 縦位置%)
SHAPE_TEXT = {"circle": (44, 58, 0), "ellipse": (44, 62, 0), "square": (48, 76, 0), "rect": (48, 80, 0),
              "rounded": (46, 72, 0), "rrect": (46, 76, 0), "hexagon": (44, 62, 0), "octagon": (44, 64, 0),
              "diamond": (28, 40, 0), "triangle": (26, 36, 12), "custom": (26, 34, 4), "none": (60, 90, 0)}
SHAPE_MAX_WIDTH = {k: v[1] for k, v in SHAPE_TEXT.items()}

FORMATS = {"PNG": ".png", "JPEG": ".jpg", "TIFF": ".tif", "BMP": ".bmp",
           "WEBP": ".webp", "PDF": ".pdf"}
NO_ALPHA = {"JPEG", "BMP", "PDF"}


# ---------------------------------------------------------------- 内容
def make_items(p):
    """[{text, hide:(開始,文字数), label, index, n}] を返す。hide は描かないが幅は取る部分"""
    items = []
    if p["mode"] == "range":
        s, e, st = int(p["start"]), int(p["end"]), abs(int(p["step"])) or 1
        if s < 0 or e < 0:
            raise ValueError("数字の範囲は0以上にしてください")
        rng = range(s, e + 1, st) if s <= e else range(s, e - 1, -st)
        d = int(p["digits"])
        pre, suf = p["prefix"], p["suffix"]
        for i, n in enumerate(rng, 1):
            t = str(n)
            lead = max(0, d - len(t))
            if p["pad"] == "0":
                items.append(dict(text=pre + "0" * lead + t + suf, hide=(0, 0),
                                  label=pre + "0" * lead + t + suf, index=i, n=n))
            elif p["pad"] == " ":
                items.append(dict(text=pre + "0" * lead + t + suf, hide=(len(pre), lead),
                                  label=pre + t + suf, index=i, n=n))
            else:
                items.append(dict(text=pre + t + suf, hide=(0, 0),
                                  label=pre + t + suf, index=i, n=n))
    else:
        parts = [x.strip() for x in re.split(r"[\n,、]", p["items"])]
        for i, t in enumerate([x for x in parts if x], 1):
            items.append(dict(text=t, hide=(0, 0), label=t, index=i, n=i))
    return items


# ---------------------------------------------------------------- フォント
_font_cache = {}


def get_font(path, index, size):
    key = (path, index, size)
    f = _font_cache.get(key)
    if f is None:
        f = ImageFont.truetype(path, size, index=index)
        if len(_font_cache) > 64:
            _font_cache.clear()
        _font_cache[key] = f
    return f


def ref_box(font):
    """基準字（数字の0）の上端・下端（ベースライン基準）"""
    for ch in ("0", "H", "あ"):
        b = font.getbbox(ch, anchor="ls")
        if b[3] - b[1] > 0:
            return b[1], b[3]
    a, d = font.getmetrics()
    return -a, d


def list_fonts():
    """{表示名: (パス, index)} を返す（数秒かかる）"""
    dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]
    fonts = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            ext = os.path.splitext(f)[1].lower()
            if ext not in (".ttf", ".otf", ".ttc", ".otc"):
                continue
            path = os.path.join(d, f)
            for idx in range(16 if ext in (".ttc", ".otc") else 1):
                try:
                    fam, style = ImageFont.truetype(path, 12, index=idx).getname()
                except Exception:
                    break
                name = f"{fam} {style}" if style and style.lower() != "regular" else fam
                if name in fonts:
                    name = f"{name} ({f})"
                fonts[name] = (path, idx)
    return dict(sorted(fonts.items(), key=lambda kv: kv[0].lower()))


# ---------------------------------------------------------------- 枠
def _regular_polygon(n, rot_deg, box):
    pts = [(math.cos(math.radians(rot_deg + 360 * k / n)),
            math.sin(math.radians(rot_deg + 360 * k / n))) for k in range(n)]
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    x0, y0, x1, y1 = box
    return [(x0 + (x - min(xs)) / (max(xs) - min(xs)) * (x1 - x0),
             y0 + (y - min(ys)) / (max(ys) - min(ys)) * (y1 - y0)) for x, y in pts]


def _inset_polygon(pts, d):
    """凸多角形を内側に d だけ縮める"""
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    sgn = 1 if area > 0 else -1
    lines = []
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        nx, ny = -dy / L * sgn, dx / L * sgn  # 内向き法線
        lines.append(((ax + nx * d, ay + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return out


def frame_area(p, w, h):
    """枠を置く範囲 (x0, y0, x1, y1)。正方形系は短辺の正方形を中央に取る"""
    if p["shape"] in SQUARE_SHAPES:
        d = min(w, h)
        return ((w - d) / 2, (h - d) / 2, (w + d) / 2, (h + d) / 2)
    return (0, 0, w, h)


_shape_img_cache = {}


def _load_shape_image(path):
    """形の画像を 0/255 のマスクにして、余白を切り落として返す"""
    st = os.stat(path)
    key = (path, st.st_mtime)
    if key not in _shape_img_cache:
        im = Image.open(path)
        im.load()
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            m = im.convert("RGBA").getchannel("A")
        else:
            m = Image.eval(im.convert("L"), lambda v: 255 - v)
        m = m.point(lambda v: 255 if v >= 128 else 0)
        bb = m.getbbox()
        if not bb:
            raise ValueError("形の画像に形が見つかりません（透過PNGか、白地に黒い形の画像にしてください）")
        _shape_img_cache.clear()
        _shape_img_cache[key] = m.crop(bb)
    return _shape_img_cache[key]


def _edge_band(inner, lw):
    """形の内側で、輪郭から lw 以内の帯（枠線）を返す。
    縮小した画像で「四角→十字」を交互に削って八角形状に縮め（ほぼ均一な太さ）、元の大きさに戻す"""
    from PIL import ImageChops, ImageFilter
    f = min(1.0, 48 / max(lw, 1))
    sw, sh = max(1, round(inner.width * f)), max(1, round(inner.height * f))
    small = inner.resize((sw, sh), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
    er = Image.new("L", (sw + 2, sh + 2), 0)
    er.paste(small, (1, 1))
    for i in range(max(1, round(lw * f))):
        if i % 2 == 0:
            er = er.filter(ImageFilter.MinFilter(3))
        else:
            base = er
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                er = ImageChops.darker(er, ImageChops.offset(base, dx, dy))
    er = er.crop((1, 1, sw + 1, sh + 1)).resize(inner.size, Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
    return ImageChops.subtract(inner, er)


def shape_masks(p, w, h):
    """(内側マスク, 枠線マスク) を返す（w, h は描画解像度）"""
    fx0, fy0, fx1, fy1 = frame_area(p, w, h)
    D = min(fx1 - fx0, fy1 - fy0)
    m = p["margin"] / 100 * D
    lw = max(0, round(p["line_width"] / 100 * D)) if p.get("frame_on", True) else 0
    box = [fx0 + m, fy0 + m, fx1 - 1 - m, fy1 - 1 - m]
    inner = Image.new("L", (w, h), 0)
    stroke = Image.new("L", (w, h), 0)
    di, ds = ImageDraw.Draw(inner), ImageDraw.Draw(stroke)
    shape = p["shape"]
    if shape == "none":
        inner.paste(255, (0, 0, w, h))
        return inner, stroke
    if box[2] <= box[0] or box[3] <= box[1]:
        return inner, stroke
    bw, bh = box[2] - box[0], box[3] - box[1]
    if shape in ("circle", "ellipse"):
        di.ellipse(box, fill=255)
        if lw:
            ds.ellipse(box, outline=255, width=lw)
    elif shape in ("rounded", "rrect", "square", "rect"):
        r = 0 if shape in ("square", "rect") else min(p["radius"] / 100 * D, bw / 2, bh / 2)
        di.rounded_rectangle(box, radius=r, fill=255)
        if lw:
            ds.rounded_rectangle(box, radius=r, outline=255, width=lw)
    elif shape == "custom":
        if not p.get("shape_image"):
            raise ValueError("任意の形状を使うには、形の画像を選んでください")
        src = _load_shape_image(p["shape_image"])
        k = min(bw / src.width, bh / src.height)  # 縦横比を保って枠の範囲に収める
        sw, sh = max(1, round(src.width * k)), max(1, round(src.height * k))
        sm = src.resize((sw, sh), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
        inner.paste(sm, (round((w - sw) / 2), round((h - sh) / 2)))
        if lw:
            stroke = _edge_band(inner, lw)
    else:
        n, rot = {"hexagon": (6, 0), "octagon": (8, 22.5), "diamond": (4, 0), "triangle": (3, -90)}[shape]
        pts = _regular_polygon(n, rot, box)
        di.polygon(pts, fill=255)
        if lw:
            ds.polygon(pts, fill=255)
            ds.polygon(_inset_polygon(pts, lw), fill=0)
    return inner, stroke


# ---------------------------------------------------------------- 文字
def text_mask(item, p, w, h):
    fx0, fy0, fx1, fy1 = frame_area(p, w, h)
    D = min(fx1 - fx0, fy1 - fy0)
    T = p["text_height"] / 100 * D
    f1000 = get_font(p["font_path"], int(p["font_index"]), 1000)
    t0, t1 = ref_box(f1000)
    size = max(4, round(1000 * T / (t1 - t0)))
    font = get_font(p["font_path"], int(p["font_index"]), size)
    rt, rb = ref_box(font)
    s = item["text"]
    a, l = item["hide"]
    bold = max(0, round(p["bold"] / 100 * T))
    asc, desc = font.getmetrics()
    pad = bold + size // 2 + 8
    cw = int(font.getlength(s)) + 2 * pad
    ch = asc + desc + 2 * pad
    bl = pad + asc
    kw = dict(font=font, fill=255, anchor="ls", stroke_width=bold, stroke_fill=255)

    full = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(full).text((pad, bl), s, **kw)
    bb = full.getbbox()
    if not bb:
        return None
    if l:
        vis = Image.new("L", (cw, ch), 0)
        dv = ImageDraw.Draw(vis)
        dv.text((pad, bl), s[:a], **kw)
        dv.text((pad + font.getlength(s[:a + l]), bl), s[a + l:], **kw)
    else:
        vis = full

    x0, x1 = bb[0], bb[2]
    if p["valign"] == "ref":
        y0, y1 = bl + rt - bold, bl + rb + bold
    else:
        y0, y1 = bb[1], bb[3]

    u = hx = 1.0
    maxw = p["max_width"] / 100 * (fx1 - fx0)
    if x1 - x0 > maxw > 0:
        k = maxw / (x1 - x0)
        u = max(k, min(1.0, p["min_scale"] / 100))
        hx = k / u
    sx, sy = u * hx, u
    if sx != 1 or sy != 1:
        vis = vis.resize((max(1, round(cw * sx)), max(1, round(ch * sy))), Image.LANCZOS)
    cx, cy = (x0 + x1) / 2 * sx, (y0 + y1) / 2 * sy
    tx = w / 2 + p["offset_x"] / 100 * w
    ty = h / 2 + p["offset_y"] / 100 * h
    mask = Image.new("L", (w, h), 0)
    mask.paste(vis, (round(tx - cx), round(ty - cy)))
    return mask


# ---------------------------------------------------------------- 合成
def _rgb(c):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


_shape_cache = {}


def render(item, p, scale=1.0):
    W = max(8, round(int(p["width"]) * scale))
    H = max(8, round(int(p["height"]) * scale))
    w, h = W * SS, H * SS
    key = (w, h, p["shape"], p["margin"], p["line_width"], p["radius"], p.get("shape_image", ""),
           p.get("frame_on", True))
    cached = _shape_cache.get(key)
    if cached is None:
        inner, stroke = shape_masks(p, w, h)
        cached = (inner.resize((W, H), Image.LANCZOS), stroke.resize((W, H), Image.LANCZOS))
        if len(_shape_cache) > 8:
            _shape_cache.clear()
        _shape_cache[key] = cached
    inner, stroke = cached
    tm = text_mask(item, p, w, h)

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def layer(color, mask):
        nonlocal out
        lay = Image.new("RGBA", (W, H), _rgb(color) + (0,))
        lay.putalpha(mask)
        out = Image.alpha_composite(out, lay)

    if not p["bg_transparent"]:
        out = Image.new("RGBA", (W, H), _rgb(p["bg_color"]) + (255,))
    if not p["fill_transparent"]:
        layer(p["fill_color"], inner)
    layer(p["frame_color"], stroke)
    if tm is not None:
        layer(p["text_color"], tm.resize((W, H), Image.LANCZOS))
    return out


# ---------------------------------------------------------------- 保存
_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]')


def file_names(items, p):
    ext = FORMATS[p["fmt"]]
    names, used = [], {}
    for it in items:
        base = p["filename"].format_map({"text": it["label"], "index": it["index"], "n": it["n"]})
        base = _BAD.sub("_", base).strip() or f"{it['index']:03d}"
        k = base.lower()
        used[k] = used.get(k, 0) + 1
        if used[k] > 1:
            base = f"{base}_{used[k]}"
        names.append(os.path.join(p["out_dir"], base + ext))
    return names


def save(img, path, p):
    fmt, dpi = p["fmt"], int(p["dpi"])
    if fmt in NO_ALPHA:
        bg = Image.new("RGB", img.size, (255, 255, 255) if p["bg_transparent"] else _rgb(p["bg_color"]))
        bg.paste(img, (0, 0), img)
        img = bg
    kw = {"dpi": (dpi, dpi)}
    if fmt == "JPEG":
        kw.update(quality=int(p["jpeg_quality"]), subsampling=0)
    elif fmt == "TIFF":
        kw["compression"] = "tiff_lzw"
    elif fmt == "WEBP":
        kw = {"lossless": True}
    elif fmt == "PDF":
        kw = {"resolution": dpi}
    img.save(path, fmt, **kw)


def generate(p, progress=None, cancel=None):
    """全件生成。progress(i, total) を呼ぶ。cancel() が True で中断。生成したパスのリストを返す"""
    items = make_items(p)
    paths = file_names(items, p)
    os.makedirs(p["out_dir"], exist_ok=True)
    done = []
    for i, (it, path) in enumerate(zip(items, paths), 1):
        if cancel and cancel():
            break
        save(render(it, p), path, p)
        done.append(path)
        if progress:
            progress(i, len(items))
    return done
