import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from sklearn.metrics import r2_score

# Vos données (à remplacer par vos vraies valeurs)
x = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
y = np.array([2.5, 6.2, 15.8, 39.1, 97.5, 244.2, 610.8, 1527.3, 3818.3, 9548.7])

# Définition des différents modèles
def lineaire(x, a, b):
    return a * x + b

def quadratique(x, a, b, c):
    return a * x**2 + b * x + c

def exponentielle(x, a, b, c):
    return a * np.exp(b * x) + c

def logarithmique(x, a, b):
    return a * np.log(x) + b

def puissance(x, a, b):
    return a * x**b

def racine(x, a, b):
    return a * np.sqrt(x) + b

# Liste des modèles à tester
modeles = {
    'Linéaire (y = ax + b)': (lineaire, 2),
    'Quadratique (y = ax² + bx + c)': (quadratique, 3),
    'Exponentielle (y = a·e^(bx) + c)': (exponentielle, 3),
    'Logarithmique (y = a·ln(x) + b)': (logarithmique, 2),
    'Puissance (y = a·x^b)': (puissance, 2),
    'Racine carrée (y = a·√x + b)': (racine, 2),
}

# Tester chaque modèle
resultats = {}
print("=" * 70)
print("RECHERCHE DU MEILLEUR MODÈLE")
print("=" * 70)

for nom, (fonction, nb_params) in modeles.items():
    try:
        # Estimation des paramètres initiaux
        p0 = [1] * nb_params
        
        # Ajustement de la courbe
        params, _ = curve_fit(fonction, x, y, p0=p0, maxfev=10000)
        
        # Prédictions
        y_pred = fonction(x, *params)
        
        # Calcul du R²
        r2 = r2_score(y, y_pred)
        
        # Stockage des résultats
        resultats[nom] = {
            'fonction': fonction,
            'params': params,
            'r2': r2,
            'y_pred': y_pred
        }
        
        print(f"\n{nom}")
        print(f"  Paramètres: {params}")
        print(f"  R² = {r2:.6f}")
        
    except Exception as e:
        print(f"\n{nom}")
        print(f"  ❌ Échec: {str(e)}")

# Trouver le meilleur modèle
if resultats:
    meilleur = max(resultats.items(), key=lambda x: x[1]['r2'])
    meilleur_nom = meilleur[0]
    meilleur_data = meilleur[1]
    
    print("\n" + "=" * 70)
    print(f"🏆 MEILLEUR MODÈLE: {meilleur_nom}")
    print(f"   R² = {meilleur_data['r2']:.6f}")
    print(f"   Paramètres: {meilleur_data['params']}")
    print("=" * 70)
    
    # Affichage de la formule selon le modèle
    params = meilleur_data['params']
    if 'Linéaire' in meilleur_nom:
        print(f"\nFormule: y = {params[0]:.4f}·x + {params[1]:.4f}")
    elif 'Quadratique' in meilleur_nom:
        print(f"\nFormule: y = {params[0]:.4f}·x² + {params[1]:.4f}·x + {params[2]:.4f}")
    elif 'Exponentielle' in meilleur_nom:
        print(f"\nFormule: y = {params[0]:.4f}·e^({params[1]:.4f}·x) + {params[2]:.4f}")
    elif 'Logarithmique' in meilleur_nom:
        print(f"\nFormule: y = {params[0]:.4f}·ln(x) + {params[1]:.4f}")
    elif 'Puissance' in meilleur_nom:
        print(f"\nFormule: y = {params[0]:.4f}·x^{params[1]:.4f}")
    elif 'Racine' in meilleur_nom:
        print(f"\nFormule: y = {params[0]:.4f}·√x + {params[1]:.4f}")
    
    # Graphique de comparaison
    plt.figure(figsize=(14, 8))
    
    # Sous-graphique 1: Tous les modèles
    plt.subplot(1, 2, 1)
    plt.scatter(x, y, color='black', s=100, label='Données réelles', zorder=5)
    
    couleurs = ['red', 'blue', 'green', 'orange', 'purple', 'brown']
    for i, (nom, data) in enumerate(resultats.items()):
        plt.plot(x, data['y_pred'], '--', color=couleurs[i % len(couleurs)], 
                 label=f"{nom.split('(')[0]} (R²={data['r2']:.3f})", linewidth=2)
    
    plt.xlabel('x', fontsize=12)
    plt.ylabel('y', fontsize=12)
    plt.title('Comparaison de tous les modèles', fontsize=14, fontweight='bold')
    plt.legend(fontsize=9)
    plt.grid(True, alpha=0.3)
    
    # Sous-graphique 2: Meilleur modèle
    plt.subplot(1, 2, 2)
    plt.scatter(x, y, color='black', s=100, label='Données réelles', zorder=5)
    plt.plot(x, meilleur_data['y_pred'], 'r-', linewidth=3, 
             label=f'{meilleur_nom}\nR² = {meilleur_data["r2"]:.6f}')
    
    plt.xlabel('x', fontsize=12)
    plt.ylabel('y', fontsize=12)
    plt.title('Meilleur modèle', fontsize=14, fontweight='bold')
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()
    
    # Fonction pour faire des prédictions
    print("\n" + "=" * 70)
    print("EXEMPLES DE PRÉDICTIONS avec le meilleur modèle:")
    print("=" * 70)
    for x_test in [2.5, 5.5, 11]:
        y_pred = meilleur_data['fonction'](x_test, *meilleur_data['params'])
        print(f"x = {x_test:5.1f} → y = {y_pred:10.2f}")