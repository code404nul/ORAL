import json
import os
from pathlib import Path
from transformers import AutoProcessor, AutoModelForImageTextToText
from os.path import normpath
import torch

# Initialisation du modèle
model_id = "models/molmo2-4b"
processor = AutoProcessor.from_pretrained(
    model_id,
    trust_remote_code=True,
    dtype="auto",
    device_map="auto"
)
model = AutoModelForImageTextToText.from_pretrained(
    model_id,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    device_map="cuda"
)

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
        generated_ids = model.generate(**inputs, max_new_tokens=2048)
    generated_tokens = generated_ids[0, inputs['input_ids'].size(1):]
    return processor.tokenizer.decode(generated_tokens, skip_special_tokens=True)

def est_completement_traite(movie_rapport_dir, nb_intervalles_total):
    """Vérifie si tous les intervalles ont été traités"""
    style_file = movie_rapport_dir / "style.json"
    action_file = movie_rapport_dir / "action.json"
    
    # Si les fichiers n'existent pas
    if not style_file.exists() or not action_file.exists():
        return False
    
    try:
        # Charge les fichiers et vérifie le nombre d'intervalles
        with open(style_file, 'r', encoding='utf-8') as f:
            style_data = json.load(f)
        with open(action_file, 'r', encoding='utf-8') as f:
            action_data = json.load(f)
        
        nb_style = len(style_data.get("intervalles", []))
        nb_action = len(action_data.get("intervalles", []))
        
        # Retourne True seulement si tous les intervalles sont présents
        return nb_style == nb_intervalles_total and nb_action == nb_intervalles_total
    except Exception as e:
        print(f"  ⚠ Erreur lecture fichiers existants : {e}")
        return False

def traiter_films():
    """Traite tous les JSON non encore analysés"""
    
    # Dossiers
    json_dir = Path("analyse/json")
    rapport_dir = Path("analyse/rapport")
    rapport_dir.mkdir(parents=True, exist_ok=True)
    
    # Liste tous les fichiers JSON
    json_files = list(json_dir.glob("*.json"))
    
    for json_file in json_files:
        movie_name = json_file.stem
        movie_rapport_dir = rapport_dir / movie_name
        
        # Charge le JSON pour connaître le nombre d'intervalles
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nb_intervalles_total = len(data["intervalles"])
        
        # Vérifie si déjà complètement traité
        if est_completement_traite(movie_rapport_dir, nb_intervalles_total):
            print(f"✓ {movie_name} déjà traité ({nb_intervalles_total} intervalles), on passe au suivant")
            continue
        
        # Crée le dossier de rapport
        movie_rapport_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n{'='*60}")
        print(f"Traitement de : {movie_name}")
        print(f"{'='*60}")
        
        # Charge les résultats existants ou initialise
        style_file = movie_rapport_dir / "style.json"
        action_file = movie_rapport_dir / "action.json"
        
        if style_file.exists():
            with open(style_file, 'r', encoding='utf-8') as f:
                style_results = json.load(f)
            print(f"→ Reprise analyse style : {len(style_results['intervalles'])}/{nb_intervalles_total} intervalles déjà traités")
        else:
            style_results = {
                "movie_id": data["movie_id"],
                "date_analyse": data["date_traitement"],
                "intervalles": []
            }
        
        if action_file.exists():
            with open(action_file, 'r', encoding='utf-8') as f:
                action_results = json.load(f)
            print(f"→ Reprise analyse action : {len(action_results['intervalles'])}/{nb_intervalles_total} intervalles déjà traités")
        else:
            action_results = {
                "movie_id": data["movie_id"],
                "date_analyse": data["date_traitement"],
                "intervalles": []
            }
        
        # Récupère les indices déjà traités
        style_indices_traites = {inter["intervalle_index"] for inter in style_results["intervalles"]}
        action_indices_traites = {inter["intervalle_index"] for inter in action_results["intervalles"]}
        
        # Traite chaque intervalle
        for i, interval in enumerate(data["intervalles"]):
            intervalle_index = interval["intervalle_index"]
            print(f"\nIntervalle {i+1}/{nb_intervalles_total} - {interval['timecode_debut_extrait']}s à {interval['timecode_fin_extrait']}s")
            
            video_path = interval["video_path"]
            
            # Vérifie que la vidéo existe
            if not os.path.exists(video_path):
                print(f"  ⚠ Vidéo non trouvée : {video_path}")
                continue
            
            # Analyse du style (si pas déjà fait)
            if intervalle_index not in style_indices_traites:
                print("  → Analyse du style cinématographique...")
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
                    print(f"  ✓ Style analysé")
                except Exception as e:
                    print(f"  ✗ Erreur style : {e}")
                    style_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_style": f"ERREUR: {str(e)}"
                    })
                
                # Sauvegarde intermédiaire du style
                with open(style_file, 'w', encoding='utf-8') as f:
                    json.dump(style_results, f, ensure_ascii=False, indent=2)
            else:
                print("  ✓ Style déjà analysé")
            
            # Analyse de l'action (si pas déjà fait)
            if intervalle_index not in action_indices_traites:
                print("  → Analyse de l'action...")
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
                    print(f"  ✓ Action analysée")
                except Exception as e:
                    print(f"  ✗ Erreur action : {e}")
                    action_results["intervalles"].append({
                        "intervalle_index": intervalle_index,
                        "intervalle_debut": interval["intervalle_debut"],
                        "intervalle_fin": interval["intervalle_fin"],
                        "analyse_action": f"ERREUR: {str(e)}"
                    })
                
                # Sauvegarde intermédiaire de l'action
                with open(action_file, 'w', encoding='utf-8') as f:
                    json.dump(action_results, f, ensure_ascii=False, indent=2)
            else:
                print("  ✓ Action déjà analysée")
        
        print(f"\n✓ Traitement terminé pour {movie_name}")
        print(f"  - Rapports sauvegardés dans : {movie_rapport_dir}")

if __name__ == "__main__":
    print("Démarrage de l'analyse des films...")
    traiter_films()
    print("\n✓ Tous les films ont été traités !")