import os
import sys
from datetime import datetime, timedelta, timezone

# Manually load .env.local if available
env_path = os.path.join(os.path.dirname(__file__), '.env.local')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v.strip('"\'')

from supabase import create_client

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SECRET_KEY")
        return

    sb = create_client(url, key)
    
    # Get user
    user_email = "kaya.zhu@icloud.com"
    users = sb.auth.admin.list_users()
    kaya = next((u for u in users if getattr(u, 'email', '') == user_email), None)
    if not kaya:
        print(f"User {user_email} not found.")
        return
        
    # Japan Standard Time (UTC+9)
    jst = timezone(timedelta(hours=9))
    target_start = datetime(2026, 3, 23, 0, 0, 0, tzinfo=jst)
    target_end = datetime(2026, 3, 23, 23, 59, 59, tzinfo=jst)

    # Fetch logs
    res = (sb.table("review_log")
           .select("word_key, rating, reviewed_at")
           .eq("user_id", kaya.id)
           .eq("book_key", "kaya-stage1")
           .execute())
           
    if not res.data:
        print("No study records found.")
        return

    logs = res.data
    
    # Filter logs for JST March 23
    target_logs = []
    for log in logs:
        reviewed_at = log['reviewed_at']
        if reviewed_at.endswith('Z'):
            reviewed_at = reviewed_at.replace('Z', '+00:00')
        elif '+' not in reviewed_at and '-' not in reviewed_at[10:]:
            reviewed_at += '+00:00'
            
        dt = datetime.fromisoformat(reviewed_at)
        dt_jst = dt.astimezone(jst)
        if target_start <= dt_jst <= target_end:
            target_logs.append((dt_jst, log))
            
    if not target_logs:
        print("No study records found for 3/23.")
        return
        
    word_keys = list(set(log['word_key'] for _, log in target_logs))
    
    # Fetch word details
    words_res = (sb.table("words")
                 .select("word_key, word")
                 .in_("word_key", word_keys)
                 .execute())
    
    word_map = {w['word_key']: w['word'] for w in words_res.data} if words_res.data else {}
    
    # Aggregate results
    stats = {}
    for dt, log in target_logs:
        wk = log['word_key']
        if wk not in stats:
            stats[wk] = {'correct': 0, 'incorrect': 0}
            
        rating = log['rating']
        if rating == 4:
            stats[wk]['correct'] += 1
        else: # 1, 2, 3
            stats[wk]['incorrect'] += 1
            
    print(f"Kaya ({user_email}) - 3/23 学習結果まとめ")
    print("-" * 65)
    print(f"{'単語':<25} | {'正解回数':<8} | {'誤解回数':<8} | {'合計回答':<8}")
    print("-" * 65)
    
    for wk, stat in sorted(stats.items(), key=lambda x: word_map.get(x[0], x[0])):
        word_str = word_map.get(wk, wk)
        total = stat['correct'] + stat['incorrect']
        print(f"{word_str:<25} | {stat['correct']:<12} | {stat['incorrect']:<12} | {total:<8}")

if __name__ == "__main__":
    main()
