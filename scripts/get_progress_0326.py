import os
import sys
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SECRET_KEY")
        return

    sb = create_client(url, key)
    
    user_email = "kaya.zhu@icloud.com"
    
    try:
        users_response = sb.auth.admin.list_users()
        users = users_response
    except Exception as e:
        print(f"Error getting users: {e}")
        return
        
    kaya = next((u for u in users if getattr(u, 'email', '') == user_email), None)
    if not kaya:
        print(f"User {user_email} not found.")
        return
        
    jst = timezone(timedelta(hours=9))
    target_start = datetime(2026, 3, 26, 0, 0, 0, tzinfo=jst)
    target_end = datetime(2026, 3, 26, 23, 59, 59, tzinfo=jst)

    res = (sb.table("review_log")
           .select("word_key, rating, reviewed_at")
           .eq("user_id", kaya.id)
           .execute())
           
    logs = res.data
    
    target_logs = []
    for log in logs:
        try:
            dt = datetime.fromisoformat(log['reviewed_at'].replace('Z', '+00:00'))
            dt_jst = dt.astimezone(jst)
            if target_start <= dt_jst <= target_end:
                target_logs.append((dt_jst, log))
        except Exception:
            pass

    target_logs.sort(key=lambda x: x[0])
    
    if not target_logs:
        print("No study records found for 3/26.")
        return
        
    word_keys = list(set(log['word_key'] for _, log in target_logs))
    
    words_res = (sb.table("words")
                 .select("word_key, word")
                 .in_("word_key", word_keys)
                 .execute())
    
    word_map = {w['word_key']: w['word'] for w in words_res.data}
    
    word_history = {}
    for dt_jst, log in target_logs:
        wk = log['word_key']
        if wk not in word_history:
            word_history[wk] = []
        word_history[wk].append((dt_jst, log['rating']))

    print(f"\nStudy records for {user_email} on 2026-03-26 (JST):")
    print("-" * 50)
    
    total_words = len(word_history)
    print(f"Total unique words studied: {total_words}\n")
    
    for wk, history in word_history.items():
        word_str = word_map.get(wk, wk)
        history_str = " -> ".join([f"Rating {r} ({dt.strftime('%H:%M:%S')})" for dt, r in history])
        
        success_count = sum(1 for _, r in history if r >= 3)
        fail_count = sum(1 for _, r in history if r < 3)
        
        print(f"Word: {word_str}")
        print(f"  History: {history_str}")
        print(f"  Summary: {success_count} Successes, {fail_count} Failures / Hard")
        print()

if __name__ == "__main__":
    main()
