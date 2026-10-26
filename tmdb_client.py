import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

def fetch_trending_and_upcoming_hindi():
    """
    Fetch MOVIES only.
    TV series are intentionally excluded.
    Animation is excluded.
    """
    content = []

    today = datetime.now().date()
    future_bound = today + timedelta(days=60)
    past_bound = today - timedelta(days=365)

    movie_url = f"{BASE_URL}/discover/movie"

    # TMDB ranks movies by popularity. Fetching only page 1 eventually
    # leaves the Neon queue empty once popular movies have been posted.
    movie_params = {
        "api_key": TMDB_API_KEY,
        "primary_release_date.gte": str(past_bound),
        "primary_release_date.lte": str(future_bound),
        "sort_by": "popularity.desc",
        "without_genres": "16",
        "include_adult": "false"
    }

    seen_ids = set()
    max_pages = 5  # Fetch pages 1–5, not just page 1.
    successful_pages = 0

    for page in range(1, max_pages + 1):
        try:
            res = requests.get(
                movie_url,
                params={**movie_params, "page": page},
                timeout=20
            )
            res.raise_for_status()
            response = res.json()
            successful_pages += 1

            results = response.get("results", [])
            print(f"TMDB discovery: page {page} returned {len(results)} movies")

            for item in results:
                release_date = item.get("release_date")
                tmdb_id = item.get("id")

                if not release_date or tmdb_id is None or tmdb_id in seen_ids:
                    continue

                seen_ids.add(tmdb_id)
                content.append({
                    "tmdb_id": tmdb_id,
                    "title": item.get("title", "Unknown"),
                    "release_date": release_date
                })

            # Stop if there are no more movies or the API's last page is reached.
            if not results or page >= response.get("total_pages", max_pages):
                break

        except Exception as e:
            print(f"Error extracting Movies from TMDB on page {page}: {e}")
            # Keep movies fetched from earlier pages, if any.
            break

    print(f"TMDB discovery complete: {len(content)} unique movies from "
          f"{successful_pages} page(s)")

    return content

def get_movie_details(tmdb_id):
    """Fetch metadata for MOVIES only."""

    url = f"{BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY}

    try:
        res = requests.get(
            url,
            params=params,
            timeout=20
        )

        res.raise_for_status()
        data = res.json()

        genres = [
            g["name"]
            for g in data.get("genres", [])
        ]

        # Extra protection against animation
        if "Animation" in genres:
            return {
                "rejected": True,
                "reason": "animation"
            }

        release_date = data.get("release_date", "")

        return {
            "rejected": False,
            "title": data.get("title", "Unknown"),
            "year": release_date[:4] if release_date else "N/A",
            "rating": f"⭐ {data.get('vote_average', 0):.1f}/10",
            "genres": ", ".join(genres) if genres else "N/A",
            "summary": data.get(
                "overview",
                "No summary provided."
            ),
            "poster_url": (
                f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}"
                if data.get("poster_path")
                else None
            )
        }

    except Exception as e:
        print(f"TMDB error for ID {tmdb_id}: {e}")
        return None
