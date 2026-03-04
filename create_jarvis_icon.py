
import os
from PIL import Image, ImageDraw

def create_jarvis_icon(output_path="jarvis.ico"):
    """
    Generates a JARVIS-style icon using Pillow and saves it as an .ico file.
    """ 
    # Create a high-resolution canvas (256x256) with transparency
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Colors
    cyan = (0, 255, 255, 255)
    dark_cyan = (0, 100, 120, 200)
    outer_glow = (0, 255, 255, 60)
    
    center = size // 2
    
    # Draw outer glowing ring (faint)
    draw.ellipse([20, 20, 236, 236], outline=outer_glow, width=8)
    
    # Draw main outer ring
    draw.ellipse([40, 40, 216, 216], outline=cyan, width=4)
    
    # Draw concentric inner ring
    draw.ellipse([80, 80, 176, 176], outline=dark_cyan, width=2)
    
    # Draw arc segments for that JARVIS look
    # Outer segments
    draw.arc([30, 30, 226, 226], start=20, end=70, fill=cyan, width=6)
    draw.arc([30, 30, 226, 226], start=110, end=160, fill=cyan, width=6)
    draw.arc([30, 30, 226, 226], start=200, end=250, fill=cyan, width=6)
    draw.arc([30, 30, 226, 226], start=290, end=340, fill=cyan, width=6)
    
    # Inner segments
    draw.arc([60, 60, 196, 196], start=0, end=45, fill=cyan, width=4)
    draw.arc([60, 60, 196, 196], start=90, end=135, fill=cyan, width=4)
    draw.arc([60, 60, 196, 196], start=180, end=225, fill=cyan, width=4)
    draw.arc([60, 60, 196, 196], start=270, end=315, fill=cyan, width=4)
    
    # Core circle
    draw.ellipse([100, 100, 156, 156], outline=cyan, width=2)
    draw.ellipse([115, 115, 141, 141], fill=cyan)
    
    # Radial lines
    import math
    for i in range(8):
        angle = math.radians(i * 45)
        x1 = center + 85 * math.cos(angle)
        y1 = center + 85 * math.sin(angle)
        x2 = center + 105 * math.cos(angle)
        y2 = center + 105 * math.sin(angle)
        draw.line([x1, y1, x2, y2], fill=cyan, width=2)
    
    # Save as .ico with multiple sizes (256, 128, 64, 48, 32, 16)
    img.save(output_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Icon saved to {os.path.abspath(output_path)}")

if __name__ == "__main__":
    create_jarvis_icon()
