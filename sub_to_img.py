import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import timedelta
import cv2
from subliminal import download_best_subtitles, save_subtitles, scan_video
from babelfish import Language
import pysrt

def renommer_avec_mnamer(dossier):
    """Renomme les fichiers avec mnamer"""
    print("\n🎬 Étape 1: Renommage des films avec mnamer...\n")
    
    try:
        result = subprocess.run(
            ['mnamer', '-b', '-r', str(dossier)],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Renommage terminé avec succès")
        else:
            print(f"⚠️  Avertissement mnamer: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ Erreur: mnamer n'est pas installé")
        print("   Installez-le avec: pip install mnamer")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erreur lors du renommage: {e}")

def telecharger_sous_titres(dossier, langues=['eng']):
    """Télécharge les sous-titres pour tous les films du dossier"""
    print("\n📥 Étape 2: Téléchargement des sous-titres...\n")
    
    dossier = Path(dossier)
    extensions_video = {'.mp4', '.mkv', '.avi', '.mov', '.m4v'}
    languages = {Language(lang) for lang in langues}
    
    videos_traitees = 0
    sous_titres_telecharges = 0
    
    # Configurer les providers
    from subliminal.providers.opensubtitles import OpenSubtitlesProvider
    
    for fichier in dossier.rglob('*'):
        if fichier.suffix.lower() in extensions_video:
            print(f"📁 {fichier.name}")
            
            try:
                video = scan_video(str(fichier))
                print(f"   🔍 Détails vidéo: {video.title} ({video.year if hasattr(video, 'year') else 'N/A'})")
                
                # Essayer avec différents providers
                providers = ['opensubtitles', 'opensubtitlescom', 'podnapisi', 'tvsubtitles']
                
                subtitles = download_best_subtitles(
                    [video], 
                    languages,
                    hearing_impaired=False,
                    providers=providers
                )
                
                if subtitles[video]:
                    save_subtitles(video, subtitles[video])
                    nb_subs = len(subtitles[video])
                    print(f"   ✅ {nb_subs} sous-titre(s) téléchargé(s)")
                    sous_titres_telecharges += nb_subs
                else:
                    print(f"   ⚠️  Aucun sous-titre trouvé avec les providers")
                    print(f"   💡 Essayez manuellement sur https://www.opensubtitles.com")
                    print(f"   💡 Recherchez: {video.title} {getattr(video, 'year', '')}")
                
                videos_traitees += 1
                    
            except Exception as e:
                print(f"   ❌ Erreur: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"\n📊 Résumé: {videos_traitees} vidéos traitées, {sous_titres_telecharges} sous-titres téléchargés")

def timecode_to_seconds(timecode):
    """Convertit un timecode SubRip en secondes"""
    return timecode.hours * 3600 + timecode.minutes * 60 + timecode.seconds + timecode.milliseconds / 1000.0

def extraire_image(fichier_video, temps_secondes, fichier_sortie):
    """Extrait une image d'une vidéo à un temps précis"""
    if not os.path.exists(fichier_video):
        return None
    
    video = cv2.VideoCapture(fichier_video)
    if not video.isOpened():
        return None
    
    fps = video.get(cv2.CAP_PROP_FPS)
    numero_frame = int(temps_secondes * fps)
    
    video.set(cv2.CAP_PROP_POS_FRAMES, numero_frame)
    success, image = video.read()
    
    if not success:
        video.release()
        return None
    
    cv2.imwrite(fichier_sortie, image)
    video.release()
    return fichier_sortie

def analyser_sous_titres_et_extraire(dossier, intervalle_secondes=3):
    """Analyse les sous-titres et extrait les images selon les intervalles"""
    print(f"\n🖼️  Étape 3: Analyse des sous-titres et extraction d'images (intervalle: {intervalle_secondes}s)...\n")
    
    dossier = Path(dossier)
    extensions_video = {'.mp4', '.mkv', '.avi', '.mov', '.m4v'}
    extensions_sous_titres = {'.srt', '.sub', '.en.srt', '.eng.srt'}
    
    resultats_globaux = []
    
    for fichier_video in dossier.rglob('*'):
        if fichier_video.suffix.lower() not in extensions_video:
            continue
        
        print(f"\n📹 Traitement: {fichier_video.name}")
        
        # Chercher le fichier de sous-titres associé (plusieurs possibilités)
        fichier_srt = None
        base_name = fichier_video.stem
        
        # Liste de tous les fichiers .srt possibles
        patterns_possibles = [
            fichier_video.with_suffix('.srt'),           # Film.srt
            fichier_video.with_suffix('.en.srt'),        # Film.en.srt
            fichier_video.with_suffix('.eng.srt'),       # Film.eng.srt
            fichier_video.parent / f"{base_name}.en.srt",
            fichier_video.parent / f"{base_name}.eng.srt",
        ]
        
        # Chercher aussi tous les .srt dans le même dossier qui contiennent le nom du film
        for srt_file in fichier_video.parent.glob('*.srt'):
            if base_name in srt_file.stem:
                patterns_possibles.append(srt_file)
        
        # Vérifier tous les patterns possibles
        for possible_srt in patterns_possibles:
            if possible_srt.exists():
                fichier_srt = possible_srt
                print(f"   ✅ Sous-titres trouvés: {fichier_srt.name}")
                break
        
        if not fichier_srt:
            print(f"   ⚠️  Pas de sous-titres trouvés")
            print(f"   🔍 Fichiers .srt recherchés dans: {fichier_video.parent}")
            # Afficher tous les .srt du dossier pour debug
            srt_files = list(fichier_video.parent.glob('*.srt'))
            if srt_files:
                print(f"   📝 Fichiers .srt présents: {[f.name for f in srt_files]}")
            continue
        
        try:
            # Charger les sous-titres
            subs = pysrt.open(str(fichier_srt), encoding='utf-8')
            print(f"   📝 {len(subs)} sous-titres chargés")
            
            # Convertir tous les timecodes en secondes
            sous_titres_data = []
            for sub in subs:
                sous_titres_data.append({
                    'index': sub.index,
                    'start': timecode_to_seconds(sub.start),
                    'end': timecode_to_seconds(sub.end),
                    'text': sub.text.replace('\n', ' ')
                })
            
            # Regrouper par intervalles de X secondes
            intervalles = []
            if sous_titres_data:
                temps_debut_interval = 0
                
                while temps_debut_interval < sous_titres_data[-1]['end']:
                    temps_fin_interval = temps_debut_interval + intervalle_secondes
                    
                    # Trouver tous les sous-titres dans cet intervalle
                    subs_dans_intervalle = [
                        s for s in sous_titres_data 
                        if s['start'] >= temps_debut_interval and s['start'] < temps_fin_interval
                    ]
                    
                    if subs_dans_intervalle:
                        intervalles.append({
                            'intervalle_debut': temps_debut_interval,
                            'intervalle_fin': temps_fin_interval,
                            'premier_timecode': subs_dans_intervalle[0]['start'],
                            'sous_titres': subs_dans_intervalle
                        })
                    
                    temps_debut_interval = temps_fin_interval
            
            print(f"   📊 {len(intervalles)} intervalles de {intervalle_secondes}s créés")
            
            # Créer le dossier pour les images
            movie_id = fichier_video.stem
            dossier_images = Path("analyse") / "images" / movie_id
            dossier_images.mkdir(parents=True, exist_ok=True)
            
            # Extraire les images
            resultats_film = {
                'movie_id': movie_id,
                'movie_path': str(fichier_video),
                'subtitle_path': str(fichier_srt),
                'intervalle_secondes': intervalle_secondes,
                'intervalles': []
            }
            
            for idx, intervalle in enumerate(intervalles):
                temps_extraction = intervalle['premier_timecode']
                nom_image = f"interval_{idx:04d}_time_{temps_extraction:.2f}s.jpg"
                chemin_image = dossier_images / nom_image
                
                # Extraire l'image
                if extraire_image(str(fichier_video), temps_extraction, str(chemin_image)):
                    resultats_film['intervalles'].append({
                        'intervalle_index': idx,
                        'intervalle_debut': intervalle['intervalle_debut'],
                        'intervalle_fin': intervalle['intervalle_fin'],
                        'timecode_extraction': temps_extraction,
                        'image_path': str(chemin_image),
                        'nombre_sous_titres': len(intervalle['sous_titres']),
                        'sous_titres': intervalle['sous_titres']
                    })
            
            print(f"   ✅ {len(resultats_film['intervalles'])} images extraites")
            resultats_globaux.append(resultats_film)
            
        except Exception as e:
            print(f"   ❌ Erreur: {e}")
    
    # Sauvegarder le JSON global
    fichier_json = Path("analyse") / "analyse_films.json"
    with open(fichier_json, 'w', encoding='utf-8') as f:
        json.dump(resultats_globaux, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Données sauvegardées dans: {fichier_json}")
    return resultats_globaux

def main():
    """Fonction principale"""
    print("=" * 70)
    print("🎥 Renommage, sous-titres et extraction d'images basée sur intervalles")
    print("=" * 70)
    
    dossier = "movies"
    intervalle = 3
    
    renommer_avec_mnamer(dossier)
    telecharger_sous_titres(dossier, langues=['eng'])
    analyser_sous_titres_et_extraire(dossier, intervalle_secondes=intervalle)
    

if __name__ == "__main__":
    main()