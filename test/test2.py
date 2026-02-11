import json
import os
from pathlib import Path
import base64
from tqdm import tqdm
import cv2
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Tuple
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

print("🚀 Démarrage du script avec auto-régulation...")

# Configuration de l'API Fireworks
API_KEY = "fw_9jPTovViK51DBPKw7ukvDm"
API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
MODEL_ID = "accounts/code404nul/deployments/uizk7clq"

# Configuration extraction frames
NUM_FRAMES = 6

# Configuration parallélisation ADAPTATIVE
MAX_WORKERS_FRAMES = 8
MAX_FILMS_PARALLEL = 5

@dataclass
class RateLimiter:
    """Gestionnaire intelligent des rate limits"""
    max_concurrent: int = 50  # Départ conservateur
    min_concurrent: int = 10
    absolute_max: int = 300  # Plafond absolu si aucune limite détectée
    
    # Métriques temps réel
    current_limit: int = None  # Limite détectée via headers
    remaining: int = None
    reset_time: float = None
    
    # Historique des requêtes (pour calculer RPM)
    request_times: deque = None
    success_count: int = 0
    rate_limit_count: int = 0
    
    # Ajustement dynamique
    last_adjustment: float = 0
    adjustment_interval: float = 5  # Ajuster toutes les 5 secondes
    
    def __post_init__(self):
        self.request_times = deque(maxlen=1000)
    
    def update_from_headers(self, headers: dict):
        """Met à jour les limites depuis les headers de réponse"""
        try:
            if 'x-ratelimit-limit-requests' in headers:
                self.current_limit = int(headers['x-ratelimit-limit-requests'])
            
            if 'x-ratelimit-remaining-requests' in headers:
                self.remaining = int(headers['x-ratelimit-remaining-requests'])
            
            if 'x-ratelimit-reset-requests' in headers:
                self.reset_time = float(headers['x-ratelimit-reset-requests'])
            
            # Alerte si on approche de la limite
            if self.remaining is not None and self.remaining < 10:
                return True  # Signal de ralentissement
        except Exception:
            pass
        return False
    
    def record_request(self, success: bool = True):
        """Enregistre une requête"""
        self.request_times.append(time.time())
        if success:
            self.success_count += 1
        else:
            self.rate_limit_count += 1
    
    def get_current_rpm(self) -> float:
        """Calcule le RPM actuel"""
        if len(self.request_times) < 2:
            return 0
        
        now = time.time()
        one_minute_ago = now - 60
        
        # Compter les requêtes dans la dernière minute
        recent = [t for t in self.request_times if t > one_minute_ago]
        return len(recent)
    
    def should_adjust(self) -> bool:
        """Détermine si on doit ajuster la concurrence"""
        now = time.time()
        return (now - self.last_adjustment) >= self.adjustment_interval
    
    def adjust_concurrency(self) -> int:
        """Ajuste dynamiquement le niveau de concurrence"""
        if not self.should_adjust():
            return self.max_concurrent
        
        self.last_adjustment = time.time()
        
        # Si on a détecté une limite via headers, l'utiliser
        if self.current_limit is not None:
            # Viser 80% de la limite pour avoir de la marge
            target = int(self.current_limit * 0.8 / 60)  # Convertir RPM en concurrent
            self.max_concurrent = max(self.min_concurrent, min(target, self.absolute_max))
            return self.max_concurrent
        
        # Sinon, ajustement basé sur le taux d'erreur
        total = self.success_count + self.rate_limit_count
        if total > 0:
            error_rate = self.rate_limit_count / total
            
            if error_rate > 0.1:  # Plus de 10% d'erreurs
                # Réduire agressivement
                self.max_concurrent = max(self.min_concurrent, int(self.max_concurrent * 0.7))
                print(f"\n⚠️  Trop d'erreurs ({error_rate*100:.1f}%) - réduction à {self.max_concurrent}")
            elif error_rate < 0.01 and self.max_concurrent < self.absolute_max:
                # Moins de 1% d'erreurs, on peut augmenter
                self.max_concurrent = min(self.absolute_max, int(self.max_concurrent * 1.3))
                print(f"\n📈 Performance stable - augmentation à {self.max_concurrent}")
        
        return self.max_concurrent
    
    def get_stats(self) -> dict:
        """Retourne les statistiques actuelles"""
        return {
            'max_concurrent': self.max_concurrent,
            'current_rpm': self.get_current_rpm(),
            'detected_limit': self.current_limit,
            'remaining': self.remaining,
            'success_rate': f"{(self.success_count / max(1, self.success_count + self.rate_limit_count) * 100):.1f}%",
            'total_requests': self.success_count + self.rate_limit_count
        }


