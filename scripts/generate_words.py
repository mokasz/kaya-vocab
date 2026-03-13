#!/usr/bin/env python3
"""
generate_words.py — SM-2 単語生成スクリプト

使い方:
  venv/bin/python kaya-vocab/scripts/generate_words.py --import   # 初回CSV取込
  venv/bin/python kaya-vocab/scripts/generate_words.py --generate # 毎日の単語生成
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from google import genai
from supabase import create_client, Client

# ── 設定 ────────────────────────────────────────────────
CSV_PATH = (
    "/Users/shiwei.zhu/Library/CloudStorage/"
    "GoogleDrive-shiwei76@gmail.com/マイドライブ/01.M&K/02.Kaya/洗足/"
    "NEW_TREASURE_Stage1_単語帳.csv"
)
BOOK_KEY = "kaya-stage1"
BOOK_NAME = "NEW TREASURE Stage 1"
KAYA_USER_EMAIL = "kaya.zhu@icloud.com"  # 実行前に更新すること
DAILY_NEW = 8
OUTPUT_PATH = Path("kaya-vocab/data/words.json")
MASTERED_INTERVAL = 21

# 品詞略称 → フル名
POS_MAP = {
    "名": "名詞", "動": "動詞", "副": "副詞", "形": "形容詞",
    "前": "前置詞", "代": "代名詞", "冠": "冠詞", "接": "接続詞",
    "感": "感嘆詞", "助": "助動詞", "疑": "疑問詞",
    "名・形": "名詞・形容詞", "動・名": "動詞・名詞",
    "形・名": "形容詞・名詞", "名・動": "名詞・動詞",
    "副・形": "副詞・形容詞", "前・副": "前置詞・副詞",
    "名・副": "名詞・副詞", "名・前": "名詞・前置詞",
}

# 品詞 → pos suffix（多義語のword_key生成用）
POS_SUFFIX = {
    "名": "noun", "動": "verb", "副": "adv", "形": "adj",
    "前": "prep", "代": "pron", "冠": "art", "接": "conj",
    "感": "interj", "助": "aux", "疑": "q",
}

FORM_LABEL = {
    "singular": "singular form",
    "plural": "plural form",
    "base": "base form (infinitive)",
    "third": "third-person singular present tense",
    "past": "past tense",
    "default": "natural usage",
}


# ── クライアント ─────────────────────────────────────
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def get_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が環境変数に設定されていません")
        sys.exit(1)
    return genai.Client(api_key=api_key)


# ── CSV パース ────────────────────────────────────────
def parse_csv(csv_path: str) -> list[dict]:
    """CSV → 単語リスト。多義語は word_key に suffix を付ける。"""
    raw = []
    word_count: dict[str, int] = defaultdict(int)

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            english = row["English"].strip()
            japanese = row["Japanese"].strip()
            pos = row["品詞備考"].strip()
            if not english:
                continue
            word_count[english] += 1
            raw.append({"_english": english, "japanese": japanese, "pos": pos, "sort_order": i})

    seen_keys: set[str] = set()
    result = []
    for row in raw:
        english = row.pop("_english")
        pos = row["pos"]
        if word_count[english] > 1:
            base_suffix = POS_SUFFIX.get(pos.split("・")[0], "x")
            word_key = f"{english}_{base_suffix}"
            counter = 2
            while word_key in seen_keys:
                word_key = f"{english}_{base_suffix}{counter}"
                counter += 1
        else:
            word_key = english
        seen_keys.add(word_key)
        result.append({"word_key": word_key, "word": english, **row})
    return result


# ── Supabase ヘルパー ─────────────────────────────────
def get_or_create_book(sb: Client, parent_user_id: str | None) -> str:
    res = sb.table("books").select("id").eq("name", BOOK_NAME).execute()
    if res.data:
        return res.data[0]["id"]
    res = sb.table("books").insert({
        "name": BOOK_NAME,
        "subject": "english",
        "created_by": parent_user_id,
        "config": {"daily_new": DAILY_NEW, "book_key": BOOK_KEY},
    }).execute()
    return res.data[0]["id"]


def upsert_words(sb: Client, words: list[dict], book_id: str):
    records = [
        {
            "book_id": book_id,
            "word_key": w["word_key"],
            "word": w["word"],
            "front": w["word"],
            "back_main": w["japanese"],
            "back_sub": POS_MAP.get(w["pos"], w["pos"]),
            "pos": w["pos"],
            "sort_order": w["sort_order"],
        }
        for w in words
    ]
    for i in range(0, len(records), 500):
        sb.table("words").upsert(records[i:i+500], on_conflict="book_id,word_key").execute()
    print(f"  upserted {len(records)} words")


# ── センテンス生成 ────────────────────────────────────
def sentence_forms(pos: str) -> list[str]:
    base_pos = pos.split("・")[0] if pos else ""
    if base_pos == "名":
        return ["singular", "singular", "plural", "plural"]
    elif base_pos == "動":
        return ["base", "base", "third", "third", "past", "past"]
    else:
        return ["default", "default", "default"]


def generate_sentences_for_word(client, word: str, japanese: str, pos: str, forms: list[str]) -> list[dict]:
    form_list = "\n".join(f"{i+1}. {FORM_LABEL[f]} of '{word}'" for i, f in enumerate(forms))
    prompt = f"""Generate {len(forms)} English example sentences for the word "{word}" (Japanese meaning: {japanese}, part of speech: {POS_MAP.get(pos, pos)}).

