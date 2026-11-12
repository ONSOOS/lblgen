"""ベクター形式の書き出し：SVG（1枚ずつ）と PowerPoint（.pptx、編集できる図形とテキスト）

座標はすべて出力画像のピクセル（幅 W × 高さ H）で計算し、SVG は mm、PowerPoint は EMU に換算する。
枠線は「線の中心」で描かれる形式なので、ラスター版と同じ見た目になるよう線幅の半分だけ内側の形に線を引く。
"""
import math
import re
from collections import defaultdict
from xml.sax.saxutils import escape

from PIL import Image, ImageChops, ImageFilter

import suji_core as core

EMU_PER_INCH = 914400
EMU_PER_MM = 36000


# ---------------------------------------------------------------- フォント情報
_font_info_cache = {}


def font_info(path, index):
    """{family, bold, italic, upm, win_asc, win_desc, hhea_asc, hhea_desc, tt} を返す"""
    key = (path, index)
    if key in _font_info_cache:
        return _font_info_cache[key]
    info = {"tt": None}
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(path, fontNumber=index, lazy=True)
        name = tt["name"]
        fam = name.getName(1, 3, 1, 0x409) or name.getName(1, 3, 1) or name.getName(1, 1, 0)
        os2 = tt["OS/2"]
        info.update(
            family=str(fam) if fam else None,
            bold=bool(os2.fsSelection & 0x20) or (os2.usWeightClass >= 600 and not (os2.fsSelection & 0x40)),
            italic=bool(os2.fsSelection & 0x01),
            upm=tt["head"].unitsPerEm,
            win_asc=os2.usWinAscent, win_desc=os2.usWinDescent,
            hhea_asc=tt["hhea"].ascent, hhea_desc=-tt["hhea"].descent,
            tt=tt)
    except Exception:
        pass
    if not info.get("family"):
        f = core.get_font(path, index, 1000)
        fam, style = f.getname()
        a, d = f.getmetrics()
        info.update(family=fam, bold="bold" in (style or "").lower(), italic="italic" in (style or "").lower(),
                    upm=1000, win_asc=a, win_desc=d, hhea_asc=a, hhea_desc=d)
    _font_info_cache[key] = info
    return info


# ---------------------------------------------------------------- 輪郭の抽出
# マーチングスクエア：各セルの (tl, tr, br, bl) が内側かどうかで、つなぐ辺の組を決める
_CASES = {1: (("L", "B"),), 2: (("B", "R"),), 3: (("L", "R"),), 4: (("T", "R"),), 6: (("T", "B"),),
          7: (("T", "L"),), 8: (("T", "L"),), 9: (("T", "B"),), 11: (("T", "R"),), 12: (("L", "R"),),
          13: (("B", "R"),), 14: (("L", "B"),)}


