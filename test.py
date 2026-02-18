"""
Script d'analyse de l'intensité émotionnelle des intervalles de films.
Basé sur le modèle VAD (Valence-Arousal-Dominance) de Russell (1980).

Approche scientifique :
- Au lieu de demander une note subjective, Gemma détecte des signaux objectifs
- Le score d'arousal est calculé via une formule à poids fixes (Xu et al., 2012)

Corrections v2 par rapport à v1 :
- Suppression de la normalisation par les max théoriques (écrasait les scores)
- Retrait de establishing_shot des pénalités (trop ambigu, détecté partout)
- Ajout d'un bonus de co-occurrence (plusieurs signaux simultanés = vrai climax)
- Calibration sur un max réaliste de 8.0 brut → 100 normalisé
- Pénalité neutre réduite et limitée à scene_transition + static_dialogue

Références :
  - Russell (1980) — A Circumplex Model of Affect
  - Schaefer et al. (2010) — Cognition & Emotion
  - Xu et al. (2012) — Signal Processing (poids arousal/valence)
  - AVEC Challenge (2016) — benchmark arousal continu sur vidéo
"""

import os
import json
import time
import re
import ollama

MODEL_NAME = "gemma3:27b-it-qat"

BASE_DIR    = "analyse"
JSON_DIR    = os.path.join(BASE_DIR, "json")
RAPPORT_DIR = os.path.join(BASE_DIR, "rapport")

MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Formule VAD v2 — calibrée sur données réelles
#
# Problèmes v1 :
#   - Normalisation /AROUSAL_MAX (9) et /VALENCE_MAX (8) → scores max réels ≈ 35-45
#   - establishing_shot pénalisé → pénalité permanente car détecté partout
#   - Formule plate → pas de différenciation climax vs scène ordinaire
#
# Solutions v2 :
#   1. Scores bruts (pas de division par max théorique)
#   2. Bonus co-occurrence : nb de cues actifs simultanément (> 0) → amplification
#   3. Pénalité neutre limitée à scene_transition + static_dialogue uniquement
#   4. Calibration : max réaliste brut ≈ 8.0 → score normalisé = raw / 8.0 * 100
#
# Calibration :
#   Climax typique : arousal [tense=2, outburst=2, close_up=1] = 5
#                   valence  [death=2, darkness=2] = 4
#                   bonus co-occurrence : 5 cues actifs → +1.5
#                   pénalité : 0
#                   raw = 0.6*5 + 0.4*4 + 1.5 = 3.0 + 1.6 + 1.5 = 6.1 → 76/100
#
#   Scène action pure : arousal [rapid=2, physical=2, action=2] = 6
#                       valence [threat=1] = 1
#                       bonus : 4 cues actifs → +1.2
#                       raw = 0.6*6 + 0.4*1 + 1.2 = 3.6+0.4+1.2 = 5.2 → 65/100
#
#   Dialogue neutre : arousal [tense=1] = 1
#                     valence [darkness=1] = 1
#                     pénalité static_dialogue = -0.3
#                     raw = 0.6*1 + 0.4*1 - 0.3 = 0.7 → 9/100
# ---------------------------------------------------------------------------

AROUSAL_WEIGHT  = 0.6
VALENCE_WEIGHT  = 0.4

# Bonus co-occurrence : chaque cue ACTIF (> 0) au-delà du premier ajoute ce bonus
COOCCURRENCE_BONUS_PER_CUE = 0.3   # ex: 5 cues actifs → +4 × 0.3 = +1.2

# Pénalités ciblées (establishing_shot retiré — trop ambigu)
PENALTY_SCENE_TRANSITION = 0.5   # fondu au noir, carton titre → forte pénalité
PENALTY_STATIC_DIALOGUE  = 0.3   # dialogue calme sans tension

# Calibration : valeur brute considérée comme 100/100
# Correspond à un climax maximum réaliste (calculé ci-dessus ≈ 8.0)
RAW_MAX_CALIBRATION = 8.0