Rules:
- Each sentence must use "{word}" in the specified form
- Sentences must be simple enough for a Japanese junior high school student
- Each sentence must be clearly different from the others
- Do NOT include any text on signs, labels, or store names in the image

Required forms:
{form_list}

Respond ONLY with a JSON array (no markdown, no explanation):
[
  {{"sentence": "...", "sentence_ja": "（日本語訳）"}},
  ...
]"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    text = response.text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else parts[0]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def save_sentences(sb: Client, word_key: str, forms: list[str], sentences: list[dict]):
    records = [
        {
            "word_key": word_key,
            "book_key": BOOK_KEY,
            "form": forms[i],
            "sentence": s["sentence"],
            "sentence_ja": s["sentence_ja"],
        }
        for i, s in enumerate(sentences)
        if i < len(forms)
    ]
    sb.table("word_sentences").insert(records).execute()


# ── --import モード ───────────────────────────────────
def run_import():
    print("=== Import: CSV → Supabase ===")
    sb = get_supabase()

    users = sb.auth.admin.list_users()
    parent = next((u for u in users if getattr(u, 'email', '') == KAYA_USER_EMAIL), None)
    if parent is None:
        print(f"  Warning: {KAYA_USER_EMAIL} not found. book.created_by will be NULL.")

    words = parse_csv(CSV_PATH)
    print(f"  parsed {len(words)} words from CSV")

    book_id = get_or_create_book(sb, parent.id if parent else None)
    print(f"  book_id: {book_id}")

    upsert_words(sb, words, book_id)

    client = get_gemini()
    existing_keys = {
        r["word_key"]
        for r in sb.table("word_sentences").select("word_key").eq("book_key", BOOK_KEY).execute().data
    }

    todo = [w for w in words if w["word_key"] not in existing_keys]
    print(f"  generating sentences for {len(todo)} words...")

    for i, w in enumerate(todo):
        forms = sentence_forms(w["pos"])
        print(f"  [{i+1}/{len(todo)}] {w['word_key']} ({len(forms)} sentences)")
        try:
            sentences = generate_sentences_for_word(client, w["word"], w["japanese"], w["pos"], forms)
            save_sentences(sb, w["word_key"], forms, sentences)
        except Exception as e:
            print(f"    ERROR: {e} — skipping")

    print("=== Import complete ===")


# ── センテンス選択 ─────────────────────────────────────
def replenish_sentences(sb: Client, client, word_key: str, word: str, japanese: str, pos: str):
    forms = sentence_forms(pos)
    print(f"    補充生成: {word_key} ({len(forms)} 文)")
    try:
        sentences = generate_sentences_for_word(client, word, japanese, pos, forms)
        save_sentences(sb, word_key, forms, sentences)
    except Exception as e:
        print(f"    補充ERROR: {e}")


def pick_sentence(sb: Client, client, word_key: str, word: str, japanese: str, pos: str) -> dict:
    rows = (
        sb.table("word_sentences")
        .select("*")
        .eq("word_key", word_key)
        .eq("book_key", BOOK_KEY)
        .order("last_used_at", desc=False, nullsfirst=True)
        .execute()
        .data
    )
    if not rows:
        return {"sentence": "", "sentence_ja": ""}

    chosen = rows[0]

    if len(rows) <= 1:
        replenish_sentences(sb, client, word_key, word, japanese, pos)

    sb.table("word_sentences").update(
        {"last_used_at": date.today().isoformat()}
    ).eq("id", chosen["id"]).execute()

    return {"sentence": chosen["sentence"], "sentence_ja": chosen["sentence_ja"]}