def trace_contours(mask, thr=128):
    """グレースケールのマスクから、しきい値の等高線（閉じた折れ線のリスト）を返す。座標はピクセル中心基準"""
    w, h = mask.size
    img = Image.new("L", (w + 2, h + 2), 0)
    img.paste(mask, (1, 1))
    W2, H2 = w + 2, h + 2
    data = img.tobytes()
    b = img.point(lambda v: 255 if v >= thr else 0)
    edge = ImageChops.difference(b.filter(ImageFilter.MaxFilter(3)), b.filter(ImageFilter.MinFilter(3))).tobytes()
    pts = {}

    def point(key):
        p = pts.get(key)
        if p is None:
            kind, x, y = key
            v0 = data[y * W2 + x]
            v1 = data[y * W2 + x + 1] if kind == "h" else data[(y + 1) * W2 + x]
            t = (thr - v0) / (v1 - v0) if v1 != v0 else 0.5
            p = (x + t, y) if kind == "h" else (x, y + t)
            pts[key] = p
        return p

    adj = defaultdict(list)
    for m in re.finditer(rb"[^\x00]", edge):
        i = m.start()
        y, x = divmod(i, W2)
        if x >= W2 - 1 or y >= H2 - 1:
            continue
        tl, tr = data[i] >= thr, data[i + 1] >= thr
        bl, br = data[i + W2] >= thr, data[i + W2 + 1] >= thr
        code = tl * 8 + tr * 4 + br * 2 + bl
        if code in (0, 15):
            continue
        e = {"T": ("h", x, y), "R": ("v", x + 1, y), "B": ("h", x, y + 1), "L": ("v", x, y)}
        if code in (5, 10):
            center = (data[i] + data[i + 1] + data[i + W2] + data[i + W2 + 1]) / 4 >= thr
            if (code == 5) == center:
                segs = (("T", "L"), ("B", "R"))
            else:
                segs = (("T", "R"), ("L", "B"))
        else:
            segs = _CASES[code]
        for a, c in segs:
            adj[e[a]].append(e[c])
            adj[e[c]].append(e[a])

    loops, seen = [], set()
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [], None, start
        while True:
            seen.add(cur)
            px, py = point(cur)
            loop.append((px - 1, py - 1))  # 1px の余白の分を戻す
            nb = adj[cur]
            nxt = nb[0] if nb[0] != prev or len(nb) == 1 else nb[1]
            if nxt == start or nxt in seen:
                break
            prev, cur = cur, nxt
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def simplify(pts, eps):
    """閉じた折れ線を Douglas-Peucker で間引く"""
    if len(pts) < 8:
        return pts
    # いちばん離れた2点で2本に分けてから間引く
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    out = []
    for seg in (pts[:far + 1], pts[far:] + pts[:1]):
        keep = [False] * len(seg)
        keep[0] = keep[-1] = True
        stack = [(0, len(seg) - 1)]
        while stack:
            a, b = stack.pop()
            (ax, ay), (bx, by) = seg[a], seg[b]
            dx, dy = bx - ax, by - ay
            L = math.hypot(dx, dy) or 1e-9
            best, bi = -1, -1
            for i in range(a + 1, b):
                d = abs((seg[i][0] - ax) * dy - (seg[i][1] - ay) * dx) / L
                if d > best:
                    best, bi = d, i
            if best > eps:
                keep[bi] = True
                stack += [(a, bi), (bi, b)]
        out += [q for q, k in zip(seg[:-1], keep[:-1]) if k]
    return out


def _poly_area(pts):
    return abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))) / 2


# ---------------------------------------------------------------- 形
_geom_cache = {}


def shape_geom(p, W, H):
    key = (W, H, p["shape"], p["margin"], p["line_width"], p["radius"], p.get("shape_image", ""),
           p.get("frame_on", True))
    if key not in _geom_cache:
        if len(_geom_cache) > 8:
            _geom_cache.clear()
        _geom_cache[key] = _shape_geom(p, W, H)
    return _geom_cache[key]


def _shape_geom(p, W, H):
    """出力ピクセル座標での形。{kind, fill, stroke, lw, r_fill, r_stroke}
    kind: "ellipse"/"rect"（fill・stroke は箱）, "poly"/"path"（fill・stroke は折れ線のリスト）"""
    fx0, fy0, fx1, fy1 = core.frame_area(p, W, H)
    D = min(fx1 - fx0, fy1 - fy0)
    m = p["margin"] / 100 * D
    lw = p["line_width"] / 100 * D if p.get("frame_on", True) else 0
    box = (fx0 + m, fy0 + m, fx1 - m, fy1 - m)
    ins = (box[0] + lw / 2, box[1] + lw / 2, box[2] - lw / 2, box[3] - lw / 2)
    shape = p["shape"]
    if shape == "none":
        return {"kind": "rect", "fill": (0, 0, W, H), "stroke": (0, 0, W, H), "lw": 0, "r_fill": 0, "r_stroke": 0}
    if shape in ("circle", "ellipse"):
        return {"kind": "ellipse", "fill": box, "stroke": ins, "lw": lw}
    if shape in ("square", "rect", "rounded", "rrect"):
        bw, bh = box[2] - box[0], box[3] - box[1]
        r = 0 if shape in ("square", "rect") else min(p["radius"] / 100 * D, bw / 2, bh / 2)
        return {"kind": "rect", "fill": box, "stroke": ins, "lw": lw, "r_fill": r, "r_stroke": max(0, r - lw / 2)}
    if shape == "custom":
        k = max(1.0, 1600 / max(W, H))  # 輪郭は 1600px 程度で抽出してから縮める
        wr, hr = round(W * k), round(H * k)
        inner, _ = core.shape_masks(dict(p, frame_on=False), wr, hr)
        lw_r = lw * k

        def contours(mask):
            out = []
            for loop in trace_contours(mask.filter(ImageFilter.GaussianBlur(1.2))):
                loop = simplify(loop, 0.45)
                if len(loop) >= 3 and _poly_area(loop) > 4:
                    out.append([(x / k, y / k) for x, y in loop])
            return out
        fill = contours(inner)
        stroke = contours(core.erode(inner, lw_r / 2)) if lw else fill
        return {"kind": "path", "fill": fill, "stroke": stroke, "lw": lw}
    n, rot = {"hexagon": (6, 0), "octagon": (8, 22.5), "diamond": (4, 0), "triangle": (3, -90)}[shape]
    pts = core._regular_polygon(n, rot, list(box))
    return {"kind": "poly", "fill": [pts], "stroke": [core._inset_polygon(pts, lw / 2) if lw else pts], "lw": lw}


