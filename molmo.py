import json
import os
from pathlib import Path
from transformers import AutoProcessor, AutoModelForImageTextToText
from os.path import normpath
import torch
import gc
from tqdm import tqdm
import time

print("🚀 Démarrage du script...")

# Vérifications initiales
print(f"✓ CUDA disponible : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"✓ GPU : {torch.cuda.get_device_name(0)}")
    print(f"✓ VRAM totale : {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print(f"✓ VRAM libre : {torch.cuda.mem_get_info()[0] / 1024**3:.1f} GB")

# Nettoyage mémoire avant de commencer
torch.cuda.empty_cache()
gc.collect()

print("\n📦 Chargement du processeur...")
model_id = "models/molmo2-4b"
try:
    processor = AutoProcessor.from_pretrained(
        model_id,
        trust_remote_code=True,
        use_fast=True,
    )
    print("✓ Processeur chargé")
except Exception as e:
    print(f"❌ Erreur processeur : {e}")
    exit(1)

print("\n🧠 Chargement du modèle (cela peut prendre 1-2 minutes)...")
try:
    model = AutoModelForImageTextToText.from_pretrained(
        model_id,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    print("✓ Modèle chargé")
    print(f"✓ Device du modèle : {model.device}")
except Exception as e:
    print(f"❌ Erreur modèle : {e}")
    print("\n💡 Suggestions :")
    print("  1. Ton GPU manque peut-être de VRAM (besoin ~8-10GB)")
    print("  2. Ferme les autres programmes utilisant le GPU")
    print("  3. Essaie de charger en CPU avec device_map='cpu' (beaucoup plus lent)")
    exit(1)

# Optimisations (optionnelles, à activer après le chargement)
try:
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    print("✓ Optimisations CUDA activées")
except:
    pass

def ask_molmo(text_input, video_path):
    """Fonction pour interroger Molmo2 avec une vidéo"""
    messages = [
        {
            "role": "user",
            "content": [
                dict(type="text", text=text_input),
                dict(type="video", video=normpath(video_path)),
            ],
        }
    ]
    
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    )
    
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    
    with torch.inference_mode():
        generated_ids = model.generate(
            **inputs, 
            max_new_tokens=512,
            do_sample=False,
            num_beams=1,
            use_cache=True,
        )
    
    generated_tokens = generated_ids[0, inputs['input_ids'].size(1):]
    result = processor.tokenizer.decode(generated_tokens, skip_special_tokens=True)
    
    # Nettoyage
    del inputs, generated_ids, generated_tokens
    torch.cuda.empty_cache()
    
    return result

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
            
            # CORRECTION ICI : Vérifier si video_path existe et n'est pas None
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
                    style_response = ask_molmo(
                        "Explain the cinematographic techniques to me; what emotion did the director want to convey?",
                        video_path
                    )
                    style_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_style": style_response
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
                    action_response = ask_molmo(
                        "What is happening in the scene?",
                        video_path
                    )
                    action_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_action": action_response
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
    
    temps_total = time.time() - temps_debut_global
    print(f"\n⏱️ Temps total d'exécution : {format_time(temps_total)}")
    if len(temps_analyses) > 0:
        print(f"📊 Temps moyen par analyse : {sum(temps_analyses)/len(temps_analyses):.1f}s")
        print(f"📊 Nombre total d'analyses effectuées : {len(temps_analyses)}")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎬 ANALYSE DE FILMS AVEC MOLMO2")
    print("="*60)
    
    traiter_films()
    
    print("\n✅ Tous les films ont été traités !")