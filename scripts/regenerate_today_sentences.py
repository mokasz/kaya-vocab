import os
import sys
import json

env_path = os.path.join(os.path.dirname(__file__), '.env.local')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v.strip('"\'')

from generate_words import get_gemini, replenish_sentences, get_supabase

def main():
    sb = get_supabase()
    client = get_gemini()
    
    with open("kaya-vocab/data/words.json") as f:
        data = json.load(f)
        words = data["words"]
        
    for w in words:
        word_key = w["id"]
        print(f"Deleting and regenerating sentences for {word_key}...")
        
        # Delete old sentences
        sb.table("word_sentences").delete().eq("word_key", word_key).execute()
        
        # Regenerate new sentences (this will call the new validation logic)
        try:
            replenish_sentences(sb, client, word_key, w["word"], w["japanese"], w["pos"])
        except Exception as e:
            print(f"Failed to replenish {word_key}: {e}")

if __name__ == "__main__":
    main()