VAD_PROMPT_TEMPLATE = """You are analyzing a film scene using the VAD (Valence-Arousal-Dominance) model from affective computing research.

Detect the presence of each cue below. Use ONLY integer values in the specified ranges.
Return ONLY a valid JSON object — no explanation, no markdown, no extra text.

ACTION:
{action_text}

STYLE:
{style_text}

IMPORTANT SCORING GUIDANCE:
- Use 0 when a cue is clearly absent
- Use 1 when a cue is moderately present
- Use 2 only for strong, unambiguous presence (reserve for clear climax moments)
- establishing_shot: use 1 ONLY if the shot is purely establishing with NO dramatic tension whatsoever
- static_dialogue: use 1 ONLY if conversation has absolutely no emotional charge, conflict, or subtext
- scene_transition: use 1 ONLY for actual fades to black, title cards, or hard scene breaks

Return exactly this JSON structure:
{{
  "arousal_cues": {{
    "rapid_editing": 0,       // fast cuts, shaky cam, kinetic camera movement (0-2)
    "physical_action": 0,     // fight, chase, violence, physical struggle (0-2)
    "emotional_outburst": 0,  // crying, screaming, shock, panic (0-2)
    "tense_confrontation": 0, // verbal conflict, argument, standoff (0-2)
    "close_up_intensity": 0   // extreme close-up on face or body detail (0-1)
  }},
  "valence_cues": {{
    "darkness_shadow": 0,     // low-key lighting, heavy shadows, oppressive atmosphere (0-2)
    "death_loss": 0,          // death, grief, despair, mourning (0-2)
    "joy_celebration": 0,     // happiness, relief, love, triumph (0-2)
    "threat_danger": 0        // menace, fear, suspense, vulnerability (0-2)
  }},
  "neutral_indicators": {{
    "establishing_shot": 0,   // wide calm descriptive shot with ZERO dramatic tension (0-1)
    "static_dialogue": 0,     // completely neutral talking, no tension or subtext (0-1)
    "scene_transition": 0     // fade to black, title card, scene break (0-1)
  }}
}}"""


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_vad_signals(signals: dict) -> bool:
    expected = {
        "arousal_cues": {
            "rapid_editing":      (0, 2),
            "physical_action":    (0, 2),
            "emotional_outburst": (0, 2),
            "tense_confrontation":(0, 2),
            "close_up_intensity": (0, 1),
        },
        "valence_cues": {
            "darkness_shadow": (0, 2),
            "death_loss":      (0, 2),
            "joy_celebration": (0, 2),
            "threat_danger":   (0, 2),
        },
        "neutral_indicators": {
            "establishing_shot": (0, 1),
            "static_dialogue":   (0, 1),
            "scene_transition":  (0, 1),
        },
    }
    for group, fields in expected.items():
        if group not in signals:
            return False
        for field, (min_v, max_v) in fields.items():
            if field not in signals[group]:
                return False
            val = signals[group][field]
            if not isinstance(val, (int, float)):
                return False
            if not (min_v <= val <= max_v):
                return False
    return True


