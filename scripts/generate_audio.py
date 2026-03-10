#!/usr/bin/env python3
"""
音声生成スクリプト
Gemini TTS を使って words.json の単語・例文・ストーリーのMP3を生成する

使い方:
  python generate_audio.py              # 全音声を生成
  python generate_audio.py --words-only # 単語のみ
  python generate_audio.py --force      # 既存ファイルも上書き
"""

import csv
import json
import os
import subprocess
import sys
import time
import argparse
from pathlib import Path

from google import genai
from google.genai import types
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

LETTER_NAMES = {
    'a':'ay','b':'bee','c':'see','d':'dee','e':'ee','f':'ef','g':'gee',
    'h':'aitch','i':'eye','j':'jay','k':'kay','l':'el','m':'em',
    'n':'en','o':'oh','p':'pee','q':'cue','r':'ar','s':'ess',
    't':'tee','u':'you','v':'vee','w':'double-you','x':'ex','y':'why','z':'zee'
}
SPELLING_TEMPO = 1.7  # atempo倍率（速度調整、旧方式）
SPELLING_BREAK_MS = 50  # Google Cloud TTS スペル文字間ポーズ（ms）
CSV_PATH = (
    "/Users/shiwei.zhu/Library/CloudStorage/"
    "GoogleDrive-shiwei76@gmail.com/マイドライブ/01.M&K/02.Kaya/洗足/"
    "NEW_TREASURE_Stage1_単語帳.csv"
)

LETTERS_AUDIO_DIR = AUDIO_DIR / "letters"

GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
VOICE_NAME = "Aoede"   # 女性英語音声（Kaya向け）
PCM_RATE = 24000
RATE_LIMIT_SLEEP = 6.5  # API レート制限対策（10 req/分 = 6秒/req）
MAX_RETRIES = 3


def init_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が環境変数に設定されていません")
        sys.exit(1)
    return genai.Client(api_key=api_key)


def pcm_to_mp3(pcm_bytes: bytes, output_path: Path) -> bool:
    """raw PCM (L16, 24kHz, mono) → MP3 変換（ffmpegを使用）"""
    cmd = [
        "ffmpeg", "-y",
        "-f", "s16le",
        "-ar", str(PCM_RATE),
        "-ac", "1",
        "-i", "pipe:0",
        "-codec:a", "libmp3lame",
        "-q:a", "4",
        str(output_path)
    ]
    result = subprocess.run(cmd, input=pcm_bytes, capture_output=True)
    return result.returncode == 0


def pcm_to_mp3_with_tempo(pcm_bytes: bytes, output_path: Path, tempo: float) -> bool:
    """raw PCM → MP3 + atempo速度調整"""
    tmp = output_path.with_suffix('.raw.mp3')
    if not pcm_to_mp3(pcm_bytes, tmp):
        return False
    cmd = ["ffmpeg", "-y", "-i", str(tmp), "-filter:a", f"atempo={tempo}", str(output_path)]
    result = subprocess.run(cmd, capture_output=True)
    tmp.unlink(missing_ok=True)
    return result.returncode == 0


def word_to_phonetic(word: str, sep: str = ", ") -> str:
    """単語をフォネティック文字名に変換 (例: store → ess, tee, oh, ar, ee)"""
    return sep.join(LETTER_NAMES.get(c, c) for c in word.lower())


def concat_letter_mp3s(letters: list, output_path: Path, pause_ms: int = 350) -> bool:
    """文字MP3リストを無音ポーズ付きで結合してoutput_pathに出力"""
    import tempfile
    # ffmpeg concat demuxer 用リストファイルを作成
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        list_path = Path(f.name)
        for i, mp3 in enumerate(letters):
            f.write(f"file '{mp3}'\n")
            if i < len(letters) - 1:  # 最後の文字の後はポーズなし
                f.write(f"duration {pause_ms / 1000:.3f}\n")
    # concat demuxerで結合
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-c:a", "libmp3lame", "-q:a", "4",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True)
    list_path.unlink(missing_ok=True)
    return result.returncode == 0


def ensure_letter_audio(client, letter: str, force: bool = False) -> Path | None:
    """a–z の1文字MP3を生成（なければ）し、Pathを返す"""
    LETTERS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out = LETTERS_AUDIO_DIR / f"{letter}.mp3"
    # 大文字の文字そのものを渡す（TTS が C→"see", F→"ef" と自然に発音）
    # 一部の文字は大文字だけでは正しく発音されないため音素名を直接指定
    LETTER_TEXT_OVERRIDES = {
        'c': 'cee.',      # "C." が content=None を返す
        'l': 'el.',       # "L." が "ら" に聞こえる
        'r': 'ar.',       # 念のため
        'w': 'double-you.',
    }
    text = LETTER_TEXT_OVERRIDES.get(letter, f"{letter.upper()}.")
    if generate_audio(client, text, out, force=force):
        return out
    return None


