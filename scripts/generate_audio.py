#!/usr/bin/env python3
"""
音声生成スクリプト
Gemini TTS を使って words.json の単語・例文・ストーリーのMP3を生成する

使い方:
  python generate_audio.py              # 全音声を生成
  python generate_audio.py --words-only # 単語のみ
  python generate_audio.py --force      # 既存ファイルも上書き
"""

import json
import os
import subprocess
import sys
import time
import argparse
from pathlib import Path

from google import genai
from google.genai import types

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
SPELLING_TEMPO = 1.7  # atempo倍率（速度調整）

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


def generate_spelling_audio(client, word: str, output_path: Path, force: bool = False) -> bool:
    """スペル読み上げMP3を生成（コンマ区切り → 失敗時はピリオド区切りで再試行）"""
    if output_path.exists() and not force:
        print(f"  SKIP (既存): {output_path.name}")
        return True

    for sep in [", ", ". "]:
        text = word_to_phonetic(word, sep)
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
                pcm_data = response.candidates[0].content.parts[0].inline_data.data
                if pcm_to_mp3_with_tempo(pcm_data, output_path, SPELLING_TEMPO):
                    size_kb = output_path.stat().st_size // 1024
                    print(f"  OK: {output_path.name} ({size_kb}KB) [{text}]")
                    return True
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    wait = 30
                    import re
                    m = re.search(r"retryDelay.*?(\d+)s", msg)
                    if m:
                        wait = int(m.group(1)) + 2
                    print(f"  WAIT: {wait}秒待機")
                    time.sleep(wait)
                    continue
                # INVALID_ARGUMENT (テキスト生成エラー) → 別セパレーターで再試行
                if "INVALID_ARGUMENT" in msg:
                    break
                print(f"  ERROR: {output_path.name} → {e}")
                return False

    print(f"  FAILED: {output_path.name}")
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
            pcm_data = response.candidates[0].content.parts[0].inline_data.data

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
    parser.add_argument("--spelling-only", action="store_true", help="スペル音声のみ生成")
    parser.add_argument("--force", action="store_true", help="既存ファイルを上書き")
    args = parser.parse_args()

    # ディレクトリ作成
    WORDS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SENTENCES_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    STORY_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SPELLING_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # データ読み込み
    with open(WORDS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    client = init_client()
    words = data["words"]
    story = data.get("story", {})

    ok = err = 0

    if args.spelling_only:
        # --- スペル音声のみ ---
        seen = set()
        unique_words = [w for w in words if not (w.get('word', w['english']) in seen or seen.add(w.get('word', w['english'])))]
        print(f"\n[スペル音声] 生成中... ({len(unique_words)}語)")
        for word in unique_words:
            base = word.get('word', word['english'])
            out = SPELLING_AUDIO_DIR / f"{base}.mp3"
            if generate_spelling_audio(client, base, out, args.force):
                ok += 1
            else:
                err += 1
            time.sleep(RATE_LIMIT_SLEEP)
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
