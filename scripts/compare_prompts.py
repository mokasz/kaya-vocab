#!/usr/bin/env python3
"""
プロンプト比較スクリプト
案A vs 案B vs 案C の画像を生成して比較用に保存する

対象: always, over, dress, store（抽象語2 + 具象語2）
出力: data/images/compare/{word_id}_a.png  (案A: 単語中心)
      data/images/compare/{word_id}_b.png  (案B: 場面中心)
      data/images/compare/{word_id}_c.png  (案C: 両方)
"""

import json, os, sys, time
from pathlib import Path
from google import genai
from google.genai import types

SCRIPT_DIR = Path(__file__).parent
DATA_DIR   = SCRIPT_DIR.parent / "data"
WORDS_FILE = DATA_DIR / "words.json"
OUT_DIR    = DATA_DIR / "images" / "compare"
MODEL      = "imagen-4.0-fast-generate-001"
SLEEP      = 4.0

# 比較対象の単語ID
TARGET_IDS = ["always", "over", "dress", "store"]


def prompt_a(word: dict) -> str:
    """案A改善版: 単語中心 + 文字混入防止を強調"""
    return (
        f"Simple flat cartoon illustration showing the concept of '{word['english']}'. "
        f"Scene inspired by: {word['sentence']} "
        f"No text, no words, no letters, no labels, no captions, no writing of any kind. "
        f"Purely visual. White background."
    )


def prompt_b(word: dict) -> str:
    """案B: 場面中心 — 単語名を出さず、例文の場面そのものをイラスト化する"""
    return (
        f"Simple flat illustration of this scene: {word['sentence']} "
        f"White background, clean cartoon style, no text, no labels."
    )


def prompt_c(word: dict) -> str:
    """案C: 両方 — 単語+日本語訳+例文+フォーカス指示"""
    return (
        f"Vocabulary flashcard illustration for '{word['english']}' ({word['japanese']}). "
        f"Inspired by: {word['sentence']} "
        f"Focus on showing the meaning of '{word['english']}' clearly. "
        f"White background, clean flat cartoon style, no text."
    )


def generate(client, prompt: str, out_path: Path) -> bool:
    if out_path.exists():
        print(f"  SKIP: {out_path.name}")
        return True
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
        out_path.write_bytes(img_bytes)
        print(f"  OK: {out_path.name} ({len(img_bytes)//1024}KB)")
        return True
    except Exception as e:
        print(f"  ERR: {out_path.name} → {e}")
        return False


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が設定されていません"); sys.exit(1)

    client = genai.Client(api_key=api_key)

    with open(WORDS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    words = {w["id"]: w for w in data["words"]}
    ok = err = 0

    print(f"[比較生成] {len(TARGET_IDS)}語 × 3案 = {len(TARGET_IDS)*3}枚\n")

    for word_id in TARGET_IDS:
        w = words[word_id]
        print(f"--- {word_id} ({w['english']} / {w['japanese']}) ---")
        print(f"    例文: {w['sentence']}")

        for variant, fn in [("A", prompt_a), ("B", prompt_b), ("C", prompt_c)]:
            p = fn(w)
            print(f"  [案{variant}] {p[:80]}...")
            if generate(client, p, OUT_DIR / f"{word_id}_{variant.lower()}.png"):
                ok += 1
            else:
                err += 1
            time.sleep(SLEEP)

        print()

    print(f"=== 完了: {ok}成功 / {err}失敗 ===")
    print(f"出力先: {OUT_DIR}")
    print(f"\n比較ギャラリーは http://localhost:8080 のコンソールで表示できます。")


if __name__ == "__main__":
    main()