def generate_spelling_audio(word: str, output_path: Path, force: bool = False) -> bool:
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
        tts_client = texttospeech.TextToSpeechClient()
        response = tts_client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml),
            voice=texttospeech.VoiceSelectionParams(
                language_code='en-US', name='en-US-Wavenet-F'
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


def generate_audio(client, text: str, output_path: Path, force: bool = False) -> bool:
    """テキストからMP3を生成して保存"""
    if output_path.exists() and not force:
        print(f"  SKIP (既存): {output_path.name}")
        return True

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=VOICE_NAME
                            )
                        )
                    ),
                ),
            )
            content = response.candidates[0].content
            if content is None:
                # FinishReason.OTHER: モデルが音声を生成しなかった → リトライ
                print(f"  RETRY: {output_path.name} (content=None, attempt {attempt+1}/{MAX_RETRIES})")
                time.sleep(RATE_LIMIT_SLEEP)
                continue
            pcm_data = content.parts[0].inline_data.data

            if pcm_to_mp3(pcm_data, output_path):
                size_kb = output_path.stat().st_size // 1024
                print(f"  OK: {output_path.name} ({size_kb}KB)")
                return True
            else:
                print(f"  ERROR: ffmpeg変換失敗 → {output_path.name}")
                return False

        except Exception as e:
            msg = str(e)
            # レート制限エラー: retryDelay を取得して待機
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                wait = 30
                import re
                m = re.search(r"retryDelay.*?(\d+)s", msg)
                if m:
                    wait = int(m.group(1)) + 2
                print(f"  WAIT: レート制限 → {wait}秒待機 (attempt {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            print(f"  ERROR: {output_path.name} → {e}")
            return False

    print(f"  FAILED: {output_path.name} (リトライ上限到達)")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--words-only", action="store_true", help="単語のみ生成")
    parser.add_argument("--spelling-only", action="store_true", help="スペル音声のみ生成（words.json対象）")
    parser.add_argument("--spelling-all", action="store_true", help="CSV全単語のスペル音声を一括生成（Google Cloud TTS）")
    parser.add_argument("--gen-letters", action="store_true", help="a–z 文字音声を生成（スペル合成の前準備）")
    parser.add_argument("--force", action="store_true", help="既存ファイルを上書き")
    args = parser.parse_args()

    # ディレクトリ作成
    WORDS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SENTENCES_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    STORY_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SPELLING_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    LETTERS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    client = init_client()

    if args.gen_letters:
        print(f"\n[文字音声] a–z を生成中... (26文字)")
        ok = err = 0
        for letter in "abcdefghijklmnopqrstuvwxyz":
            p = ensure_letter_audio(client, letter, force=args.force)
            if p:
                ok += 1
            else:
                err += 1
            time.sleep(RATE_LIMIT_SLEEP)
        print(f"\n完了: {ok}成功 / {err}失敗")
        return

    # データ読み込み
    with open(WORDS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    words = data["words"]
    story = data.get("story", {})

    ok = err = 0

    if args.spelling_all:
        # --- CSV から全単語のスペル音声を一括生成 ---
        seen: set[str] = set()
        with open(CSV_PATH, encoding="utf-8") as f:
            all_words = sorted({row["English"].strip() for row in csv.DictReader(f) if row["English"].strip()})
        print(f"\n[スペル音声・全単語] 生成中... ({len(all_words)}語)")
        for word in all_words:
            out = SPELLING_AUDIO_DIR / f"{word}.mp3"
            if generate_spelling_audio(word, out, args.force):
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
            if generate_spelling_audio(base, out, args.force):
                ok += 1
            else:
                err += 1
        print(f"\n完了: {ok}成功 / {err}失敗")
        return

    # --- 単語の読み上げ ---
    print(f"\n[1/4] 単語音声を生成中... ({len(words)}語)")
    for word in words:
        out = WORDS_AUDIO_DIR / f"{word['id']}.mp3"
        # 単語を自然に読み上げるため "The word is: store" 形式にする
        text = f"{word['english']}"
        if generate_audio(client, text, out, args.force):
            ok += 1
        else:
            err += 1
        time.sleep(RATE_LIMIT_SLEEP)

    if args.words_only:
        print(f"\n完了: {ok}成功 / {err}失敗")
        return

    # --- 例文の読み上げ ---
    print(f"\n[2/4] 例文音声を生成中... ({len(words)}文)")
    for word in words:
        out = SENTENCES_AUDIO_DIR / f"{word['id']}.mp3"
        if generate_audio(client, word["sentence"], out, args.force):
            ok += 1
        else:
            err += 1
        time.sleep(RATE_LIMIT_SLEEP)

    # --- ストーリーの読み上げ ---
    sentences = story.get("sentences", [])
    print(f"\n[3/4] ストーリー音声を生成中... ({len(sentences)}文)")
    for i, sentence in enumerate(sentences):
        out = STORY_AUDIO_DIR / f"s{i+1:02d}.mp3"
        if generate_audio(client, sentence, out, args.force):
            ok += 1
        else:
            err += 1
        time.sleep(RATE_LIMIT_SLEEP)

    # --- スペル読み上げ ---
    seen = set()
    unique_words = [w for w in words if not (w.get('word', w['english']) in seen or seen.add(w.get('word', w['english'])))]
    print(f"\n[4/4] スペル音声を生成中... ({len(unique_words)}語)")
    for word in unique_words:
        base = word.get('word', word['english'])
        out = SPELLING_AUDIO_DIR / f"{base}.mp3"
        if generate_spelling_audio(client, base, out, args.force):
            ok += 1
        else:
            err += 1
        time.sleep(RATE_LIMIT_SLEEP)

    print(f"\n=== 完了: {ok}成功 / {err}失敗 ===")
    print(f"出力先: {AUDIO_DIR}")


if __name__ == "__main__":
    main()
