#!/usr/bin/env python3
"""
音声生成スクリプト
Google Cloud TTS を使って words.json の単語・例文・ストーリーのMP3を生成する

使い方:
  python generate_audio.py              # 全音声を生成
  python generate_audio.py --words-only # 単語のみ
  python generate_audio.py --spelling-only # スペルのみ
  python generate_audio.py --force      # 既存ファイルも上書き
"""

import csv
import json
import os
import sys
import argparse
from datetime import date
from pathlib import Path

from google.cloud import texttospeech

# --- 設定 ---
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
WORDS_FILE = DATA_DIR / "words.json"
AUDIO_DIR = DATA_DIR / "audio"
WORDS_AUDIO_DIR = AUDIO_DIR / "words"
SENTENCES_AUDIO_DIR = AUDIO_DIR / "sentences"
STORY_AUDIO_DIR = AUDIO_DIR / "story"
SPELLING_AUDIO_DIR = AUDIO_DIR / "spelling"

CSV_PATH = (
    "/Users/shiwei.zhu/Library/CloudStorage/"
    "GoogleDrive-shiwei76@gmail.com/マイドライブ/01.M&K/02.Kaya/洗足/"
    "NEW_TREASURE_Stage1_単語帳.csv"
)

# 音声モデル設定
VOICE_NAME = "en-US-Journey-F" # 表現豊かな女性音声
LANGUAGE_CODE = "en-US"
SPELLING_BREAK_MS = 50  # Google Cloud TTS スペル文字間ポーズ（ms）


def get_tts_client():
    try:
        return texttospeech.TextToSpeechClient()
    except Exception as e:
        print(f"ERROR: Google Cloud TTS クライアントの初期化に失敗しました。認証情報を確認してください。\n{e}")
        sys.exit(1)


def generate_text_audio(client: texttospeech.TextToSpeechClient, text: str, output_path: Path, force: bool = False) -> bool:
    """プレーンテキストからMP3を生成して保存"""
    if output_path.exists() and not force:
        print(f"  SKIP (既存): {output_path.name}")
        return True

    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=LANGUAGE_CODE,
            name=VOICE_NAME
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        output_path.write_bytes(response.audio_content)
        size_kb = len(response.audio_content) // 1024
        print(f"  OK: {output_path.name} ({size_kb}KB)")
        return True

    except Exception as e:
        print(f"  FAILED: {output_path.name} ({e})")
        return False


def generate_spelling_audio(client: texttospeech.TextToSpeechClient, word: str, output_path: Path, force: bool = False) -> bool:
    """Google Cloud TTS + SSML でスペル読み上げMP3を生成"""
    if output_path.exists() and not force:
        print(f"  SKIP (既存): {output_path.name}")
        return True

    # アルファベット以外の文字を除外
    letters = [c for c in word.upper() if c.isalpha()]
    if not letters:
        print(f"  SKIP (非アルファベット): {output_path.name}")
        return True

    break_tag = f' <break time="{SPELLING_BREAK_MS}ms"/> '
    ssml = f'<speak><prosody rate="0.9">{break_tag.join(letters)}</prosody></speak>'

    try:
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml),
            voice=texttospeech.VoiceSelectionParams(
                language_code=LANGUAGE_CODE,
                name=VOICE_NAME
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
        )
        output_path.write_bytes(response.audio_content)
        size_kb = len(response.audio_content) // 1024
        print(f"  OK: {output_path.name} ({size_kb}KB)")
        return True
    except Exception as e:
        print(f"  FAILED: {output_path.name} ({e})")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--words-only", action="store_true", help="単語のみ生成")
    parser.add_argument("--spelling-only", action="store_true", help="スペル音声のみ生成（words.json対象）")
    parser.add_argument("--spelling-all", action="store_true", help="CSV全単語のスペル音声を一括生成")
    parser.add_argument("--force", action="store_true", help="既存ファイルを上書き")
    parser.add_argument("--date", dest="target_date", default=None,
                        help="生成対象日 YYYY-MM-DD（省略時は words.json の meta.created）")
    args = parser.parse_args()

    # ディレクトリ作成
    WORDS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SENTENCES_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    STORY_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SPELLING_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    client = get_tts_client()

    # データ読み込み
    with open(WORDS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    words = data["words"]
    story = data.get("story", {})

    # 日付: --date 引数 > meta.created > 今日
    audio_date = args.target_date or data.get("meta", {}).get("created") or date.today().isoformat()
    print(f"音声日付: {audio_date}")

    ok = err = 0

    if args.spelling_all:
        # --- CSV から全単語のスペル音声を一括生成 ---
        seen: set[str] = set()
        with open(CSV_PATH, encoding="utf-8") as f:
            all_words = sorted({row["English"].strip() for row in csv.DictReader(f) if row["English"].strip()})
        print(f"\n[スペル音声・全単語] 生成中... ({len(all_words)}語)")
        for word in all_words:
            out = SPELLING_AUDIO_DIR / f"{word}.mp3"
            if generate_spelling_audio(client, word, out, args.force):
                ok += 1
            else:
                err += 1
        print(f"\n完了: {ok}成功 / {err}失敗")
        return

    if args.spelling_only:
        # --- words.json のスペル音声のみ ---
        seen: set[str] = set()
        unique_words = [w for w in words if not (w.get('word', w['english']) in seen or seen.add(w.get('word', w['english'])))]
        print(f"\n[スペル音声] 生成中... ({len(unique_words)}語)")
        for word in unique_words:
            base = word.get('word', word['english'])
            out = SPELLING_AUDIO_DIR / f"{base}.mp3"
            if generate_spelling_audio(client, base, out, args.force):
                ok += 1
            else:
                err += 1
        print(f"\n完了: {ok}成功 / {err}失敗")
        return

    # --- 単語の読み上げ ---
    print(f"\n[1/3] 単語音声を生成中... ({len(words)}語)")
    seen_words: set[str] = set()
    for word in words:
        base = word.get('word', word['english'])
        if base in seen_words:
            print(f"  SKIP (共有音声済み): {base}.mp3")
            continue
        seen_words.add(base)
        out = WORDS_AUDIO_DIR / f"{base}.mp3"
        # 以前は "Say the word: {base}" としていたが、Google Cloud TTSは1単語でも安定しているためそのまま渡す
        if generate_text_audio(client, base, out, args.force):
            ok += 1
        else:
            err += 1

    if args.words_only:
        print(f"\n完了: {ok}成功 / {err}失敗")
        return

    # --- 例文の読み上げ（日付付きファイル名） ---
    print(f"\n[2/3] 例文音声を生成中... ({len(words)}文)")
    for word in words:
        out = SENTENCES_AUDIO_DIR / f"{word['id']}_{audio_date}.mp3"
        if generate_text_audio(client, word["sentence"], out, args.force):
            ok += 1
        else:
            err += 1

    # --- ストーリーの読み上げ（日付付きファイル名） ---
    sentences = story.get("sentences", [])
    print(f"\n[3/3] ストーリー音声を生成中... ({len(sentences)}文)")
    for i, sentence in enumerate(sentences):
        out = STORY_AUDIO_DIR / f"s{i+1:02d}_{audio_date}.mp3"
        if generate_text_audio(client, sentence, out, args.force):
            ok += 1
        else:
            err += 1

    print(f"\n=== 完了: {ok}成功 / {err}失敗 ===")
    print(f"出力先: {AUDIO_DIR}")


if __name__ == "__main__":
    main()