# Gestionnaire global
rate_limiter = RateLimiter()


def extract_frames_from_video(video_path, num_frames=6):
    """Extrait des frames uniformément réparties d'une vidéo"""
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        raise Exception(f"Impossible d'ouvrir la vidéo: {video_path}")
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames == 0:
        cap.release()
        raise Exception(f"La vidéo ne contient aucune frame: {video_path}")
    
    frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
    frames_base64 = []
    
    for frame_idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        
        if ret:
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            frames_base64.append(frame_base64)
    
    cap.release()
    return frames_base64


async def ask_molmo_api_async(session: aiohttp.ClientSession, text_input: str, frames_base64: List[str], semaphore: asyncio.Semaphore):
    """Fonction asynchrone pour interroger Molmo8b avec retry intelligent"""
    
    content = [{"type": "text", "text": text_input}]
    
    for frame_b64 in frames_base64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{frame_b64}"
            }
        })
    
    payload = {
        "model": MODEL_ID,
        "max_tokens": 512,
        "top_p": 1,
        "top_k": 40,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "temperature": 0.6,
        "messages": [
            {
                "role": "user",
                "content": content
            }
        ]
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    # Retry avec backoff exponentiel
    max_retries = 5
    base_delay = 1
    
    for attempt in range(max_retries):
        async with semaphore:
            try:
                async with session.post(API_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
                    
                    # Analyser les headers pour détecter les limites
                    should_slow = rate_limiter.update_from_headers(response.headers)
                    
                    if response.status == 429:  # Rate limit
                        rate_limiter.record_request(success=False)
                        
                        # Attendre le temps indiqué ou backoff exponentiel
                        if 'retry-after' in response.headers:
                            wait_time = int(response.headers['retry-after'])
                        else:
                            wait_time = base_delay * (2 ** attempt)
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise Exception(f"Rate limit après {max_retries} tentatives")
                    
                    response.raise_for_status()
                    result = await response.json()
                    
                    rate_limiter.record_request(success=True)
                    
                    # Si on approche de la limite, pause courte
                    if should_slow:
                        await asyncio.sleep(0.5)
                    
                    return result['choices'][0]['message']['content']
                    
            except aiohttp.ClientResponseError as e:
                if e.status == 429 and attempt < max_retries - 1:
                    rate_limiter.record_request(success=False)
                    wait_time = base_delay * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                
                error_detail = await response.text() if 'response' in locals() else str(e)
                raise Exception(f"Erreur API HTTP {e.status}: {error_detail}")
            
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (2 ** attempt))
                    continue
                raise Exception(f"Erreur API: {e}")
    
    raise Exception(f"Échec après {max_retries} tentatives")


def est_completement_traite(movie_rapport_dir, nb_intervalles_total):
    """Vérifie si tous les intervalles ont été traités"""
    style_file = movie_rapport_dir / "style.json"
    action_file = movie_rapport_dir / "action.json"
    
    if not style_file.exists() or not action_file.exists():
        return False
    
    try:
        with open(style_file, 'r', encoding='utf-8') as f:
            style_data = json.load(f)
        with open(action_file, 'r', encoding='utf-8') as f:
            action_data = json.load(f)
        
        nb_style = len(style_data.get("intervalles", []))
        nb_action = len(action_data.get("intervalles", []))
        
        return nb_style == nb_intervalles_total and nb_action == nb_intervalles_total
    except Exception as e:
        return False


async def frame_extractor_worker(executor: ThreadPoolExecutor, work_queue: asyncio.Queue, frame_queue: asyncio.Queue, extraction_pbar: tqdm):
    """Worker asynchrone qui extrait les frames en continu"""
    while True:
        try:
            item = await work_queue.get()
            if item is None:
                work_queue.task_done()
                break
            
            interval, movie_name, style_indices_traites, action_indices_traites = item
            video_path = interval.get("video_path")
            
            # Vérifier si le path est valide
            if not video_path or not isinstance(video_path, (str, Path)):
                work_queue.task_done()
                continue
            
            if not os.path.exists(video_path):
                work_queue.task_done()
                continue
            
            loop = asyncio.get_event_loop()
            try:
                frames = await loop.run_in_executor(executor, extract_frames_from_video, video_path, NUM_FRAMES)
                
                await frame_queue.put({
                    'interval': interval,
                    'frames': frames,
                    'movie_name': movie_name,
                    'style_indices_traites': style_indices_traites,
                    'action_indices_traites': action_indices_traites
                })
                extraction_pbar.update(1)
            except Exception as e:
                tqdm.write(f"   ⚠ Erreur extraction intervalle {interval.get('intervalle_index', '?')}: {e}")
            
            work_queue.task_done()
        except Exception as e:
            work_queue.task_done()
            continue


async def api_sender_worker(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, frame_queue: asyncio.Queue, results_dict: dict, requetes_pbar: tqdm):
    """Worker qui envoie les requêtes API avec respect des limites"""
    while True:
        try:
            item = await frame_queue.get()
            if item is None:
                frame_queue.task_done()
                break
            
            interval = item['interval']
            frames = item['frames']
            movie_name = item['movie_name']
            style_indices_traites = item['style_indices_traites']
            action_indices_traites = item['action_indices_traites']
            
            intervalle_index = interval["intervalle_index"]
            
            tasks = []
            task_types = []
            
            if intervalle_index not in style_indices_traites:
                tasks.append(ask_molmo_api_async(
                    session,
                    "Explain the cinematographic techniques to me; what emotion did the director want to convey?",
                    frames,
                    semaphore
                ))
                task_types.append("style")
            
            if intervalle_index not in action_indices_traites:
                tasks.append(ask_molmo_api_async(
                    session,
                    "What is happening in the scene?",
                    frames,
                    semaphore
                ))
                task_types.append("action")
            
            if tasks:
                task_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for task_type, result in zip(task_types, task_results):
                    if isinstance(result, Exception):
                        result_text = f"ERREUR: {str(result)}"
                        tqdm.write(f"   ⚠ Erreur API intervalle {intervalle_index} ({task_type}): {result}")
                    else:
                        result_text = result
                    
                    if movie_name not in results_dict:
                        results_dict[movie_name] = {'style': [], 'action': []}
                    
                    result_obj = {
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        f"analyse_{task_type}": result_text
                    }
                    
                    results_dict[movie_name][task_type].append(result_obj)
                    requetes_pbar.update(1)
            
            frame_queue.task_done()
        except Exception as e:
            tqdm.write(f"   ⚠ Erreur critique worker API: {e}")
            frame_queue.task_done()
            continue  # Continue au lieu de break


async def dynamic_semaphore_adjuster(semaphore_holder: dict, stats_pbar: tqdm):
    """Ajuste dynamiquement le sémaphore selon les rate limits"""
    while True:
        await asyncio.sleep(5)  # Vérifier toutes les 5 secondes
        
        new_limit = rate_limiter.adjust_concurrency()
        
        # Mettre à jour le sémaphore (créer un nouveau, l'ancien se videra naturellement)
        semaphore_holder['current'] = asyncio.Semaphore(new_limit)
        
        # Mettre à jour la barre de stats
        stats = rate_limiter.get_stats()
        stats_msg = f"⚡ Concurrent={stats['max_concurrent']} | RPM={stats['current_rpm']:.0f} | Success={stats['success_rate']} | Total={stats['total_requests']}"
        
        if stats['detected_limit']:
            stats_msg += f" | Limit={stats['detected_limit']}"
        if stats['remaining'] is not None:
            stats_msg += f" | Remaining={stats['remaining']}"
        
        stats_pbar.set_description_str(stats_msg)
        stats_pbar.refresh()


async def traiter_film_async(json_file: Path, rapport_dir: Path, work_queue: asyncio.Queue, results_dict: dict, films_pbar: tqdm):
    """Ajoute les tâches d'un film à la file d'attente"""
    
    movie_name = json_file.stem
    movie_rapport_dir = rapport_dir / movie_name
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    nb_intervalles_total = len(data["intervalles"])
    
    if est_completement_traite(movie_rapport_dir, nb_intervalles_total):
        films_pbar.update(1)
        return
    
    movie_rapport_dir.mkdir(parents=True, exist_ok=True)
    
    style_file = movie_rapport_dir / "style.json"
    action_file = movie_rapport_dir / "action.json"
    
    if style_file.exists():
        with open(style_file, 'r', encoding='utf-8') as f:
            existing_style = json.load(f)
    else:
        existing_style = {
            "movie_id": data["movie_id"],
            "date_analyse": data["date_traitement"],
            "intervalles": []
        }
    
    if action_file.exists():
        with open(action_file, 'r', encoding='utf-8') as f:
            existing_action = json.load(f)
    else:
        existing_action = {
            "movie_id": data["movie_id"],
            "date_analyse": data["date_traitement"],
            "intervalles": []
        }
    
    style_indices_traites = {inter["intervalle_index"] for inter in existing_style["intervalles"]}
    action_indices_traites = {inter["intervalle_index"] for inter in existing_action["intervalles"]}
    
    results_dict[movie_name] = {
        'style': [],
        'action': [],
        'existing_style': existing_style,
        'existing_action': existing_action,
        'movie_id': data["movie_id"],
        'date_analyse': data["date_traitement"],
        'rapport_dir': movie_rapport_dir
    }
    
    # Ajouter seulement les intervalles valides
    for interval in data["intervalles"]:
        video_path = interval.get("video_path")
        
        # Vérifier que le video_path est valide
        if not video_path or not isinstance(video_path, (str, Path)):
            continue
        
        if not os.path.exists(video_path):
            continue
        
        # Vérifier si l'intervalle a déjà été traité
        intervalle_index = interval.get("intervalle_index")
        if intervalle_index in style_indices_traites and intervalle_index in action_indices_traites:
            continue
        
        await work_queue.put((interval, movie_name, style_indices_traites, action_indices_traites))


async def save_results_periodically(results_dict: dict, interval_seconds: int = 30):
    """Sauvegarde les résultats périodiquement"""
    while True:
        await asyncio.sleep(interval_seconds)
        
        for movie_name, data in results_dict.items():
            if 'rapport_dir' not in data:
                continue
            
            rapport_dir = data['rapport_dir']
            style_file = rapport_dir / "style.json"
            action_file = rapport_dir / "action.json"
            
            style_results = data['existing_style'].copy()
            style_results['intervalles'].extend(data['style'])
            
            action_results = data['existing_action'].copy()
            action_results['intervalles'].extend(data['action'])
            
            try:
                with open(style_file, 'w', encoding='utf-8') as f:
                    json.dump(style_results, f, ensure_ascii=False, indent=2)
                
                with open(action_file, 'w', encoding='utf-8') as f:
                    json.dump(action_results, f, ensure_ascii=False, indent=2)
            except Exception as e:
                tqdm.write(f"   ⚠ Erreur sauvegarde {movie_name}: {e}")


async def traiter_films_async():
    """Pipeline ultra-optimisé avec auto-régulation"""
    
    json_dir = Path("analyse/json")
    rapport_dir = Path("analyse/rapport")
    rapport_dir.mkdir(parents=True, exist_ok=True)
    
    json_files = list(json_dir.glob("*.json"))
    
    if not json_files:
        print("⚠ Aucun fichier JSON trouvé dans analyse/json/")
        return
    
    nb_films_deja_traites = 0
    total_intervals = 0
    for json_file in json_files:
        movie_rapport_dir = rapport_dir / json_file.stem
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        nb_intervalles_total = len(data["intervalles"])
        total_intervals += nb_intervalles_total
        if est_completement_traite(movie_rapport_dir, nb_intervalles_total):
            nb_films_deja_traites += 1
    
    print(f"\n📁 {len(json_files)} fichiers JSON trouvés")
    print(f"✓ {nb_films_deja_traites} déjà traités, {len(json_files) - nb_films_deja_traites} à traiter")
    print(f"📊 Total: ~{total_intervals} intervalles\n")
    
    work_queue = asyncio.Queue()
    frame_queue = asyncio.Queue()
    results_dict = {}
    semaphore_holder = {'current': asyncio.Semaphore(rate_limiter.max_concurrent)}
    
    films_pbar = tqdm(
        total=len(json_files),
        desc="🎬 Films",
        initial=nb_films_deja_traites,
        bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}',
        position=0
    )
    
    extraction_pbar = tqdm(
        total=total_intervals,
        desc="🎞️  Extraction",
        bar_format='{desc}: {n_fmt} | {rate_fmt}',
        position=1
    )
    
    requetes_pbar = tqdm(
        total=total_intervals * 2,
        desc="📡 API",
        bar_format='{desc}: {n_fmt} | {rate_fmt}',
        position=2
    )
    
    stats_pbar = tqdm(
        total=0,
        desc="⚡ Stats",
        bar_format='{desc}',
        position=3
    )
    
    start_time = time.time()
    
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS_FRAMES)
    
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=500)  # Haute limite pour le connector
    ) as session:
        
        # Lancer les workers d'extraction
        extraction_workers = [
            asyncio.create_task(frame_extractor_worker(executor, work_queue, frame_queue, extraction_pbar))
            for _ in range(MAX_WORKERS_FRAMES)
        ]
        
        # Lancer les workers API (beaucoup pour gérer la concurrence)
        api_workers = [
            asyncio.create_task(api_sender_worker(session, semaphore_holder['current'], frame_queue, results_dict, requetes_pbar))
            for _ in range(100)  # 100 workers qui se partagent le sémaphore
        ]
        
        # Lancer l'ajustement dynamique
        adjuster_task = asyncio.create_task(dynamic_semaphore_adjuster(semaphore_holder, stats_pbar))
        
        # Lancer la sauvegarde périodique
        save_task = asyncio.create_task(save_results_periodically(results_dict))
        
        # Ajouter tous les films
        film_tasks = []
        for json_file in json_files:
            task = asyncio.create_task(traiter_film_async(json_file, rapport_dir, work_queue, results_dict, films_pbar))
            film_tasks.append(task)
            
            if len(film_tasks) >= MAX_FILMS_PARALLEL:
                await asyncio.gather(*film_tasks)
                film_tasks = []
        
        if film_tasks:
            await asyncio.gather(*film_tasks)
        
        await work_queue.join()
        
        for _ in range(MAX_WORKERS_FRAMES):
            await work_queue.put(None)
        
        await asyncio.gather(*extraction_workers)
        
        await frame_queue.join()
        
        for _ in range(100):
            await frame_queue.put(None)
        
        await asyncio.gather(*api_workers)
        
        adjuster_task.cancel()
        save_task.cancel()
        
        # Sauvegarde finale
        for movie_name, data in results_dict.items():
            if 'rapport_dir' not in data:
                continue
            
            rapport_dir = data['rapport_dir']
            style_file = rapport_dir / "style.json"
            action_file = rapport_dir / "action.json"
            
            style_results = data['existing_style'].copy()
            style_results['intervalles'].extend(data['style'])
            
            action_results = data['existing_action'].copy()
            action_results['intervalles'].extend(data['action'])
            
            with open(style_file, 'w', encoding='utf-8') as f:
                json.dump(style_results, f, ensure_ascii=False, indent=2)
            
            with open(action_file, 'w', encoding='utf-8') as f:
                json.dump(action_results, f, ensure_ascii=False, indent=2)
            
            films_pbar.update(1)
    
    executor.shutdown()
    
    films_pbar.close()
    extraction_pbar.close()
    requetes_pbar.close()
    stats_pbar.close()
    
    elapsed_time = time.time() - start_time
    
    print("\n" + "="*60)
    print("📊 STATISTIQUES FINALES")
    print("="*60)
    final_stats = rate_limiter.get_stats()
    print(f"⏱️  Temps total: {elapsed_time:.1f}s")
    print(f"📡 Requêtes totales: {final_stats['total_requests']}")
    print(f"✓ Taux de succès: {final_stats['success_rate']}")
    print(f"⚡ Concurrence max atteinte: {final_stats['max_concurrent']}")
    print(f"🚀 Vitesse moyenne: {total_intervals / elapsed_time:.1f} intervalles/s")
    if final_stats['detected_limit']:
        print(f"🎯 Limite API détectée: {final_stats['detected_limit']} RPM")


def main():
    print("\n" + "="*60)
    print("🚀 ANALYSE AVEC AUTO-RÉGULATION INTELLIGENTE")
    print("="*60)
    print(f"✓ Modèle : {MODEL_ID}")
    print(f"✓ Frames par vidéo : {NUM_FRAMES}")
    print(f"⚡ Concurrence initiale : {rate_limiter.max_concurrent}")
    print(f"📈 Ajustement dynamique : OUI")
    print(f"🎯 Détection auto des limites : OUI")
    print(f"🔄 Retry automatique : OUI")
    print(f"💾 Sauvegarde continue : OUI")
    
    asyncio.run(traiter_films_async())
    
    print("\n✅ Tous les films ont été traités !")


if __name__ == "__main__":
    main()