"""アプリのアイコン（icon.ico / icon.png）を作る。

YouTube Music の雰囲気（赤い丸＋白い再生マーク）に、
「タグを書き込む」意味の白い荷札マークを足した、オリジナルのデザイン。
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
S = 1024                 # 大きく描いてから縮めると、ふちがなめらかになる
RED = (226, 32, 44, 255)
WHITE = (255, 255, 255, 255)
DARK = (40, 40, 40, 255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 赤い丸（右下に荷札がはみ出す場所を空けるため、少し左上に寄せる）
R = 420
cx, cy = 20 + R, 20 + R
d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=RED)

# 白い再生マーク（丸のまん中。三角の重心を丸の中心に合わせる）
w, h = 330, 380
d.polygon([(cx - w / 3, cy - h / 2), (cx - w / 3, cy + h / 2), (cx + w * 2 / 3, cy)], fill=WHITE)

# 右下の荷札（タグ）マーク：丸のふちから外へはみ出すように置く
tag = Image.new("RGBA", (S, S), (0, 0, 0, 0))
t = ImageDraw.Draw(tag)
x0, y0, x1, y1 = 640, 700, 990, 920
point = [(x0 - 110, (y0 + y1) / 2), (x0, y0), (x1, y0), (x1, y1), (x0, y1)]
t.polygon(point, fill=DARK)
inset = 26
inner = [(x0 - 110 + inset * 1.8, (y0 + y1) / 2), (x0 + inset / 2, y0 + inset),
         (x1 - inset, y0 + inset), (x1 - inset, y1 - inset), (x0 + inset / 2, y1 - inset)]
t.polygon(inner, fill=WHITE)
t.ellipse((x0 - 10, (y0 + y1) / 2 - 28, x0 + 46, (y0 + y1) / 2 + 28), fill=DARK)
# 札の上に横線（文字＝情報のイメージ）
for i, y in enumerate((775, 845)):
    t.rounded_rectangle((x0 + 90, y - 14, x1 - 60 - i * 70, y + 14), radius=14, fill=RED)
tag = tag.rotate(-20, resample=Image.BICUBIC, center=(815, 810))
img.alpha_composite(tag)

img.resize((512, 512), Image.LANCZOS).save(HERE / "icon.png")
img.save(HERE / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon.png と icon.ico を作りました")
