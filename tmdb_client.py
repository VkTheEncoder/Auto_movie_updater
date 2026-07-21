import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

def fetch_trending_and_upcoming_hindi():
    """
    Discovers trending and upcoming content across all regions (Hollywood, Tollywood, etc.)
    that have a verified Hindi audio track. Fetches both Movies and TV Series.
    """
    content = []
    today = datetime.now().date()
    future_bound = today + timedelta(days=60)
    past_bound = today - timedelta(days=365)
    
    # --- 1. FETCH MOVIES (All Regions, Hindi Dub/Audio) ---
    movie_url = f"{BASE_URL}/discover/movie"
    movie_params = {
        "api_key": TMDB_API_KEY,
        "with_spoken_languages": "hi", # CRITICAL: This grabs dubbed content globally
        "primary_release_date.gte": past_bound,
        "primary_release_date.lte": future_bound,
        "sort_by": "popularity.desc"
    }
    
    try:
        response = requests.get(movie_url, params=movie_params).json()
        for item in response.get("results", []):
            if item.get("release_date"):
                content.append({
                    "tmdb_id": item["id"], # Positive ID for movies
                    "title": item["title"],
                    "release_date": item["release_date"]
                })
    except Exception as e:
        print(f"Error extracting Movies from TMDB: {e}")

    # --- 2. FETCH TV SERIES (All Regions, Hindi Dub/Audio) ---
    tv_url = f"{BASE_URL}/discover/tv"
    tv_params = {
        "api_key": TMDB_API_KEY,
        "with_spoken_languages": "hi", # CRITICAL: Grabs dubbed TV shows
        "first_air_date.gte": past_bound,
        "first_air_date.lte": future_bound,
        "sort_by": "popularity.desc"
    }
    
    try:
        response = requests.get(tv_url, params=tv_params).json()
        for item in response.get("results", []):
            if item.get("first_air_date"):
                content.append({
                    "tmdb_id": -item["id"], # NEGATIVE ID to prevent clashing with movie IDs
                    "title": item["name"], # TV shows use 'name' instead of 'title'
                    "release_date": item["first_air_date"]
                })
    except Exception as e:
        print(f"Error extracting TV Series from TMDB: {e}")
        
    return content

def get_movie_details(tmdb_id):
    """Fetches full analytical payload. Uses positive/negative logic to identify if Movie or TV."""
    is_tv = tmdb_id < 0
    real_id = abs(tmdb_id)
    
    url = f"{BASE_URL}/tv/{real_id}" if is_tv else f"{BASE_URL}/movie/{real_id}"
    params = {"api_key": TMDB_API_KEY}
    
    try:
        data = requests.get(url, params=params).json()
        genres = [g["name"] for g in data.get("genres", [])]
        
        # Handle the naming differences between TV and Movies APIs
        title = data.get("name") if is_tv else data.get("title")
        release_date = data.get("first_air_date", "N/A") if is_tv else data.get("release_date", "N/A")
        
        return {
            "title": title,
            "year": release_date[:4] if release_date else "N/A",
            "rating": f"⭐ {data.get('vote_average', 0):.1f}/10",
            "genres": ", ".join(genres) if genres else "N/A",
            "summary": data.get("overview", "No summary provided."),
            "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None
        }
    except Exception as e:
        print(f"Failed to fetch metadata for ID {real_id}: {e}")
        return None
