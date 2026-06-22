"""
Point d'entrée WSGI pour l'hébergement (PythonAnywhere, gunicorn, etc.).

Sur PythonAnywhere : copiez le contenu de ce fichier dans le fichier WSGI
proposé par l'onglet "Web", en adaptant le chemin `PROJECT_DIR`.

Variables d'environnement à définir en production :
  - EDT_SECRET_KEY      : clé secrète aléatoire pour les sessions (obligatoire)
  - EDT_ADMIN_PASSWORD  : mot de passe du compte Admin (recommandé)
"""

import os
import sys

# Chemin du projet (à adapter : remplacez VOTRENOM par votre login PythonAnywhere)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# --- Configuration production (à définir de préférence dans l'interface de l'hébergeur) ---
# Décommentez et renseignez si vous ne pouvez pas définir de variables d'environnement :
# os.environ.setdefault('EDT_SECRET_KEY', 'CHANGEZ-MOI-cle-aleatoire')
# os.environ.setdefault('EDT_ADMIN_PASSWORD', 'CHANGEZ-MOI')

from app import app as application  # noqa: E402  (nom attendu par WSGI)

if __name__ == '__main__':
    application.run()
