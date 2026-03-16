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

sys.path.insert(0, str(Path(__file__).parent))
from sm2 import sm2_update, quality_from_review_log, MASTERED_INTERVAL

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
DAILY_NEW = 10
DAILY_MAX = 15
OUTPUT_PATH = Path("kaya-vocab/data/words.json")

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


# ── 活用形生成 ────────────────────────────────────────
def generate_forms(client, word: str, japanese: str, pos: str) -> dict:
    """品詞に応じた活用形を Gemini で生成して返す。名詞・動詞以外は {}。"""
    base_pos = pos.split("・")[0] if pos else ""
    if base_pos == "名":
        prompt = (
            f'Give the plural form of the English noun "{word}" (Japanese: {japanese}).\n'
            f'Respond ONLY with JSON (no markdown): {{"plural": "..."}}'
        )
    elif base_pos == "動":
        prompt = (
            f'Give all inflected forms of the English verb "{word}" (Japanese: {japanese}).\n'
            f'Respond ONLY with JSON (no markdown): {{"base": "...", "third": "...", "past": "...", "ing": "..."}}'
        )
    else:
        return {}

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = response.text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else parts[0]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── テーマ生成 ────────────────────────────────────────
def generate_theme(client, word: str, japanese: str, pos: str) -> str:
    """単語の意味的カテゴリ（テーマ）を Gemini で生成して返す。"""
    pos_full = POS_MAP.get(pos, pos)
    prompt = (
        f'Assign a short Japanese semantic category (2–5 characters) for the English word "{word}" '
        f'(Japanese: {japanese}, part of speech: {pos_full}).\n'
        f'Examples: 場所・建物, 動作, 食べ物, 学校・教育, 感情・状態, 自然・環境, 数・時間, 人・家族\n'
        f'Respond ONLY with the category string, no explanation.'
    )
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text.strip()


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
def run_import(user_email: str):
    print("=== Import: CSV → Supabase ===")
    print(f"  user: {user_email}")
    sb = get_supabase()

    users = sb.auth.admin.list_users()
    parent = next((u for u in users if getattr(u, 'email', '') == user_email), None)
    if parent is None:
        print(f"  Warning: {user_email} not found. book.created_by will be NULL.")

    words = parse_csv(CSV_PATH)
    print(f"  parsed {len(words)} words from CSV")

    book_id = get_or_create_book(sb, parent.id if parent else None)
    print(f"  book_id: {book_id}")

    upsert_words(sb, words, book_id)

    client = get_gemini()

    # metadata（活用形）未設定の単語に生成・保存
    existing_meta = {
        r["word_key"]: r["metadata"]
        for r in sb.table("words").select("word_key, metadata").eq("book_id", book_id).execute().data
    }
    todo_meta = [w for w in words if not existing_meta.get(w["word_key"])]
    print(f"  generating metadata for {len(todo_meta)} words...")
    for i, w in enumerate(todo_meta):
        base_pos = w["pos"].split("・")[0] if w["pos"] else ""
        if base_pos not in ("名", "動"):
            continue
        print(f"  [{i+1}/{len(todo_meta)}] {w['word_key']}")
        try:
            metadata = generate_forms(client, w["word"], w["japanese"], w["pos"])
            sb.table("words").update({"metadata": metadata}) \
                .eq("book_id", book_id).eq("word_key", w["word_key"]).execute()
        except Exception as e:
            print(f"    ERROR: {e} — skipping")

    # theme 未設定の単語に生成・保存
    existing_themes = {
        r["word_key"]
        for r in sb.table("words").select("word_key, theme").eq("book_id", book_id).execute().data
        if r["theme"]
    }
    todo_theme = [w for w in words if w["word_key"] not in existing_themes]
    print(f"  generating themes for {len(todo_theme)} words...")
    for i, w in enumerate(todo_theme):
        print(f"  [{i+1}/{len(todo_theme)}] {w['word_key']}")
        try:
            theme = generate_theme(client, w["word"], w["japanese"], w["pos"])
            sb.table("words").update({"theme": theme}) \
                .eq("book_id", book_id).eq("word_key", w["word_key"]).execute()
        except Exception as e:
            print(f"    ERROR: {e} — skipping")

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
        replenish_sentences(sb, client, word_key, word, japanese, pos)
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
            return {"sentence": "", "sentence_ja": "", "form": "default"}

    chosen = rows[0]

    if len(rows) <= 1:
        replenish_sentences(sb, client, word_key, word, japanese, pos)

    sb.table("word_sentences").update(
        {"last_used_at": date.today().isoformat()}
    ).eq("id", chosen["id"]).execute()

    return {"sentence": chosen["sentence"], "sentence_ja": chosen["sentence_ja"], "form": chosen["form"]}


