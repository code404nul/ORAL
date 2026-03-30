#!/usr/bin/env python3
"""
Script de réparation: détecte et retraite les segments vidéo défectueux
Usage: python fix_corrupted_segments.py
Analyse tous les films et recrée uniquement les segments problématiques
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import time


class SegmentFixer:
    """Détecte et répare les segments vidéo défectueux"""
    
    def __init__(self, base_dir: Path = Path("analyse")):
        self.base_dir = Path(base_dir)
        self.videos_dir = self.base_dir / "videos"
        self.json_dir = self.base_dir / "json"
        self.codec_gpu = None
        
        # Statistiques
        self.stats = {
            'films_analyses': 0,
            'segments_totaux': 0,
            'segments_ok': 0,
            'segments_zero': 0,
            'segments_petits': 0,
            'segments_corrompus': 0,
            'segments_repares': 0,
            'segments_echecs': 0
        }
    
    def detecter_codec_gpu(self) -> Optional[str]:
        """Détecte le codec GPU disponible"""
        if self.codec_gpu is not None:
            return self.codec_gpu
        
        try:
            result = subprocess.run(
                [r'C:\ffmpeg\bin\ffmpeg.exe', '-hide_banner', '-encoders'],
                capture_output=True,
                text=True,
                timeout=5
            )
            encoders = result.stdout.lower()
            
            if 'h264_nvenc' in encoders:
                self.codec_gpu = 'h264_nvenc'
                print(f"   🎮 GPU détecté: NVIDIA (h264_nvenc)")
            elif 'h264_qsv' in encoders:
                self.codec_gpu = 'h264_qsv'
                print(f"   🎮 GPU détecté: Intel QuickSync (h264_qsv)")
            elif 'h264_amf' in encoders:
                self.codec_gpu = 'h264_amf'
                print(f"   🎮 GPU détecté: AMD (h264_amf)")
            else:
                self.codec_gpu = None
                print(f"   💻 Mode CPU uniquement")
                
        except:
            self.codec_gpu = None
        
        return self.codec_gpu
    
    def analyser_segment(self, segment_path: Path) -> Tuple[bool, str, int]:
        """
        Analyse un segment vidéo
        Returns: (is_valid, raison, taille_octets)
        """
        if not segment_path.exists():
            return False, "fichier_inexistant", 0
        
        taille = segment_path.stat().st_size
        
        # Vérifier si le fichier est vide
        if taille == 0:
            return False, "vide_0_octet", 0
        
        # Vérifier si le fichier est anormalement petit (< 10 KB)
        if taille < 10240:
            return False, "trop_petit", taille
        
        # Vérifier l'intégrité avec ffprobe
        try:
            cmd = [
                r'C:\ffmpeg\bin\ffprobe.exe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name,duration',
                '-of', 'json',
                str(segment_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return False, "corrompu_ffprobe_erreur", taille
            
            # Vérifier que ffprobe a pu lire le fichier
            try:
                data = json.loads(result.stdout)
                if 'streams' not in data or len(data['streams']) == 0:
                    return False, "corrompu_pas_de_stream", taille
                
                # Tout semble OK
                return True, "ok", taille
                
            except json.JSONDecodeError:
                return False, "corrompu_json_invalide", taille
                
        except subprocess.TimeouçtExpired:
            return False, "corrompu_timeout", taille
        except Exception as e:
            return False, f"erreur_{str(e)[:20]}", taille
    
    def analyser_film(self, movie_id: str) -> Dict:
        """Analyse tous les segments d'un film"""
        json_path = self.json_dir / f"{movie_id}.json"
        
        if not json_path.exists():
            return {
                'movie_id': movie_id,
                'erreur': 'json_inexistant',
                'segments_defectueux': []
            }
        
        # Charger le JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        movie_path = Path(data['movie_path'])
        dossier_videos = Path(data['dossier_videos'])
        
        if not movie_path.exists():
            return {
                'movie_id': movie_id,
                'erreur': 'video_originale_inexistante',
                'movie_path': str(movie_path),
                'segments_defectueux': []
            }
        
        segments_defectueux = []
        segments_ok = 0
        
        # Analyser chaque intervalle
        for intervalle in data['intervalles']:
            if 'video_path' not in intervalle or not intervalle['video_path']:
                # Segment jamais créé
                segments_defectueux.append({
                    'intervalle_index': intervalle['intervalle_index'],
                    'debut': intervalle['intervalle_debut'],
                    'fin': intervalle['intervalle_fin'],
                    'raison': 'jamais_cree',
                    'taille': 0,
                    'video_path': None
                })
                continue
            
            segment_path = Path(intervalle['video_path'])
            is_valid, raison, taille = self.analyser_segment(segment_path)
            
            self.stats['segments_totaux'] += 1
            
            if is_valid:
                segments_ok += 1
                self.stats['segments_ok'] += 1
            else:
                segments_defectueux.append({
                    'intervalle_index': intervalle['intervalle_index'],
                    'debut': intervalle['intervalle_debut'],
                    'fin': intervalle['intervalle_fin'],
                    'raison': raison,
                    'taille': taille,
                    'video_path': str(segment_path)
                })
                
                if raison == "vide_0_octet":
                    self.stats['segments_zero'] += 1
                elif raison == "trop_petit":
                    self.stats['segments_petits'] += 1
                else:
                    self.stats['segments_corrompus'] += 1
        
        self.stats['films_analyses'] += 1
        
        return {
            'movie_id': movie_id,
            'movie_path': str(movie_path),
            'dossier_videos': str(dossier_videos),
            'segments_totaux': len(data['intervalles']),
            'segments_ok': segments_ok,
            'segments_defectueux': segments_defectueux,
            'json_data': data
        }
    
    def reparer_segment(self, movie_path: Path, segment_info: Dict, dossier_videos: Path) -> bool:
        """Répare un segment défectueux"""
        temps_debut = segment_info['debut']
        temps_fin = segment_info['fin']
        duree = temps_fin - temps_debut
        
        # Reconstruire le nom du fichier
        index = segment_info['intervalle_index']
        nom_video = f"interval_{index:04d}_time_{temps_debut:.2f}s-{temps_fin:.2f}s.mp4"
        output_path = dossier_videos / nom_video
        
        # Supprimer l'ancien fichier s'il existe
        if output_path.exists():
            try:
                output_path.unlink()
            except:
                pass
        
        # Construire la commande ffmpeg
        if self.codec_gpu:
            cmd = self._build_gpu_command(movie_path, temps_debut, duree, output_path)
        else:
            cmd = self._build_cpu_command(movie_path, temps_debut, duree, output_path)
        
        # Exécuter l'extraction avec 3 tentatives
        for tentative in range(3):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0 and output_path.exists():
                    # Vérifier que le fichier n'est pas vide
                    if output_path.stat().st_size > 10240:
                        # Vérifier avec ffprobe
                        is_valid, _, _ = self.analyser_segment(output_path)
                        if is_valid:
                            return True
                
                # Attendre un peu avant de réessayer
                if tentative < 2:
                    time.sleep(1)
                    
            except subprocess.TimeoutExpired:
                if tentative < 2:
                    time.sleep(2)
            except Exception as e:
                if tentative < 2:
                    time.sleep(1)
        
        return False
    
    def _build_gpu_command(self, movie_path: Path, temps_debut: float, duree: float, output_path: Path) -> List[str]:
        """Commande GPU optimisée"""
        if self.codec_gpu == 'h264_nvenc':
            return [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                '-hwaccel', 'cuda',
                '-hwaccel_output_format', 'cuda',
                '-ss', str(temps_debut),
                '-i', str(movie_path),
                '-t', str(duree),
                '-c:v', 'h264_nvenc',
                '-preset', 'p1',
                '-tune', 'hq',
                '-rc', 'vbr',
                '-cq', '28',
                '-b:v', '0',
                '-maxrate', '3M',
                '-bufsize', '6M',
                '-c:a', 'copy',
                '-movflags', '+faststart',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                '-loglevel', 'error',
                '-hide_banner',
                str(output_path)
            ]
        elif self.codec_gpu == 'h264_qsv':
            return [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                '-hwaccel', 'qsv',
                '-ss', str(temps_debut),
                '-i', str(movie_path),
                '-t', str(duree),
                '-c:v', 'h264_qsv',
                '-preset', 'veryfast',
                '-global_quality', '23',
                '-c:a', 'copy',
                '-movflags', '+faststart',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                '-loglevel', 'error',
                '-hide_banner',
                str(output_path)
            ]
        elif self.codec_gpu == 'h264_amf':
            return [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                '-ss', str(temps_debut),
                '-i', str(movie_path),
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
        
        return self._build_cpu_command(movie_path, temps_debut, duree, output_path)
    
    def _build_cpu_command(self, movie_path: Path, temps_debut: float, duree: float, output_path: Path) -> List[str]:
        """Commande CPU de secours"""
        return [
            r'C:\ffmpeg\bin\ffmpeg.exe',
            '-ss', str(temps_debut),
            '-i', str(movie_path),
            '-t', str(duree),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            '-y',
            '-loglevel', 'error',
            '-hide_banner',
            str(output_path)
        ]
    
    def reparer_film(self, analyse_result: Dict, max_workers: int = 4) -> Dict:
        """Répare tous les segments défectueux d'un film"""
        if 'erreur' in analyse_result:
            return {
                'movie_id': analyse_result['movie_id'],
                'erreur': analyse_result['erreur'],
                'segments_repares': 0,
                'segments_echecs': 0
            }
        
        movie_path = Path(analyse_result['movie_path'])
        dossier_videos = Path(analyse_result['dossier_videos'])
        segments_defectueux = analyse_result['segments_defectueux']
        
        if not segments_defectueux:
            return {
                'movie_id': analyse_result['movie_id'],
                'segments_repares': 0,
                'segments_echecs': 0
            }
        
        segments_repares = 0
        segments_echecs = 0
        
        # Réparer en parallèle
        def reparer_worker(segment_info):
            success = self.reparer_segment(movie_path, segment_info, dossier_videos)
            return (segment_info, success)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(reparer_worker, seg) for seg in segments_defectueux]
            
            for future in tqdm(futures, desc=f"   🔧 Réparation", unit="seg", leave=False):
                segment_info, success = future.result()
                if success:
                    segments_repares += 1
                    self.stats['segments_repares'] += 1
                    
                    # Mettre à jour le JSON
                    self._update_json_segment(
                        analyse_result['json_data'],
                        segment_info['intervalle_index'],
                        dossier_videos,
                        segment_info['debut'],
                        segment_info['fin']
                    )
                else:
                    segments_echecs += 1
                    self.stats['segments_echecs'] += 1
        
        # Sauvegarder le JSON mis à jour
        json_path = self.json_dir / f"{analyse_result['movie_id']}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(analyse_result['json_data'], f, ensure_ascii=False, indent=2)
        
        return {
            'movie_id': analyse_result['movie_id'],
            'segments_repares': segments_repares,
            'segments_echecs': segments_echecs
        }
    
    def _update_json_segment(self, json_data: Dict, index: int, dossier_videos: Path, debut: float, fin: float):
        """Met à jour le chemin vidéo dans le JSON"""
        for intervalle in json_data['intervalles']:
            if intervalle['intervalle_index'] == index:
                nom_video = f"interval_{index:04d}_time_{debut:.2f}s-{fin:.2f}s.mp4"
                intervalle['video_path'] = str(dossier_videos / nom_video)
                break
    
    def generer_rapport(self, analyses: List[Dict], output_path: Path = Path("analyse/rapport_reparation.json")):
        """Génère un rapport détaillé"""
        rapport = {
            'date_analyse': time.strftime('%Y-%m-%d %H:%M:%S'),
            'statistiques_globales': self.stats,
            'films': []
        }
        
        for analyse in analyses:
            if 'erreur' in analyse:
                rapport['films'].append({
                    'movie_id': analyse['movie_id'],
                    'erreur': analyse['erreur'],
                    'segments_defectueux': []
                })
            else:
                rapport['films'].append({
                    'movie_id': analyse['movie_id'],
                    'segments_totaux': analyse['segments_totaux'],
                    'segments_ok': analyse['segments_ok'],
                    'nombre_defectueux': len(analyse['segments_defectueux']),
                    'segments_defectueux': analyse['segments_defectueux']
                })
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)
        
        return output_path


