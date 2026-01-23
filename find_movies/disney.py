import requests
import csv

# Configuration
API_KEY = "5c59bf579f40a813caf2e3874a5a8de8"  # Remplacez par votre clé API
BASE_URL = "https://api.themoviedb.org/3"


def get_disney_movies():
    """
    Récupère TOUS les films Disney depuis l'API TMDB
    
    Returns:
        Liste de tous les films Disney
    """
    all_movies = []
    
    # ID de la société de production Disney
    DISNEY_COMPANY_ID = 2  # Walt Disney Pictures
    
    current_page = 1
    total_pages = None
    
    while True:
        url = f"{BASE_URL}/discover/movie"
        
        params = {
            "api_key": API_KEY,
            "with_companies": DISNEY_COMPANY_ID,
            "sort_by": "popularity.desc",
            "page": current_page,
            "language": "fr-FR"
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Récupérer le nombre total de pages à la première requête
            if total_pages is None:
                total_pages = data.get("total_pages", 1)
                total_results = data.get("total_results", 0)
                print(f"Total de films Disney à récupérer: {total_results}")
                print(f"Nombre de pages: {total_pages}")
                print("-" * 80)
            
            movies = data.get("results", [])
            all_movies.extend(movies)
            
            print(f"Page {current_page}/{total_pages} récupérée - {len(movies)} films | Total: {len(all_movies)}")
            
            # Si on a récupéré toutes les pages disponibles
            if current_page >= total_pages:
                break
            
            current_page += 1
                
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la requête: {e}")
            break
    
    return all_movies

def save_to_csv(movies, filename="disney_movies.csv"):
    """
    Sauvegarde les films dans un fichier CSV avec les colonnes demandées
    """
    fieldnames = [
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
        
        for movie in movies:
            # Extraire l'année de la date de sortie
            date_sortie = movie.get('release_date', '')
            annee = date_sortie.split('-')[0] if date_sortie else ''
            
            row = {
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
    
    print(f"\n✓ {len(movies)} films sauvegardés dans {filename}")

def main():
    print("Récupération des films Disney depuis TMDB...")
    print("-" * 80)
    
    # Récupérer TOUS les films Disney
    movies = get_disney_movies()
    
    if movies:
        # Sauvegarder dans un fichier CSV
        save_to_csv(movies)
        
        # Statistiques
        print(f"\nStatistiques:")
        print(f"Total de films récupérés: {len(movies)}")
        if movies:
            avg_rating = sum(m.get("vote_average", 0) for m in movies) / len(movies)
            print(f"Note moyenne: {avg_rating:.2f}/10")
    else:
        print("Aucun film trouvé ou erreur lors de la récupération")

if __name__ == "__main__":
    main()