# ── ストーリー生成 ────────────────────────────────────
def get_study_day(sb: Client, kaya_user_id: str) -> int:
    """Kayaの累積学習日数 + 1（今日はまだ記録されていないため +1）。"""
    rows = (
        sb.table("progress_sync")
        .select("last_studied")
        .eq("user_id", kaya_user_id)
        .eq("book_key", BOOK_KEY)
        .not_.is_("last_studied", "null")
        .execute()
        .data
    )
    distinct_dates = {r["last_studied"] for r in rows}
    return len(distinct_dates) + 1


def generate_story(client, words_data: list[dict], day: int) -> dict:
    """今日の単語を全て使った短編ストーリーを Gemini で生成して返す。"""
    word_list = ", ".join(w["word"] for w in words_data)
    prompt = f"""Write a short story in English for Kaya, a Japanese junior high school student (beginner level).

Rules:
- The main character is Kaya
- Use ALL of these words at least once (any natural form): {word_list}
- Exactly 10 sentences
- Each sentence must be simple (under 15 words)
- The story must have a single unified theme or scene
- Dialogue is allowed but limited to 1-2 lines
- Write for a beginner English learner — no difficult vocabulary beyond the word list

Respond ONLY with a JSON object (no markdown, no explanation):
{{"title": "...", "sentences": ["...", ...]}}"""

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = response.text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else parts[0]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text.strip())
    return {"day": day, "title": data["title"], "sentences": data["sentences"]}


# ── --generate モード ─────────────────────────────────
def update_sm2_from_progress(sb: Client, kaya_user_id: str, as_of_date: date):
    rows = (
        sb.table("progress_sync")
        .select("*")
        .eq("user_id", kaya_user_id)
        .eq("book_key", BOOK_KEY)
        .neq("status", "new")
        .not_.is_("last_studied", "null")
        .lt("last_studied", as_of_date.isoformat())
        .execute()
        .data
    )
    # next_review が NULL または last_studied 以前の行のみ処理（未反映の回答結果）
    rows = [
        r for r in rows
        if r["next_review"] is None or r["next_review"] <= r["last_studied"]
    ]
    if not rows:
        print(f"  SM-2 updated 0 words")
        return

    # review_log を一括取得（対象単語の last_studied 日付分）
    word_keys = [r["word_key"] for r in rows]
    log_rows = (
        sb.table("review_log")
        .select("word_key, rating, reviewed_at")
        .eq("user_id", kaya_user_id)
        .eq("book_key", BOOK_KEY)
        .in_("word_key", word_keys)
        .execute()
        .data
    )
    # word_key → {date → [ratings]} のマップを構築
    from collections import defaultdict
    log_map: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for log in log_rows:
        d = log["reviewed_at"][:10]  # "YYYY-MM-DD"
        log_map[log["word_key"]][d].append(log["rating"])

    for row in rows:
        ratings = log_map[row["word_key"]].get(row["last_studied"], [])
        quality = quality_from_review_log(ratings)
        ease, interval, reps = sm2_update(
            row["ease_factor"], row["interval_days"], row["repetitions"], quality
        )
        next_review = (date.fromisoformat(row["last_studied"]) + timedelta(days=interval)).isoformat()
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


