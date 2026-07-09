import os
import time
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
import requests

import database as db
import tmdb_client as tmdb

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
POST_LIMIT = int(os.getenv("POSTS_PER_DAY", 3))

def build_caption(details, post_type):
    """Formats raw metadata into a clean, presentation-ready string layout."""
    header = "🚨 COMING SOON IN 7 DAYS! 🚨" if post_type == "COMING_SOON" else "🎬 NOW RELEASED / AVAILABLE 🎬"
    
    caption = (
        f"{header}\n\n"
        f"🎥 **Movie Name:** {details['title']}\n"
        f"📅 **Release Year:** {details['year']}\n"
        f"🎭 **Genre:** {details['genres']}\n"
        f"🌟 **Rating:** {details['rating']}\n"
        f"🌐 **Language:** Hindi Dubbed / Audio\n\n"
        f"📝 **Summary:**\n{details['summary']}"
    )
    return caption

def send_to_telegram(photo_url, caption):
    """Dispatches the complete image and formatted caption directly to the channel via Telegram API."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": CHANNEL_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload)
        return res.status_code == 200
    except Exception as e:
        print(f"Failed to cleanly broadcast message package to API stack: {e}")
        return False

def daily_job():
    print(f"[{datetime.now()}] Step 1: Querying TMDB for updates...")
    discovered_movies = tmdb.fetch_trending_and_upcoming_hindi()
    
    # Store new content strings cleanly inside our tracker
    for movie in discovered_movies:
        db.insert_new_movie(movie["tmdb_id"], movie["title"], movie["release_date"])
        
    print(f"[{datetime.now()}] Step 2: Extracting items matching priority state constraints...")
    queue = db.get_priority_queue(limit=POST_LIMIT)
    
    if not queue:
        print("No matches detected in priority queue matrix for today.")
        return

    for target in queue:
        details = tmdb.get_movie_details(target["tmdb_id"])
        if not details or not details["poster_url"]:
            continue
            
        caption = build_caption(details, target["type"])
        
        print(f"Sending message block for: {target['title']} ({target['type']})")
        success = send_to_telegram(details["poster_url"], caption)
        
        if success:
            # Shift the database logic column to true based on identity rule flag
            column_triggered = "posted_released" if target["type"] == "RELEASED" else "posted_7_days"
            db.update_post_status(target["tmdb_id"], column_triggered)
            print(f"Success! Database tracker flag '{column_triggered}' updated.")
        
        # Avoid flood limits on sudden multiple updates
        time.sleep(5)

if __name__ == "__main__":
    print("Automation application execution engine initialized safely.")
    
    # Setup scheduler to execute daily at a designated point in time
    scheduler = BlockingScheduler()
    scheduler.add_job(daily_job, 'cron', hour=9, minute=0) # Runs daily at 09:00 AM
    
    # Optional: Run immediately on launch once to verify everything functions
    daily_job()
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Shutdown intercept registered.")
