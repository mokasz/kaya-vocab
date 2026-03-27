import os
from supabase import create_client, Client

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SECRET_KEY")
        return

    sb = create_client(url, key)
    
    # query words table for yacht
    res = sb.table("words").select("*").eq("word", "yacht").execute()
    
    if res.data:
        print("Word data:")
        for w in res.data:
            print(w)
            
        # check if word_sentences has pos info
        word_ids = [w['id'] for w in res.data]
        res2 = sb.table("word_sentences").select("*").in_("word_id", word_ids).execute()
        if res2.data:
            print("\nWord_sentences data:")
            for ws in res2.data:
                print(ws)
    else:
        print("yacht not found in words table")

if __name__ == "__main__":
    main()
