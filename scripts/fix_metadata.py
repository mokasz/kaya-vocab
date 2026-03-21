import os
from supabase import create_client

def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    
    updates = [
        {"word_key": "pharmacy", "metadata": {"plural": "pharmacies"}},
        {"word_key": "ink", "metadata": {"plural": "ink"}},
        {"word_key": "jam", "metadata": {"plural": "jam"}}
    ]
    
    for u in updates:
        sb.table("words").update({"metadata": u["metadata"]}).eq("word_key", u["word_key"]).execute()
        print(f"Updated metadata for {u['word_key']}")

if __name__ == "__main__":
    main()
