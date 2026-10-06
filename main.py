import os
import time
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytz

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
        f"🎥 **Name:** {details['title']}\n"
        f"📅 **Release Year:** {details['year']}\n"
        f"🎭 **Genre:** {details['genres']}\n"
        f"🌟 **Rating:** {details['rating']}\n"
        f"🌐 **Language:** Hindi Dubbed / Audio\n\n"
        f"📝 **Summary:**\n{details['summary']}\n\n"
        f"**Download Link :- [Search](https://t.me/movie_request_group_033)**"
    )
    return caption

def send_to_telegram(photo_url, caption):
    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendPhoto"
    )

    payload = {
        "chat_id": CHANNEL_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "Markdown"
    }

    try:
        res = requests.post(
            url,
            json=payload,
            timeout=30
        )

        if res.status_code != 200:
            print(
                f"Telegram API failed "
                f"[{res.status_code}]: "
                f"{res.text}"
            )
            return False

        return True

    except Exception as e:
        print(
            f"Telegram request failed: {e}"
        )
        return False

def daily_job():
    print(f"[{datetime.now()}] Step 1: Querying TMDB for updates...")
    discovered_movies = tmdb.fetch_trending_and_upcoming_hindi()
    
    for movie in discovered_movies:
        db.insert_new_movie(movie["tmdb_id"], movie["title"], movie["release_date"])
        
    print(f"[{datetime.now()}] Step 2: Extracting top 1 priority item for this time slot...")
    
    # 🔴 CHANGE HERE: Change limit to 1 so it only sends one post at a time
        print(
        f"[{datetime.now()}] Step 2: "
        "Searching queue for one valid movie..."
    )

    queue = db.get_priority_queue(limit=50)

    if not queue:
        print("No pending candidate found.")
        return


    for target in queue:

        print(
            f"Checking candidate: "
            f"{target['title']} "
            f"(TMDB {target['tmdb_id']})"
        )

        details = tmdb.get_movie_details(
            target["tmdb_id"]
        )

        # IMPORTANT:
        # API failure should NOT modify database status
        if details is None:
            print(
                f"Temporary metadata/API failure for "
                f"{target['title']}. Leaving it pending."
            )
            continue

        # Real rejection
        if details.get("rejected"):
            reason = details.get(
                "reason",
                "unknown"
            )

            print(
                f"Rejecting {target['title']}: "
                f"{reason}"
            )

            db.reject_movie(
                target["tmdb_id"],
                reason
            )

            continue

        # Missing poster
        if not details.get("poster_url"):

            print(
                f"Rejecting {target['title']}: "
                "missing poster"
            )

            db.reject_movie(
                target["tmdb_id"],
                "missing_poster"
            )

            continue


        caption = build_caption(
            details,
            target["type"]
        )

        print(
            f"Sending Telegram post: "
            f"{target['title']}"
        )

        success = send_to_telegram(
            details["poster_url"],
            caption
        )

        if success:

            column_triggered = (
                "posted_released"
                if target["type"] == "RELEASED"
                else "posted_7_days"
            )

            db.update_post_status(
                target["tmdb_id"],
                column_triggered
            )

            print(
                f"SUCCESS: {target['title']}"
            )

            # VERY IMPORTANT:
            # only one post per scheduled run
            break

        else:
            print(
                f"Telegram send failed for "
                f"{target['title']}. "
                "Database status NOT changed."
            )
    
    if not queue:
        print("No matches detected in priority queue matrix for this time slot.")
        return

    for target in queue:
        details = tmdb.get_movie_details(target["tmdb_id"])
        if not details or not details["poster_url"]:
            continue
            
        caption = build_caption(details, target["type"])
        
        print(f"Sending message block for: {target['title']} ({target['type']})")
        success = send_to_telegram(details["poster_url"], caption)
        
        if success:
            column_triggered = "posted_released" if target["type"] == "RELEASED" else "posted_7_days"
            db.update_post_status(target["tmdb_id"], column_triggered)
            print(f"Success! Database tracker flag '{column_triggered}' updated.")


# --- DUMMY WEB SERVER TO SATISFY RENDER & UPTIMEROBOT ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        # This answers UptimeRobot's ping successfully
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def do_GET(self):
        # This answers normal web browser visits
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def keep_alive():
    # Render assigns a dynamic port via the PORT environment variable
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
# ------------------------------------------

if __name__ == "__main__":
    print("Automation application execution engine initialized safely.")
    
    keep_alive() # Your fake web server for Render
    
    # 🔴 CHANGE HERE: Force the scheduler to strictly use Indian Standard Time
    ist_timezone = pytz.timezone('Asia/Kolkata')
    scheduler = BlockingScheduler(timezone=ist_timezone)
    
    # The cron job will now trigger at 9 AM, 2 PM, and 6 PM IST regardless of the server's clock
    scheduler.add_job(daily_job, 'cron', hour='9,14,18', minute=0)
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Shutdown intercept registered.")
