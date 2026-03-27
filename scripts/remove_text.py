import os
import sys
import json
from google import genai
from PIL import Image, ImageDraw

from pydantic import BaseModel

class BoundingBox(BaseModel):
    ymin: int
    xmin: int
    ymax: int
    xmax: int

class BoxList(BaseModel):
    boxes: list[BoundingBox]

def paint_over_text(image_path):
    print(f"Processing {image_path}...")
    if not os.path.exists(image_path):
        print("Image not found.")
        return

    try:
        # Ask Gemini to find text bounding boxes
        client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
        img = Image.open(image_path)
        width, height = img.size
        
        prompt = """Identify all text, words, and letters in this image.
Return ONLY a valid JSON object with a list of bounding boxes for the text areas.
If there is no text at all, return an empty array for 'boxes'."""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[img, prompt],
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BoxList
            )
        )
        
        text = response.text.strip()
        print(f"Detected: {text}")
        result = json.loads(text)
        boxes = result.get('boxes', [])
        
        if not boxes:
            print("No text detected. Skipping.")
            return
            
        # Draw over the text
        draw = ImageDraw.Draw(img)
        for box in boxes:
            ymin, xmin, ymax, xmax = box['ymin'], box['xmin'], box['ymax'], box['xmax']
            
            # Convert normalized 1000 to pixel coordinates
            left = int((xmin / 1000) * width)
            top = int((ymin / 1000) * height)
            right = int((xmax / 1000) * width)
            bottom = int((ymax / 1000) * height)
            
            # Expand box slightly to cover edges
            left = max(0, left - 15)
            top = max(0, top - 15)
            right = min(width, right + 15)
            bottom = min(height, bottom + 15)
            
            # Get background color around the box
            # We sample from slightly outside the top-left corner
            sample_x = max(0, left - 10)
            sample_y = max(0, top - 10)
            fill_color = img.getpixel((sample_x, sample_y))
            
            print(f"Painting over text at: ({left}, {top}) to ({right}, {bottom}) with color {fill_color}")
            draw.rectangle([left, top, right, bottom], fill=fill_color)
            
        img.save(image_path)
        print(f"Successfully painted over text and saved {image_path}")
        
    except Exception as e:
        print(f"Error processing {image_path}: {e}")

if __name__ == "__main__":
    env_path = os.path.join(os.path.dirname(__file__), '.env.local')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    os.environ[k] = v.strip('"\'')
                    
    # Scan all images in the data/images directory
    images_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "images")
    for filename in os.listdir(images_dir):
        if filename.endswith(".png"):
            paint_over_text(os.path.join(images_dir, filename))
