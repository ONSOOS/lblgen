"""登録した枠の形（任意の形状）のライブラリ

形は、輪郭だけを取り出した透過PNGとしてライブラリのフォルダに保存する（元の画像を消しても使える）。
shapes.json に 名前・ファイル・おすすめの文字の高さ／最大幅／縦位置 を記録する。
"""
import json
import math
import os

from PIL import Image, ImageDraw

import suji_core as core

DEFAULT_TEXT = core.SHAPE_TEXT["custom"]


def to_mask(src):
    """画像から形のマスク（0/255、余白を切り落とし）を作る。透過PNGなら不透明部分、それ以外は暗い部分"""
    im = Image.open(src)
    im.load()
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        m = im.convert("RGBA").getchannel("A")
    else:
        m = Image.eval(im.convert("L"), lambda v: 255 - v)
    m = m.point(lambda v: 255 if v >= 128 else 0)
    bb = m.getbbox()
    if not bb:
        raise ValueError("画像に形が見つかりません。透過PNGか、白地に黒い形の画像にしてください。")
    return m.crop(bb)


def mask_to_png(mask, path):
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    out.putalpha(mask)
    out.save(path)


# ---------------------------------------------------------------- 見本の形
def _sample_masks():
    S = 1000
    ss = 2

    def canvas(w=S, h=S):
        im = Image.new("L", (w * ss, h * ss), 0)
        return im, ImageDraw.Draw(im)

    def done(im):
        return im.resize((im.width // ss, im.height // ss), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)

    out = {}
    # 星
    im, d = canvas()
    c = S * ss / 2
    pts = [(c + c * math.cos(math.radians(-90 + 36 * k)) * (1 if k % 2 == 0 else 0.5),
            c + c * math.sin(math.radians(-90 + 36 * k)) * (1 if k % 2 == 0 else 0.5)) for k in range(10)]
    d.polygon(pts, fill=255)
    out["星"] = (done(im), (21, 28, 7))
    # ハート
    im, d = canvas()
    pts = []
    for i in range(720):
        t = 2 * math.pi * i / 720
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((c + x * c / 17, c * 0.9 - y * c / 17))
    d.polygon(pts, fill=255)
    out["ハート"] = (done(im), (25, 38, 6))
    # 吹き出し
    im, d = canvas(S, 820)
    d.rounded_rectangle((0, 0, S * ss - 1, 640 * ss), radius=160 * ss, fill=255)
    d.polygon([(230 * ss, 600 * ss), (440 * ss, 600 * ss), (190 * ss, 820 * ss - 1)], fill=255)
    out["吹き出し"] = (done(im), (36, 64, -10))
    # 盾
    im, d = canvas(S, 1100)
    pts = [(0, 0), (S * ss, 0), (S * ss, 480 * ss)]
    for i in range(1, 41):  # 右下から先端へ（2次ベジェ）
        u = i / 40
        x = (1 - u) ** 2 * S + 2 * (1 - u) * u * S + u * u * 500
        y = (1 - u) ** 2 * 480 + 2 * (1 - u) * u * 900 + u * u * 1100
        pts.append((x * ss, y * ss))
    for i in range(39, -1, -1):  # 先端から左下へ
        u = i / 40
        x = (1 - u) ** 2 * 0 + 2 * (1 - u) * u * 0 + u * u * 500
        y = (1 - u) ** 2 * 480 + 2 * (1 - u) * u * 900 + u * u * 1100
        pts.append((x * ss, y * ss))
    d.polygon(pts, fill=255)
    out["盾"] = (done(im), (34, 56, -6))
    # 五角形
    im, d = canvas()
    pts = [(c + c * math.cos(math.radians(-90 + 72 * k)), c + c * math.sin(math.radians(-90 + 72 * k))) for k in range(5)]
    d.polygon(pts, fill=255)
    out["五角形"] = (done(im), (36, 56, 5))
    # ホームベース
    im, d = canvas(S, 1000)
    d.polygon([(0, 0), (S * ss, 0), (S * ss, 600 * ss), (500 * ss, 1000 * ss - 1), (0, 600 * ss)], fill=255)
    out["ホームベース"] = (done(im), (40, 72, -8))
    for k, (m, rec) in out.items():
        out[k] = (m.crop(m.getbbox()), rec)
    return out


# ---------------------------------------------------------------- ライブラリ
class ShapeLibrary:
    def __init__(self, folder):
        self.dir = folder
        self.index = os.path.join(folder, "shapes.json")
        os.makedirs(folder, exist_ok=True)
        self.items = []
        first = not os.path.exists(self.index)
        self.load()
        if first:
            try:
                for name, (m, rec) in _sample_masks().items():
                    self._add_mask(name, m, rec)
            except Exception:
                pass

    def load(self):
        try:
            with open(self.index, encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []
        self.items = [it for it in items if os.path.exists(os.path.join(self.dir, it.get("file", "")))]

    def save(self):
        with open(self.index, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=2)

    def names(self):
        return [it["name"] for it in self.items]

    def get(self, name):
        return next((it for it in self.items if it["name"] == name), None)

    def path(self, it):
        return os.path.join(self.dir, it["file"])

    def find_by_path(self, path):
        if not path:
            return None
        n = os.path.normcase(os.path.abspath(path))
        return next((it for it in self.items if os.path.normcase(os.path.abspath(self.path(it))) == n), None)

    def recommended(self, it):
        return (it.get("text_height", DEFAULT_TEXT[0]), it.get("max_width", DEFAULT_TEXT[1]),
                it.get("offset_y", DEFAULT_TEXT[2]))

    def _check_name(self, name):
        name = name.strip()
        if not name:
            raise ValueError("名前を入力してください。")
        if self.get(name):
            raise ValueError(f"「{name}」はすでに登録されています。")
        return name

    def _add_mask(self, name, mask, rec=None):
        name = self._check_name(name)
        n = 1
        while os.path.exists(os.path.join(self.dir, f"shape_{n:03d}.png")):
            n += 1
        fn = f"shape_{n:03d}.png"
        mask_to_png(mask, os.path.join(self.dir, fn))
        th, mw, oy = rec or DEFAULT_TEXT
        it = {"name": name, "file": fn, "text_height": th, "max_width": mw, "offset_y": oy}
        self.items.append(it)
        self.save()
        return it

    def add(self, name, src, rec=None):
        return self._add_mask(name, to_mask(src), rec)

    def rename(self, old, new):
        it = self.get(old)
        if not it or old == new.strip():
            return it
        it["name"] = self._check_name(new)
        self.save()
        return it

    def delete(self, name):
        it = self.get(name)
        if not it:
            return
        try:
            os.remove(self.path(it))
        except OSError:
            pass
        self.items.remove(it)
        self.save()

    def set_recommended(self, name, th, mw, oy):
        it = self.get(name)
        if it:
            it.update(text_height=th, max_width=mw, offset_y=oy)
            self.save()

    def move(self, name, delta):
        it = self.get(name)
        i = self.items.index(it)
        j = max(0, min(len(self.items) - 1, i + delta))
        self.items.insert(j, self.items.pop(i))
        self.save()
