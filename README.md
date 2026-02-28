# Gestion EDT - IUT GIM Toulon

Application web de gestion des Emplois Du Temps pour le département GIM de l'IUT de Toulon.
Gère les formations FTP, ALT et mutualisées sur 3 années (S1 à S6).

## Fonctionnalités

- **Gestion des enseignants** : CRUD complet, coordonnées, disponibilités avec priorités
- **Gestion des matières** : Ressources (R1.01...) et SAE, par semestre (S1-S6)
- **Sessions de cours** : CM/TD/TP 12/TP 8/PT avec enseignant, salle, durée, formation (FTP/ALT/MUT)
- **Répartition hebdomadaire** : Heures par semaine pour chaque session (import Excel)
- **Calcul de service HETD** : CM×1.5 + TD×1.0 + TP×2/3 + PT×1.0
- **Génération automatique d'EDT** avec contraintes :
  - Pas de conflit salle/enseignant/formation
  - Max 6h CM/TD par jour par enseignant
  - Respect des durées de créneaux (CM/TD=1h30, TP=2h)
- **Import Excel** : Charge directement le fichier de répartition annuelle

## Installation rapide

```bash
# Installer les dépendances Python
pip install flask flask-cors openpyxl pandas --break-system-packages

# Importer les données depuis le fichier Excel
python3 import_excel.py

# Lancer l'application
python3 run.py
```

Ouvrir **http://localhost:5000** dans le navigateur.

## Structure des fichiers

| Fichier | Description |
|---------|-------------|
| `app.py` | Backend Flask — API REST (40+ endpoints) |
| `schema.sql` | Schéma SQLite (10 tables, 9 index) |
| `import_excel.py` | Import du fichier Excel de répartition |
| `run.py` | Script de lancement avec vérifications |
| `static/index.html` | Interface React SPA (CDN, pas de build) |
| `config.py` | Configuration (coefficients HETD, etc.) |

## Pages de l'interface

| Page | Description |
|------|-------------|
| Dashboard | Vue d'ensemble (compteurs, accès rapide) |
| Enseignants | CRUD enseignants avec contacts |
| Matières | Liste des cours par semestre |
| Salles | Gestion des salles (standard, info fixe/mobile) |
| Sessions | Détail des sessions (type, enseignant, formation, heures) |
| Répartition | Grille hebdomadaire des heures |
| Service | Calcul HETD par enseignant |
| Emploi du temps | Grille EDT par semaine, filtrable par enseignant/salle |

## API principales

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/teachers` | Liste des enseignants |
| GET | `/api/courses` | Liste des matières |
| GET | `/api/course-sessions` | Sessions avec détails complets |
| GET | `/api/service/all` | Service HETD tous enseignants |
| GET | `/api/available-weeks` | Semaines disponibles |
| POST | `/api/generate-timetable` | Générer un EDT |
| GET | `/api/timetable/week/<n>` | EDT d'une semaine |
| GET | `/api/rooms` | Liste des salles |

## Calcul HETD

```
CM  × 1.5  = heures eq. TD
TD  × 1.0  = heures eq. TD
TP  × 2/3  = heures eq. TD
PT  × 1.0  = heures eq. TD
```

## Données importées (depuis Excel)

- 53 enseignants (avec contacts vacataires)
- 6 semestres (S1-S6, années 1-3)
- 91 matières (Ressources + SAE)
- 469 sessions de cours
- 11 salles
- 1741 entrées de répartition hebdomadaire

## Technologies

- **Backend** : Python 3 + Flask + SQLite3
- **Frontend** : React 18 + Tailwind CSS (CDN, fichier unique)
- **Pas de build** : Ouvrir et utiliser directement
