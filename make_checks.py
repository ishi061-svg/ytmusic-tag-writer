"""チェックボックスの絵（✓）を作って、base64 の文字にする。"""
import base64, io, sys
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8")
N, K = 18, 8  # 18px を 8 倍で描いて縮める


def make(checked: bool, hover=False) -> str:
    img = Image.new("RGBA", (N * K, N * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = 4 * K
    box = (K, K, (N - 1) * K, (N - 1) * K)
    if checked:
        d.rounded_rectangle(box, radius=r, fill=(226, 32, 44, 255))
        d.line([(5 * K, 9.3 * K), (7.8 * K, 12 * K), (13 * K, 6.3 * K)], fill="white", width=int(2.2 * K),
               joint="curve")
    else:
        fill = (253, 232, 234, 255) if hover else (255, 255, 255, 255)
        d.rounded_rectangle(box, radius=r, fill=fill, outline=(190, 190, 198, 255), width=int(1.4 * K))
    img = img.resize((N, N), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


print(f'CHECK_ON = "{make(True)}"')
print(f'CHECK_OFF = "{make(False)}"')
print(f'CHECK_HOVER = "{make(False, True)}"')
