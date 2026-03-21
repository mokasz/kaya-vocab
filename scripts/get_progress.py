import os
import sys
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
        return

    sb = create_client(url, key)
    
    # Get user
    user_email = "kaya.zhu@icloud.com"
    users = sb.auth.admin.list_users()
    kaya = next((u for u in users if getattr(u, 'email', '') == user_email), None)
    if not kaya:
        print(f"User {user_email} not found.")
        return
        
    print(f"User ID: {kaya.id}")
    
    # Japan Standard Time (UTC+9)
    jst = timezone(timedelta(hours=9))
    target_start = datetime(2026, 3, 21, 0, 0, 0, tzinfo=jst)
    target_end = datetime(2026, 3, 21, 23, 59, 59, tzinfo=jst)

    res = (sb.table("review_log")
           .select("word_key, rating, reviewed_at")
           .eq("user_id", kaya.id)
           .eq("book_key", "kaya-stage1")
           .execute())
           
    logs = res.data
    
    # Filter logs for JST March 21
    target_logs = []
    for log in logs:
        # reviewed_at is like '2026-03-21T02:14:02.123+00:00'
        dt = datetime.fromisoformat(log['reviewed_at'].replace('Z', '+00:00'))
        dt_jst = dt.astimezone(jst)
        if target_start <= dt_jst <= target_end:
            target_logs.append((dt_jst, log))

    target_logs.sort(key=lambda x: x[0])
    
    if not target_logs:
        print("No study records found for 3/21.")
        return
        
    word_keys = list(set(log['word_key'] for _, log in target_logs))
    
    # Fetch word details
    words_res = (sb.table("words")
                 .select("word_key, word")
                 .in_("word_key", word_keys)
                 .execute())
    
    word_map = {w['word_key']: w['word'] for w in words_res.data}
    
    print(f"\nStudy records for {user_email} on 2026-03-21 (JST):")
    for dt_jst, log in target_logs:
        word_str = word_map.get(log['word_key'], log['word_key'])
        print(f"[{dt_jst.strftime('%H:%M:%S')}] Word: {word_str} (Key: {log['word_key']}) - Rating: {log['rating']}")

if __name__ == "__main__":
    main()
