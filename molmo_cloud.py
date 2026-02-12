"""
Script d'analyse de films avec Molmo2-8B via OpenRouter API
Analyse les vidéos avec des questions sur les techniques cinématographiques et les actions
"""

import json
import os
from pathlib import Path
import requests
import base64
from tqdm import tqdm
import time

print("🚀 Démarrage du script avec OpenRouter API...")

class Molmo2OpenRouterAnalyzer:
    """Classe pour analyser des vidéos avec Molmo2-8B via OpenRouter"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "allenai/molmo-2-8b"
        
        # Prix par million de tokens
        self.price_input = 0.20
        self.price_output = 0.20
        
        # Statistiques de session
        self.total_tokens_input = 0
        self.total_tokens_output = 0
        self.total_analyses = 0
    
    def encode_video_to_base64(self, video_path: str) -> str:
        """
        Encoder une vidéo locale en base64
        
        Args:
            video_path: Chemin vers le fichier vidéo
            
        Returns:
            Vidéo encodée en base64
        """
        video_path = str(Path(video_path).resolve())
        
        if not Path(video_path).exists():
            raise FileNotFoundError(f"Le fichier n'existe pas: {video_path}")
        
        with open(video_path, "rb") as video_file:
            video_bytes = video_file.read()
        
        if len(video_bytes) == 0:
            raise ValueError(f"Le fichier vidéo est vide: {video_path}")
        
        video_base64 = base64.b64encode(video_bytes).decode("utf-8")
        return video_base64
    
    def analyze_video(self, video_path: str, prompt: str) -> tuple[str, dict]:
        """
        Analyser une vidéo locale
        
        Args:
            video_path: Chemin vers le fichier vidéo local
            prompt: Question/instruction pour le modèle
            
        Returns:
            Tuple (réponse du modèle, statistiques d'usage)
        """
        # Détecter le format vidéo
        video_extension = Path(video_path).suffix.lower()
        mime_types = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".mpeg": "video/mpeg"
        }
        
        mime_type = mime_types.get(video_extension, "video/mp4")
        
        # Encoder la vidéo
        video_base64 = self.encode_video_to_base64(video_path)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "max_tokens": 1024,  # Limite la longueur de la réponse
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "video_url",
                            "video_url": {
                                "url": f"data:{mime_type};base64,{video_base64}"
                            }
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(self.base_url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        # Extraire le contenu
        content = ""
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
        
        # Extraire les statistiques d'usage
        usage_stats = {}
        if "usage" in result:
            usage = result["usage"]
            usage_stats = {
                "prompt_tokens": usage.get('prompt_tokens', 0),
                "completion_tokens": usage.get('completion_tokens', 0),
                "total_tokens": usage.get('total_tokens', 0)
            }
            
            # Mettre à jour les statistiques de session
            self.total_tokens_input += usage_stats["prompt_tokens"]
            self.total_tokens_output += usage_stats["completion_tokens"]
            self.total_analyses += 1
        
        return content, usage_stats
    
    def get_session_cost(self) -> dict:
        """Calculer le coût total de la session"""
        cost_input = (self.total_tokens_input / 1_000_000) * self.price_input
        cost_output = (self.total_tokens_output / 1_000_000) * self.price_output
        total_cost = cost_input + cost_output
        
        return {
            "total_tokens_input": self.total_tokens_input,
            "total_tokens_output": self.total_tokens_output,
            "total_tokens": self.total_tokens_input + self.total_tokens_output,
            "cost_input": cost_input,
            "cost_output": cost_output,
            "total_cost": total_cost,
            "total_analyses": self.total_analyses
        }


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


def get_progress_info(movie_rapport_dir):
    """Récupère le nombre d'intervalles déjà traités"""
    style_file = movie_rapport_dir / "style.json"
    action_file = movie_rapport_dir / "action.json"
    
    nb_style = 0
    nb_action = 0
    
    if style_file.exists():
        try:
            with open(style_file, 'r', encoding='utf-8') as f:
                style_data = json.load(f)
                nb_style = len(style_data.get("intervalles", []))
        except:
            pass
    
    if action_file.exists():
        try:
            with open(action_file, 'r', encoding='utf-8') as f:
                action_data = json.load(f)
                nb_action = len(action_data.get("intervalles", []))
        except:
            pass
    
    return nb_style, nb_action


def format_time(seconds):
    """Formate le temps en heures, minutes, secondes"""
    if seconds < 0:
        return "Calcul..."
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    elif minutes > 0:
        return f"{minutes}m{secs:02d}s"
    else:
        return f"{secs}s"


def calculer_analyses_restantes(json_files, rapport_dir, film_index_actuel, intervalle_actuel, style_traite, action_traite):
    """Calcule le nombre total d'analyses restantes"""
    nb_restantes = 0
    
    for idx, json_file in enumerate(json_files):
        movie_rapport_dir = rapport_dir / json_file.stem
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nb_intervalles = len(data["intervalles"])
        
        # Si le film est complètement traité, on passe
        if est_completement_traite(movie_rapport_dir, nb_intervalles):
            continue
        
        if idx < film_index_actuel:
            # Films déjà passés
            continue
        elif idx == film_index_actuel:
            # Film en cours : compter à partir de l'intervalle actuel
            style_indices, action_indices = set(), set()
            
            if (movie_rapport_dir / "style.json").exists():
                with open(movie_rapport_dir / "style.json", 'r', encoding='utf-8') as f:
                    style_data = json.load(f)
                    style_indices = {inter["intervalle_index"] for inter in style_data["intervalles"]}
            
            if (movie_rapport_dir / "action.json").exists():
                with open(movie_rapport_dir / "action.json", 'r', encoding='utf-8') as f:
                    action_data = json.load(f)
                    action_indices = {inter["intervalle_index"] for inter in action_data["intervalles"]}
            
            for i in range(intervalle_actuel, nb_intervalles):
                intervalle_index = data["intervalles"][i]["intervalle_index"]
                
                if i == intervalle_actuel:
                    # Intervalle en cours
                    if not style_traite:
                        nb_restantes += 1
                    if not action_traite:
                        nb_restantes += 1
                else:
                    # Intervalles suivants
                    if intervalle_index not in style_indices:
                        nb_restantes += 1
                    if intervalle_index not in action_indices:
                        nb_restantes += 1
        else:
            # Films suivants
            nb_style, nb_action = get_progress_info(movie_rapport_dir)
            nb_restantes += (2 * nb_intervalles - nb_style - nb_action)
    
    return nb_restantes


def traiter_films(api_key: str):
    """Traite tous les JSON non encore analysés"""
    
    # Initialiser l'analyseur
    analyzer = Molmo2OpenRouterAnalyzer(api_key)
    
    json_dir = Path("analyse/json")
    rapport_dir = Path("analyse/rapport")
    rapport_dir.mkdir(parents=True, exist_ok=True)
    
    json_files = list(json_dir.glob("*.json"))
    
    if not json_files:
        print("⚠ Aucun fichier JSON trouvé dans analyse/json/")
        return
    
    # Compter d'abord les films déjà traités
    nb_films_deja_traites = 0
    for json_file in json_files:
        movie_rapport_dir = rapport_dir / json_file.stem
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        nb_intervalles_total = len(data["intervalles"])
        if est_completement_traite(movie_rapport_dir, nb_intervalles_total):
            nb_films_deja_traites += 1
    
    print(f"\n📁 {len(json_files)} fichiers JSON trouvés")
    print(f"✓ {nb_films_deja_traites} déjà traités, {len(json_files) - nb_films_deja_traites} à traiter\n")
    
    # Variables pour le calcul du temps
    temps_debut_global = time.time()
    temps_analyses = []  # Liste des temps pour chaque analyse
    
    # Barre de progression pour les films
    films_pbar = tqdm(json_files, desc="🎬 Films", position=0, leave=True, 
                      initial=nb_films_deja_traites,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} films')
    
    for film_idx, json_file in enumerate(films_pbar):
        movie_name = json_file.stem
        movie_rapport_dir = rapport_dir / movie_name
        
        films_pbar.set_description(f"🎬 Films [{movie_name[:50]}...]" if len(movie_name) > 50 else f"🎬 Films [{movie_name}]")
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nb_intervalles_total = len(data["intervalles"])
        
        if est_completement_traite(movie_rapport_dir, nb_intervalles_total):
            # Film déjà traité, on passe au suivant silencieusement
            continue
        
        movie_rapport_dir.mkdir(parents=True, exist_ok=True)
        
        style_file = movie_rapport_dir / "style.json"
        action_file = movie_rapport_dir / "action.json"
        
        if style_file.exists():
            with open(style_file, 'r', encoding='utf-8') as f:
                style_results = json.load(f)
        else:
            style_results = {
                "movie_id": data["movie_id"],
                "date_analyse": data["date_traitement"],
                "intervalles": []
            }
        
        if action_file.exists():
            with open(action_file, 'r', encoding='utf-8') as f:
                action_results = json.load(f)
        else:
            action_results = {
                "movie_id": data["movie_id"],
                "date_analyse": data["date_traitement"],
                "intervalles": []
            }
        
        style_indices_traites = {inter["intervalle_index"] for inter in style_results["intervalles"]}
        action_indices_traites = {inter["intervalle_index"] for inter in action_results["intervalles"]}
        
        # Calculer le nombre d'intervalles déjà traités
        nb_deja_traites = len(style_indices_traites & action_indices_traites)
        
        # Barre de progression pour les intervalles
        intervalles_pbar = tqdm(enumerate(data["intervalles"]), 
                               total=nb_intervalles_total,
                               desc="📹 Intervalles", 
                               position=1, 
                               leave=False,
                               initial=nb_deja_traites,
                               bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}')
        
        for i, interval in intervalles_pbar:
            intervalle_index = interval["intervalle_index"]
            timecode = f"{interval['timecode_debut_extrait']}s-{interval['timecode_fin_extrait']}s"
            
            # Vérifier si video_path existe et n'est pas None
            video_path = interval.get("video_path")
            
            if video_path is None:
                tqdm.write(f"  ⚠ Chemin vidéo manquant pour l'intervalle {intervalle_index} (timecode: {timecode})")
                continue
            
            if not os.path.exists(video_path):
                tqdm.write(f"  ⚠ Vidéo non trouvée : {video_path}")
                continue
            
            style_fait_cet_intervalle = intervalle_index in style_indices_traites
            action_fait_cet_intervalle = intervalle_index in action_indices_traites
            
            # Style
            if not style_fait_cet_intervalle:
                temps_debut_analyse = time.time()
                
                # Calculer les analyses restantes AVANT cette analyse
                nb_restantes = calculer_analyses_restantes(
                    json_files, rapport_dir, film_idx, i, 
                    style_traite=False, action_traite=action_fait_cet_intervalle
                )
                
                # Afficher estimation si on a déjà des données
                if len(temps_analyses) >= 3:
                    temps_moyen = sum(temps_analyses) / len(temps_analyses)
                    temps_restant = nb_restantes * temps_moyen
                    intervalles_pbar.set_description(
                        f"📹 [{timecode}] Style - ⏱️ {format_time(temps_restant)} (moy:{temps_moyen:.1f}s)"
                    )
                else:
                    intervalles_pbar.set_description(f"📹 [{timecode}] Style - ⏱️ Calcul...")
                
                try:
                    style_response, usage_stats = analyzer.analyze_video(
                        video_path,
                        "Explain the cinematographic techniques to me; what emotion did the director want to convey?"
                    )
                    style_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_style": style_response,
                        "tokens": usage_stats
                    })
                    style_indices_traites.add(intervalle_index)
                except Exception as e:
                    tqdm.write(f"  ✗ Erreur style (intervalle {intervalle_index}): {e}")
                    style_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_style": f"ERREUR: {str(e)}"
                    })
                
                temps_analyses.append(time.time() - temps_debut_analyse)
                
                with open(style_file, 'w', encoding='utf-8') as f:
                    json.dump(style_results, f, ensure_ascii=False, indent=2)
            
            # Action
            if not action_fait_cet_intervalle:
                temps_debut_analyse = time.time()
                
                # Calculer les analyses restantes AVANT cette analyse
                nb_restantes = calculer_analyses_restantes(
                    json_files, rapport_dir, film_idx, i, 
                    style_traite=True, action_traite=False
                )
                
                # Afficher estimation si on a déjà des données
                if len(temps_analyses) >= 3:
                    temps_moyen = sum(temps_analyses) / len(temps_analyses)
                    temps_restant = nb_restantes * temps_moyen
                    intervalles_pbar.set_description(
                        f"📹 [{timecode}] Action - ⏱️ {format_time(temps_restant)} (moy:{temps_moyen:.1f}s)"
                    )
                else:
                    intervalles_pbar.set_description(f"📹 [{timecode}] Action - ⏱️ Calcul...")
                
                try:
                    action_response, usage_stats = analyzer.analyze_video(
                        video_path,
                        "What is happening in the scene?"
                    )
                    action_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_action": action_response,
                        "tokens": usage_stats
                    })
                    action_indices_traites.add(intervalle_index)
                except Exception as e:
                    tqdm.write(f"  ✗ Erreur action (intervalle {intervalle_index}): {e}")
                    action_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_action": f"ERREUR: {str(e)}"
                    })
                
                temps_analyses.append(time.time() - temps_debut_analyse)
                
                with open(action_file, 'w', encoding='utf-8') as f:
                    json.dump(action_results, f, ensure_ascii=False, indent=2)
        
        intervalles_pbar.close()
        tqdm.write(f"✓ {movie_name} terminé ({nb_intervalles_total} intervalles)")
    
    films_pbar.close()
    
    # Afficher les statistiques finales
    temps_total = time.time() - temps_debut_global
    print(f"\n⏱️ Temps total d'exécution : {format_time(temps_total)}")
    if len(temps_analyses) > 0:
        print(f"📊 Temps moyen par analyse : {sum(temps_analyses)/len(temps_analyses):.1f}s")
        print(f"📊 Nombre total d'analyses effectuées : {len(temps_analyses)}")
    
    # Afficher les coûts
    session_cost = analyzer.get_session_cost()
    print(f"\n💰 COÛTS DE LA SESSION")
    print(f"   Tokens d'entrée: {session_cost['total_tokens_input']:,}")
    print(f"   Tokens de sortie: {session_cost['total_tokens_output']:,}")
    print(f"   Total tokens: {session_cost['total_tokens']:,}")
    print(f"   Coût entrée: ${session_cost['cost_input']:.6f}")
    print(f"   Coût sortie: ${session_cost['cost_output']:.6f}")
    print(f"   COÛT TOTAL: ${session_cost['total_cost']:.4f}")
    print(f"   Nombre d'analyses: {session_cost['total_analyses']}")
    if session_cost['total_analyses'] > 0:
        print(f"   Coût moyen par analyse: ${session_cost['total_cost']/session_cost['total_analyses']:.6f}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎬 ANALYSE DE FILMS AVEC MOLMO2 via OpenRouter")
    print("="*60)
    
    # IMPORTANT: Remplacez par votre clé API OpenRouter
    API_KEY = "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"
    
    if API_KEY == "VOTRE_CLÉ_API_ICI":
        print("\n❌ ERREUR: Vous devez remplacer 'VOTRE_CLÉ_API_ICI' par votre vraie clé API OpenRouter")
        print("   Obtenez une clé ici: https://openrouter.ai/settings/keys")
        print("   Modifiez la ligne API_KEY dans ce fichier")
    else:
        print(f"\n⚠️  AVERTISSEMENT: Ce script utilise l'API OpenRouter (payante)")
        print(f"   Prix: 0.20$/M tokens (entrée et sortie)")
        print(f"   Estimation: ~$0.0012 - $0.0024 par vidéo de 15s")
        print(f"\n   Assurez-vous d'avoir des crédits sur votre compte OpenRouter!\n")
        
        traiter_films(API_KEY)
        
        print("\n✅ Tous les films ont été traités !")