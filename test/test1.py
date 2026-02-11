"""
Script de test pour Molmo2-8B sur OpenRouter
Analyse une vidéo avec des questions sur les techniques cinématographiques
"""

import requests
import base64
import json
from pathlib import Path


class Molmo2VideoAnalyzer:
    """Classe pour analyser des vidéos avec Molmo2-8B via OpenRouter"""
    
    def __init__(self, api_key: str):
        """
        Initialiser l'analyseur
        
        Args:
            api_key: Votre clé API OpenRouter
        """
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "allenai/molmo-2-8b"  # Version payante (0.20$/M tokens)
        
        # Prix par million de tokens
        self.price_input = 0.20  # $/M tokens
        self.price_output = 0.20  # $/M tokens
    
    def encode_video_to_base64(self, video_path: str) -> str:
        """
        Encoder une vidéo locale en base64
        
        Args:
            video_path: Chemin vers le fichier vidéo
            
        Returns:
            Vidéo encodée en base64
        """
        # Normaliser le chemin (convertir \ en / et résoudre le chemin absolu)
        video_path = str(Path(video_path).resolve())
        print(f"📹 Encodage de la vidéo: {video_path}")
        
        # Vérifier que le fichier existe
        if not Path(video_path).exists():
            raise FileNotFoundError(f"Le fichier n'existe pas: {video_path}")
        
        # Lire la vidéo
        with open(video_path, "rb") as video_file:
            video_bytes = video_file.read()
        
        # Vérifier que le fichier n'est pas vide
        if len(video_bytes) == 0:
            raise ValueError(f"Le fichier vidéo est vide: {video_path}")
        
        # Afficher la taille
        size_mb = len(video_bytes) / (1024 * 1024)
        print(f"   Taille: {size_mb:.2f} MB")
        
        # Avertissement si la vidéo est trop grosse
        if size_mb > 50:
            print(f"   ⚠️  ATTENTION: Vidéo volumineuse ({size_mb:.2f} MB)")
            print(f"      Cela peut échouer ou coûter très cher en tokens!")
            response = input("   Continuer quand même? (o/n): ")
            if response.lower() != 'o':
                raise ValueError("Opération annulée par l'utilisateur")
        
        # Encoder en base64
        video_base64 = base64.b64encode(video_bytes).decode("utf-8")
        
        return video_base64
    
    def analyze_video_url(self, video_url: str, prompt: str) -> dict:
        """
        Analyser une vidéo via URL
        
        Args:
            video_url: URL de la vidéo
            prompt: Question/instruction pour le modèle
            
        Returns:
            Réponse du modèle
        """
        print(f"🎬 Analyse de la vidéo (URL)...")
        print(f"   Prompt: {prompt}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "video_url",
                            "video_url": {"url": video_url}
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(self.base_url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def analyze_video_local(self, video_path: str, prompt: str) -> dict:
        """
        Analyser une vidéo locale (encodée en base64)
        
        Args:
            video_path: Chemin vers le fichier vidéo local
            prompt: Question/instruction pour le modèle
            
        Returns:
            Réponse du modèle
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
        
        print(f"🎬 Analyse de la vidéo (locale)...")
        print(f"   Prompt: {prompt}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
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
        
        return response.json()
    
    def print_response(self, response: dict):
        """
        Afficher la réponse du modèle de manière formatée
        
        Args:
            response: Réponse JSON de l'API
        """
        print("\n" + "="*80)
        print("📊 RÉSULTAT DE L'ANALYSE")
        print("="*80)
        
        # Extraire le contenu
        if "choices" in response and len(response["choices"]) > 0:
            content = response["choices"][0]["message"]["content"]
            print(f"\n{content}\n")
        
        # Afficher les tokens utilisés
        if "usage" in response:
            usage = response["usage"]
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)
            
            # Calculer le coût
            cost_input = (prompt_tokens / 1_000_000) * self.price_input
            cost_output = (completion_tokens / 1_000_000) * self.price_output
            total_cost = cost_input + cost_output
            
            print("-"*80)
            print("📈 STATISTIQUES D'UTILISATION")
            print(f"   Tokens d'entrée (prompt): {prompt_tokens:,}")
            print(f"   Tokens de sortie: {completion_tokens:,}")
            print(f"   Total tokens: {total_tokens:,}")
            print(f"\n💰 COÛT")
            print(f"   Entrée: ${cost_input:.6f} ({prompt_tokens:,} tokens × ${self.price_input}/M)")
            print(f"   Sortie: ${cost_output:.6f} ({completion_tokens:,} tokens × ${self.price_output}/M)")
            print(f"   TOTAL: ${total_cost:.6f}")
            
            # Estimation pour 1000 requêtes similaires
            cost_1000 = total_cost * 1000
            print(f"   📊 Pour 1000 requêtes similaires: ~${cost_1000:.2f}")
        
        print("="*80 + "\n")


def test_avec_fichier_local():
    """Test avec une vidéo locale"""
    print("\n🧪 TEST 2: Vidéo locale (base64)\n")
    
    # Remplacez par votre clé API
    API_KEY = "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"
    
    # Chemin vers votre vidéo locale
    video_path = r"analyse\videos\Hocus Pocus (1993) 1080p BrRip x264 - YIFY\interval_0071_time_1065.00s-1080.00s.mp4"
    
    # Prompt sur les techniques cinématographiques
    prompt = "Explain the cinematographic techniques to me; what emotion did the director want to convey?"
    
    analyzer = Molmo2VideoAnalyzer(API_KEY)
    
    try:
        response = analyzer.analyze_video_local(video_path, prompt)
        analyzer.print_response(response)
    except FileNotFoundError as e:
        print(f"❌ Erreur: {e}")
        print("\n💡 SUGGESTIONS:")
        print("   - Vérifiez que le chemin est correct")
        print("   - Utilisez des guillemets pour les chemins avec espaces")
        print("   - Sur Windows, utilisez r'chemin\\fichier.mp4' ou 'chemin/fichier.mp4'")
        print(f"   - Exemple: r'{video_path}'")
    except ValueError as e:
        print(f"❌ Erreur: {e}")
    except requests.exceptions.HTTPError as e:
        print(f"❌ Erreur HTTP: {e}")
        print(f"   Réponse: {e.response.text}")
        
        # Analyser l'erreur pour donner des suggestions
        if "Could not open video stream" in e.response.text:
            print("\n💡 SUGGESTIONS:")
            print("   - La vidéo est peut-être trop grosse (limite ~10-20 MB recommandée)")
            print("   - Le format vidéo n'est peut-être pas supporté")
            print("   - Essayez de compresser/réencoder la vidéo en MP4 H.264")
            print("   - Utilisez une vidéo plus courte ou de résolution inférieure")
    except Exception as e:
        print(f"❌ Erreur: {e}")



if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║        TEST MOLMO2-8B - ANALYSE VIDÉO SUR OPENROUTER          ║
    ║                    (Version payante - 0.20$/M tokens)          ║
    ╚════════════════════════════════════════════════════════════════╝
    
    Ce script teste l'analyse de vidéos avec Molmo2-8B.
    
    ⚠️  IMPORTANT: La période gratuite est terminée !
    Prix: 0.20$/M tokens (entrée et sortie)
    
    📊 Estimation pour votre requête (15 sec vidéo):
    - ~6,000-12,000 tokens d'entrée
    - Coût estimé: ~$0.0012 - $0.0024 par requête
    - Pour 1000 requêtes: ~$1.20 - $2.40
    
    📝 INSTRUCTIONS:
    1. Remplacez 'VOTRE_CLÉ_API_ICI' par votre vraie clé OpenRouter
    2. Obtenez une clé ici: https://openrouter.ai/settings/keys
    3. Ajoutez des crédits sur votre compte OpenRouter
    4. Choisissez un test à exécuter ci-dessous
    
    """)
    
    # Décommenter le test que vous voulez exécuter:
    
    # test_avec_url()              # Pour tester avec une URL
    test_avec_fichier_local()    # Pour tester avec un fichier local
    # test_questions_multiples()   # Pour poser plusieurs questions
    
    print("\n⚠️  Décommentez un des tests ci-dessus pour commencer!")
    print("    Modifiez le fichier et remplacez 'VOTRE_CLÉ_API_ICI' par votre clé API\n")