import os
from datetime import datetime, timedelta, timezone
from supabase import create_client

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
    
    # 1. Update progress_sync
    # We only update rows where last_studied is '2026-03-21' for kaya
    print("Updating progress_sync...")
    res_progress = (sb.table("progress_sync")
                    .select("word_key, last_studied")
                    .eq("user_id", kaya.id)
                    .eq("book_key", "kaya-stage1")
                    .eq("last_studied", "2026-03-21")
                    .execute())
                    
    progress_data = res_progress.data
    print(f"Found {len(progress_data)} rows in progress_sync to update.")
    
    for row in progress_data:
        sb.table("progress_sync").update({"last_studied": "2026-03-20"}).eq("user_id", kaya.id).eq("book_key", "kaya-stage1").eq("word_key", row["word_key"]).execute()
        
    print("progress_sync updated.")

    # 2. Update review_log
    jst = timezone(timedelta(hours=9))
    target_start = datetime(2026, 3, 21, 0, 0, 0, tzinfo=jst)
    target_end = datetime(2026, 3, 21, 23, 59, 59, tzinfo=jst)
    
    print("Updating review_log...")
    res_log = (sb.table("review_log")
               .select("id, reviewed_at")
               .eq("user_id", kaya.id)
               .eq("book_key", "kaya-stage1")
               .execute())
               
    log_data = res_log.data
    logs_to_update = []
    
    for row in log_data:
        dt = datetime.fromisoformat(row['reviewed_at'].replace('Z', '+00:00'))
        dt_jst = dt.astimezone(jst)
        if target_start <= dt_jst <= target_end:
            # Subtract 24 hours
            new_dt_jst = dt_jst - timedelta(days=1)
            # Format to ISO string for Supabase
            new_reviewed_at = new_dt_jst.isoformat()
            logs_to_update.append({"id": row["id"], "reviewed_at": new_reviewed_at})
            
    print(f"Found {len(logs_to_update)} rows in review_log to update.")
    
    for update_data in logs_to_update:
        sb.table("review_log").update({"reviewed_at": update_data["reviewed_at"]}).eq("id", update_data["id"]).execute()
        
    print("review_log updated.")
    print("Done!")

if __name__ == "__main__":
    main()
