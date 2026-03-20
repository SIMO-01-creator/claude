"""
Module Gestion des Utilisateurs - Labo CQ
Création, modification, désactivation, affectation aux labos
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from core.database import (get_connection, hash_password, ROLES, LABOS,
                            has_permission, log_action)


class GestionUtilisateurs(ttk.Frame):
    def __init__(self, parent, current_user, **kwargs):
        super().__init__(parent, **kwargs)
        self.current_user = current_user
        self.selected_id = None
        self._build_ui()
        self._load_users()

    def _build_ui(self):
        # ── Barre d'outils ────────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=10, pady=6)

        ttk.Label(toolbar, text="Gestion des utilisateurs",
                  font=("Helvetica", 14, "bold")).pack(side="left")

        if has_permission(self.current_user, "all"):
            ttk.Button(toolbar, text="+ Nouvel utilisateur",
                       command=self._open_form).pack(side="right", padx=4)
            ttk.Button(toolbar, text="Modifier",
                       command=self._edit_selected).pack(side="right", padx=4)
            ttk.Button(toolbar, text="Désactiver",
                       command=self._toggle_active).pack(side="right", padx=4)

        # ── Filtre ────────────────────────────────────────────────────────────
        filter_frame = ttk.LabelFrame(self, text="Filtres")
        filter_frame.pack(fill="x", padx=10, pady=4)

        ttk.Label(filter_frame, text="Rôle:").pack(side="left", padx=4)
        self.var_role_filter = tk.StringVar(value="Tous")
        roles_list = ["Tous"] + list(ROLES.values())
        ttk.Combobox(filter_frame, textvariable=self.var_role_filter,
                     values=roles_list, width=28, state="readonly"
                     ).pack(side="left", padx=4)

        ttk.Label(filter_frame, text="Labo:").pack(side="left", padx=4)
        self.var_labo_filter = tk.StringVar(value="Tous")
        labos_list = ["Tous"] + list(LABOS.values())
        ttk.Combobox(filter_frame, textvariable=self.var_labo_filter,
                     values=labos_list, width=30, state="readonly"
                     ).pack(side="left", padx=4)

        ttk.Button(filter_frame, text="Filtrer",
                   command=self._load_users).pack(side="left", padx=8)

        # ── Tableau ───────────────────────────────────────────────────────────
        cols = ("Nom", "Prénom", "Login", "Rôle", "Labos", "Statut",
                "Dernière connexion")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=18)
        widths = (120, 120, 110, 180, 200, 80, 150)
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center")

        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
        sb.pack(side="left", fill="y", pady=4)

        self.tree.tag_configure("inactif", foreground="gray")
        self.tree.bind("<Double-1>", lambda e: self._edit_selected())

        # ── Panneau compétences en bas ────────────────────────────────────────
        comp_frame = ttk.LabelFrame(
            self, text="Compétences et formations de l'utilisateur sélectionné"
        )
        comp_frame.pack(fill="x", padx=10, pady=6)

        comp_cols = ("Formation", "Date", "Expiration", "Statut", "Score")
        self.comp_tree = ttk.Treeview(comp_frame, columns=comp_cols,
                                      show="headings", height=5)
        for col in comp_cols:
            self.comp_tree.heading(col, text=col)
            self.comp_tree.column(col, width=150)
        self.comp_tree.pack(fill="x", padx=4, pady=4)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _load_users(self):
        self.tree.delete(*self.tree.get_children())
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM utilisateurs ORDER BY nom, prenom"
        ).fetchall()
        conn.close()

        role_filter = self.var_role_filter.get()
        labo_filter = self.var_labo_filter.get()

        for r in rows:
            # Filtre rôle
            if role_filter != "Tous" and ROLES.get(r["role"]) != role_filter:
                continue
            # Labos de l'utilisateur
            conn = get_connection()
            labo_ids = [x["labo_id"] for x in conn.execute(
                "SELECT labo_id FROM user_labos WHERE user_id=?",
                (r["id"],)).fetchall()]
            conn.close()
            labo_names = ", ".join(LABOS[lid] for lid in labo_ids if lid in LABOS)

            if labo_filter != "Tous":
                labo_id_filter = next(
                    (k for k, v in LABOS.items() if v == labo_filter), None
                )
                if labo_id_filter not in labo_ids:
                    continue

            statut = "Actif" if r["actif"] else "Inactif"
            tags = () if r["actif"] else ("inactif",)
            self.tree.insert("", "end", iid=r["id"],
                             values=(r["nom"], r["prenom"], r["login"],
                                     ROLES.get(r["role"], r["role"]),
                                     labo_names, statut,
                                     r["derniere_connexion"] or "Jamais"),
                             tags=tags)

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        user_id = int(sel[0])
        self.selected_id = user_id
        self._load_competences(user_id)

    def _load_competences(self, user_id: int):
        self.comp_tree.delete(*self.comp_tree.get_children())
        conn = get_connection()
        rows = conn.execute("""
            SELECT f.titre, cp.date_formation, cp.date_expiration,
                   cp.statut, cp.score
            FROM competences_personnel cp
            JOIN formations f ON f.id = cp.formation_id
            WHERE cp.user_id = ?
            ORDER BY cp.date_formation DESC
        """, (user_id,)).fetchall()
        conn.close()
        for r in rows:
            self.comp_tree.insert("", "end",
                                  values=(r[0], r[1], r[2] or "—",
                                          r[3], r[4] or "—"))

    def _edit_selected(self):
        if not self.selected_id:
            messagebox.showinfo("Info", "Sélectionnez un utilisateur.")
            return
        conn = get_connection()
        user = conn.execute("SELECT * FROM utilisateurs WHERE id=?",
                            (self.selected_id,)).fetchone()
        conn.close()
        UserForm(self, self.current_user, user_data=dict(user),
                 on_save=self._load_users)

    def _toggle_active(self):
        if not self.selected_id:
            messagebox.showinfo("Info", "Sélectionnez un utilisateur.")
            return
        conn = get_connection()
        row = conn.execute("SELECT actif, login FROM utilisateurs WHERE id=?",
                           (self.selected_id,)).fetchone()
        if row["login"] == "admin":
            messagebox.showwarning("Impossible",
                                   "Le compte admin ne peut pas être désactivé.")
            conn.close()
            return
        new_val = 0 if row["actif"] else 1
        conn.execute("UPDATE utilisateurs SET actif=? WHERE id=?",
                     (new_val, self.selected_id))
        conn.commit()
        conn.close()
        log_action(self.current_user["id"],
                   f"{'Activation' if new_val else 'Désactivation'} utilisateur",
                   "utilisateurs", self.selected_id)
        self._load_users()

    def _open_form(self):
        UserForm(self, self.current_user, on_save=self._load_users)


class UserForm(tk.Toplevel):
    """Formulaire création / modification utilisateur."""
    def __init__(self, parent, current_user, user_data=None, on_save=None):
        super().__init__(parent)
        self.current_user = current_user
        self.user_data = user_data
        self.on_save = on_save
        self.title("Modifier utilisateur" if user_data else "Nouvel utilisateur")
        self.resizable(False, False)
        self._build()
        self.grab_set()

    def _build(self):
        pad = {"padx": 8, "pady": 4}
        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)

        fields = [
            ("Nom *", "nom"), ("Prénom *", "prenom"),
            ("Login *", "login"), ("Email", "email"),
            ("Téléphone", "telephone"), ("Notes", "notes"),
        ]
        self.vars = {}
        for i, (label, key) in enumerate(fields):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="e", **pad)
            v = tk.StringVar(
                value=self.user_data.get(key, "") if self.user_data else ""
            )
            self.vars[key] = v
            ttk.Entry(f, textvariable=v, width=30).grid(
                row=i, column=1, sticky="w", **pad
            )

        # Mot de passe
        row = len(fields)
        ttk.Label(f, text="Mot de passe" + (
            " (laisser vide = inchangé)" if self.user_data else " *"
        )).grid(row=row, column=0, sticky="e", **pad)
        self.var_pwd = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_pwd, show="*", width=30
                  ).grid(row=row, column=1, sticky="w", **pad)

        # Rôle
        row += 1
        ttk.Label(f, text="Rôle *").grid(row=row, column=0, sticky="e", **pad)
        self.var_role = tk.StringVar(
            value=ROLES.get(self.user_data["role"], "technicien")
            if self.user_data else "Technicien laboratoire"
        )
        ttk.Combobox(f, textvariable=self.var_role, values=list(ROLES.values()),
                     width=28, state="readonly"
                     ).grid(row=row, column=1, sticky="w", **pad)

        # Expiration accès (pour visiteurs)
        row += 1
        ttk.Label(f, text="Expiration accès").grid(
            row=row, column=0, sticky="e", **pad
        )
        self.var_expire = tk.StringVar(
            value=self.user_data.get("acces_expire", "") if self.user_data else ""
        )
        ttk.Entry(f, textvariable=self.var_expire, width=14
                  ).grid(row=row, column=1, sticky="w", **pad)
        ttk.Label(f, text="(AAAA-MM-JJ — pour visiteurs)").grid(
            row=row, column=2, sticky="w"
        )

        # Labos
        row += 1
        ttk.Label(f, text="Labos assignés *").grid(
            row=row, column=0, sticky="ne", **pad
        )
        labo_frame = ttk.Frame(f)
        labo_frame.grid(row=row, column=1, sticky="w", **pad)
        self.var_labos = {}
        assigned = []
        if self.user_data:
            conn = get_connection()
            assigned = [x["labo_id"] for x in conn.execute(
                "SELECT labo_id FROM user_labos WHERE user_id=?",
                (self.user_data["id"],)).fetchall()]
            conn.close()
        for labo_id, labo_name in LABOS.items():
            v = tk.IntVar(value=1 if labo_id in assigned else 0)
            self.var_labos[labo_id] = v
            ttk.Checkbutton(labo_frame, text=labo_name, variable=v).pack(anchor="w")

        # Boutons
        row += 1
        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=12)
        ttk.Button(btn_frame, text="Enregistrer",
                   command=self._save).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="Annuler",
                   command=self.destroy).pack(side="left")

    def _save(self):
        nom = self.vars["nom"].get().strip()
        prenom = self.vars["prenom"].get().strip()
        login = self.vars["login"].get().strip()
        if not nom or not prenom or not login:
            messagebox.showerror("Erreur",
                                 "Nom, prénom et login sont obligatoires.")
            return

        role_label = self.var_role.get()
        role_key = next(
            (k for k, v in ROLES.items() if v == role_label), "technicien"
        )

        assigned_labos = [lid for lid, v in self.var_labos.items() if v.get()]
        if not assigned_labos:
            messagebox.showerror("Erreur", "Assignez au moins un laboratoire.")
            return

        conn = get_connection()
        try:
            if self.user_data:
                updates = {
                    "nom": nom, "prenom": prenom, "login": login,
                    "role": role_key,
                    "email": self.vars["email"].get().strip(),
                    "telephone": self.vars["telephone"].get().strip(),
                    "notes": self.vars["notes"].get().strip(),
                    "acces_expire": self.var_expire.get().strip() or None,
                }
                conn.execute("""
                    UPDATE utilisateurs
                    SET nom=:nom, prenom=:prenom, login=:login, role=:role,
                        email=:email, telephone=:telephone, notes=:notes,
                        acces_expire=:acces_expire
                    WHERE id=:id
                """, {**updates, "id": self.user_data["id"]})
                if self.var_pwd.get():
                    conn.execute(
                        "UPDATE utilisateurs SET password=? WHERE id=?",
                        (hash_password(self.var_pwd.get()), self.user_data["id"]),
                    )
                # Mettre à jour labos
                conn.execute("DELETE FROM user_labos WHERE user_id=?",
                             (self.user_data["id"],))
                for lid in assigned_labos:
                    conn.execute("INSERT INTO user_labos VALUES (?, ?)",
                                 (self.user_data["id"], lid))
                log_action(self.current_user["id"], "Modification utilisateur",
                           "utilisateurs", self.user_data["id"])
            else:
                pwd = self.var_pwd.get()
                if not pwd:
                    messagebox.showerror("Erreur",
                                         "Le mot de passe est obligatoire.")
                    return
                c = conn.execute("""
                    INSERT INTO utilisateurs
                        (nom, prenom, login, password, role, email,
                         telephone, notes, acces_expire)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (nom, prenom, login, hash_password(pwd), role_key,
                      self.vars["email"].get().strip(),
                      self.vars["telephone"].get().strip(),
                      self.vars["notes"].get().strip(),
                      self.var_expire.get().strip() or None))
                new_id = c.lastrowid
                for lid in assigned_labos:
                    conn.execute("INSERT INTO user_labos VALUES (?, ?)",
                                 (new_id, lid))
                log_action(self.current_user["id"], "Création utilisateur",
                           "utilisateurs", new_id)
            conn.commit()
        except Exception as e:
            messagebox.showerror("Erreur base de données", str(e))
            conn.close()
            return
        conn.close()
        if self.on_save:
            self.on_save()
        self.destroy()
