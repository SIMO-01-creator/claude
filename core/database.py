"""
Gestion de la base de données SQLite - Labo CQ Agroalimentaire
Schéma complet : utilisateurs, laboratoires, échantillons, résultats,
NCR, équipements, onboarding
"""
import sqlite3
import hashlib
import os
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path.home() / "labo_cq_data" / "labo_cq.db"

LABOS = {
    1: "Labo PC Fèves & Nibs",
    2: "Labo PC Encours & Produits finis",
    3: "Labo Microbiologie",
    4: "Labo Dégustation",
}

ROLES = {
    "admin":       "Administrateur / Responsable CQ",
    "superviseur": "Superviseur laboratoire",
    "technicien":  "Technicien laboratoire",
    "visiteur":    "Visiteur / Accès temporaire",
    "auditeur":    "Auditeur interne (lecture seule)",
}

PERMISSIONS = {
    "admin":       ["all"],
    "superviseur": ["read_all", "write_results", "validate_results",
                    "manage_equipments", "open_ncr", "read_reports",
                    "manage_samples"],
    "technicien":  ["read_plan", "write_results", "register_samples",
                    "signal_ecart", "read_equipments"],
    "visiteur":    ["read_results", "read_reports", "comment_ncr"],
    "auditeur":    ["read_all", "download_reports"],
}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():
    """Crée toutes les tables si elles n'existent pas."""
    conn = get_connection()
    c = conn.cursor()

    # ── Utilisateurs ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nom         TEXT NOT NULL,
            prenom      TEXT NOT NULL,
            login       TEXT NOT NULL UNIQUE,
            password    TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'technicien',
            actif       INTEGER NOT NULL DEFAULT 1,
            email       TEXT,
            telephone   TEXT,
            date_creation TEXT DEFAULT (datetime('now')),
            derniere_connexion TEXT,
            acces_expire TEXT,
            notes       TEXT
        )
    """)

    # ── Affectation utilisateurs ↔ laboratoires ────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_labos (
            user_id  INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
            labo_id  INTEGER NOT NULL,
            PRIMARY KEY (user_id, labo_id)
        )
    """)

    # ── Fournisseurs ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS fournisseurs (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nom     TEXT NOT NULL,
            pays    TEXT,
            contact TEXT,
            actif   INTEGER DEFAULT 1
        )
    """)

    # ── Produits / Références ─────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS produits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL UNIQUE,
            nom         TEXT NOT NULL,
            type_produit TEXT NOT NULL,
            labo_id     INTEGER NOT NULL,
            description TEXT,
            actif       INTEGER DEFAULT 1
        )
    """)

    # ── Plan de contrôle ──────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS plan_controle (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            produit_id      INTEGER NOT NULL REFERENCES produits(id),
            parametre       TEXT NOT NULL,
            unite           TEXT,
            methode         TEXT,
            frequence       TEXT NOT NULL,
            valeur_cible    REAL,
            limite_inf      REAL,
            limite_sup      REAL,
            limite_alerte_inf REAL,
            limite_alerte_sup REAL,
            etape_process   TEXT,
            labo_id         INTEGER NOT NULL,
            obligatoire     INTEGER DEFAULT 1,
            actif           INTEGER DEFAULT 1,
            notes           TEXT
        )
    """)

    # ── Échantillons ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS echantillons (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            code_echantillon TEXT NOT NULL UNIQUE,
            numero_lot      TEXT NOT NULL,
            produit_id      INTEGER REFERENCES produits(id),
            fournisseur_id  INTEGER REFERENCES fournisseurs(id),
            labo_id         INTEGER NOT NULL,
            type_analyse    TEXT NOT NULL,
            date_reception  TEXT NOT NULL,
            date_analyse    TEXT,
            operateur_id    INTEGER REFERENCES utilisateurs(id),
            statut          TEXT DEFAULT 'En attente',
            priorite        TEXT DEFAULT 'Normale',
            commentaire     TEXT,
            date_creation   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Résultats d'analyse ───────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS resultats (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            echantillon_id  INTEGER NOT NULL REFERENCES echantillons(id),
            plan_controle_id INTEGER REFERENCES plan_controle(id),
            parametre       TEXT NOT NULL,
            valeur_numerique REAL,
            valeur_texte    TEXT,
            unite           TEXT,
            conforme        INTEGER,
            ecart           INTEGER DEFAULT 0,
            operateur_id    INTEGER REFERENCES utilisateurs(id),
            validateur_id   INTEGER REFERENCES utilisateurs(id),
            date_saisie     TEXT DEFAULT (datetime('now')),
            date_validation TEXT,
            equipement_id   INTEGER REFERENCES equipements(id),
            commentaire     TEXT,
            source          TEXT DEFAULT 'manuel'
        )
    """)

    # ── Équipements ───────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS equipements (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            code_equipement     TEXT NOT NULL UNIQUE,
            nom                 TEXT NOT NULL,
            marque              TEXT,
            modele              TEXT,
            numero_serie        TEXT,
            labo_id             INTEGER NOT NULL,
            date_mise_en_service TEXT,
            prochaine_verification TEXT,
            prochaine_etalonnage TEXT,
            statut              TEXT DEFAULT 'Opérationnel',
            responsable_id      INTEGER REFERENCES utilisateurs(id),
            notes               TEXT,
            actif               INTEGER DEFAULT 1
        )
    """)

    # ── Historique étalonnages ────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS etalonnages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            equipement_id   INTEGER NOT NULL REFERENCES equipements(id),
            date_etalonnage TEXT NOT NULL,
            type_operation  TEXT NOT NULL,
            resultat        TEXT,
            conforme        INTEGER,
            operateur_id    INTEGER REFERENCES utilisateurs(id),
            prochain_etalonnage TEXT,
            certificat_ref  TEXT,
            notes           TEXT
        )
    """)

    # ── Non-conformités (NCR) ─────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS non_conformites (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_ncr      TEXT NOT NULL UNIQUE,
            resultat_id     INTEGER REFERENCES resultats(id),
            echantillon_id  INTEGER REFERENCES echantillons(id),
            labo_id         INTEGER NOT NULL,
            description     TEXT NOT NULL,
            gravite         TEXT DEFAULT 'Mineure',
            statut          TEXT DEFAULT 'Ouverte',
            lot_bloque      INTEGER DEFAULT 0,
            ouvert_par_id   INTEGER REFERENCES utilisateurs(id),
            date_ouverture  TEXT DEFAULT (datetime('now')),
            date_cloture    TEXT,
            clos_par_id     INTEGER REFERENCES utilisateurs(id)
        )
    """)

    # ── Causes des NCR ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS ncr_causes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ncr_id      INTEGER NOT NULL REFERENCES non_conformites(id),
            categorie   TEXT,
            description TEXT NOT NULL,
            analyse_5m  TEXT,
            auteur_id   INTEGER REFERENCES utilisateurs(id),
            date_saisie TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Actions correctives / corrections ────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS actions_correctives (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ncr_id          INTEGER NOT NULL REFERENCES non_conformites(id),
            type_action     TEXT NOT NULL,
            description     TEXT NOT NULL,
            responsable_id  INTEGER REFERENCES utilisateurs(id),
            date_echeance   TEXT,
            date_realisation TEXT,
            statut          TEXT DEFAULT 'Planifiée',
            efficacite      TEXT,
            preuve          TEXT,
            notes           TEXT
        )
    """)

    # ── Onboarding / Formation personnel ──────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS formations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            titre           TEXT NOT NULL,
            description     TEXT,
            type_formation  TEXT,
            labo_id         INTEGER,
            duree_heures    REAL,
            validite_mois   INTEGER,
            obligatoire     INTEGER DEFAULT 1,
            actif           INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS competences_personnel (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES utilisateurs(id),
            formation_id    INTEGER NOT NULL REFERENCES formations(id),
            date_formation  TEXT NOT NULL,
            date_expiration TEXT,
            resultat        TEXT,
            score           REAL,
            formateur       TEXT,
            preuve_ref      TEXT,
            statut          TEXT DEFAULT 'Valide',
            notes           TEXT
        )
    """)

    # ── Journal des actions (audit trail) ────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES utilisateurs(id),
            action      TEXT NOT NULL,
            table_cible TEXT,
            record_id   INTEGER,
            details     TEXT,
            ip_machine  TEXT,
            timestamp   TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    _create_default_admin()


def _create_default_admin():
    """Crée le compte admin par défaut si aucun utilisateur n'existe."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM utilisateurs").fetchone()[0]
    if count == 0:
        conn.execute("""
            INSERT INTO utilisateurs (nom, prenom, login, password, role)
            VALUES (?, ?, ?, ?, ?)
        """, ("Admin", "Système", "admin", hash_password("Admin2024!"), "admin"))
        # L'admin a accès à tous les labos
        admin_id = conn.execute(
            "SELECT id FROM utilisateurs WHERE login='admin'"
        ).fetchone()[0]
        for labo_id in LABOS:
            conn.execute(
                "INSERT INTO user_labos (user_id, labo_id) VALUES (?, ?)",
                (admin_id, labo_id),
            )
        conn.commit()
    conn.close()


