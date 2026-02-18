#!/usr/bin/env python3
"""
Visualisation des scores d'intensité émotionnelle (VAD)
- Recalcule l'intensité à partir des vad_signals (Russell 1980, Xu et al. 2012)
- Interpole les no_data pour combler les trous (optionnel)
- Lisse la courbe par fenêtre glissante (optionnel)

Options principales :
  --smooth N        Fenêtre de lissage (défaut: 5, 0 = désactivé)
  --interpolate     Comble les no_data par interpolation linéaire
  --no-smooth       Désactive le lissage
  --no-interpolate  Conserve les trous no_data (comportement original)
"""

import json
import os
import sys
import glob
import argparse
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path


# ─── Configuration ────────────────────────────────────────────────────────────

RAPPORT_DIR = "analyse/rapport"
OUTPUT_DIR  = "analyse/graphs"

COLORS = [
    "#4C9BE8", "#E8834C", "#4CE874", "#E84C6B",
    "#B04CE8", "#E8D94C", "#4CE8D9", "#E84CAA",
]


# ─── Post-traitement : interpolation + lissage ────────────────────────────────

DEFAULT_SMOOTH       = 5     # fenêtre glissante (nb d'intervalles)
DEFAULT_INTERPOLATE  = True  # combler les no_data


def interpolate_gaps(all_intervals_raw: list, ok_intervals: list) -> list:
    """
    Reconstitue une timeline complète en interpolant linéairement
    les intervalles no_data entre les intervalles ok connus.
    """
    if len(ok_intervals) < 2:
        return ok_intervals

    ok_map   = {iv["debut"]: iv for iv in ok_intervals}
    known_t  = np.array([iv["debut"] for iv in ok_intervals])
    known_s  = np.array([iv["score"] for iv in ok_intervals])

    # Tous les timestamps (ok + no_data)
    all_debuts = sorted(set(
        iv.get("intervalle_debut", iv.get("debut", 0))
        for iv in all_intervals_raw
    ))

    result = []
    for debut in all_debuts:
        if debut in ok_map:
            result.append(ok_map[debut])
        else:
            interp_score = float(np.interp(debut, known_t, known_s))
            result.append({
                "index": -1,
                "debut": debut,
                "fin":   debut + 15,
                "score": round(interp_score, 1),
                "stored_score": 0,
                "interpolated": True,
            })

    return sorted(result, key=lambda x: x["debut"])


def smooth_scores(intervals: list, window: int) -> list:
    """
    Lissage gaussien sur les scores (fenêtre = nb d'intervalles).
    window=5 ~= 75s, window=10 ~= 150s.
    """
    if window <= 1 or not intervals:
        return intervals

    scores = np.array([iv["score"] for iv in intervals])
    half   = window // 2
    x      = np.arange(-half, half + 1)
    kernel = np.exp(-x**2 / (2 * (window / 4.0) ** 2))
    kernel /= kernel.sum()
    smoothed = np.clip(np.convolve(scores, kernel, mode="same"), 0, 100)

    return [{**iv, "score": round(float(s), 1)} for iv, s in zip(intervals, smoothed)]


# ─── Chargement ───────────────────────────────────────────────────────────────