def select_todays_words(sb: Client, kaya_user_id: str, book_id: str, target_date: date) -> list[dict]:
    # 復習単語: next_review <= target_date かつ 未習得（期日が古い順、最大 DAILY_MAX 語）
    review_rows = (
        sb.table("progress_sync")
        .select("word_key")
        .eq("user_id", kaya_user_id)
        .eq("book_key", BOOK_KEY)
        .lte("next_review", target_date.isoformat())
        .lt("interval_days", MASTERED_INTERVAL)
        .neq("status", "new")
        .order("next_review")
        .limit(DAILY_MAX)
        .execute()
        .data
    )
    review_keys = {r["word_key"] for r in review_rows}

    # 既出単語キー（PostgREST デフォルト1000行制限を超えるため上限を明示）
    all_seen = {
        r["word_key"]
        for r in (
            sb.table("progress_sync")
            .select("word_key")
            .eq("user_id", kaya_user_id)
            .eq("book_key", BOOK_KEY)
            .limit(10000)
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


def build_words_json(words_data: list[dict], sentences: dict[str, dict], story: dict | None = None, target_date: date | None = None) -> dict:
    result = []
    for w in words_data:
        sent = sentences.get(w["word_key"], {})
        metadata = w.get("metadata") or {}
        form = sent.get("form", "default")
        pos_base = (w["pos"] or "").split("・")[0]

        # word_sentences.form + words.metadata から english を導出
        form_to_english = {
            "singular": w["word"],
            "plural":   metadata.get("plural", w["word"]),
            "base":     w["word"],
            "third":    metadata.get("third", w["word"]),
            "past":     metadata.get("past",  w["word"]),
            "default":  w["word"],
        }
        english = form_to_english.get(form, w["word"])

        card = {
            "id": w["word_key"],
            "word": w["word"],
            "english": english,
            "japanese": w["back_main"],
            "pos": w["pos"] or "",
            "theme": w["theme"] or "",
            "status": "new",
            "correct": 0,
            "incorrect": 0,
            "lastSeen": None,
            "sentence": sent.get("sentence", ""),
            "sentence_ja": sent.get("sentence_ja", ""),
            "image": w["image_path"] or (
                f"data/images/{w['word_key']}.png"
                if (OUTPUT_PATH.parent / "images" / f"{w['word_key']}.png").exists()
                else ""
            ),
        }

        # 活用形フィールド（ミス検出用）— pos に応じて必要なものだけ追加
        if pos_base == "名":
            card["plural"] = metadata.get("plural")
        elif pos_base == "動":
            card["base"]  = metadata.get("base")
            card["third"] = metadata.get("third")
            card["past"]  = metadata.get("past")
            card["ing"]   = metadata.get("ing")

        result.append(card)

    output = {
        "meta": {
            "total": len(result),
            "theme": BOOK_NAME,
            "created": (target_date or date.today()).isoformat(),
        },
        "words": result,
    }
    if story:
        output["story"] = story
    return output


def run_generate(user_email: str, target_date: date):
    print("=== Generate: SM-2 → words.json ===")
    print(f"  user: {user_email}")
    print(f"  date: {target_date.isoformat()}")
    sb = get_supabase()
    client = get_gemini()

    users = sb.auth.admin.list_users()
    kaya = next((u for u in users if getattr(u, 'email', '') == user_email), None)
    if not kaya:
        print(f"ERROR: {user_email} not found in Supabase Auth.")
        sys.exit(1)
    kaya_user_id = kaya.id

    book_res = sb.table("books").select("id").eq("name", BOOK_NAME).execute()
    if not book_res.data:
        print("ERROR: book not found. Run --import first.")
        sys.exit(1)
    book_id = book_res.data[0]["id"]

    update_sm2_from_progress(sb, kaya_user_id, as_of_date=target_date)
    words_data = select_todays_words(sb, kaya_user_id, book_id, target_date=target_date)
    print(f"  selected {len(words_data)} words for today")

    sentences = {}
    for w in words_data:
        sentences[w["word_key"]] = pick_sentence(
            sb, client, w["word_key"], w["word"], w["back_main"], w["pos"] or ""
        )

    day = get_study_day(sb, kaya_user_id)
    print(f"  generating story for day {day}...")
    story = None
    try:
        story = generate_story(client, words_data, day)
    except Exception as e:
        print(f"  story generation failed: {e} — skipping")

    output = build_words_json(words_data, sentences, story, target_date=target_date)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"  wrote {OUTPUT_PATH} ({len(words_data)} words, story={'yes' if story else 'no'})")
    print("=== Generate complete ===")


# ── エントリポイント ──────────────────────────────────
def resolve_user_email(args_user: str | None) -> str:
    """--user 引数 → KAYA_USER_EMAIL 環境変数 の順で解決。どちらもなければエラー終了。"""
    email = args_user or os.environ.get("KAYA_USER_EMAIL")
    if not email:
        print("ERROR: ユーザーメールが指定されていません。")
        print("  ローカルテスト: --user shiwei76@gmail.com")
        print("  本番実行:       --user kaya.zhu@icloud.com")
        print("  または環境変数: export KAYA_USER_EMAIL=<email>")
        sys.exit(1)
    return email


def main():
    parser = argparse.ArgumentParser(description="SM-2 単語生成スクリプト")
    parser.add_argument("--import", dest="do_import", action="store_true", help="CSV → Supabase インポート")
    parser.add_argument("--generate", dest="do_generate", action="store_true", help="SM-2 → words.json 生成")
    parser.add_argument("--user", dest="user_email", default=None,
                        help="対象ユーザーのメールアドレス（省略時は KAYA_USER_EMAIL 環境変数）")
    parser.add_argument("--date", dest="target_date", default=None,
                        help="生成対象日 YYYY-MM-DD（省略時は今日）。事前生成時に使用")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.target_date) if args.target_date else date.today()

    if args.do_import:
        run_import(resolve_user_email(args.user_email))
    elif args.do_generate:
        run_generate(resolve_user_email(args.user_email), target_date)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
