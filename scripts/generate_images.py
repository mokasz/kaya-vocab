#!/usr/bin/env python3
"""
イラスト生成スクリプト
Imagen 4.0 を使って words.json の各単語のイラストを生成する
"""

import json, os, sys, time
from pathlib import Path
from google import genai
from google.genai import types

SCRIPT_DIR  = Path(__file__).parent
DATA_DIR    = SCRIPT_DIR.parent / "data"
WORDS_FILE  = DATA_DIR / "words.json"
IMAGES_DIR  = DATA_DIR / "images"
MODEL       = "imagen-4.0-fast-generate-001"
SLEEP       = 4.0   # レート制限対策

PROMPTS = {
    "store":      "Simple flat illustration of a colorful shop store front with an awning, white background, no text",
    "well":       "Simple flat illustration of a person playing piano beautifully with musical notes, white background, no text",
    "dress":      "Simple flat illustration of a cute red dress on a hanger, white background, no text",
    "coat":       "Simple flat illustration of a warm winter coat, white background, no text",
    "hospital":   "Simple flat illustration of a hospital building with a red cross sign, white background, no text",
    "always":     "Simple flat illustration of a clock with a sun and moon showing always/all the time, white background, no text",
    "pencil":     "Simple flat illustration of a yellow pencil writing on paper, white background, no text",
    "calendar":   "Simple flat illustration of a monthly calendar with dates, white background, no text",
    "pharmacy":   "Simple flat illustration of a pharmacy drugstore with medicine bottles, white background, no text",
    "tickets":    "Simple flat illustration of two colorful movie tickets, white background, no text",
    "station":    "Simple flat illustration of a train station with a train arriving, white background, no text",
    "awesome":    "Simple flat illustration of a shining gold star trophy with sparkles, white background, no text",
    "excited":    "Simple flat illustration of a happy jumping child with arms raised, white background, no text",
    "clown":      "Simple flat illustration of a colorful friendly circus clown with a red nose, white background, no text",
    "over":       "Simple flat illustration of a finish line ribbon at the end of a race, white background, no text",
    "difficult":  "Simple flat illustration of a student looking puzzled at a math problem on a blackboard, white background, no text",
}

def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が設定されていません"); sys.exit(1)

    client = genai.Client(api_key=api_key)

    with open(WORDS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    words = data["words"]
    ok = err = 0

    print(f"[イラスト生成] {len(words)}語 → {IMAGES_DIR}")
    for w in words:
        word_id = w["id"]
        out = IMAGES_DIR / f"{word_id}.png"
        prompt = PROMPTS.get(word_id, f"Simple flat illustration of {w['english']}, white background, no text")

        if out.exists():
            print(f"  SKIP: {word_id}.png")
            continue

        try:
            resp = client.models.generate_images(
                model=MODEL,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                    output_mime_type="image/png"
                )
            )
            img_bytes = resp.generated_images[0].image.image_bytes
            out.write_bytes(img_bytes)
            print(f"  OK:   {word_id}.png ({len(img_bytes)//1024}KB)")
            ok += 1
        except Exception as e:
            print(f"  ERR:  {word_id} → {e}")
            err += 1

        time.sleep(SLEEP)

    # words.json に image フィールドを追加
    for w in data["words"]:
        w["image"] = f"data/images/{w['id']}.png"
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完了: {ok}成功 / {err}失敗 ===")

if __name__ == "__main__":
    main()
