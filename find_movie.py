import csv
import json
from pyarr import RadarrAPI
import time

# Configuration Radarr
host_url = "http://192.168.1.188:7878"
api_key = "f9bc647e11a64b4c8e313f177941eb68"
radarr = RadarrAPI(host_url, api_key)

def lookup_and_add_movie(titre, note_csv):
    """
    Recherche un film dans Radarr, récupère les notes et l'ajoute pour téléchargement
    """
    try:
        # Recherche du film
        results = radarr.lookup_movie(titre)
        
        if not results:
            print(f"❌ Film non trouvé : {titre}")
            return None
        
        movie = results[0]
        title = movie.get('title', 'Titre inconnu')
        
        # Récupération des notes
        ratings = movie.get('ratings', {})
        rating_values = {
            'csv': note_csv,
            'imdb': ratings.get('imdb', {}).get('value'),
            'tmdb': ratings.get('tmdb', {}).get('value'),
            'trakt': ratings.get('trakt', {}).get('value')
        }
        
        print(f"\n✅ Trouvé : {title}")
        print(f"   Notes : {rating_values}")
        
        # Récupération des profils de qualité
        quality_profiles = radarr.get_quality_profile()
        
        if not quality_profiles:
            print(f"⚠️  Aucun profil de qualité trouvé")
            return {
                'titre': title,
                'notes': rating_values,
                'added': False
            }
        
        # Chercher un profil HD (1080p de préférence)
        hd_profile = next(
            (p for p in quality_profiles if 'HD' in p['name'] and '1080p' in p['name']), 
            None
        )
        
        # Si pas de profil 1080p, chercher HD-720p
        if not hd_profile:
            hd_profile = next(
                (p for p in quality_profiles if 'HD' in p['name'] and '720p' in p['name']), 
                None
            )
        
        # Si toujours rien, prendre le premier profil
        if not hd_profile:
            hd_profile = quality_profiles[0]
            print(f"   ⚠️  Profil HD non trouvé, utilisation de '{hd_profile['name']}'")
        
        # Ajout du film avec la bonne syntaxe
        radarr.add_movie(
            movie=movie,
            root_dir="E:\\film_oral",
            quality_profile_id=hd_profile['id'],
            monitored=True,
            search_for_movie=True
        )
        
        print(f"   ➕ Ajouté à Radarr (Qualité: {hd_profile['name']})")
        
        return {
            'titre': title,
            'notes': rating_values,
            'added': True,
            'quality_profile': hd_profile['name']
        }
        
    except Exception as e:
        print(f"❌ Erreur pour {titre} : {str(e)}")
        return None

def process_csv(csv_file, output_json='films_notes.json'):
    """
    Traite le fichier CSV et génère le fichier JSON avec les notes
    """
    results = []
    
    print(f"📂 Lecture du fichier : {csv_file}\n")
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            titre = row['titre']
            note_csv = float(row['note']) if row['note'] else None
            
            result = lookup_and_add_movie(titre, note_csv)
            
            if result:
                results.append(result)
            
            # Pause pour éviter de surcharger l'API
            time.sleep(0.5)
    
    # Sauvegarde des résultats dans un JSON
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✨ Terminé ! {len(results)} films traités")
    print(f"📄 Résultats sauvegardés dans : {output_json}")
    
    # Statistiques
    added_count = sum(1 for r in results if r.get('added'))
    print(f"➕ Films ajoutés à Radarr : {added_count}/{len(results)}")

    time.sleep(60*15)

if __name__ == "__main__":
    # Nom de votre fichier CSV
    csv_file = "disney_movies.csv"
    
    # Lancement du traitement
    process_csv(csv_file)