#!/usr/bin/env python3
"""
Recalcule les scores emotional_intensity dans les JSON existants
en appliquant la formule VAD v2 directement sur les vad_signals déjà stockés.

Aucun appel à Gemma — traitement purement local et instantané.

Usage :
  python recalculate_scores.py                    # tous les films dans analyse/rapport/
  python recalculate_scores.py --dry-run          # aperçu sans modifier les fichiers
  python recalculate_scores.py --film "After the Wedding [2019...]"
"""

import os
import json
import glob
import argparse
from pathlib import Path

RAPPORT_DIR = "analyse/rapport"

# ---------------------------------------------------------------------------
# Formule VAD v2
# ---------------------------------------------------------------------------
AROUSAL_WEIGHT             = 0.6
VALENCE_WEIGHT             = 0.4
COOCCURRENCE_BONUS_PER_CUE = 0.3
PENALTY_SCENE_TRANSITION   = 0.5
PENALTY_STATIC_DIALOGUE    = 0.3
RAW_MAX_CALIBRATION        = 8.0


def compute_score_v2(vad_signals: dict) -> int:
    """Recalcule le score 0-100 avec la formule v2."""
    if not vad_signals:
        return 0

    arousal_cues = vad_signals.get("arousal_cues", {})
    valence_cues = vad_signals.get("valence_cues", {})
    neutral      = vad_signals.get("neutral_indicators", {})

    a_sum = sum(arousal_cues.values())
    v_sum = sum(valence_cues.values())

    base = AROUSAL_WEIGHT * a_sum + VALENCE_WEIGHT * v_sum

    all_cues = list(arousal_cues.values()) + list(valence_cues.values())
    n_active = sum(1 for v in all_cues if v > 0)
    bonus    = max(0, n_active - 1) * COOCCURRENCE_BONUS_PER_CUE

    penalty = (neutral.get("scene_transition", 0) * PENALTY_SCENE_TRANSITION
             + neutral.get("static_dialogue",   0) * PENALTY_STATIC_DIALOGUE)

    raw = max(0.0, base + bonus - penalty)
    return min(round(raw / RAW_MAX_CALIBRATION * 100), 100)


# ---------------------------------------------------------------------------
# Traitement d'un fichier
# ---------------------------------------------------------------------------

def recalculate_file(json_path: str, dry_run: bool = False) -> dict:
    """
    Relit un emotional_intensity.json, recalcule les scores,
    met à jour le fichier (sauf si dry_run).
    Retourne des stats : {n_updated, n_skipped, n_error, delta_mean, delta_max}
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    film_name  = data.get("movie_id", Path(json_path).parent.name)
    intervalles = data.get("intervalles", [])

    n_updated = 0
    n_skipped = 0
    n_error   = 0
    deltas    = []

    for iv in intervalles:
        status = iv.get("status")

        if status == "no_data":
            n_skipped += 1
            continue

        if status == "error" or iv.get("vad_signals") is None:
            n_error += 1
            continue

        old_score = iv.get("emotional_intensity", 0)
        new_score = compute_score_v2(iv["vad_signals"])
        delta     = new_score - (old_score or 0)

        deltas.append(delta)
        iv["emotional_intensity"] = new_score
        n_updated += 1

    # Met à jour la mention de méthode dans le header
    data["method"] = "VAD-arousal v2 (Russell 1980, Xu et al. 2012 — co-occurrence bonus)"

    if not dry_run:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    stats = {
        "film":       film_name,
        "n_updated":  n_updated,
        "n_skipped":  n_skipped,
        "n_error":    n_error,
        "delta_mean": round(sum(deltas) / len(deltas), 1) if deltas else 0,
        "delta_max":  max(deltas) if deltas else 0,
        "delta_min":  min(deltas) if deltas else 0,
    }
    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def find_all_json(base_dir: str) -> list[str]:
    pattern = os.path.join(base_dir, "**", "emotional_intensity.json")
    return sorted(glob.glob(pattern, recursive=True))


def main():
    parser = argparse.ArgumentParser(
        description="Recalcule les scores VAD v2 dans les JSON existants.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python recalculate_scores.py                             # tous les films
  python recalculate_scores.py --dry-run                   # aperçu sans modifier
  python recalculate_scores.py --film "After the Wedding"  # un seul film (sous-chaîne)
  python recalculate_scores.py --rapport-dir /mon/chemin   # dossier personnalisé
        """,
    )
    parser.add_argument("--rapport-dir", default=RAPPORT_DIR,
        help=f"Dossier racine des rapports (défaut: {RAPPORT_DIR})")
    parser.add_argument("--film", default=None,
        help="Filtre par nom de film (sous-chaîne, insensible à la casse)")
    parser.add_argument("--dry-run", action="store_true",
        help="Affiche les changements sans modifier les fichiers")
    args = parser.parse_args()

    json_files = find_all_json(args.rapport_dir)

    if args.film:
        json_files = [p for p in json_files
                      if args.film.lower() in str(Path(p).parent.name).lower()]

    if not json_files:
        print(f"❌ Aucun fichier emotional_intensity.json trouvé dans '{args.rapport_dir}'.")
        return

    if args.dry_run:
        print("🔍 Mode DRY-RUN — aucun fichier ne sera modifié\n")
    else:
        print(f"✏️  Recalcul des scores (formule VAD v2) — {len(json_files)} fichier(s)\n")

    print(f"{'Film':<45} {'OK':>5} {'Skip':>5} {'Err':>5}  {'Δmoy':>6}  {'Δmin':>6}  {'Δmax':>6}")
    print("─" * 85)

    total_updated = 0
    for path in json_files:
        try:
            stats = recalculate_file(path, dry_run=args.dry_run)
            name  = stats["film"]
            # Raccourcit le nom si trop long
            short = name if len(name) <= 44 else name[:41] + "…"
            status_icon = "✅" if not args.dry_run else "🔍"
            print(f"{status_icon} {short:<44} "
                  f"{stats['n_updated']:>5} {stats['n_skipped']:>5} {stats['n_error']:>5}  "
                  f"{stats['delta_mean']:>+6.1f}  {stats['delta_min']:>+6}  {stats['delta_max']:>+6}")
            total_updated += stats["n_updated"]
        except Exception as e:
            print(f"❌ {path} : {e}")

    print("─" * 85)
    action = "auraient été mis à jour" if args.dry_run else "mis à jour"
    print(f"\n✅ {total_updated} intervalles {action} au total.")

    if args.dry_run:
        print("\nRelance sans --dry-run pour appliquer les changements.")


if __name__ == "__main__":
    main()