def text_geom(item, p, W, H):
    """出力ピクセル座標での文字の配置。文字が無ければ None"""
    info = {}
    if core.text_mask(item, p, W * core.SS, H * core.SS, info) is None or not info:
        return None
    s = core.SS
    return dict(info, font_px=info["font_px"] / s, bold=info["bold"] / s, start_x=info["start_x"] / s,
                baseline=info["baseline"] / s, center_x=info["center_x"] / s, center_y=info["center_y"] / s,
                ink_center_y=info["ink_center_y"] / s, sx=info["font_px"] / s / info["size"] * info["hx"])


# ---------------------------------------------------------------- SVG
def _f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _path_d(loops):
    return " ".join("M" + " L".join(f"{_f(x)},{_f(y)}" for x, y in loop) + " Z" for loop in loops)


def _svg_shape(g, part, attrs):
    if g["kind"] == "ellipse":
        x0, y0, x1, y1 = g[part]
        return (f'<ellipse cx="{_f((x0 + x1) / 2)}" cy="{_f((y0 + y1) / 2)}" '
                f'rx="{_f((x1 - x0) / 2)}" ry="{_f((y1 - y0) / 2)}" {attrs}/>')
    if g["kind"] == "rect":
        x0, y0, x1, y1 = g[part]
        r = g["r_fill"] if part == "fill" else g["r_stroke"]
        rr = f' rx="{_f(r)}"' if r else ""
        return f'<rect x="{_f(x0)}" y="{_f(y0)}" width="{_f(x1 - x0)}" height="{_f(y1 - y0)}"{rr} {attrs}/>'
    return f'<path d="{_path_d(g[part])}" fill-rule="evenodd" {attrs}/>'


def svg_string(item, p):
    W, H, dpi = int(p["width"]), int(p["height"]), int(p["dpi"])
    g = shape_geom(p, W, H)
    t = text_geom(item, p, W, H)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(W / dpi * 25.4)}mm" height="{_f(H / dpi * 25.4)}mm" '
           f'viewBox="0 0 {W} {H}">']
    if not p["bg_transparent"]:
        out.append(f'<rect width="{W}" height="{H}" fill="{p["bg_color"]}"/>')
    if not p["fill_transparent"]:
        out.append(_svg_shape(g, "stroke" if g["lw"] > 0 else "fill", f'fill="{p["fill_color"]}"'))
    if g["lw"] > 0:
        out.append(_svg_shape(g, "stroke", f'fill="none" stroke="{p["frame_color"]}" stroke-width="{_f(g["lw"])}"'))
    if t:
        out.append(_svg_text(t, p))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _svg_text(t, p):
    fi = font_info(p["font_path"], int(p["font_index"]))
    s, (a, l) = t["text"], t["hide"]
    color = p["text_color"]
    bold = (f' stroke="{color}" stroke-width="{_f(t["bold"] * 2)}" stroke-linejoin="round" paint-order="stroke"'
            if t["bold"] > 0 else "")
    if p.get("svg_outline") and fi["tt"] is not None:
        return _svg_text_outline(t, fi, color, bold)
    fam = fi["family"].replace('"', "")
    style = (' font-weight="bold"' if fi["bold"] else "") + (' font-style="italic"' if fi["italic"] else "")
    parts = [(s[:a], ""), (s[a:a + l], ' fill-opacity="0"'), (s[a + l:], "")] if l else [(s, "")]
    spans = "".join(f"<tspan{extra}>{escape(txt)}</tspan>" if extra else escape(txt) for txt, extra in parts if txt)
    return (f'<text transform="translate({_f(t["start_x"])} {_f(t["baseline"])}) scale({_f(t["hx"])} 1)" '
            f'font-family="&quot;{escape(fam)}&quot;, sans-serif" font-size="{_f(t["font_px"])}"{style} '
            f'fill="{color}"{bold} xml:space="preserve">{spans}</text>')


