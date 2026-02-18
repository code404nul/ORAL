#!/usr/bin/env python3
"""
Script pour supprimer les vidéos avec un intervalle de 50 secondes
dans le dossier analyse/videos
"""

import os
import re
from pathlib import Path

def supprimer_videos_50s(dossier_racine="analyse/videos"):
    """
    Supprime toutes les vidéos dont l'intervalle de temps est de 50 secondes.
    Par exemple: interval_0001_time_50.00s-100.00s.mp4
    """
    
    # Pattern pour détecter les fichiers avec intervalle de 50s
    # Recherche: time_XX.XXs-YY.YYs.mp4 où la différence est 50s
    pattern = re.compile(r'time_(\d+\.?\d*)s-(\d+\.?\d*)s\.mp4$')
    
    fichiers_supprimes = []
    fichiers_non_supprimes = []
    
    # Parcourir tous les fichiers dans le dossier et ses sous-dossiers
    for root, dirs, files in os.walk(dossier_racine):
        for filename in files:
            match = pattern.search(filename)
            if match:
                debut = float(match.group(1))
                fin = float(match.group(2))
                intervalle = fin - debut
                
                # Si l'intervalle est de 50 secondes (avec une petite marge pour les erreurs d'arrondi)
                if abs(intervalle - 50.0) < 0.1:
                    filepath = os.path.join(root, filename)
                    try:
                        os.remove(filepath)
                        fichiers_supprimes.append(filepath)
                        print(f"✓ Supprimé: {filepath}")
                    except Exception as e:
                        print(f"✗ Erreur lors de la suppression de {filepath}: {e}")
                        fichiers_non_supprimes.append(filepath)
    
    # Résumé
    print("\n" + "="*70)
    print(f"RÉSUMÉ:")
    print(f"  Fichiers supprimés: {len(fichiers_supprimes)}")
    print(f"  Erreurs: {len(fichiers_non_supprimes)}")
    print("="*70)
    
    if fichiers_non_supprimes:
        print("\nFichiers non supprimés (erreurs):")
        for f in fichiers_non_supprimes:
            print(f"  - {f}")
    
    return fichiers_supprimes, fichiers_non_supprimes


if __name__ == "__main__":
    print("Recherche et suppression des vidéos avec intervalle de 50 secondes...")
    print("Dossier cible: analyse/videos\n")
    
    # Vérifier que le dossier existe
    if not os.path.exists("analyse/videos"):
        print("❌ Le dossier 'analyse/videos' n'existe pas!")
        print("Veuillez exécuter ce script depuis le bon répertoire.")
        exit(1)
    
    # Demander confirmation
    reponse = input("Voulez-vous continuer? (oui/non): ").strip().lower()
    if reponse not in ['oui', 'o', 'yes', 'y']:
        print("Opération annulée.")
        exit(0)
    
    print("\nSuppression en cours...\n")
    supprimer_videos_50s()