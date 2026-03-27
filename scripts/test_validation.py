import os
import json
from google import genai
from generate_words import validate_sentence

def get_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    return genai.Client(api_key=api_key)

def test():
    client = get_gemini()
    
    cases = [
        # Nouns
        ("key", "名", "plural", "He keeps his keys in his bag.", False), # Should be ambiguous
        ("key", "名", "plural", "He keeps three keys in his bag.", True), # Should be valid
        ("apple", "名", "singular", "I eat an apple every day.", True), # Should be valid
        ("apple", "名", "singular", "I eat apple every day.", False), # Invalid (missing 'an')
        
        # Verbs
        ("play", "動", "third", "He plays soccer.", False), # Maybe ambiguous with 'played' or 'plays'?
        ("play", "動", "third", "He plays soccer every Sunday.", True), # Clearer
    ]
    
    for word, pos, form, sentence, expected_valid in cases:
        print(f"Testing: [{word}] ({form}) \"{sentence}\"")
        is_valid = validate_sentence(client, word, pos, form, sentence)
        status = "PASS" if is_valid == expected_valid else "FAIL"
        print(f"  Result: {'Valid' if is_valid else 'Ambiguous'}, Expected: {'Valid' if expected_valid else 'Ambiguous'} -> {status}")

if __name__ == "__main__":
    test()
