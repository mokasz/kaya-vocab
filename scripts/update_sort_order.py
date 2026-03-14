#!/usr/bin/env python3
"""
PDFから抽出したLesson順の単語リストを使って、Supabase words テーブルの sort_order を更新する。

使い方:
    venv/bin/python kaya-vocab/scripts/update_sort_order.py [--dry-run]

--dry-run: DBを変更せず、マッピング結果だけ表示する。
"""

import os
import sys
import argparse
from pathlib import Path

from supabase import create_client

BOOK_KEY = "kaya-stage1"

# ── PDFから抽出したLesson順の単語リスト ────────────────────────────
# 各エントリは DB の `word` フィールド（英語ベース形）と照合する。
# 重複単語は最初の出現位置を採用。
ORDERED_WORDS = [
    # ── Words Beginning ──────────────────────────
    "apple", "boat", "cat", "dog", "egg", "fish", "guitar", "house", "ink", "jam",
    "key", "lion", "milk", "name", "orange", "panda", "question", "rabbit", "sun",
    "tea", "umbrella", "violin", "woman", "box", "yacht", "zoo",
    "classroom", "door", "map", "calendar", "clock", "blackboard", "chalk", "desk",
    "chair", "dictionary", "notebook", "pencil", "eraser", "textbook", "picture",
    "TV", "doll", "computer", "bed", "radio", "watch", "camera", "telephone", "bag",
    "album", "window", "garden", "train", "station", "car", "bus", "tree", "school",
    "bike",
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "spring", "summer", "fall", "autumn", "winter",
    "pink", "red", "brown", "yellow", "green", "blue", "violet", "purple", "white",
    "gray", "black",
    "ear", "eye", "nose", "mouth", "hair",

    # ── Lesson 1 ──────────────────────────────────
    "America", "Australia", "Canada", "China", "Japan", "France",
    "hello", "hi", "please", "call", "me", "nice", "meet",
    "you", "are", "from", "no", "not", "my", "is",
    "Mr.", "this", "your", "teacher", "student", "card", "here", "and",
    "locker", "thank", "that", "it",
    "sister", "let's", "start", "everyone",
    "year", "old", "favorite", "Japanese", "food", "next",
    "like", "hot", "good", "job",
    "Finland", "salmon", "soup",
    "delicious", "sweet", "sour", "hard", "soft",

    # ── Lesson 2 ──────────────────────────────────
    "doctor", "nurse", "firefighter", "police officer", "pilot", "office worker",
    "vet",
    "classmate", "she", "her", "father", "mother",
    "math", "science", "English", "Ms.", "friend", "his",
    "big", "book", "lunchbox",
    "time", "o'clock", "lunch", "now", "radish", "eggplant",
    "tall", "boy", "small", "hungry", "bad", "new", "young", "man",
    "long", "short", "girl", "high", "low", "building", "lady",
    "really", "right", "temple", "uncle",
    "fruit", "vegetable", "family", "very", "busy",
    "beautiful", "toy", "tool", "kind",
    "grandfather", "grandmother", "aunt", "dad", "mom", "cousin", "brother",
    "funny", "shy", "friendly", "smart",

    # ── Lesson 3 ──────────────────────────────────
    "play", "park", "with", "piano", "trumpet", "drum", "soccer",
    "basketball", "every", "do", "but", "tennis", "practice",
    "after", "well", "much", "day", "everyday", "speak", "study",
    "party", "sandwich", "how", "about", "candy", "see", "over", "there",
    "want", "have", "ball", "some", "pen", "any", "need", "dish",
    "evening", "morning", "afternoon", "photo", "welcome", "today", "these",
    "they", "Mexico", "Spanish", "home", "talk", "them", "their", "Mexican",
    "dress", "color", "design", "baseball", "player", "teammate", "singer",
    "T-shirt", "those", "coat", "know", "him", "us", "our", "parent",

    # ── Lesson 4 ──────────────────────────────────
    "hamster", "bird", "monkey", "horse", "eat",
    "breakfast", "cucumber", "thick",
    "people", "child", "children", "many", "lot", "potato", "city",
    "leaf", "leaves", "knife", "knives", "sheep",
    "Chinese", "rose", "pie",
    "also", "fridge", "song", "class", "coin", "water", "money",
    "pocket", "yen", "fan", "love", "chef", "restaurant", "roll", "put",
    "seaweed", "inside", "rice", "sticky", "avocado", "crab", "meat",
    "interesting", "serve", "healthy", "another", "California",
    "best", "regard", "strange", "lychee", "banana", "tomato", "excuse",

    # ── Lesson 5 ──────────────────────────────────
    "headache", "racket", "bench", "mine", "whose", "maybe", "case", "ruler",
    "yours", "stapler", "ours", "hers", "theirs", "hat",
    "dollar", "size", "centimeter", "inch", "fine", "just",
    "meter", "river", "kilometer", "deep", "lake", "ticket", "yard", "mile",
    "point", "which", "pants", "shorts", "sale", "percent", "wow", "deal",
    "different", "captain", "team", "cup",
    "subject", "Bali", "island", "Indonesia", "mountain", "beach",
    "god", "most", "custom", "touch", "other", "left", "life",
    "Hindu", "visit", "someday", "place", "religious", "dance",
    "ketjak", "barong", "story", "battle", "between", "witch",
    "change", "cent", "shirt", "jeans", "skirt", "sock", "shoe",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="DBを変更せず結果のみ表示")
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # book_id を取得
    book = sb.table("books").select("id").eq("name", "NEW TREASURE Stage 1").execute()
    book_id = book.data[0]["id"]
    print(f"book_id: {book_id}")

    # DB から全単語を取得（word_key + word フィールド）
    rows = sb.table("words").select("word_key, word").eq("book_id", book_id).execute().data
    print(f"DB の単語数: {len(rows)}")

    # word（英語ベース形）→ word_key リスト のマップ（小文字で正規化）
    word_to_keys: dict[str, list[str]] = {}
    for r in rows:
        key = r["word"].lower().strip()
        word_to_keys.setdefault(key, []).append(r["word_key"])

    # PDF と DB で表記が異なるケースのエイリアス
    ALIASES: dict[str, str] = {
        "telephone": "phone",          # Words Beginning では telephone、DB では phone
        "police officer": "policeofficer",
        "office worker": "officeworker",
        "fall": "autumn",              # fall/autumn
    }
    for pdf_word, db_word in ALIASES.items():
        if db_word in word_to_keys and pdf_word not in word_to_keys:
            word_to_keys[pdf_word] = word_to_keys[db_word]

    # 重複なしの ordered list（最初の出現位置を採用）
    seen: set[str] = set()
    deduped: list[str] = []
    for w in ORDERED_WORDS:
        wl = w.lower().strip()
        if wl not in seen:
            seen.add(wl)
            deduped.append(w)

    # sort_order の割り当て（1-based、10刻みで余裕を持たせる）
    updates: list[tuple[str, int]] = []  # (word_key, sort_order)
    not_found: list[str] = []

    sort_order = 10
    for w in deduped:
        wl = w.lower().strip()
        matched_keys = word_to_keys.get(wl, [])
        if matched_keys:
            for wk in matched_keys:
                updates.append((wk, sort_order))
            sort_order += 10
        else:
            not_found.append(w)

    print(f"\n--- マッピング結果 ---")
    print(f"  対応あり: {len(updates)} 件 (word_key)")
    print(f"  DB に未存在: {len(not_found)} 語")
    if not_found:
        print(f"  未存在リスト: {not_found[:20]}{'...' if len(not_found)>20 else ''}")

    # DB に存在するが ORDERED_WORDS に含まれない単語
    ordered_words_lower = {w.lower().strip() for w in deduped}
    unordered_keys = [r["word_key"] for r in rows if r["word"].lower().strip() not in ordered_words_lower]
    print(f"\n  sort_order=NULL のまま残る単語: {len(unordered_keys)} 件")

    if args.dry_run:
        print("\n[dry-run] DB 更新をスキップ")
        print("\nサンプル（最初の20件）:")
        for wk, so in updates[:20]:
            print(f"  {wk:30s} → sort_order={so}")
        return

    # ① まず全語の sort_order を NULL にリセット（旧CSV行順が残らないように）
    print(f"\n全語の sort_order を NULL にリセット中...")
    sb.table("words").update({"sort_order": None}).eq("book_id", book_id).execute()
    print("  リセット完了")

    # ② Lesson 順で sort_order を設定
    print(f"\nLesson 順で sort_order を設定中... ({len(updates)} 件)")
    for i, (wk, so) in enumerate(updates):
        sb.table("words").update({"sort_order": so}) \
            .eq("book_id", book_id).eq("word_key", wk).execute()
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(updates)} 完了")

    print(f"\n完了: {len(updates)} 件の sort_order を更新しました。")
    print(f"sort_order=NULL のまま: {len(unordered_keys)} 件 (Lesson 6〜10 など)")


if __name__ == "__main__":
    main()
