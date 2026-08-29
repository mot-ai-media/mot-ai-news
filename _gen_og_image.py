from PIL import Image, ImageDraw, ImageFont

src = Image.open("MOT logo.png").convert("RGB")
draw = ImageDraw.Draw(src)
W, H = src.size

font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 62)
text = "MEDIA"
letter_spacing = 22

widths = []
for ch in text:
    bbox = font.getbbox(ch)
    widths.append(bbox[2] - bbox[0])
total_width = sum(widths) + letter_spacing * (len(text) - 1)

start_x = (W - total_width) / 2
y = 860

x = start_x
for ch, w in zip(text, widths):
    draw.text((x, y), ch, font=font, fill=(255, 255, 255))
    x += w + letter_spacing

src.save("docs/og-image.png")
print("saved", src.size)
