#!/usr/bin/env python3
"""
Script OPTIMISÉ: gestion des timeouts et réduction de la charge GPU
Changements principaux:
- Timeout augmenté à 120s (segments de 15s peuvent être lourds)
- Workers réduits de 8 à 4 pour éviter saturation GPU
- Retry automatique en cas de timeout
- Fallback CPU si GPU échoue
- Statistiques détaillées des échecs
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from subliminal import download_best_subtitles, save_subtitles, scan_video
from babelfish import Language
import pysrt
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import multiprocessing


class SubtitleInterval:
    """Représente un intervalle de sous-titres"""
    
    def __init__(self, index: int, debut: float, fin: float, premier_timecode: float):
        self.index = index
        self.debut = debut
        self.fin = fin
        self.premier_timecode = premier_timecode
        self.sous_titres = []
        self.video_path = None
        self.failed_attempts = 0  # Nouveau: compteur d'échecs
    
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
            'timecode_debut_extrait': self.debut,
            'timecode_fin_extrait': self.fin,
            'video_path': self.video_path,
            'nombre_sous_titres': len(self.sous_titres),
            'sous_titres': self.sous_titres,
            'failed_attempts': self.failed_attempts
        }


class Movie:
    """Représente un film avec ses métadonnées"""
    
    _codec_cache = None
    
    def __init__(self, video_path: Path):
        self.video_path = video_path
        self.movie_id = video_path.stem
        self.subtitle_path = None
        self.intervalles: List[SubtitleInterval] = []
        self.intervalle_secondes = 3
        self.dossier_videos = None
        self.date_traitement = None
        # Statistiques d'extraction
        self.stats = {
            'total': 0,
            'reussis': 0,
            'echecs': 0,
            'timeouts': 0,
            'gpu_errors': 0,
            'cpu_fallbacks': 0
        }
    
    def definir_sous_titres(self, subtitle_path: Path):
        """Définit le chemin des sous-titres"""
        self.subtitle_path = subtitle_path
    
    def creer_dossier_videos(self, base_dir: Path = Path("analyse/videos")):
        """Crée le dossier pour les vidéos extraites"""
        self.dossier_videos = base_dir / self.movie_id
        self.dossier_videos.mkdir(parents=True, exist_ok=True)
        return self.dossier_videos
    
    def est_deja_segmente(self, base_dir_json: Path = Path("analyse/json"), 
                          base_dir_videos: Path = Path("analyse/videos"),
                          min_videos_required: int = 10) -> bool:
        """Vérifie si le film a déjà été segmenté"""
        fichier_json = base_dir_json / f"{self.movie_id}.json"
        if not fichier_json.exists():
            return False
        
        dossier_videos = base_dir_videos / self.movie_id
        if not dossier_videos.exists():
            return False
        
        videos_existantes = list(dossier_videos.glob("interval_*.mp4"))
        return len(videos_existantes) >= min_videos_required
    
    def analyser_sous_titres(self, intervalle_secondes: int = 3):
        """Analyse les sous-titres et crée les intervalles"""
        self.intervalle_secondes = intervalle_secondes
        self.date_traitement = datetime.now().isoformat()
        
        if not self.subtitle_path or not self.subtitle_path.exists():
            raise FileNotFoundError(f"Fichier de sous-titres introuvable: {self.subtitle_path}")
        
        subs = pysrt.open(str(self.subtitle_path), encoding='utf-8')
        
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
        
        duree_totale = self._obtenir_duree_video()
        
        temps_debut = 0
        index_intervalle = 0
        
        while temps_debut < duree_totale:
            temps_fin = min(temps_debut + intervalle_secondes, duree_totale)
            
            subs_dans_intervalle = [
                s for s in sous_titres_data 
                if s['start'] >= temps_debut and s['start'] < temps_fin
            ]
            
            intervalle = SubtitleInterval(
                index=index_intervalle,
                debut=temps_debut,
                fin=temps_fin,
                premier_timecode=temps_debut
            )
            
            for sub in subs_dans_intervalle:
                intervalle.ajouter_sous_titre(
                    sub['index'], sub['start'], sub['end'], sub['text']
                )
            
            self.intervalles.append(intervalle)
            index_intervalle += 1
            temps_debut = temps_fin
    
    def _obtenir_duree_video(self) -> float:
        """Obtient la durée de la vidéo avec ffprobe"""
        try:
            cmd = [
                r'C:\ffmpeg\bin\ffprobe.exe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(self.video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                return 7200
        except Exception as e:
            print(f"   ⚠️  Impossible d'obtenir la durée: {e}")
            return 7200
    
    def extraire_videos(self, show_progress=True, update_json_every=10, 
                       max_workers=4, timeout_seconds=120):
        """
        Extrait les vidéos avec GESTION OPTIMISÉE DES TIMEOUTS
        
        Changements:
        - Workers réduits à 4 (au lieu de 8) pour moins saturer le GPU
        - Timeout augmenté à 120s (au lieu de 60s)
        - Retry automatique avec CPU si GPU échoue
        - Statistiques détaillées
        """
        if not self.dossier_videos:
            self.creer_dossier_videos()
        
        codec_gpu = self._detecter_codec_gpu()
        self.stats['total'] = len(self.intervalles)
        
        def extraire_segment_avec_retry(intervalle, max_retries=2):
            """Extraction avec retry automatique et fallback CPU"""
            temps_debut = intervalle.debut
            duree = intervalle.fin - intervalle.debut
            
            nom_video = f"interval_{intervalle.index:04d}_time_{temps_debut:.2f}s-{intervalle.fin:.2f}s.mp4"
            chemin_video = self.dossier_videos / nom_video
            
            # Essai 1: GPU
            if codec_gpu:
                cmd = self._build_gpu_command(codec_gpu, temps_debut, duree, chemin_video)
                success, error_type = self._run_ffmpeg_safe(cmd, timeout_seconds)
                
                if success:
                    intervalle.video_path = str(chemin_video)
                    self.stats['reussis'] += 1
                    return True
                
                # Enregistrer type d'erreur
                if error_type == 'timeout':
                    self.stats['timeouts'] += 1
                else:
                    self.stats['gpu_errors'] += 1
            
            # Fallback CPU si GPU a échoué
            if show_progress:
                tqdm.write(f"   🔄 Fallback CPU pour intervalle {intervalle.index}")
            
            cmd = self._build_cpu_command(temps_debut, duree, chemin_video)
            success, error_type = self._run_ffmpeg_safe(cmd, timeout_seconds * 2)  # Double timeout pour CPU
            
            if success:
                intervalle.video_path = str(chemin_video)
                self.stats['reussis'] += 1
                self.stats['cpu_fallbacks'] += 1
                return True
            
            # Échec total
            intervalle.failed_attempts += 1
            self.stats['echecs'] += 1
            if show_progress:
                tqdm.write(f"   ❌ Échec définitif intervalle {intervalle.index}")
            return False
        
        # TRAITEMENT PARALLÈLE AVEC WORKERS RÉDUITS
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            
            for intervalle in self.intervalles:
                future = executor.submit(extraire_segment_avec_retry, intervalle)
                futures.append(future)
            
            # Barre de progression
            if show_progress:
                for i, future in enumerate(tqdm(futures, 
                                               desc=f"   📹 Segments ({max_workers} workers)", 
                                               unit="seg", 
                                               leave=False)):
                    try:
                        future.result()  # Attendre la fin
                    except Exception as e:
                        tqdm.write(f"   ⚠️  Erreur inattendue: {e}")
                    
                    # Sauvegarder JSON périodiquement
                    if (i + 1) % update_json_every == 0:
                        self.sauvegarder_json()
            else:
                for future in futures:
                    try:
                        future.result()
                    except:
                        pass
        
        return self.stats['reussis']
    
    def _run_ffmpeg_safe(self, cmd: List[str], timeout: int) -> tuple[bool, str]:
        """
        Exécute ffmpeg avec gestion sécurisée des erreurs
        
        Returns:
            (success: bool, error_type: str) - error_type peut être 'timeout', 'error', ou 'none'
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                # Vérifier que le fichier existe
                output_path = Path(cmd[-1])
                if output_path.exists() and output_path.stat().st_size > 0:
                    return (True, 'none')
            
            return (False, 'error')
            
        except subprocess.TimeoutExpired:
            return (False, 'timeout')
        except Exception:
            return (False, 'error')

    def _detecter_codec_gpu(self) -> Optional[str]:
        """Détecte le codec GPU (avec cache)"""
        if Movie._codec_cache is not None:
            return Movie._codec_cache
        
        try:
            result = subprocess.run(
                [r'C:\ffmpeg\bin\ffmpeg.exe', '-hide_banner', '-encoders'],
                capture_output=True,
                text=True,
                timeout=5
            )
            encoders = result.stdout.lower()
            
            if 'h264_nvenc' in encoders:
                Movie._codec_cache = 'h264_nvenc'
            elif 'h264_qsv' in encoders:
                Movie._codec_cache = 'h264_qsv'
            elif 'h264_amf' in encoders:
                Movie._codec_cache = 'h264_amf'
            else:
                Movie._codec_cache = None
            
            if Movie._codec_cache:
                print(f"   🎮 GPU détecté: {Movie._codec_cache}")
            else:
                print(f"   💻 CPU uniquement")
                
        except:
            Movie._codec_cache = None
        
        return Movie._codec_cache

    def _build_gpu_command(self, codec: str, temps_debut: float, duree: float, output_path: Path) -> List[str]:
        """Construit la commande ffmpeg GPU - PRESET PLUS RAPIDE"""
        
        if codec == 'h264_nvenc':
            return [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                '-hwaccel', 'cuda',
                '-hwaccel_output_format', 'cuda',
                '-ss', str(temps_debut),
                '-i', str(self.video_path),
                '-t', str(duree),
                '-c:v', 'h264_nvenc',
                '-preset', 'p1',              # Plus rapide
                '-tune', 'hq',
                '-rc', 'vbr',
                '-cq', '30',                  # Qualité légèrement réduite (28->30) pour vitesse
                '-b:v', '0',
                '-maxrate', '2M',             # Réduit de 3M->2M
                '-bufsize', '4M',             # Réduit de 6M->4M
                '-c:a', 'copy',
                '-movflags', '+faststart',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                '-loglevel', 'error',
                '-hide_banner',
                str(output_path)
            ]
        
        elif codec == 'h264_qsv':
            return [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                '-hwaccel', 'qsv',
                '-ss', str(temps_debut),
                '-i', str(self.video_path),
                '-t', str(duree),
                '-c:v', 'h264_qsv',
                '-preset', 'veryfast',
                '-global_quality', '25',      # Réduit de 23->25
                '-c:a', 'copy',
                '-movflags', '+faststart',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                '-loglevel', 'error',
                '-hide_banner',
                str(output_path)
            ]
        
        elif codec == 'h264_amf':
            return [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                '-ss', str(temps_debut),
                '-i', str(self.video_path),
                '-t', str(duree),
                '-c:v', 'h264_amf',
                '-quality', 'speed',
                '-rc', 'vbr_latency',
                '-c:a', 'copy',
                '-movflags', '+faststart',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                '-loglevel', 'error',
                '-hide_banner',
                str(output_path)
            ]
        
        return self._build_cpu_command(temps_debut, duree, output_path)

    def _build_cpu_command(self, temps_debut: float, duree: float, output_path: Path) -> List[str]:
        """Commande CPU de secours"""
        return [
            r'C:\ffmpeg\bin\ffmpeg.exe',
            '-ss', str(temps_debut),
            '-i', str(self.video_path),
            '-t', str(duree),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '28',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            '-y',
            '-loglevel', 'error',
            '-hide_banner',
            str(output_path)
        ]
        
    def sauvegarder_json(self, base_dir: Path = Path("analyse/json")):
        """Sauvegarde les données du film en JSON avec statistiques"""
        base_dir.mkdir(parents=True, exist_ok=True)
        fichier_json = base_dir / f"{self.movie_id}.json"
        
        data = {
            'movie_id': self.movie_id,
            'movie_path': str(self.video_path),
            'subtitle_path': str(self.subtitle_path) if self.subtitle_path else None,
            'intervalle_secondes': self.intervalle_secondes,
            'nombre_intervalles': len(self.intervalles),
            'dossier_videos': str(self.dossier_videos) if self.dossier_videos else None,
            'date_traitement': self.date_traitement,
            'stats_extraction': self.stats,
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
            'dossier_videos': str(self.dossier_videos) if self.dossier_videos else None,
            'stats_extraction': self.stats
        }


