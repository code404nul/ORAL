import json
import os
from pathlib import Path
import requests
import base64
from tqdm import tqdm
import cv2
import tempfile

print("🚀 Démarrage du script...")

# Configuration de l'API Fireworks
API_KEY = "fw_9jPTovViK51DBPKw7ukvDm"
API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
MODEL_ID = "accounts/code404nul/deployments/uizk7clq"

# Configuration extraction frames
NUM_FRAMES = 6  # Nombre de frames à extraire par vidéo

def extract_frames_from_video(video_path, num_frames=8):
    """Extrait des frames uniformément réparties d'une vidéo"""
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        raise Exception(f"Impossible d'ouvrir la vidéo: {video_path}")
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames == 0:
        cap.release()
        raise Exception(f"La vidéo ne contient aucune frame: {video_path}")
    
    # Calculer les indices des frames à extraire
    frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
    
    frames_base64 = []
    
    for frame_idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        
        if ret:
            # Encoder la frame en JPEG puis en base64
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            frames_base64.append(frame_base64)
    
    cap.release()
    
    return frames_base64

def ask_molmo_api(text_input, video_path):
    """Fonction pour interroger Molmo8b via l'API Fireworks avec des frames"""
    
    # Extraire les frames de la vidéo
    try:
        frames_base64 = extract_frames_from_video(video_path, NUM_FRAMES)
    except Exception as e:
        raise Exception(f"Erreur lors de l'extraction des frames: {e}")
    
    if not frames_base64:
        raise Exception("Aucune frame extraite de la vidéo")
    
    # Construire le contenu avec texte + frames
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
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.exceptions.HTTPError as e:
        # Afficher plus de détails sur l'erreur
        error_detail = ""
        try:
            error_detail = response.json()
        except:
            error_detail = response.text
        raise Exception(f"Erreur API HTTP {response.status_code}: {error_detail}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Erreur API: {e}")

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

def traiter_films():
    """Traite tous les JSON non encore analysés"""
    
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
    
    # Barre de progression pour les films
    films_pbar = tqdm(json_files, desc="🎬 Films", position=0, leave=True, 
                      initial=nb_films_deja_traites,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} films')
    
    for json_file in films_pbar:
        movie_name = json_file.stem
        movie_rapport_dir = rapport_dir / movie_name
        
        films_pbar.set_description(f"🎬 Films [{movie_name[:40]}...]")
        
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
            
            video_path = interval["video_path"]
            
            if not os.path.exists(video_path):
                tqdm.write(f"  ⚠ Vidéo non trouvée : {video_path}")
                continue
            
            # Style
            if intervalle_index not in style_indices_traites:
                intervalles_pbar.set_description(f"📹 Intervalles [{timecode}] - Style")
                try:
                    style_response = ask_molmo_api(
                        "Explain the cinematographic techniques to me; what emotion did the director want to convey?",
                        video_path
                    )
                    style_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_style": style_response
                    })
                except Exception as e:
                    tqdm.write(f"  ✗ Erreur style (intervalle {intervalle_index}): {e}")
                    style_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_style": f"ERREUR: {str(e)}"
                    })
                
                with open(style_file, 'w', encoding='utf-8') as f:
                    json.dump(style_results, f, ensure_ascii=False, indent=2)
            
            # Action
            if intervalle_index not in action_indices_traites:
                intervalles_pbar.set_description(f"📹 Intervalles [{timecode}] - Action")
                try:
                    action_response = ask_molmo_api(
                        "What is happening in the scene?",
                        video_path
                    )
                    action_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_action": action_response
                    })
                except Exception as e:
                    tqdm.write(f"  ✗ Erreur action (intervalle {intervalle_index}): {e}")
                    action_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_action": f"ERREUR: {str(e)}"
                    })
                
                with open(action_file, 'w', encoding='utf-8') as f:
                    json.dump(action_results, f, ensure_ascii=False, indent=2)
            
            intervalles_pbar.set_description("📹 Intervalles")
        
        intervalles_pbar.close()
        tqdm.write(f"✓ {movie_name} terminé ({nb_intervalles_total} intervalles)")
    
    films_pbar.close()

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎬 ANALYSE DE FILMS AVEC MOLMO8B (API FIREWORKS)")
    print("="*60)
    print(f"✓ API configurée")
    print(f"✓ Modèle : {MODEL_ID}")
    print(f"✓ Max tokens : 512")
    print(f"✓ Frames extraites par vidéo : {NUM_FRAMES}")
    
    traiter_films()
    
    print("\n✅ Tous les films ont été traités !")