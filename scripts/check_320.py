import os
from supabase import create_client

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    sb = create_client(url, key)
    
    user_email = "kaya.zhu@icloud.com"
    users = sb.auth.admin.list_users()
    kaya = next((u for u in users if getattr(u, 'email', '') == user_email), None)
    
    # Check progress_sync for 3/20
    res = sb.table("progress_sync").select("word_key, last_studied").eq("user_id", kaya.id).eq("last_studied", "2026-03-20").execute()
    print(f"3/20 progress_sync count: {len(res.data)}")

if __name__ == "__main__":
    main()