class MovieProcessor:
    """Gestionnaire principal du traitement des films"""
    
    EXTENSIONS_VIDEO = {'.mp4', '.mkv', '.avi', '.mov', '.m4v'}
    
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.films: List[Movie] = []
    
    def renommer_avec_mnamer(self, skip_if_error=True):
        """Renomme les fichiers avec mnamer"""
        print("\n🎬 Étape 1: Renommage des films avec mnamer...\n")
        
        try:
            result = subprocess.run(
                ['python', '-m', 'mnamer', '-b', '-r', str(self.dossier)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print("✅ Renommage terminé avec succès")
            else:
                print(f"⚠️  Avertissement mnamer: {result.stderr}")
                
        except FileNotFoundError:
            if skip_if_error:
                print("⚠️  mnamer non trouvé - étape ignorée")
            else:
                print("❌ Erreur: mnamer n'est pas accessible")
                sys.exit(1)
        except subprocess.TimeoutExpired:
            print("⚠️  Timeout mnamer - étape ignorée")
        except Exception as e:
            if skip_if_error:
                print(f"⚠️  Erreur mnamer ({e}) - étape ignorée")
            else:
                print(f"❌ Erreur lors du renommage: {e}")
                sys.exit(1)
    
    def telecharger_sous_titres(self, langues: List[str] = None):
        """Télécharge les sous-titres pour tous les films"""
        if langues is None:
            langues = ['eng']
        
        print("\n📥 Étape 2: Téléchargement des sous-titres...\n")
        
        languages = {Language(lang) for lang in langues}
        videos_traitees = 0
        sous_titres_telecharges = 0
        sous_titres_deja_presents = 0
        
        for fichier in self.dossier.rglob('*'):
            if fichier.suffix.lower() not in self.EXTENSIONS_VIDEO:
                continue
            
            srt_existant = self._trouver_sous_titres(fichier)
            if srt_existant:
                print(f"📁 {fichier.name}")
                print(f"   ✅ Sous-titres déjà présents: {srt_existant.name}")
                sous_titres_deja_presents += 1
                videos_traitees += 1
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
        
        print(f"\n📊 Résumé:")
        print(f"   • Vidéos traitées: {videos_traitees}")
        print(f"   • Sous-titres déjà présents: {sous_titres_deja_presents}")
        print(f"   • Sous-titres téléchargés: {sous_titres_telecharges}")
    
    def charger_films(self):
        """Charge tous les films du dossier"""
        print("\n📂 Chargement des films...\n")
        
        for fichier_video in self.dossier.rglob('*'):
            if fichier_video.suffix.lower() not in self.EXTENSIONS_VIDEO:
                continue
            
            film = Movie(fichier_video)
            
            subtitle_path = self._trouver_sous_titres(fichier_video)
            if subtitle_path:
                film.definir_sous_titres(subtitle_path)
            
            self.films.append(film)
        
        print(f"✅ {len(self.films)} film(s) chargé(s)")
    
    def _trouver_sous_titres(self, fichier_video: Path) -> Optional[Path]:
        """Trouve le fichier de sous-titres associé"""
        base_name = fichier_video.stem
        
        patterns_possibles = [
            fichier_video.with_suffix('.srt'),
            fichier_video.with_suffix('.en.srt'),
            fichier_video.with_suffix('.eng.srt'),
            fichier_video.parent / f"{base_name}.en.srt",
            fichier_video.parent / f"{base_name}.eng.srt",
        ]
        
        for srt_file in fichier_video.parent.glob('*.srt'):
            if base_name in srt_file.stem:
                patterns_possibles.append(srt_file)
        
        for possible_srt in patterns_possibles:
            if possible_srt.exists():
                return possible_srt
        
        return None
    
    def traiter_films(self, intervalle_secondes: int = 3, max_workers: int = 4, 
                     skip_existing: bool = True, timeout_seconds: int = 120):
        """
        Traite tous les films avec extraction OPTIMISÉE
        
        Args:
            max_workers: Nombre de workers (RÉDUIT à 4 par défaut)
            timeout_seconds: Timeout par segment (AUGMENTÉ à 120s)
        """
        print(f"\n🎬 Étape 3: Traitement OPTIMISÉ...\n")
        print(f"   • Workers: {max_workers} (réduit pour stabilité)")
        print(f"   • Timeout: {timeout_seconds}s par segment")
        print(f"   • Retry automatique avec fallback CPU\n")
        
        if skip_existing:
            print("   ⏩ Mode SKIP: films déjà segmentés ignorés\n")
        
        films_traites = 0
        films_sans_sous_titres = 0
        films_deja_segmentes = 0
        
        for film in tqdm(self.films, desc="🎥 Films", unit="film"):
            tqdm.write(f"\n📹 {film.movie_id}")
            
            if skip_existing and film.est_deja_segmente():
                tqdm.write(f"   ⏩ DÉJÀ SEGMENTÉ - ignoré")
                films_deja_segmentes += 1
                continue
            
            if not film.subtitle_path:
                tqdm.write(f"   ⚠️  Pas de sous-titres - ignoré")
                films_sans_sous_titres += 1
                continue
            
            try:
                tqdm.write(f"   📝 Analyse des sous-titres...")
                film.analyser_sous_titres(intervalle_secondes)
                tqdm.write(f"   ✅ {len(film.intervalles)} intervalles créés")
                
                film.creer_dossier_videos()
                
                videos_extraites = film.extraire_videos(
                    show_progress=True,
                    update_json_every=10,
                    max_workers=max_workers,
                    timeout_seconds=timeout_seconds
                )
                
                # Afficher statistiques détaillées
                tqdm.write(f"   📊 Statistiques d'extraction:")
                tqdm.write(f"      • Réussis: {film.stats['reussis']}/{film.stats['total']}")
                tqdm.write(f"      • Échecs: {film.stats['echecs']}")
                tqdm.write(f"      • Timeouts: {film.stats['timeouts']}")
                tqdm.write(f"      • Erreurs GPU: {film.stats['gpu_errors']}")
                tqdm.write(f"      • Fallbacks CPU: {film.stats['cpu_fallbacks']}")
                
                json_path = film.sauvegarder_json()
                tqdm.write(f"   💾 JSON sauvegardé: {json_path.name}")
                
                films_traites += 1
                
            except Exception as e:
                tqdm.write(f"   ❌ Erreur: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n📊 Résumé final:")
        print(f"   • Films traités: {films_traites}")
        print(f"   • Films sans sous-titres: {films_sans_sous_titres}")
        print(f"   • Films déjà segmentés: {films_deja_segmentes}")
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
    print("🎥 Extraction OPTIMISÉE - Gestion avancée des timeouts")
    print("=" * 70)
    
    # ==================== CONFIGURATION OPTIMISÉE ====================
    dossier_racine = r"E:\film_oral"
    
    RENOMMER_AVEC_MNAMER = False
    TELECHARGER_SOUS_TITRES = True
    INTERVALLE_SECONDES = 15
    LANGUES_SOUS_TITRES = ['eng']
    
    # PARAMÈTRES OPTIMISÉS
    MAX_WORKERS = 4              # ⬇️ Réduit de 8 -> 4
    TIMEOUT_SECONDS = 120        # ⬆️ Augmenté de 60 -> 120
    SKIP_FILMS_DEJA_SEGMENTES = True
    # =================================================================
    
    print(f"\n📂 Dossier: {dossier_racine}")
    print(f"\n⚙️  Configuration OPTIMISÉE:")
    print(f"   • Intervalle: {INTERVALLE_SECONDES}s")
    print(f"   • Workers: {MAX_WORKERS} 🔽 (réduit pour stabilité)")
    print(f"   • Timeout: {TIMEOUT_SECONDS}s 🔼 (augmenté)")
    print(f"   • Retry automatique: OUI")
    print(f"   • Fallback CPU: OUI")
    print(f"   • Skip films segmentés: {'OUI ⏩' if SKIP_FILMS_DEJA_SEGMENTES else 'NON'}")
    print()
    
    processor = MovieProcessor(dossier_racine)
    
    if RENOMMER_AVEC_MNAMER:
        processor.renommer_avec_mnamer(skip_if_error=True)
    else:
        print("\n🎬 Étape 1: Renommage ignoré")
    
    if TELECHARGER_SOUS_TITRES:
        processor.telecharger_sous_titres(langues=LANGUES_SOUS_TITRES)
    else:
        print("\n📥 Étape 2: Téléchargement ignoré")
    
    processor.charger_films()
    processor.traiter_films(
        intervalle_secondes=INTERVALLE_SECONDES,
        max_workers=MAX_WORKERS,
        skip_existing=SKIP_FILMS_DEJA_SEGMENTES,
        timeout_seconds=TIMEOUT_SECONDS
    )
    processor.generer_index_global()
    
    print("\n" + "=" * 70)
    print("✅ Traitement terminé!")
    print("=" * 70)


if __name__ == "__main__":
    main()