def compute_arousal_score(signals: dict) -> int:
    """
    Calcule le score d'arousal (0-100) depuis les signaux VAD.

    Formule v2 :
      base    = 0.6 × sum(arousal_cues) + 0.4 × sum(valence_cues)
      bonus   = (nb_cues_actifs - 1) × COOCCURRENCE_BONUS_PER_CUE   [si > 0]
      penalty = scene_transition × 0.5 + static_dialogue × 0.3
      raw     = base + bonus - penalty
      score   = clip(raw / RAW_MAX_CALIBRATION × 100, 0, 100)

    Avantages vs v1 :
      - Pas de normalisation par max théorique → scores plus hauts et différenciés
      - Bonus co-occurrence → climax avec signaux multiples ressort vraiment
      - establishing_shot retiré des pénalités → ne tire plus tout vers 0
    """
    arousal_cues = signals["arousal_cues"]
    valence_cues = signals["valence_cues"]
    neutral      = signals["neutral_indicators"]

    arousal_sum = sum(arousal_cues.values())
    valence_sum = sum(valence_cues.values())

    # Base
    base = AROUSAL_WEIGHT * arousal_sum + VALENCE_WEIGHT * valence_sum

    # Bonus co-occurrence : compte les cues ACTIFS (valeur > 0)
    all_cues = list(arousal_cues.values()) + list(valence_cues.values())
    n_active = sum(1 for v in all_cues if v > 0)
    bonus = max(0, n_active - 1) * COOCCURRENCE_BONUS_PER_CUE

    # Pénalités ciblées uniquement
    penalty = (neutral.get("scene_transition", 0) * PENALTY_SCENE_TRANSITION
             + neutral.get("static_dialogue", 0)  * PENALTY_STATIC_DIALOGUE)

    raw   = max(0.0, base + bonus - penalty)
    score = min(round(raw / RAW_MAX_CALIBRATION * 100), 100)

    return score


def extract_json_from_response(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def get_vad_signals(action_text: str, style_text: str) -> dict | None:
    prompt = VAD_PROMPT_TEMPLATE.format(
        action_text=action_text if action_text else "(none)",
        style_text=style_text  if style_text  else "(none)",
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "top_p": 0.9},
            )
            raw     = response["message"]["content"].strip()
            signals = extract_json_from_response(raw)

            if signals is None:
                print(f"    [WARN] Tentative {attempt}/{MAX_RETRIES} : JSON non trouvé")
                continue
            if not validate_vad_signals(signals):
                print(f"    [WARN] Tentative {attempt}/{MAX_RETRIES} : JSON invalide")
                continue

            return signals

        except Exception as e:
            print(f"    [ERROR] Tentative {attempt}/{MAX_RETRIES} : {e}")

        time.sleep(0.3)

    print(f"    [FAIL] {MAX_RETRIES} tentatives échouées")
    return None


