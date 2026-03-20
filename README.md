# LaboCQ — Gestion laboratoire contrôle qualité agroalimentaire

Application bureau Python/Tkinter pour la gestion complète d'un laboratoire
de contrôle qualité agroalimentaire avec 4 laboratoires spécialisés.

---

## Prérequis

- Python 3.10 ou supérieur
- pip (gestionnaire de paquets Python)

---

## Installation

1. Télécharger et extraire le dossier `labo_cq`
2. Installer les dépendances

```bash
pip install -r requirements.txt
```

3. Lancer l'application

```bash
python main.py
```

---

## Première connexion

Compte administrateur créé automatiquement :

| Identifiant | Mot de passe |
|-------------|--------------|
| `admin`     | `Admin2024!` |

Changez le mot de passe dès la première connexion via **Gestion Utilisateurs**.

---

## Structure des modules

```
labo_cq/
├── main.py                    # Point d'entrée, login, dashboard
├── requirements.txt
├── core/
│   └── database.py            # BDD SQLite, authentification, rôles
└── modules/
    ├── gestion_users.py        # Utilisateurs, rôles, affectation labos
    ├── saisie_resultats.py     # Saisie résultats, import Excel, alertes
    ├── non_conformites.py      # NCR, causes 5M, actions correctives
    ├── onboarding.py           # Formations, compétences, habilitations
    ├── plan_controle.py        # Plans de contrôle par produit/labo
    ├── equipements.py          # Équipements, étalonnages, alertes
    ├── tracabilite.py          # Recherche traçabilité lot complet
    ├── tendances.py            # Graphiques, cartes de contrôle, SPC
    └── rapports.py             # Export PDF, bulletins analyse, rapports ISO
```

La base de données est stockée dans :

```
~/labo_cq_data/labo_cq.db
```

---

## Rôles utilisateurs

| Rôle          | Description                                                    |
|---------------|----------------------------------------------------------------|
| `admin`       | Accès complet à tous les modules et à la configuration         |
| `superviseur` | Validation des résultats, gestion de son/ses laboratoire(s)    |
| `technicien`  | Saisie des résultats, enregistrement des échantillons          |
| `visiteur`    | Lecture + commentaires NCR, accès daté avec expiration         |
| `auditeur`    | Lecture seule complète, téléchargement rapports                |

---

## Laboratoires configurés

- Labo PC Fèves & Nibs
- Labo PC Encours & Produits finis
- Labo Microbiologie
- Labo Dégustation

---

## Fonctionnalités principales

### Traçabilité complète

- Chaque résultat est lié au lot, à l'opérateur, à l'équipement et horodaté
- Recherche rétrospective par numéro de lot
- Chaîne MP → Encours → Produit fini

### Alertes automatiques

- Détection des écarts dès la saisie (limites inf/sup + limites d'alerte)
- Alerte visuelle et proposition d'ouverture de NCR
- Alertes d'expiration d'étalonnage (J-30)
- Alertes de compétences expirées

### Import Excel

Format attendu pour les résultats :

```
Code_echantillon | Parametre | Valeur | Unite | Commentaire
```

### Non-conformités

- Numérotation automatique (NCR-AAAA-XXXX)
- Analyse des causes par catégorie (5M : Matière, Méthode, Machine,
  Main d'œuvre, Milieu + Mesure)
- Analyse 5 Pourquoi
- Actions correctives avec responsable et échéance
- Blocage de lot

### Onboarding

- Catalogue de formations par laboratoire
- Enregistrement des compétences avec preuves
- Matrice d'habilitations par laboratoire (vue synthétique)
- Alertes d'expiration 30 jours avant

---

## Utilisation multi-postes (réseau)

Pour utiliser l'application sur plusieurs postes en réseau local :

1. Installer l'application sur chaque poste
2. Placer la base de données sur un dossier partagé réseau
3. Modifier `DB_PATH` dans `core/database.py` :

```python
DB_PATH = Path(r"\\SERVEUR\partage\labo_cq.db")
# ou sur Linux/Mac :
DB_PATH = Path("/mnt/partage/labo_cq.db")
```

> **Note** : SQLite supporte un accès concurrent limité.
> Pour plus de 5 utilisateurs simultanés, envisagez une migration vers
> PostgreSQL (les modèles de données sont compatibles).

---

## Sauvegardes

La base de données est un fichier unique :

```
~/labo_cq_data/labo_cq.db
```

Programmez une copie automatique quotidienne de ce fichier.

---

## Modules à compléter (v1 → v2)

Les modules suivants ont leur interface de navigation déclarée dans `main.py`
mais leur code détaillé est à développer dans une v2 :

- `modules/plan_controle.py` — Gestion des plans de contrôle
- `modules/equipements.py` — Gestion des équipements et étalonnages
- `modules/tracabilite.py` — Recherche traçabilité par lot
- `modules/tendances.py` — Analyse statistique et cartes de contrôle
- `modules/rapports.py` — Export PDF et rapports ISO 22000

Ces modules peuvent être développés en priorité selon vos besoins.
