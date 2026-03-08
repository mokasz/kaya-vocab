#!/usr/bin/env python3
"""
イラスト生成スクリプト（Gemini → 自動評価 → Vertex AI フォールバック）

フロー:
  1. Gemini API で生成（無料）
  2. Gemini Vision で自動評価（テキスト混入・関連性・品質）
  3. FAIL → Vertex AI + negative_prompt で再生成
  4. 再評価 → ログに記録
  5. 全語完了後 → docs/image-evaluation-criteria.md に結果を追記
"""

import json, os, sys, time, base64
from pathlib import Path
from dataclasses import dataclass, field
from google import genai
from google.genai import types
from google.oauth2 import service_account

SCRIPT_DIR  = Path(__file__).parent
DATA_DIR    = SCRIPT_DIR.parent / "data"
WORDS_FILE  = DATA_DIR / "words.json"
IMAGES_DIR  = DATA_DIR / "images"
MODEL_IMAGE = "imagen-4.0-fast-generate-001"
MODEL_EVAL  = "gemini-2.5-flash"
SLEEP       = 4.0

# Vertex AI 設定
VERTEX_PROJECT  = "ppt-autogen-481811"
VERTEX_LOCATION = "us-central1"
VERTEX_KEY_FILE = SCRIPT_DIR.parent.parent / "service-account-key.json"

# Gemini API プロンプト（案A改善版）
def build_prompt(word: dict) -> str:
    if word["id"] in PROMPT_OVERRIDES:
        return PROMPT_OVERRIDES[word["id"]]
    return (
        f"Simple flat cartoon illustration showing the concept of '{word['english']}'. "
        f"Scene inspired by: {word['sentence']} "
        f"No text, no words, no letters, no labels, no captions, no writing of any kind. "
        f"Purely visual. White background."
    )

# Vertex AI 用プロンプト（negative_prompt と組み合わせる）
def build_vertex_prompt(word: dict) -> str:
    if word["id"] in PROMPT_OVERRIDES:
        return PROMPT_OVERRIDES[word["id"]]
    return (
        f"Simple flat cartoon illustration showing the concept of '{word['english']}'. "
        f"Scene inspired by: {word['sentence']} "
        f"Purely visual. White background."
    )

NEGATIVE_PROMPT = "text, words, letters, labels, signs, captions, writing, typography, signage"

# 単語名が看板になりやすい語のプロンプトオーバーライド（場面描写で代替）
PROMPT_OVERRIDES = {
    "store": (
        "Simple flat cartoon illustration of a mother and young child "
        "walking together through a supermarket aisle, colorful product shelves on both sides. "
        "No text, no words, no letters, no labels, no signs. Purely visual. White background."
    ),
}


# ─── 評価結果 ────────────────────────────────────────────
@dataclass
class EvalResult:
    passed: bool
    has_text: bool
    relevance: str      # "clear" / "ambiguous" / "unrelated"
    quality: str        # "good" / "poor"
    reason: str         # 自由記述
    api_used: str       # "gemini" / "vertex"


# ─── 評価関数（Gemini Vision） ───────────────────────────
def evaluate_image(gemini_client: genai.Client, word: dict, image_bytes: bytes) -> EvalResult:
    """
    Gemini Vision で画像を評価する。
    評価軸:
      1. テキスト混入（has_text）
      2. 単語との関連性（relevance）
      3. 視覚品質（quality）
    """
    # 評価プロンプト
    eval_prompt = f"""You are evaluating a flashcard illustration for the English word "{word['english']}" (meaning: {word['japanese']}).

Evaluate this image on these 3 criteria and respond in JSON only:

1. has_text: Does the image contain ANY text, words, letters, labels, or signs? (true/false)
2. relevance: Does the image clearly represent the meaning of "{word['english']}"?
   - "clear": The word's meaning is immediately obvious from the image
   - "ambiguous": The image is loosely related but might confuse a student
   - "unrelated": The image does not represent the word's meaning
3. quality: Is the illustration clean and visually clear?
   - "good": Clean, clear, suitable for a 12-year-old student
   - "poor": Blurry, cluttered, inappropriate, or confusing

Respond with ONLY valid JSON, no explanation:
{{"has_text": true/false, "relevance": "clear|ambiguous|unrelated", "quality": "good|poor", "reason": "brief reason"}}"""

    img_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    response = gemini_client.models.generate_content(
        model=MODEL_EVAL,
        contents=[eval_prompt, img_part]
    )

    raw = response.text.strip()
    # JSONのみ抽出
    if "```" in raw:
        raw = raw.split("```")[1].replace("json", "").strip()

    result = json.loads(raw)
    passed = (not result["has_text"]) and \
             result["relevance"] == "clear" and \
             result["quality"] == "good"

    return EvalResult(
        passed=passed,
        has_text=result["has_text"],
        relevance=result["relevance"],
        quality=result["quality"],
        reason=result.get("reason", ""),
        api_used=""  # caller が設定する
    )


