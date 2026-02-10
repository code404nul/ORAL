import json
import os
from pathlib import Path
from transformers import AutoProcessor, AutoModelForImageTextToText
from os.path import normpath
import torch
import gc

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
        use_fast=True,  # ← Ajoute ceci pour éviter le warning
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
        torch_dtype=torch.float16,  # ← Enlève le paramètre deprecated
        device_map="auto",  # ← Laisse auto gérer
        low_cpu_mem_usage=True,  # ← Important pour éviter les OOM
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
    
    print(f"  → Preprocessing...")
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    )
    
    print(f"  → Transfert GPU...")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    
    print(f"  → Génération...")
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
        print(f"  ⚠ Erreur lecture fichiers existants : {e}")
        return False

def traiter_films():
    """Traite tous les JSON non encore analysés"""
    
    json_dir = Path("analyse/json")
    rapport_dir = Path("analyse/rapport")
    rapport_dir.mkdir(parents=True, exist_ok=True)
    
    json_files = list(json_dir.glob("*.json"))
    print(f"\n📁 {len(json_files)} fichiers JSON trouvés")
    
    for json_file in json_files:
        movie_name = json_file.stem
        movie_rapport_dir = rapport_dir / movie_name
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nb_intervalles_total = len(data["intervalles"])
        
        if est_completement_traite(movie_rapport_dir, nb_intervalles_total):
            print(f"✓ {movie_name} déjà traité ({nb_intervalles_total} intervalles), skip")
            continue
        
        movie_rapport_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n{'='*60}")
        print(f"Traitement de : {movie_name}")
        print(f"{'='*60}")
        
        style_file = movie_rapport_dir / "style.json"
        action_file = movie_rapport_dir / "action.json"
        
        if style_file.exists():
            with open(style_file, 'r', encoding='utf-8') as f:
                style_results = json.load(f)
            print(f"→ Reprise analyse style : {len(style_results['intervalles'])}/{nb_intervalles_total}")
        else:
            style_results = {
                "movie_id": data["movie_id"],
                "date_analyse": data["date_traitement"],
                "intervalles": []
            }
        
        if action_file.exists():
            with open(action_file, 'r', encoding='utf-8') as f:
                action_results = json.load(f)
            print(f"→ Reprise analyse action : {len(action_results['intervalles'])}/{nb_intervalles_total}")
        else:
            action_results = {
                "movie_id": data["movie_id"],
                "date_analyse": data["date_traitement"],
                "intervalles": []
            }
        
        style_indices_traites = {inter["intervalle_index"] for inter in style_results["intervalles"]}
        action_indices_traites = {inter["intervalle_index"] for inter in action_results["intervalles"]}
        
        for i, interval in enumerate(data["intervalles"]):
            intervalle_index = interval["intervalle_index"]
            print(f"\nIntervalle {i+1}/{nb_intervalles_total} - {interval['timecode_debut_extrait']}s à {interval['timecode_fin_extrait']}s")
            
            video_path = interval["video_path"]
            
            if not os.path.exists(video_path):
                print(f"  ⚠ Vidéo non trouvée : {video_path}")
                continue
            
            # Style
            if intervalle_index not in style_indices_traites:
                print("  → Analyse du style...")
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
                
                with open(style_file, 'w', encoding='utf-8') as f:
                    json.dump(style_results, f, ensure_ascii=False, indent=2)
            else:
                print("  ✓ Style déjà analysé")
            
            # Action
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
                
                with open(action_file, 'w', encoding='utf-8') as f:
                    json.dump(action_results, f, ensure_ascii=False, indent=2)
            else:
                print("  ✓ Action déjà analysée")
        
        print(f"\n✓ Traitement terminé pour {movie_name}")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎬 ANALYSE DE FILMS AVEC MOLMO2")
    print("="*60)
    
    traiter_films()
    
    print("\n✅ Tous les films ont été traités !")