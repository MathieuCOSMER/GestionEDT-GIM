# Déploiement gratuit (sans publicité)

Cette app est **Flask + SQLite**. Les données sont dans des fichiers `.db` sur le
disque : il faut donc un hébergeur dont le **disque est persistant**.

➡️ **Recommandé : PythonAnywhere** (disque persistant, gratuit, sans pub).
Render gratuit fonctionne aussi mais **perd les données** à chaque redéploiement
(disque éphémère) — à réserver si la persistance ne compte pas.

---

## Avant tout : variables d'environnement

À définir sur l'hébergeur (jamais en clair dans le code) :

| Variable | Rôle | Exemple |
|---|---|---|
| `EDT_SECRET_KEY` | clé des sessions (obligatoire) | générée ci-dessous |
| `EDT_ADMIN_PASSWORD` | mot de passe du compte Admin | (votre choix) |

Générer une clé secrète :
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Option A — PythonAnywhere (recommandé)

1. Créer un compte gratuit "Beginner" sur https://www.pythonanywhere.com
2. **Files** → uploader le projet, ou dans une console Bash :
   ```bash
   git clone <votre-repo> GestionEDT
   ```
   ⚠️ Ne pas uploader `node_modules/`, `venv_*/` ni les `*.db` (déjà dans `.gitignore`).
3. Console Bash :
   ```bash
   cd GestionEDT
   pip install --user -r requirements.txt
   ```
4. **Web** → *Add a new web app* → **Manual configuration** → Python 3.10+.
5. Éditer le fichier WSGI proposé et y mettre (en adaptant `VOTRENOM`) :
   ```python
   import sys, os
   path = '/home/VOTRENOM/GestionEDT'
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ['EDT_SECRET_KEY'] = 'COLLEZ_VOTRE_CLE_ICI'
   os.environ['EDT_ADMIN_PASSWORD'] = 'VOTRE_MOT_DE_PASSE'
   from app import app as application
   ```
   (Le fichier `wsgi.py` du projet sert de modèle.)
6. **Reload**. App en ligne sur `https://VOTRENOM.pythonanywhere.com`.

> Pensez à cliquer "Run until 3 months from today" quand PythonAnywhere le demande
> (renouvellement gratuit en 1 clic).

---

## Option B — Render (sans pub, mais données non persistantes en gratuit)

1. Pousser le projet sur GitHub.
2. https://render.com → *New* → *Web Service* → connecter le repo.
3. Réglages :
   - Build command : `pip install -r requirements.txt`
   - Start command : `gunicorn wsgi:application --bind 0.0.0.0:$PORT`
     (ou laisser le `Procfile` faire le travail)
4. Onglet *Environment* → ajouter `EDT_SECRET_KEY` et `EDT_ADMIN_PASSWORD`.
5. Deploy.

⚠️ Sur l'offre gratuite : mise en veille après 15 min d'inactivité (réveil ~30 s)
et **base SQLite réinitialisée** à chaque déploiement. Pour conserver les données,
il faut un disque persistant payant (~7 $/mois) ou migrer vers PostgreSQL.

---

## Test en local avec gunicorn (optionnel)
```bash
EDT_SECRET_KEY=test gunicorn wsgi:application --bind 0.0.0.0:5000
```
