import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from generate_words import build_words_json


# ── テストデータヘルパー ──────────────────────────────

def _word(word_key, word, pos, metadata=None):
    return {
        "word_key": word_key,
        "word": word,
        "back_main": "テスト",
        "pos": pos,
        "theme": None,
        "image_path": "",
        "metadata": metadata or {},
    }


def _sent(sentence, sentence_ja, form):
    return {"sentence": sentence, "sentence_ja": sentence_ja, "form": form}


# ── english 導出 ──────────────────────────────────────

def test_english_singular():
    w = _word("store", "store", "名", {"plural": "stores"})
    card = build_words_json([w], {"store": _sent("I see a store.", "...", "singular")})["words"][0]
    assert card["english"] == "store"


def test_english_plural():
    w = _word("store", "store", "名", {"plural": "stores"})
    card = build_words_json([w], {"store": _sent("Many stores are open.", "...", "plural")})["words"][0]
    assert card["english"] == "stores"


def test_english_base():
    w = _word("play", "play", "動", {"base": "play", "third": "plays", "past": "played", "ing": "playing"})
    card = build_words_json([w], {"play": _sent("I play soccer.", "...", "base")})["words"][0]
    assert card["english"] == "play"


def test_english_third():
    w = _word("play", "play", "動", {"base": "play", "third": "plays", "past": "played", "ing": "playing"})
    card = build_words_json([w], {"play": _sent("She plays piano.", "...", "third")})["words"][0]
    assert card["english"] == "plays"


def test_english_past():
    w = _word("play", "play", "動", {"base": "play", "third": "plays", "past": "played", "ing": "playing"})
    card = build_words_json([w], {"play": _sent("He played soccer.", "...", "past")})["words"][0]
    assert card["english"] == "played"


def test_english_default():
    w = _word("awesome", "awesome", "形", {})
    card = build_words_json([w], {"awesome": _sent("That is awesome.", "...", "default")})["words"][0]
    assert card["english"] == "awesome"


def test_english_empty_metadata_falls_back_to_word():
    """metadata が空のとき plural/third/past は word にフォールバック"""
    w = _word("store", "store", "名", {})
    card = build_words_json([w], {"store": _sent("Many stores.", "...", "plural")})["words"][0]
    assert card["english"] == "store"


def test_english_no_sentence_falls_back_to_word():
    """センテンスなし（sentences dict に key がない）のとき form=default → english = word"""
    w = _word("store", "store", "名", {"plural": "stores"})
    card = build_words_json([w], {})["words"][0]
    assert card["english"] == "store"


# ── 名詞の活用フィールド ──────────────────────────────

def test_noun_has_plural_field():
    w = _word("store", "store", "名", {"plural": "stores"})
    card = build_words_json([w], {})["words"][0]
    assert card["plural"] == "stores"


def test_noun_has_no_verb_fields():
    w = _word("store", "store", "名", {"plural": "stores"})
    card = build_words_json([w], {})["words"][0]
    assert "base" not in card
    assert "third" not in card
    assert "past" not in card
    assert "ing" not in card


# ── 動詞の活用フィールド ──────────────────────────────

def test_verb_has_all_conjugation_fields():
    w = _word("play", "play", "動", {"base": "play", "third": "plays", "past": "played", "ing": "playing"})
    card = build_words_json([w], {})["words"][0]
    assert card["base"] == "play"
    assert card["third"] == "plays"
    assert card["past"] == "played"
    assert card["ing"] == "playing"


def test_verb_has_no_plural_field():
    w = _word("play", "play", "動", {"base": "play", "third": "plays", "past": "played", "ing": "playing"})
    card = build_words_json([w], {})["words"][0]
    assert "plural" not in card


# ── 形容詞・副詞（その他）────────────────────────────

def test_other_pos_has_no_inflection_fields():
    w = _word("awesome", "awesome", "形", {})
    card = build_words_json([w], {})["words"][0]
    assert "plural" not in card
    assert "base" not in card
    assert "third" not in card
    assert "past" not in card
    assert "ing" not in card


# ── meta ─────────────────────────────────────────────

def test_meta_total_matches_word_count():
    words = [
        _word("store", "store", "名", {"plural": "stores"}),
        _word("play",  "play",  "動", {"base": "play", "third": "plays", "past": "played", "ing": "playing"}),
        _word("awesome", "awesome", "形", {}),
    ]
    result = build_words_json(words, {})
    assert result["meta"]["total"] == 3


def test_meta_created_is_today():
    from datetime import date
    w = _word("store", "store", "名", {})
    result = build_words_json([w], {})
    assert result["meta"]["created"] == date.today().isoformat()
