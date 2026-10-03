"""Create a visually exact, image-based PDF preview of the final editable PPTX."""
from pathlib import Path
import json
from PIL import Image
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "output/4C/.build/presentation"
result = json.loads((BUILD / "build-result.json").read_text())
pptx = Path(result["pptx"])
images = [Path(result["pngDir"]) / f"slide-{i:02d}.png" for i in range(1, 19)]
for image in images:
    with Image.open(image) as img:
        if img.size != (1280, 720):
            raise ValueError(f"Unexpected slide size: {image} {img.size}")
pdf = pptx.with_name(pptx.stem + "_预览.pdf")
c = canvas.Canvas(str(pdf), pagesize=(960, 540), pageCompression=1)
c.setTitle("寒域智航 · 18页展示预览")
c.setSubject("由最终PPTX的逐页渲染图生成；PDF为图片预览，可编辑内容保留在PPTX。")
c.setAuthor("寒域智航演示材料")
for image in images:
    c.drawImage(str(image), 0, 0, width=960, height=540)
    c.showPage()
c.save()
print(pdf)