# ── Helpers génériques ────────────────────────────────────────────────────────

def log_action(user_id: int, action: str, table: str = None,
               record_id: int = None, details: str = None):
    conn = get_connection()
    conn.execute("""
        INSERT INTO audit_log (user_id, action, table_cible, record_id, details)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, action, table, record_id, details))
    conn.commit()
    conn.close()


def authenticate(login: str, password: str):
    """Retourne la ligne utilisateur si les identifiants sont valides, sinon None."""
    conn = get_connection()
    user = conn.execute("""
        SELECT * FROM utilisateurs
        WHERE login = ? AND password = ? AND actif = 1
    """, (login, hash_password(password))).fetchone()
    if user:
        conn.execute("""
            UPDATE utilisateurs SET derniere_connexion = datetime('now') WHERE id = ?
        """, (user["id"],))
        conn.commit()
        # Vérifier expiration pour visiteurs
        if user["acces_expire"]:
            if user["acces_expire"] < datetime.now().strftime("%Y-%m-%d"):
                conn.close()
                return None, "Accès expiré"
    conn.close()
    return user, None


def get_user_labos(user_id: int) -> list[int]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT labo_id FROM user_labos WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return [r["labo_id"] for r in rows]


def has_permission(user, permission: str) -> bool:
    role = user["role"]
    perms = PERMISSIONS.get(role, [])
    return "all" in perms or permission in perms
