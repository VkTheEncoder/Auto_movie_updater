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

    movie_params = {
        "api_key": TMDB_API_KEY,
        "primary_release_date.gte": str(past_bound),
        "primary_release_date.lte": str(future_bound),
        "sort_by": "popularity.desc",
        "without_genres": "16",
        "include_adult": "false",
        "page": 1
    }

    try:
        res = requests.get(
            movie_url,
            params=movie_params,
            timeout=20
        )

        res.raise_for_status()
        response = res.json()

        for item in response.get("results", []):
            release_date = item.get("release_date")

            if not release_date:
                continue

            content.append({
                "tmdb_id": item["id"],
                "title": item.get("title", "Unknown"),
                "release_date": release_date
            })

    except Exception as e:
        print(f"Error extracting Movies from TMDB: {e}")

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