# ── --generate モード ─────────────────────────────────
def update_sm2_from_progress(sb: Client, kaya_user_id: str):
    sys.path.insert(0, str(Path(__file__).parent))
    from sm2 import sm2_update, quality_from_status

    rows = (
        sb.table("progress_sync")
        .select("*")
        .eq("user_id", kaya_user_id)
        .eq("book_key", BOOK_KEY)
        .neq("status", "new")
        .execute()
        .data
    )
    for row in rows:
        quality = quality_from_status(row["status"])
        ease, interval, reps = sm2_update(
            row["ease_factor"], row["interval_days"], row["repetitions"], quality
        )
        next_review = (date.today() + timedelta(days=interval)).isoformat()
        (
            sb.table("progress_sync")
            .update({
                "ease_factor": ease,
                "interval_days": interval,
                "repetitions": reps,
                "next_review": next_review,
            })
            .eq("user_id", kaya_user_id)
            .eq("book_key", BOOK_KEY)
            .eq("word_key", row["word_key"])
            .execute()
        )
    print(f"  SM-2 updated {len(rows)} words")


def select_todays_words(sb: Client, kaya_user_id: str, book_id: str) -> list[dict]:
    from sm2 import is_mastered

    today = date.today().isoformat()

    # 復習単語: next_review <= 今日 かつ 未習得
    review_rows = (
        sb.table("progress_sync")
        .select("word_key")
        .eq("user_id", kaya_user_id)
        .eq("book_key", BOOK_KEY)
        .lte("next_review", today)
        .lt("interval_days", MASTERED_INTERVAL)
        .neq("status", "new")
        .execute()
        .data
    )
    review_keys = {r["word_key"] for r in review_rows}

    # 既出単語キー
    all_seen = {
        r["word_key"]
        for r in (
            sb.table("progress_sync")
            .select("word_key")
            .eq("user_id", kaya_user_id)
            .eq("book_key", BOOK_KEY)
            .execute()
            .data
        )
    }

    # 新出単語
    new_words_needed = max(0, DAILY_NEW - len(review_keys))
    exclude = list(all_seen) if all_seen else ["__none__"]
    new_rows = (
        sb.table("words")
        .select("word_key")
        .eq("book_id", book_id)
        .not_.in_("word_key", exclude)
        .order("sort_order")
        .limit(new_words_needed)
        .execute()
        .data
    )
    new_keys = {r["word_key"] for r in new_rows}

    selected_keys = list(review_keys | new_keys)
    if not selected_keys:
        return []

    return (
        sb.table("words")
        .select("*")
        .eq("book_id", book_id)
        .in_("word_key", selected_keys)
        .execute()
        .data
    )


def build_words_json(words_data: list[dict], sentences: dict[str, dict]) -> dict:
    result = []
    for w in words_data:
        sent = sentences.get(w["word_key"], {})
        result.append({
            "id": w["word_key"],
            "word": w["word"],
            "english": w["word"],
            "japanese": w["back_main"],
            "pos": w["pos"] or "",
            "theme": w["theme"] or "",
            "status": "new",
            "correct": 0,
            "incorrect": 0,
            "lastSeen": None,
            "sentence": sent.get("sentence", ""),
            "sentence_ja": sent.get("sentence_ja", ""),
            "image": w["image_path"] or "",
        })
    return {
        "meta": {
            "total": len(result),
            "theme": BOOK_NAME,
            "created": date.today().isoformat(),
        },
        "words": result,
    }


def run_generate():
    print("=== Generate: SM-2 → words.json ===")
    sb = get_supabase()
    client = get_gemini()

    users = sb.auth.admin.list_users()
    kaya = next((u for u in users if getattr(u, 'email', '') == KAYA_USER_EMAIL), None)
    if not kaya:
        print(f"ERROR: {KAYA_USER_EMAIL} not found. Update KAYA_USER_EMAIL.")
        sys.exit(1)
    kaya_user_id = kaya.id

    book_res = sb.table("books").select("id").eq("name", BOOK_NAME).execute()
    if not book_res.data:
        print("ERROR: book not found. Run --import first.")
        sys.exit(1)
    book_id = book_res.data[0]["id"]

    update_sm2_from_progress(sb, kaya_user_id)
    words_data = select_todays_words(sb, kaya_user_id, book_id)
    print(f"  selected {len(words_data)} words for today")

    sentences = {}
    for w in words_data:
        sentences[w["word_key"]] = pick_sentence(
            sb, client, w["word_key"], w["word"], w["back_main"], w["pos"] or ""
        )

    output = build_words_json(words_data, sentences)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"  wrote {OUTPUT_PATH} ({len(words_data)} words)")
    print("=== Generate complete ===")


# ── エントリポイント ──────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SM-2 単語生成スクリプト")
    parser.add_argument("--import", dest="do_import", action="store_true", help="CSV → Supabase インポート")
    parser.add_argument("--generate", dest="do_generate", action="store_true", help="SM-2 → words.json 生成")
    args = parser.parse_args()

    if args.do_import:
        run_import()
    elif args.do_generate:
        run_generate()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