# ─── Gemini API で生成 ───────────────────────────────────
def generate_gemini(client: genai.Client, word: dict) -> bytes:
    resp = client.models.generate_images(
        model=MODEL_IMAGE,
        prompt=build_prompt(word),
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="1:1",
            output_mime_type="image/png"
        )
    )
    return resp.generated_images[0].image.image_bytes


# ─── Vertex AI で生成 ────────────────────────────────────
def generate_vertex(vertex_client: genai.Client, word: dict) -> bytes:
    resp = vertex_client.models.generate_images(
        model=MODEL_IMAGE,
        prompt=build_vertex_prompt(word),
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="1:1",
            output_mime_type="image/png",
            negative_prompt=NEGATIVE_PROMPT,
        )
    )
    return resp.generated_images[0].image.image_bytes


# ─── メイン ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="既存画像を上書き再生成")
    parser.add_argument("--word", help="特定の単語IDのみ処理")
    args = parser.parse_args()

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が設定されていません"); sys.exit(1)

    # Gemini クライアント（生成 + 評価）
    gemini_client = genai.Client(api_key=api_key)

    # Vertex AI クライアント（フォールバック）
    vertex_client = None
    if VERTEX_KEY_FILE.exists():
        creds = service_account.Credentials.from_service_account_file(
            str(VERTEX_KEY_FILE),
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        vertex_client = genai.Client(
            vertexai=True,
            project=VERTEX_PROJECT,
            location=VERTEX_LOCATION,
            credentials=creds
        )
        print(f"Vertex AI: {VERTEX_PROJECT} ({VERTEX_LOCATION}) ✓")
    else:
        print("⚠️  Vertex AI キーなし — Gemini のみ使用")

    with open(WORDS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    words = data["words"]
    if args.word:
        words = [w for w in words if w["id"] == args.word]

    results = []
    ok = err = fallback = 0

    print(f"\n[画像生成] {len(words)}語\n{'─'*50}")

    for w in words:
        word_id = w["id"]
        out_path = IMAGES_DIR / f"{word_id}.png"

        if out_path.exists() and not args.force:
            print(f"  SKIP: {word_id}")
            continue

        print(f"\n  [{word_id}] {w['english']} / {w['japanese']}")

        # ── Step 1: Gemini API で生成
        try:
            img_bytes = generate_gemini(gemini_client, w)
            time.sleep(SLEEP)
        except Exception as e:
            print(f"    Gemini 生成失敗: {e}")
            err += 1
            continue

        # ── Step 2: 自動評価
        try:
            eval_result = evaluate_image(gemini_client, w, img_bytes)
            eval_result.api_used = "gemini"
            print(f"    評価: text={eval_result.has_text} rel={eval_result.relevance} qual={eval_result.quality} → {'PASS' if eval_result.passed else 'FAIL'}")
            print(f"    理由: {eval_result.reason}")
        except Exception as e:
            print(f"    評価失敗（スキップ）: {e}")
            eval_result = EvalResult(True, True, "ambiguous", "poor", f"評価エラー: {e}", "gemini")

        # ── Step 3: FAIL → Vertex AI フォールバック
        if not eval_result.passed and vertex_client:
            print(f"    → Vertex AI で再生成...")
            try:
                img_bytes = generate_vertex(vertex_client, w)
                time.sleep(SLEEP)
                eval_result = evaluate_image(gemini_client, w, img_bytes)
                eval_result.api_used = "vertex"
                print(f"    再評価: text={eval_result.has_text} rel={eval_result.relevance} qual={eval_result.quality} → {'PASS' if eval_result.passed else 'FAIL'}")
                fallback += 1
            except Exception as e:
                print(f"    Vertex AI 失敗: {e}")

        # ── Step 4: 保存
        out_path.write_bytes(img_bytes)
        status = "✅ PASS" if eval_result.passed else "⚠️  保存（FAIL）"
        print(f"    {status} [{eval_result.api_used}] → {out_path.name}")
        ok += 1

        results.append({
            "id": word_id,
            "english": w["english"],
            "japanese": w["japanese"],
            "api": eval_result.api_used,
            "passed": eval_result.passed,
            "has_text": eval_result.has_text,
            "relevance": eval_result.relevance,
            "quality": eval_result.quality,
            "reason": eval_result.reason,
        })

    # words.json に image フィールドを追加
    for w in data["words"]:
        w["image"] = f"data/images/{w['id']}.png"
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 結果サマリー
    print(f"\n{'─'*50}")
    print(f"完了: {ok}成功 / {err}失敗 / {fallback}語がVertexにフォールバック")
    if results:
        print("\n評価サマリー:")
        for r in results:
            mark = "✅" if r["passed"] else "⚠️ "
            print(f"  {mark} {r['english']:12} [{r['api']:6}] text={str(r['has_text']):5} rel={r['relevance']:10} {r['reason'][:50]}")


if __name__ == "__main__":
    main()
