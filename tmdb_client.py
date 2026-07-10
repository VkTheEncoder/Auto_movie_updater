import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

def fetch_trending_and_upcoming_hindi():
    """
    Discovers trending and upcoming content. Filters for native Hindi productions 
    or productions targeted heavily toward the regional language distribution track.
    """
    movies = []
    today = datetime.now().date()
    future_bound = today + timedelta(days=60)
    
    # Endpoint to discover Hindi movies (Original Language)
    url = f"{BASE_URL}/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "with_original_language": "hi",
        "primary_release_date.gte": today - timedelta(days=365),
        "primary_release_date.lte": future_bound,
        "sort_by": "popularity.desc"
    }
    
    try:
        response = requests.get(url, params=params).json()
        if "results" in response:
            for item in response["results"]:
                if item.get("release_date"):
                    movies.append({
                        "tmdb_id": item["id"],
                        "title": item["title"],
                        "release_date": item["release_date"]
                    })
    except Exception as e:
        print(f"Error extracting items from TMDB: {e}")
        
    return movies

def get_movie_details(tmdb_id):
    """Fetches full analytical payload needed to compile the final caption block."""
    url = f"{BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "append_to_response": "release_dates"}
    
    try:
        data = requests.get(url, params=params).json()
        genres = [g["name"] for g in data.get("genres", [])]
        
        return {
            "title": data.get("title"),
            "year": data.get("release_date", "N/A")[:4],
            "rating": f"⭐ {data.get('vote_average', 0):.1f}/10",
            "genres": ", ".join(genres) if genres else "N/A",
            "summary": data.get("overview", "No summary provided."),
            "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None
        }
    except Exception as e:
        print(f"Failed to fetch metadata execution profile for payload ID {tmdb_id}: {e}")
        return None
