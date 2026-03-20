"""
LaboCQ — Application de gestion laboratoire contrôle qualité agroalimentaire
Point d'entrée principal · Login sécurisé · Navigation multi-modules · Dashboard
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from core.database import (init_database, authenticate, get_connection,
                            has_permission, LABOS, ROLES)


# ═══════════════════════════════════════════════════════════════════════════════
#  Écran de connexion
# ═══════════════════════════════════════════════════════════════════════════════

class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LaboCQ — Connexion")
        self.resizable(False, False)
        self.geometry("400x300")
        self._center()
        self._build()
        self.current_user = None

    def _center(self):
        self.update_idletasks()
        w, h = 400, 300
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        main = ttk.Frame(self, padding=32)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="LaboCQ",
                  font=("Helvetica", 22, "bold")).pack(pady=(0, 4))
        ttk.Label(main, text="Gestion laboratoire contrôle qualité",
                  font=("Helvetica", 10)).pack(pady=(0, 24))

        ttk.Label(main, text="Identifiant").pack(anchor="w")
        self.var_login = tk.StringVar()
        ttk.Entry(main, textvariable=self.var_login, width=32).pack(pady=4)

        ttk.Label(main, text="Mot de passe").pack(anchor="w")
        self.var_pwd = tk.StringVar()
        pwd_entry = ttk.Entry(main, textvariable=self.var_pwd,
                              show="*", width=32)
        pwd_entry.pack(pady=4)
        pwd_entry.bind("<Return>", lambda e: self._login())

        self.lbl_error = ttk.Label(main, text="", foreground="red")
        self.lbl_error.pack(pady=4)

        ttk.Button(main, text="Se connecter",
                   command=self._login).pack(pady=8)

    def _login(self):
        login = self.var_login.get().strip()
        pwd = self.var_pwd.get()
        if not login or not pwd:
            self.lbl_error.config(text="Identifiant et mot de passe requis.")
            return
        user, error = authenticate(login, pwd)
        if user:
            self.current_user = dict(user)
            self.destroy()
        else:
            msg = error or "Identifiants incorrects ou compte inactif."
            self.lbl_error.config(text=msg)
            self.var_pwd.set("")


# ═══════════════════════════════════════════════════════════════════════════════
#  Fenêtre principale
# ═══════════════════════════════════════════════════════════════════════════════

class MainApp(tk.Tk):
    def __init__(self, current_user: dict):
        super().__init__()
        self.current_user = current_user
        self.title(f"LaboCQ — {current_user['prenom']} {current_user['nom']}  "
                   f"[{ROLES.get(current_user['role'], current_user['role'])}]")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self._build_ui()
        self._show_dashboard()

    def _build_ui(self):
        # ── Barre de navigation gauche ────────────────────────────────────────
        self.nav = ttk.Frame(self, width=200, relief="groove")
        self.nav.pack(side="left", fill="y")
        self.nav.pack_propagate(False)

        ttk.Label(self.nav, text="LaboCQ",
                  font=("Helvetica", 14, "bold")).pack(pady=(16, 4))
        ttk.Separator(self.nav, orient="horizontal").pack(fill="x", padx=8, pady=4)

        # Infos utilisateur
        ttk.Label(self.nav,
                  text=f"{self.current_user['prenom']} {self.current_user['nom']}",
                  font=("Helvetica", 10, "bold")).pack(pady=(0, 2))
        ttk.Label(self.nav,
                  text=ROLES.get(self.current_user["role"],
                                 self.current_user["role"]),
                  font=("Helvetica", 9), foreground="gray").pack(pady=(0, 8))
        ttk.Separator(self.nav, orient="horizontal").pack(fill="x", padx=8, pady=4)

        # Boutons de navigation
        self.nav_buttons = []
        nav_items = self._get_nav_items()
        for label, cmd in nav_items:
            btn = ttk.Button(self.nav, text=label,
                             command=cmd, width=22)
            btn.pack(pady=2, padx=8)
            self.nav_buttons.append(btn)

        ttk.Separator(self.nav, orient="horizontal").pack(fill="x", padx=8, pady=8)
        ttk.Button(self.nav, text="Se déconnecter",
                   command=self._logout, width=22).pack(pady=2, padx=8)

        # ── Zone de contenu ───────────────────────────────────────────────────
        self.content = ttk.Frame(self)
        self.content.pack(side="left", fill="both", expand=True)

        # Barre de statut
        self.statusbar = ttk.Label(self, text="Prêt", relief="sunken",
                                   anchor="w", padding=(4, 2))
        self.statusbar.pack(side="bottom", fill="x")

    def _get_nav_items(self):
        items = [("Tableau de bord", self._show_dashboard)]

        if has_permission(self.current_user, "write_results") or \
           has_permission(self.current_user, "read_all"):
            items.append(("Saisie résultats", self._show_saisie))

        if has_permission(self.current_user, "open_ncr") or \
           has_permission(self.current_user, "read_all"):
            items.append(("Non-conformités", self._show_ncr))

        if has_permission(self.current_user, "all") or \
           has_permission(self.current_user, "read_all"):
            items.append(("Plan de contrôle", self._show_plan_controle))

        if has_permission(self.current_user, "manage_equipments") or \
           has_permission(self.current_user, "read_equipments"):
            items.append(("Équipements", self._show_equipements))

        items.append(("Traçabilité / Lots", self._show_tracabilite))
        items.append(("Analyse tendances", self._show_tendances))
        items.append(("Onboarding / RH", self._show_onboarding))

        if has_permission(self.current_user, "read_reports") or \
           has_permission(self.current_user, "all"):
            items.append(("Rapports", self._show_rapports))

        if has_permission(self.current_user, "all"):
            items.append(("Utilisateurs", self._show_users))

        return items

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def _show_dashboard(self):
        self._clear_content()
        Dashboard(self.content, self.current_user).pack(fill="both", expand=True)
        self._set_status("Tableau de bord")

    def _show_saisie(self):
        self._clear_content()
        from modules.saisie_resultats import SaisieResultats
        SaisieResultats(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Saisie des résultats")

    def _show_ncr(self):
        self._clear_content()
        from modules.non_conformites import GestionNCR
        GestionNCR(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Non-conformités")

    def _show_users(self):
        self._clear_content()
        from modules.gestion_users import GestionUtilisateurs
        GestionUtilisateurs(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Gestion des utilisateurs")

    def _show_onboarding(self):
        self._clear_content()
        from modules.onboarding import OnboardingCompetences
        OnboardingCompetences(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Onboarding et compétences")

    def _show_plan_controle(self):
        self._clear_content()
        from modules.plan_controle import PlanControle
        PlanControle(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Plan de contrôle")

    def _show_equipements(self):
        self._clear_content()
        from modules.equipements import GestionEquipements
        GestionEquipements(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Équipements et étalonnages")

    def _show_tracabilite(self):
        self._clear_content()
        from modules.tracabilite import Tracabilite
        Tracabilite(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Traçabilité")

    def _show_tendances(self):
        self._clear_content()
        from modules.tendances import AnalyseTendances
        AnalyseTendances(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Analyse des tendances")

    def _show_rapports(self):
        self._clear_content()
        from modules.rapports import Rapports
        Rapports(self.content, self.current_user).pack(
            fill="both", expand=True)
        self._set_status("Rapports")

    def _logout(self):
        if messagebox.askyesno("Déconnexion", "Confirmer la déconnexion ?"):
            self.destroy()

    def _set_status(self, msg: str):
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        self.statusbar.config(
            text=f"  {msg}   —   {now}   |   "
                 f"{self.current_user['prenom']} {self.current_user['nom']}   |   "
                 f"{ROLES.get(self.current_user['role'], '')}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Tableau de bord
# ═══════════════════════════════════════════════════════════════════════════════

class Dashboard(ttk.Frame):
    def __init__(self, parent, current_user, **kwargs):
        super().__init__(parent, **kwargs)
        self.current_user = current_user
        self._build()

    def _build(self):
        ttk.Label(self,
                  text=f"Bienvenue, {self.current_user['prenom']} {self.current_user['nom']}",
                  font=("Helvetica", 16, "bold")).pack(pady=(16, 4), padx=16, anchor="w")
        ttk.Label(self,
                  text=datetime.now().strftime("%A %d %B %Y  —  %H:%M"),
                  font=("Helvetica", 11), foreground="gray"
                  ).pack(padx=16, anchor="w")

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=12)

        # ── Indicateurs KPI ───────────────────────────────────────────────────
        kpi_frame = ttk.Frame(self)
        kpi_frame.pack(fill="x", padx=16, pady=4)

        conn = get_connection()
        kpis = self._compute_kpis(conn)
        conn.close()

        kpi_defs = [
            ("Échantillons\nEn attente",     kpis["ech_attente"],   "#2980b9"),
            ("Non-conformités\nOuvertes",    kpis["ncr_ouvertes"],  "#c0392b"),
            ("Équipements\nÀ étalonner",     kpis["equip_alerte"],  "#d68910"),
            ("Résultats\nAujourd'hui",       kpis["res_today"],     "#27ae60"),
            ("Compétences\nExpirées / alerte", kpis["comp_alerte"], "#8e44ad"),
        ]

        for label, value, color in kpi_defs:
            card = tk.Frame(kpi_frame, relief="ridge", bd=1,
                            padx=12, pady=8)
            card.pack(side="left", expand=True, fill="both", padx=6)
            tk.Label(card, text=str(value), font=("Helvetica", 28, "bold"),
                     foreground=color).pack()
            tk.Label(card, text=label, font=("Helvetica", 9),
                     justify="center").pack()

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=12)

        # ── Zone alertes ──────────────────────────────────────────────────────
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=16)

        # Derniers écarts
        left = ttk.LabelFrame(mid, text="Dernières non-conformités ouvertes")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ncr_cols = ("N° NCR", "Labo", "Gravité", "Statut", "Date")
        ncr_tree = ttk.Treeview(left, columns=ncr_cols, show="headings", height=8)
        for col in ncr_cols:
            ncr_tree.heading(col, text=col)
            ncr_tree.column(col, width=120, anchor="center")
        ncr_tree.tag_configure("Critique",  foreground="#c0392b")
        ncr_tree.tag_configure("Majeure",   foreground="#d68910")
        ncr_tree.pack(fill="both", expand=True, padx=4, pady=4)

        conn = get_connection()
        for r in conn.execute("""
            SELECT numero_ncr, labo_id, gravite, statut, date_ouverture
            FROM non_conformites WHERE statut NOT IN ('Clôturée','Abandonnée')
            ORDER BY date_ouverture DESC LIMIT 10
        """).fetchall():
            tag = r["gravite"] if r["gravite"] in ("Critique", "Majeure") else ""
            ncr_tree.insert("", "end", values=(
                r["numero_ncr"], LABOS.get(r["labo_id"], "?"),
                r["gravite"], r["statut"],
                r["date_ouverture"][:10] if r["date_ouverture"] else "—"),
                tags=(tag,))

        # Alertes équipements
        right = ttk.LabelFrame(mid, text="Alertes équipements et étalonnages")
        right.pack(side="left", fill="both", expand=True)
        eq_cols = ("Équipement", "Labo", "Prochain étalonnage", "Statut")
        eq_tree = ttk.Treeview(right, columns=eq_cols, show="headings", height=8)
        for col in eq_cols:
            eq_tree.heading(col, text=col)
            eq_tree.column(col, width=140, anchor="center")
        eq_tree.tag_configure("alerte", foreground="#d68910")
        eq_tree.tag_configure("depasse", foreground="#c0392b")
        eq_tree.pack(fill="both", expand=True, padx=4, pady=4)

        today = datetime.now().strftime("%Y-%m-%d")
        for r in conn.execute("""
            SELECT nom, labo_id, prochaine_etalonnage, statut
            FROM equipements WHERE actif=1 AND prochaine_etalonnage IS NOT NULL
            ORDER BY prochaine_etalonnage
            LIMIT 10
        """).fetchall():
            tag = ""
            if r["prochaine_etalonnage"] < today:
                tag = "depasse"
            elif r["prochaine_etalonnage"] <= (
                    datetime.now().strftime("%Y-") +
                    str(int(datetime.now().strftime("%m")) + 1).zfill(2) +
                    datetime.now().strftime("-%d")):
                tag = "alerte"
            eq_tree.insert("", "end", values=(
                r["nom"], LABOS.get(r["labo_id"], "?"),
                r["prochaine_etalonnage"], r["statut"]),
                tags=(tag,))
        conn.close()

    def _compute_kpis(self, conn) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "ech_attente": conn.execute(
                "SELECT COUNT(*) FROM echantillons WHERE statut='En attente'"
            ).fetchone()[0],
            "ncr_ouvertes": conn.execute(
                "SELECT COUNT(*) FROM non_conformites "
                "WHERE statut NOT IN ('Clôturée','Abandonnée')"
            ).fetchone()[0],
            "equip_alerte": conn.execute(
                "SELECT COUNT(*) FROM equipements "
                "WHERE actif=1 AND prochaine_etalonnage < ?", (today,)
            ).fetchone()[0],
            "res_today": conn.execute(
                "SELECT COUNT(*) FROM resultats "
                "WHERE date_saisie LIKE ?", (today + "%",)
            ).fetchone()[0],
            "comp_alerte": conn.execute(
                "SELECT COUNT(*) FROM competences_personnel "
                "WHERE statut='Expirée' OR (date_expiration IS NOT NULL "
                "AND date_expiration <= date('now','+30 days'))"
            ).fetchone()[0],
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # Initialiser la base de données
    init_database()

    # Écran de connexion
    login = LoginWindow()
    login.mainloop()

    if not login.current_user:
        return  # Fenêtre fermée sans connexion

    # Application principale
    app = MainApp(login.current_user)
    app.mainloop()


if __name__ == "__main__":
    main()