def load_film_data(json_path: str) -> tuple[str, list, list]:
    """Retourne (film_name, ok_intervals, all_intervals_raw)."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    film_name     = data.get("movie_id") or Path(json_path).parent.name
    intervals_raw = data.get("intervalles", data if isinstance(data, list) else [])

    ok_intervals = []
    for iv in intervals_raw:
        if iv.get("status") == "no_data":
            continue
        ok_intervals.append({
            "index": iv.get("intervalle_index", 0),
            "debut": iv.get("intervalle_debut", 0),
            "fin":   iv.get("intervalle_fin", 0),
            "score": iv.get("emotional_intensity") or 0,
        })

    return film_name, ok_intervals, intervals_raw


def find_all_films(base_dir: str) -> list[str]:
    pattern = os.path.join(base_dir, "**", "emotional_intensity.json")
    return sorted(glob.glob(pattern, recursive=True))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def seconds_to_hms(s: float) -> str:
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def shorten_title(title: str, max_len: int = 60) -> str:
    if len(title) <= max_len:
        return title
    for sep in ("[", "(", " - "):
        idx = title.find(sep)
        if 10 < idx < max_len:
            return title[:idx].strip()
    return title[:max_len].strip() + "…"


def _setup_xaxis(ax, times):
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: seconds_to_hms(x)))
    ax.tick_params(axis="x", labelsize=8, rotation=30)
    if times:
        ax.set_xlim(min(times), max(times))


# ─── Graphiques ───────────────────────────────────────────────────────────────

def plot_single_film(film_name: str, intervals: list, ax: plt.Axes, color: str,
                     smooth_window: int = 0):
    times  = [iv["debut"] for iv in intervals]
    scores = [iv["score"] for iv in intervals]

    # Points réels vs interpolés
    real_t   = [iv["debut"] for iv in intervals if not iv.get("interpolated")]
    real_s   = [iv["score"] for iv in intervals if not iv.get("interpolated")]
    interp_t = [iv["debut"] for iv in intervals if iv.get("interpolated")]
    interp_s = [iv["score"] for iv in intervals if iv.get("interpolated")]

    ax.fill_between(times, scores, alpha=0.18, color=color)
    ax.plot(times, scores, color=color, linewidth=1.8)
    ax.scatter(real_t, real_s, color=color, s=14, zorder=3, alpha=0.6)
    if interp_t:
        ax.scatter(interp_t, interp_s, color=color, s=5, zorder=2, alpha=0.2,
                   marker="x", linewidths=0.5)

    # Top 5 pics annotés
    peak_idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
    for idx in peak_idxs:
        if scores[idx] > 3:
            ax.annotate(
                f"{scores[idx]:.0f}",
                xy=(times[idx], scores[idx]),
                xytext=(0, 7), textcoords="offset points",
                ha="center", fontsize=7, color=color, fontweight="bold",
            )

    ax.set_ylim(0, 105)
    ax.set_ylabel("Intensité (VAD)", fontsize=9)
    ax.yaxis.set_major_locator(ticker.MultipleLocator(10))
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.grid(axis="x", linestyle=":", alpha=0.3)
    _setup_xaxis(ax, times)

    moy = np.mean(scores) if scores else 0
    mx  = max(scores) if scores else 0
    smooth_info = f" · lissage={smooth_window}" if smooth_window > 1 else ""
    interp_info = f" · {len(interp_t)} interpolés" if interp_t else ""
    ax.set_title(
        f"{shorten_title(film_name)}\n"
        f"[{len(real_t)} analysés{interp_info}{smooth_info} · moy {moy:.1f} · max {mx:.0f}]",
        fontsize=10, fontweight="bold", pad=6,
    )


def build_figure_per_film(films_data, smooth_window=0):
    n    = len(films_data)
    fig, axes = plt.subplots(n, 1, figsize=(14, 4 * n), constrained_layout=True)
    if n == 1:
        axes = [axes]
    for i, (name, intervals) in enumerate(films_data):
        plot_single_film(name, intervals, axes[i], COLORS[i % len(COLORS)],
                         smooth_window=smooth_window)
        axes[i].set_xlabel("Temps", fontsize=9)
    fig.suptitle("Intensité émotionnelle (VAD) — intervalles analysés", fontsize=13, fontweight="bold")
    return fig


def build_figure_overlay(films_data):
    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    all_times = []
    for i, (name, intervals) in enumerate(films_data):
        color  = COLORS[i % len(COLORS)]
        times  = [iv["debut"] for iv in intervals]
        scores = [iv["score"] for iv in intervals]
        ax.plot(times, scores, color=color, linewidth=1.5,
                label=shorten_title(name, 50), alpha=0.85)
        ax.fill_between(times, scores, alpha=0.07, color=color)
        all_times.extend(times)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Intensité (VAD)", fontsize=10)
    ax.yaxis.set_major_locator(ticker.MultipleLocator(10))
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.grid(axis="x", linestyle=":", alpha=0.3)
    _setup_xaxis(ax, all_times)
    ax.set_xlabel("Temps", fontsize=10)
    ax.set_title("Intensité émotionnelle comparée (VAD)", fontsize=13, fontweight="bold")
    ax.legend(fontsize=8, loc="upper right")
    return fig


def build_figure_heatmap(films_data):
    N_BINS = 200
    film_names, matrix = [], []
    for name, intervals in films_data:
        if not intervals:
            continue
        times  = np.array([iv["debut"] for iv in intervals], dtype=float)
        scores = np.array([iv["score"] for iv in intervals])
        t_norm = (times - times.min()) / max(times.max() - times.min(), 1)
        row, counts = np.zeros(N_BINS), np.zeros(N_BINS)
        for t, s in zip(t_norm, scores):
            idx = min(int(t * N_BINS), N_BINS - 1)
            row[idx] += s; counts[idx] += 1
        counts[counts == 0] = 1
        matrix.append(row / counts)
        film_names.append(shorten_title(name, 45))

    if not matrix:
        return None

    fig, ax = plt.subplots(figsize=(14, max(3, len(matrix) * 0.8 + 1)), constrained_layout=True)
    im = ax.imshow(np.array(matrix), aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)
    ax.set_yticks(range(len(film_names)))
    ax.set_yticklabels(film_names, fontsize=9)
    ax.set_xticks(np.linspace(0, N_BINS - 1, 6))
    ax.set_xticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])
    ax.set_xlabel("Progression normalisée du film", fontsize=10)
    plt.colorbar(im, ax=ax, label="Score VAD moyen")
    ax.set_title("Heatmap d'intensité émotionnelle (VAD)", fontsize=13, fontweight="bold")
    return fig


# ─── Stats terminal ───────────────────────────────────────────────────────────

def print_stats(films_data):
    print("\n" + "═" * 72)
    print(f"{'Film':<42} {'ok':>5} {'Moy':>6} {'Max':>6} {'Pic à':>8}")
    print("─" * 72)
    for name, intervals in films_data:
        if not intervals:
            print(f"{shorten_title(name, 41):<42} {'0':>5}")
            continue
        scores = [iv["score"] for iv in intervals]
        times  = [iv["debut"] for iv in intervals]
        peak   = int(np.argmax(scores))
        print(f"{shorten_title(name, 41):<42} {len(intervals):>5} "
              f"{np.mean(scores):>6.1f} {max(scores):>6.0f} {seconds_to_hms(times[peak]):>8}")
    print("═" * 72 + "\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Visualise les scores d'intensité émotionnelle VAD par film.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python visualize_emotional_intensity.py                          # tous les films, lissage=5
  python visualize_emotional_intensity.py --smooth 10             # lissage plus fort
  python visualize_emotional_intensity.py --no-smooth             # courbe brute
  python visualize_emotional_intensity.py --no-interpolate        # garde les trous no_data
  python visualize_emotional_intensity.py --mode overlay          # superposition
  python visualize_emotional_intensity.py --mode all --save       # tout sauvegarder
        """,
    )
    parser.add_argument("paths", nargs="*",
        help="Chemins vers des emotional_intensity.json ou des dossiers.")
    parser.add_argument("--mode", choices=["stacked", "overlay", "heatmap", "all"],
        default="stacked")
    parser.add_argument("--save", action="store_true",
        help=f"Sauvegarde dans {OUTPUT_DIR}/")
    parser.add_argument("--rapport-dir", default=RAPPORT_DIR)

    # Post-traitement
    smooth_grp = parser.add_mutually_exclusive_group()
    smooth_grp.add_argument("--smooth", type=int, default=DEFAULT_SMOOTH, metavar="N",
        help=f"Fenêtre de lissage gaussien en nb d'intervalles (défaut: {DEFAULT_SMOOTH}). "
             f"N=1 ou 0 = désactivé. Ex: --smooth 10 ≈ fenêtre de 2min30")
    smooth_grp.add_argument("--no-smooth", action="store_true",
        help="Désactive le lissage (équivalent à --smooth 0)")

    interp_grp = parser.add_mutually_exclusive_group()
    interp_grp.add_argument("--interpolate", action="store_true", default=DEFAULT_INTERPOLATE,
        help="Comble les trous no_data par interpolation linéaire (défaut: activé)")
    interp_grp.add_argument("--no-interpolate", action="store_true",
        help="Conserve les trous no_data (courbe discontinue)")

    args = parser.parse_args()

    smooth_window = 0 if args.no_smooth else args.smooth
    do_interpolate = not args.no_interpolate

    # Collecte des fichiers
    json_files = []
    if args.paths:
        for p in args.paths:
            if os.path.isfile(p):
                json_files.append(p)
            elif os.path.isdir(p):
                json_files.extend(sorted(glob.glob(
                    os.path.join(p, "**", "emotional_intensity.json"), recursive=True)))
            else:
                print(f"⚠️  Introuvable : {p}", file=sys.stderr)
    else:
        json_files = find_all_films(args.rapport_dir)

    if not json_files:
        print(f"❌ Aucun fichier trouvé. Vérifiez --rapport-dir='{args.rapport_dir}'.")
        sys.exit(1)

    # Chargement + post-traitement
    films_data = []
    for path in json_files:
        try:
            name, ok_intervals, raw_intervals = load_film_data(path)
            n_ok     = len(ok_intervals)
            n_no_data = len(raw_intervals) - n_ok

            if not ok_intervals:
                print(f"⚠️  {shorten_title(name, 55)} — aucun intervalle valide, ignoré")
                continue

            # 1. Interpolation des trous
            if do_interpolate and n_no_data > 0:
                intervals = interpolate_gaps(raw_intervals, ok_intervals)
                n_interp  = len(intervals) - n_ok
            else:
                intervals = ok_intervals
                n_interp  = 0

            # 2. Lissage gaussien
            if smooth_window > 1:
                intervals = smooth_scores(intervals, smooth_window)

            print(f"✅ {shorten_title(name, 55)}")
            print(f"   {n_ok} analysés · {n_no_data} no_data · "
                  f"{n_interp} interpolés · lissage={smooth_window}")

            films_data.append((name, intervals))

        except Exception as e:
            print(f"❌ {path} : {e}", file=sys.stderr)
            import traceback; traceback.print_exc()

    if not films_data:
        print("❌ Aucune donnée à afficher.")
        sys.exit(1)

    print_stats(films_data)

    # Génération des figures
    figures = []
    if args.mode in ("stacked", "all"):
        figures.append(("stacked", build_figure_per_film(films_data, smooth_window)))
    if args.mode in ("overlay", "all") and len(films_data) > 1:
        figures.append(("overlay", build_figure_overlay(films_data)))
    if args.mode in ("heatmap", "all") and len(films_data) > 1:
        fig = build_figure_heatmap(films_data)
        if fig:
            figures.append(("heatmap", fig))
    if args.mode == "overlay" and len(films_data) == 1:
        figures.append(("stacked", build_figure_per_film(films_data, smooth_window)))

    if args.save:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        for name, fig in figures:
            out = os.path.join(OUTPUT_DIR, f"emotional_intensity_{name}.png")
            fig.savefig(out, dpi=150, bbox_inches="tight")
            print(f"💾 {out}")
    else:
        plt.show()


if __name__ == "__main__":
    main()