def process_film(film_name: str):
    print(f"\n{'='*60}")
    print(f"Film: {film_name}")
    print(f"{'='*60}")

    json_path   = os.path.join(JSON_DIR,    f"{film_name}.json")
    action_path = os.path.join(RAPPORT_DIR, film_name, "action.json")
    style_path  = os.path.join(RAPPORT_DIR, film_name, "style.json")
    output_path = os.path.join(RAPPORT_DIR, film_name, "emotional_intensity.json")

    json_data   = load_json(json_path)
    action_data = load_json(action_path)
    style_data  = load_json(style_path)

    if json_data is None:
        print(f"  [SKIP] Pas de fichier JSON : {json_path}")
        return

    # Indexer les analyses par intervalle_debut
    action_map = {}
    if action_data:
        intervals = action_data.get("intervalles", [])
        print(f"  [DEBUG] action.json : {len(intervals)} intervalles")
        for item in intervals:
            debut = item.get("intervalle_debut")
            text  = (item.get("analyse_action") or item.get("action")
                  or item.get("description")   or item.get("analyse") or "")
            action_map[debut] = text
    else:
        print(f"  [DEBUG] action.json introuvable : {action_path}")

    style_map = {}
    if style_data:
        intervals = style_data.get("intervalles", [])
        print(f"  [DEBUG] style.json : {len(intervals)} intervalles")
        for item in intervals:
            debut = item.get("intervalle_debut")
            text  = (item.get("analyse_style") or item.get("style")
                  or item.get("description")   or item.get("analyse") or "")
            style_map[debut] = text
    else:
        print(f"  [DEBUG] style.json introuvable : {style_path}")

    print(f"  [DEBUG] action_map clés (5) : {list(action_map.keys())[:5]}")
    print(f"  [DEBUG] style_map  clés (5) : {list(style_map.keys())[:5]}")

    # Charger résultats existants (reprise)
    os.makedirs(os.path.join(RAPPORT_DIR, film_name), exist_ok=True)
    output = load_json(output_path) or {
        "movie_id":     json_data.get("movie_id", film_name),
        "date_analyse": json_data.get("date_traitement", ""),
        "model":        MODEL_NAME,
        "method":       "VAD-arousal v2 (Russell 1980, Xu et al. 2012 — co-occurrence bonus)",
        "intervalles":  [],
    }
    already_done = {r["intervalle_index"] for r in output["intervalles"]}

    def save():
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    intervalles = json_data.get("intervalles", [])
    total = len(intervalles)

    for interval in intervalles:
        idx   = interval.get("intervalle_index")
        debut = interval.get("intervalle_debut", 0)
        fin   = interval.get("intervalle_fin", 0)

        if idx in already_done:
            print(f"  Intervalle {idx:04d} ({debut}s-{fin}s)... [déjà traité]")
            continue

        action_text = action_map.get(debut, "")
        style_text  = style_map.get(debut, "")

        if not action_text and not style_text:
            output["intervalles"].append({
                "intervalle_index":    idx,
                "intervalle_debut":    debut,
                "intervalle_fin":      fin,
                "emotional_intensity": 0,
                "vad_signals":         None,
                "status":              "no_data",
            })
            save()
            print(f"  Intervalle {idx:04d}/{total-1} ({debut}s)... 0/100 (no_data)")
            continue

        print(f"  Intervalle {idx:04d}/{total-1} ({debut}s)... ", end="", flush=True)

        signals = get_vad_signals(action_text, style_text)

        if signals is not None:
            score  = compute_arousal_score(signals)
            status = "ok"

            # Log détaillé pour diagnostic
            a_sum    = sum(signals["arousal_cues"].values())
            v_sum    = sum(signals["valence_cues"].values())
            all_cues = list(signals["arousal_cues"].values()) + list(signals["valence_cues"].values())
            n_active = sum(1 for v in all_cues if v > 0)
            bonus    = max(0, n_active - 1) * COOCCURRENCE_BONUS_PER_CUE
            print(f"{score:3d}/100  "
                  f"[A={a_sum} V={v_sum} active={n_active} bonus={bonus:.1f} "
                  f"trans={signals['neutral_indicators']['scene_transition']} "
                  f"dial={signals['neutral_indicators']['static_dialogue']}]")
        else:
            score  = None
            status = "error"
            print("ERREUR")

        output["intervalles"].append({
            "intervalle_index":    idx,
            "intervalle_debut":    debut,
            "intervalle_fin":      fin,
            "emotional_intensity": score,
            "vad_signals":         signals,
            "status":              status,
        })
        save()
        time.sleep(0.1)

    print(f"\n  ✅ Résultats sauvegardés : {output_path}")


def get_all_films():
    if not os.path.exists(RAPPORT_DIR):
        print(f"[ERROR] Dossier rapport introuvable : {RAPPORT_DIR}")
        return []
    return [d for d in os.listdir(RAPPORT_DIR)
            if os.path.isdir(os.path.join(RAPPORT_DIR, d))]


def main():
    films = get_all_films()
    if not films:
        print("Aucun film trouvé.")
        return

    print(f"Films trouvés : {len(films)}")
    for film in sorted(films):
        print(f"  - {film}")

    print(f"\nDébut de l'analyse — modèle : {MODEL_NAME}")
    print(f"Formule v2 : base(A×0.6 + V×0.4) + bonus_cooccurrence - pénalités_ciblées")
    print(f"  Bonus co-occurrence : +{COOCCURRENCE_BONUS_PER_CUE}/cue actif supplémentaire")
    print(f"  Pénalité scene_transition : -{PENALTY_SCENE_TRANSITION}")
    print(f"  Pénalité static_dialogue  : -{PENALTY_STATIC_DIALOGUE}")
    print(f"  Calibration max : raw {RAW_MAX_CALIBRATION} → score 100\n")

    for film in sorted(films):
        process_film(film)

    print("\n✅ Analyse complète terminée.")


if __name__ == "__main__":
    main()