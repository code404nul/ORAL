import requests
import csv
import time

# Configuration
API_KEY = "5c59bf579f40a813caf2e3874a5a8de8"
BASE_URL = "https://api.themoviedb.org/3"

def get_all_genres():
    """
    Récupère la liste complète des genres de films depuis TMDB
    
    Returns:
        Liste des genres avec leur ID et nom
    """
    url = f"{BASE_URL}/genre/movie/list"
    params = {
        "api_key": API_KEY,
        "language": "fr-FR"
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("genres", [])
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération des genres: {e}")
        return []

def get_top_movies_by_genre(genre_id, genre_name, top_n=50):
    """
    Récupère les N films les plus populaires d'un genre spécifique
    
    Args:
        genre_id: ID du genre
        genre_name: Nom du genre
        top_n: Nombre de films à récupérer (par défaut 50)
    
    Returns:
        Liste des films du genre
    """
    movies = []
    pages_needed = (top_n // 20) + 1  # 20 films par page
    
    print(f"\nRécupération des {top_n} films les plus populaires - Genre: {genre_name}")
    print("-" * 80)
    
    for page in range(1, pages_needed + 1):
        if len(movies) >= top_n:
            break
            
        url = f"{BASE_URL}/discover/movie"
        params = {
            "api_key": API_KEY,
            "with_genres": genre_id,
            "sort_by": "popularity.desc",  # Tri par popularité
            "page": page,
            "language": "fr-FR",
            "include_adult": "false"
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            page_movies = data.get("results", [])
            
            # Ajouter le nom du genre à chaque film
            for movie in page_movies:
                movie['genre_principal'] = genre_name
                movie['genre_id'] = genre_id
            
            movies.extend(page_movies)
            print(f"  Page {page}/{pages_needed} - {len(page_movies)} films | Total: {len(movies)}")
            
            # Pause pour respecter les limites de l'API
            time.sleep(0.25)
            
        except requests.exceptions.RequestException as e:
            print(f"  Erreur lors de la requête pour {genre_name}, page {page}: {e}")
            break
    
    # Limiter au nombre demandé
    return movies[:top_n]

def save_to_csv(all_movies, filename="top_50_movies_par_genre.csv"):
    """
    Sauvegarde tous les films dans un fichier CSV
    """
    fieldnames = [
        'genre_principal',
        'genre_id',
        'id',
        'titre',
        'titre_original',
        'annee',
        'date_sortie',
        'note',
        'nombre_votes',
        'popularite',
        'langue_originale',
        'synopsis',
        'adulte'
    ]
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for movie in all_movies:
            # Extraire l'année de la date de sortie
            date_sortie = movie.get('release_date', '')
            annee = date_sortie.split('-')[0] if date_sortie else ''
            
            row = {
                'genre_principal': movie.get('genre_principal', ''),
                'genre_id': movie.get('genre_id', ''),
                'id': movie.get('id', ''),
                'titre': movie.get('title', ''),
                'titre_original': movie.get('original_title', ''),
                'annee': annee,
                'date_sortie': date_sortie,
                'note': movie.get('vote_average', ''),
                'nombre_votes': movie.get('vote_count', ''),
                'popularite': movie.get('popularity', ''),
                'langue_originale': movie.get('original_language', ''),
                'synopsis': movie.get('overview', ''),
                'adulte': movie.get('adult', False)
            }
            
            writer.writerow(row)
    
    print(f"\n✓ {len(all_movies)} films sauvegardés dans {filename}")

def main():
    print("=" * 80)
    print("Récupération des TOP 50 films les plus populaires PAR GENRE depuis TMDB")
    print("=" * 80)
    
    # Récupérer tous les genres
    genres = get_all_genres()
    
    if not genres:
        print("Impossible de récupérer la liste des genres")
        return
    
    print(f"\n{len(genres)} genres trouvés:")
    for genre in genres:
        print(f"  - {genre['name']} (ID: {genre['id']})")
    
    # Récupérer les 50 films les plus populaires pour chaque genre
    all_movies = []
    genre_stats = {}
    
    for genre in genres:
        genre_id = genre['id']
        genre_name = genre['name']
        
        movies = get_top_movies_by_genre(genre_id, genre_name, top_n=50)
        all_movies.extend(movies)
        genre_stats[genre_name] = len(movies)
    
    # Sauvegarder dans un fichier CSV
    if all_movies:
        save_to_csv(all_movies, filename="top_50_movies_par_genre.csv")
        
        # Statistiques finales
        print("\n" + "=" * 80)
        print("STATISTIQUES FINALES")
        print("=" * 80)
        print(f"Total de films récupérés: {len(all_movies)}")
        print(f"Nombre de genres traités: {len(genre_stats)}")
        print("\nRépartition par genre:")
        for genre_name, count in sorted(genre_stats.items()):
            print(f"  {genre_name}: {count} films")
        
        if all_movies:
            avg_rating = sum(m.get("vote_average", 0) for m in all_movies) / len(all_movies)
            print(f"\nNote moyenne globale: {avg_rating:.2f}/10")
    else:
        print("\nAucun film trouvé")

if __name__ == "__main__":
    main()