def _svg_text_outline(t, fi, color, bold):
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    tt = fi["tt"]
    gs = tt.getGlyphSet()
    cmap = tt.getBestCmap() or {}
    font = t["font"]  # 描画解像度のフォント（文字の送り幅を Pillow と揃える）
    s, (a, l) = t["text"], t["hide"]
    k = t["font_px"] / fi["upm"]
    ds = []
    for i, ch in enumerate(s):
        if a <= i < a + l or ch.isspace():
            continue
        gname = cmap.get(ord(ch))
        if gname is None:
            continue
        x = t["start_x"] + font.getlength(s[:i]) * t["sx"]
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        gs[gname].draw(TransformPen(pen, (k * t["hx"], 0, 0, -k, x, t["baseline"])))
        ds.append(pen.getCommands())
    return f'<path d="{" ".join(ds)}" fill="{color}"{bold}/>'


def save_svg(item, p, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + svg_string(item, p))


# ---------------------------------------------------------------- PowerPoint
def pptx_available():
    try:
        import pptx  # noqa: F401
        return True
    except Exception:
        return False


def save_pptx(items, p, path, progress=None, cancel=None):
    """全件を1つの .pptx に、編集できる図形（文字入り）として並べる。生成したパスのリストを返す"""
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
        from pptx.oxml.ns import qn
        from pptx.util import Emu, Pt
    except ImportError:
        raise RuntimeError("PowerPoint 形式で保存するには python-pptx が必要です。")
    from lxml import etree

    W, H, dpi = int(p["width"]), int(p["height"]), int(p["dpi"])
    k = EMU_PER_INCH / dpi            # 1px あたりの EMU
    iw, ih = W * k, H * k
    g = shape_geom(p, W, H)
    fi = font_info(p["font_path"], int(p["font_index"]))

    prs = Presentation()
    blank = prs.slide_layouts[6]
    if p.get("pptx_layout") == "single":
        prs.slide_width, prs.slide_height = Emu(round(iw)), Emu(round(ih))
        margin = gap = 0
        cols = rows = 1
    else:  # A4 縦に並べる（余白 10mm・間隔 5mm）。入らない大きさならページを広げる
        margin, gap = 10 * EMU_PER_MM, 5 * EMU_PER_MM
        pw, ph = max(210 * EMU_PER_MM, iw + 2 * margin), max(297 * EMU_PER_MM, ih + 2 * margin)
        prs.slide_width, prs.slide_height = Emu(round(pw)), Emu(round(ph))
        cols = max(1, int((pw - 2 * margin + gap) // (iw + gap)))
        rows = max(1, int((ph - 2 * margin + gap) // (ih + gap)))
    per = cols * rows
    slide = None

    def rgb(c):
        return RGBColor(*core._rgb(c))

    for idx, item in enumerate(items):
        if cancel and cancel():
            break
        if idx % per == 0:
            slide = prs.slides.add_slide(blank)
        cell = idx % per
        ox = margin + (cell % cols) * (iw + gap)
        oy = margin + (cell // cols) * (ih + gap)
        shapes = slide.shapes
        if not p["bg_transparent"]:
            shapes = slide.shapes.add_group_shape().shapes
            bg = shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(round(ox)), Emu(round(oy)), Emu(round(iw)), Emu(round(ih)))
            bg.fill.solid()
            bg.fill.fore_color.rgb = rgb(p["bg_color"])
            bg.line.fill.background()
            bg.shadow.inherit = False
            bg.name = "背景"

        # --- 形（線は中心で引かれるので、線幅の半分だけ内側の形を使う）
        part = "stroke" if g["lw"] > 0 else "fill"
        if g["kind"] in ("ellipse", "rect"):
            x0, y0, x1, y1 = g[part]
            r = 0 if g["kind"] == "ellipse" else g["r_stroke" if part == "stroke" else "r_fill"]
            kind = MSO_SHAPE.OVAL if g["kind"] == "ellipse" else (
                MSO_SHAPE.ROUNDED_RECTANGLE if r > 0 else MSO_SHAPE.RECTANGLE)
            sh = shapes.add_shape(kind, Emu(round(ox + x0 * k)), Emu(round(oy + y0 * k)),
                                  Emu(round((x1 - x0) * k)), Emu(round((y1 - y0) * k)))
            if r > 0:
                sh.adjustments[0] = min(0.5, r / min(x1 - x0, y1 - y0))
            sb = (x0, y0, x1, y1)
        else:
            loops = g[part]
            u = 100  # 折れ線の座標は 1/100px 単位の整数で持つ
            fb = shapes.build_freeform(round(loops[0][0][0] * u), round(loops[0][0][1] * u), scale=k / u)
            for li, loop in enumerate(loops):
                if li:
                    fb.move_to(round(loop[0][0] * u), round(loop[0][1] * u))
                fb.add_line_segments([(round(x * u), round(y * u)) for x, y in loop[1:]], close=True)
            sh = fb.convert_to_shape(Emu(round(ox)), Emu(round(oy)))
            xs = [x for loop in loops for x, _ in loop]
            ys = [y for loop in loops for _, y in loop]
            sb = (min(xs), min(ys), max(xs), max(ys))
        sh.name = "枠"
        sh.shadow.inherit = False
        if p["fill_transparent"]:
            sh.fill.background()
        else:
            sh.fill.solid()
            sh.fill.fore_color.rgb = rgb(p["fill_color"])
        if g["lw"] > 0:
            sh.line.color.rgb = rgb(p["frame_color"])
            sh.line.width = Emu(round(g["lw"] * k))
        else:
            sh.line.fill.background()

        # --- 文字（図形の中に入れるので、図形と一緒に動き、ダブルクリックで編集できる）
        t = text_geom(item, p, W, H)
        tf = sh.text_frame
        tf.word_wrap = False
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para = tf.paragraphs[0]
        para.alignment = PP_ALIGN.CENTER
        if t:
            F = t["font_px"] * t["hx"]  # 横だけ縮める指定はできないので、全体を縮めて幅を合わせる
            # PowerPoint の1行は「文字サイズ × 1.2」の高さで、その中のベースライン位置は
            # フォントの winAscent : winDescent の比で決まる（複数のフォントで実測して確認）
            L = 1.2 * F
            asc = L * fi["win_asc"] / (fi["win_asc"] + fi["win_desc"])
            # 基準字（0）の中心を、ラスター版と同じ位置に置く
            ref_c = (t["ref_top"] + t["ref_bottom"]) / 2 / t["size"] * F
            target_y = t["center_y"] if p["valign"] == "ref" else t["ink_center_y"]
            baseline = target_y - ref_c
            line_c = baseline - asc + L / 2
            dy = 2 * (line_c - (sb[1] + sb[3]) / 2)
            # PowerPoint は送り幅（左右の余白を含む）の中央でそろえるので、ラスター版での送り幅の中央に合わせる
            adv_c = t["start_x"] + t["font"].getlength(t["text"]) * t["sx"] / 2
            dx = 2 * (adv_c - (sb[0] + sb[2]) / 2)
            tf.margin_left, tf.margin_right = Emu(round(max(0, dx) * k)), Emu(round(max(0, -dx) * k))
            tf.margin_top, tf.margin_bottom = Emu(round(max(0, dy) * k)), Emu(round(max(0, -dy) * k))
            s, (a, l) = t["text"], t["hide"]
            for txt, hidden in ([(s[:a], False), (s[a:a + l], True), (s[a + l:], False)] if l else [(s, False)]):
                if not txt:
                    continue
                run = para.add_run()
                run.text = txt
                f = run.font
                f.size = Pt(F / dpi * 72)
                f.bold, f.italic = fi["bold"], fi["italic"]
                f.color.rgb = rgb(p["text_color"])
                if hidden:  # ゼロサプレスで隠す桁は透明にする（幅は残る）
                    clr = run._r.find(".//" + qn("a:srgbClr"))
                    etree.SubElement(clr, qn("a:alpha")).set("val", "0")
                f.name = fi["family"]
                rpr = run._r.get_or_add_rPr()
                latin = rpr.find(qn("a:latin"))
                for tag in ("a:cs", "a:ea"):  # 日本語の文字にも同じフォントを使う
                    el = etree.Element(qn(tag))
                    el.set("typeface", fi["family"])
                    latin.addnext(el)
        else:
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        if progress:
            progress(idx + 1, len(items))
    prs.save(path)
    return [path]