def main():
    """Fonction principale"""
    print("=" * 70)
    print("🔧 RÉPARATION DES SEGMENTS VIDÉO DÉFECTUEUX")
    print("=" * 70)
    
    # Configuration
    MAX_WORKERS_REPARATION = 4  # Moins de workers pour la réparation (plus stable)
    
    fixer = SegmentFixer()
    
    # Détecter le GPU
    print("\n🎮 Détection du matériel...")
    fixer.detecter_codec_gpu()
    
    # Lister tous les films
    json_dir = Path("analyse/json")
    if not json_dir.exists():
        print(f"\n❌ Erreur: Le dossier {json_dir} n'existe pas")
        print("   Exécutez d'abord movie_processor.py")
        sys.exit(1)
    
    films_json = list(json_dir.glob("*.json"))
    if not films_json:
        print(f"\n❌ Aucun fichier JSON trouvé dans {json_dir}")
        sys.exit(1)
    
    print(f"\n📂 {len(films_json)} film(s) trouvé(s)")
    
    # Phase 1: Analyser tous les films
    print("\n" + "=" * 70)
    print("📊 PHASE 1: ANALYSE DES SEGMENTS")
    print("=" * 70)
    
    analyses = []
    for json_file in tqdm(films_json, desc="🔍 Analyse", unit="film"):
        movie_id = json_file.stem
        analyse = fixer.analyser_film(movie_id)
        analyses.append(analyse)
        
        if 'segments_defectueux' in analyse and analyse['segments_defectueux']:
            tqdm.write(f"   ⚠️  {movie_id}: {len(analyse['segments_defectueux'])} segments défectueux")
    
    # Afficher les statistiques
    print("\n📊 Résultats de l'analyse:")
    print(f"   • Films analysés: {fixer.stats['films_analyses']}")
    print(f"   • Segments totaux: {fixer.stats['segments_totaux']}")
    print(f"   • Segments OK: {fixer.stats['segments_ok']} ✅")
    print(f"   • Segments vides (0 octet): {fixer.stats['segments_zero']} ❌")
    print(f"   • Segments trop petits: {fixer.stats['segments_petits']} ⚠️")
    print(f"   • Segments corrompus: {fixer.stats['segments_corrompus']} 💥")
    
    total_defectueux = fixer.stats['segments_zero'] + fixer.stats['segments_petits'] + fixer.stats['segments_corrompus']
    
    if total_defectueux == 0:
        print("\n✅ Aucun segment défectueux détecté!")
        
        # Générer quand même le rapport
        rapport_path = fixer.generer_rapport(analyses)
        print(f"\n📋 Rapport sauvegardé: {rapport_path}")
        return
    
    # Phase 2: Demander confirmation
    print("\n" + "=" * 70)
    print("🔧 PHASE 2: RÉPARATION")
    print("=" * 70)
    print(f"\n⚠️  {total_defectueux} segment(s) à réparer")
    print(f"   Workers: {MAX_WORKERS_REPARATION} en parallèle")
    
    reponse = input("\n   Lancer la réparation? (o/N): ").strip().lower()
    
    if reponse != 'o':
        print("\n❌ Réparation annulée")
        
        # Générer le rapport d'analyse
        rapport_path = fixer.generer_rapport(analyses)
        print(f"\n📋 Rapport d'analyse sauvegardé: {rapport_path}")
        return
    
    # Phase 3: Réparer les films
    print("\n🔧 Réparation en cours...\n")
    
    films_a_reparer = [a for a in analyses if 'segments_defectueux' in a and a['segments_defectueux']]
    
    for analyse in tqdm(films_a_reparer, desc="🎬 Films", unit="film"):
        tqdm.write(f"\n🎥 {analyse['movie_id']}")
        tqdm.write(f"   {len(analyse['segments_defectueux'])} segment(s) à réparer")
        
        resultat = fixer.reparer_film(analyse, max_workers=MAX_WORKERS_REPARATION)
        
        if resultat['segments_repares'] > 0:
            tqdm.write(f"   ✅ {resultat['segments_repares']} réparé(s)")
        if resultat['segments_echecs'] > 0:
            tqdm.write(f"   ❌ {resultat['segments_echecs']} échec(s)")
    
    # Résumé final
    print("\n" + "=" * 70)
    print("📊 RÉSUMÉ FINAL")
    print("=" * 70)
    print(f"   • Segments réparés avec succès: {fixer.stats['segments_repares']} ✅")
    print(f"   • Segments en échec: {fixer.stats['segments_echecs']} ❌")
    
    # Générer le rapport final
    rapport_path = fixer.generer_rapport(analyses)
    print(f"\n📋 Rapport détaillé: {rapport_path}")
    
    print("\n✅ Réparation terminée!")


if __name__ == "__main__":
    main()