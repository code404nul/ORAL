#!/usr/bin/env python3
"""
Script complet: renommage, sous-titres et extraction d'images
Usage: python script.py /chemin/vers/dossier/films
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import cv2
from subliminal import download_best_subtitles, save_subtitles, scan_video
from babelfish import Language
import pysrt


class SubtitleInterval:
    """Représente un intervalle de sous-titres"""
    
    def __init__(self, index: int, debut: float, fin: float, premier_timecode: float):
        self.index = index
        self.debut = debut
        self.fin = fin
        self.premier_timecode = premier_timecode
        self.sous_titres = []
        self.image_path = None
    
    def ajouter_sous_titre(self, index: int, start: float, end: float, text: str):
        """Ajoute un sous-titre à l'intervalle"""
        self.sous_titres.append({
            'index': index,
            'start': start,
            'end': end,
            'text': text
        })
    
    def to_dict(self) -> Dict:
        """Convertit l'intervalle en dictionnaire"""
        return {
            'intervalle_index': self.index,
            'intervalle_debut': self.debut,
            'intervalle_fin': self.fin,
            'timecode_extraction': self.premier_timecode,
            'image_path': self.image_path,
            'nombre_sous_titres': len(self.sous_titres),
            'sous_titres': self.sous_titres
        }


class Movie:
    """Représente un film avec ses métadonnées"""
    
    def __init__(self, video_path: Path):
        self.video_path = video_path
        self.movie_id = video_path.stem
        self.subtitle_path = None
        self.intervalles: List[SubtitleInterval] = []
        self.intervalle_secondes = 3
        self.dossier_images = None
        self.date_traitement = None
    
    def definir_sous_titres(self, subtitle_path: Path):
        """Définit le chemin des sous-titres"""
        self.subtitle_path = subtitle_path
    
    def creer_dossier_images(self, base_dir: Path = Path("analyse/images")):
        """Crée le dossier pour les images"""
        self.dossier_images = base_dir / self.movie_id
        self.dossier_images.mkdir(parents=True, exist_ok=True)
        return self.dossier_images
    
    def analyser_sous_titres(self, intervalle_secondes: int = 3):
        """Analyse les sous-titres et crée les intervalles"""
        self.intervalle_secondes = intervalle_secondes
        self.date_traitement = datetime.now().isoformat()
        
        if not self.subtitle_path or not self.subtitle_path.exists():
            raise FileNotFoundError(f"Fichier de sous-titres introuvable: {self.subtitle_path}")
        
        # Charger les sous-titres
        subs = pysrt.open(str(self.subtitle_path), encoding='utf-8')
        
        # Convertir en données structurées
        sous_titres_data = []
        for sub in subs:
            sous_titres_data.append({
                'index': sub.index,
                'start': self._timecode_to_seconds(sub.start),
                'end': self._timecode_to_seconds(sub.end),
                'text': sub.text.replace('\n', ' ')
            })
        
        if not sous_titres_data:
            return
        
        # Créer les intervalles
        temps_debut = 0
        index_intervalle = 0
        
        while temps_debut < sous_titres_data[-1]['end']:
            temps_fin = temps_debut + intervalle_secondes
            
            # Trouver les sous-titres dans cet intervalle
            subs_dans_intervalle = [
                s for s in sous_titres_data 
                if s['start'] >= temps_debut and s['start'] < temps_fin
            ]
            
            if subs_dans_intervalle:
                intervalle = SubtitleInterval(
                    index=index_intervalle,
                    debut=temps_debut,
                    fin=temps_fin,
                    premier_timecode=subs_dans_intervalle[0]['start']
                )
                
                for sub in subs_dans_intervalle:
                    intervalle.ajouter_sous_titre(
                        sub['index'], sub['start'], sub['end'], sub['text']
                    )
                
                self.intervalles.append(intervalle)
                index_intervalle += 1
            
            temps_debut = temps_fin
    
    def extraire_images(self):
        """Extrait les images pour tous les intervalles"""
        if not self.dossier_images:
            self.creer_dossier_images()
        
        video = cv2.VideoCapture(str(self.video_path))
        if not video.isOpened():
            raise Exception(f"Impossible d'ouvrir la vidéo: {self.video_path}")
        
        fps = video.get(cv2.CAP_PROP_FPS)
        
        for intervalle in self.intervalles:
            temps = intervalle.premier_timecode
            numero_frame = int(temps * fps)
            
            video.set(cv2.CAP_PROP_POS_FRAMES, numero_frame)
            success, image = video.read()
            
            if success:
                nom_image = f"interval_{intervalle.index:04d}_time_{temps:.2f}s.jpg"
                chemin_image = self.dossier_images / nom_image
                cv2.imwrite(str(chemin_image), image)
                intervalle.image_path = str(chemin_image)
        
        video.release()
    
    def sauvegarder_json(self, base_dir: Path = Path("analyse/json")):
        """Sauvegarde les données du film en JSON"""
        base_dir.mkdir(parents=True, exist_ok=True)
        fichier_json = base_dir / f"{self.movie_id}.json"
        
        data = {
            'movie_id': self.movie_id,
            'movie_path': str(self.video_path),
            'subtitle_path': str(self.subtitle_path) if self.subtitle_path else None,
            'intervalle_secondes': self.intervalle_secondes,
            'nombre_intervalles': len(self.intervalles),
            'dossier_images': str(self.dossier_images) if self.dossier_images else None,
            'date_traitement': self.date_traitement,
            'intervalles': [intervalle.to_dict() for intervalle in self.intervalles]
        }
        
        with open(fichier_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return fichier_json
    
    @staticmethod
    def _timecode_to_seconds(timecode) -> float:
        """Convertit un timecode SubRip en secondes"""
        return (timecode.hours * 3600 + 
                timecode.minutes * 60 + 
                timecode.seconds + 
                timecode.milliseconds / 1000.0)
    
    def to_dict(self) -> Dict:
        """Convertit le film en dictionnaire"""
        return {
            'movie_id': self.movie_id,
            'movie_path': str(self.video_path),
            'subtitle_path': str(self.subtitle_path) if self.subtitle_path else None,
            'intervalle_secondes': self.intervalle_secondes,
            'nombre_intervalles': len(self.intervalles),
            'dossier_images': str(self.dossier_images) if self.dossier_images else None
        }


class MovieProcessor:
    """Gestionnaire principal du traitement des films"""
    
    EXTENSIONS_VIDEO = {'.mp4', '.mkv', '.avi', '.mov', '.m4v'}
    
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.films: List[Movie] = []
    
    def renommer_avec_mnamer(self):
        """Renomme les fichiers avec mnamer"""
        print("\n🎬 Étape 1: Renommage des films avec mnamer...\n")
        
        try:
            result = subprocess.run(
                ['mnamer', '-b', '-r', str(self.dossier)],
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
    
    def telecharger_sous_titres(self, langues: List[str] = None):
        """Télécharge les sous-titres pour tous les films"""
        if langues is None:
            langues = ['eng']
        
        print("\n📥 Étape 2: Téléchargement des sous-titres...\n")
        
        languages = {Language(lang) for lang in langues}
        videos_traitees = 0
        sous_titres_telecharges = 0
        
        for fichier in self.dossier.rglob('*'):
            if fichier.suffix.lower() not in self.EXTENSIONS_VIDEO:
                continue
            
            print(f"📁 {fichier.name}")
            
            try:
                video = scan_video(str(fichier))
                print(f"   🔍 Détails: {video.title} ({getattr(video, 'year', 'N/A')})")
                
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
                    print(f"   ⚠️  Aucun sous-titre trouvé")
                
                videos_traitees += 1
                    
            except Exception as e:
                print(f"   ❌ Erreur: {e}")
        
        print(f"\n📊 Résumé: {videos_traitees} vidéos traitées, {sous_titres_telecharges} sous-titres téléchargés")
    
    def charger_films(self):
        """Charge tous les films du dossier"""
        print("\n📂 Chargement des films...\n")
        
        for fichier_video in self.dossier.rglob('*'):
            if fichier_video.suffix.lower() not in self.EXTENSIONS_VIDEO:
                continue
            
            film = Movie(fichier_video)
            
            # Chercher les sous-titres
            subtitle_path = self._trouver_sous_titres(fichier_video)
            if subtitle_path:
                film.definir_sous_titres(subtitle_path)
            
            self.films.append(film)
        
        print(f"✅ {len(self.films)} film(s) chargé(s)")
    
    def _trouver_sous_titres(self, fichier_video: Path) -> Optional[Path]:
        """Trouve le fichier de sous-titres associé à une vidéo"""
        base_name = fichier_video.stem
        
        patterns_possibles = [
            fichier_video.with_suffix('.srt'),
            fichier_video.with_suffix('.en.srt'),
            fichier_video.with_suffix('.eng.srt'),
            fichier_video.parent / f"{base_name}.en.srt",
            fichier_video.parent / f"{base_name}.eng.srt",
        ]
        
        # Chercher aussi tous les .srt contenant le nom
        for srt_file in fichier_video.parent.glob('*.srt'):
            if base_name in srt_file.stem:
                patterns_possibles.append(srt_file)
        
        for possible_srt in patterns_possibles:
            if possible_srt.exists():
                return possible_srt
        
        return None
    
    def traiter_films(self, intervalle_secondes: int = 3):
        """Traite tous les films: analyse, extraction, sauvegarde"""
        print(f"\n🖼️  Étape 3: Traitement des films (intervalle: {intervalle_secondes}s)...\n")
        
        films_traites = 0
        films_sans_sous_titres = 0
        
        for film in self.films:
            print(f"\n📹 {film.movie_id}")
            
            if not film.subtitle_path:
                print(f"   ⚠️  Pas de sous-titres - film ignoré")
                films_sans_sous_titres += 1
                continue
            
            try:
                # Analyser les sous-titres
                print(f"   📝 Analyse des sous-titres...")
                film.analyser_sous_titres(intervalle_secondes)
                print(f"   ✅ {len(film.intervalles)} intervalles créés")
                
                # Créer le dossier images
                film.creer_dossier_images()
                
                # Extraire les images
                print(f"   🖼️  Extraction des images...")
                film.extraire_images()
                print(f"   ✅ {len(film.intervalles)} images extraites")
                
                # Sauvegarder le JSON immédiatement
                json_path = film.sauvegarder_json()
                print(f"   💾 JSON sauvegardé: {json_path.name}")
                
                films_traites += 1
                
            except Exception as e:
                print(f"   ❌ Erreur: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n📊 Résumé final:")
        print(f"   • Films traités: {films_traites}")
        print(f"   • Films sans sous-titres: {films_sans_sous_titres}")
        print(f"   • Total: {len(self.films)}")
    
    def generer_index_global(self):
        """Génère un fichier index.json avec tous les films"""
        index_path = Path("analyse") / "index.json"
        
        data = {
            'date_generation': datetime.now().isoformat(),
            'nombre_films': len(self.films),
            'films': [film.to_dict() for film in self.films]
        }
        
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n📋 Index global créé: {index_path}")


def main():
    """Fonction principale"""
    print("=" * 70)
    print("🎥 Renommage, sous-titres et extraction d'images (POO)")
    print("=" * 70)
    
    dossier = "movies"
    
    # Traitement
    processor = MovieProcessor(dossier)
    
    processor.renommer_avec_mnamer()
    processor.telecharger_sous_titres(langues=['eng'])
    processor.charger_films()
    processor.traiter_films(intervalle_secondes=15)
    processor.generer_index_global()
    


if __name__ == "__main__":
    main()