import requests
import csv

# Configuration
API_KEY = "5c59bf579f40a813caf2e3874a5a8de8"  # Remplacez par votre clé API
BASE_URL = "https://api.themoviedb.org/3"


def get_popular_movies():
    """
    Récupère les 1500 films les plus populaires (tous studios) depuis l'API TMDB
    
    Returns:
        Liste des 1500 films les plus populaires
    """
    all_movies = []
    
    # 1500 films = 75 pages (20 films par page)
    max_movies = 1500
    max_pages = (max_movies // 20) + 1  # 75 pages
    
    current_page = 1
    
    print(f"Récupération des {max_movies} films les plus populaires au box office")
    print("-" * 80)
    
    while current_page <= max_pages and len(all_movies) < max_movies:
        url = f"{BASE_URL}/discover/movie"
        
        params = {
            "api_key": API_KEY,
            "sort_by": "revenue.desc",  # Tri par revenus au box office
            "page": current_page,
            "language": "fr-FR"
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            movies = data.get("results", [])
            all_movies.extend(movies)
            
            print(f"Page {current_page}/{max_pages} récupérée - {len(movies)} films | Total: {len(all_movies)}")
            
            # Si on a atteint ou dépassé 1500 films
            if len(all_movies) >= max_movies:
                all_movies = all_movies[:max_movies]  # Limiter à exactement 1500
                break
            
            current_page += 1
                
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la requête: {e}")
            break
    
    return all_movies

def save_to_csv(movies, filename="top_1500_movies.csv"):
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
    print("Récupération des films les plus populaires au box office depuis TMDB...")
    print("-" * 80)
    
    # Récupérer les 1500 films les plus populaires au box office
    movies = get_popular_movies()
    
    if movies:
        # Sauvegarder dans un fichier CSV
        save_to_csv(movies, filename="top_1500_movies.csv")
        
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