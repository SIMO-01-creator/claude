"""
Module Traçabilité / Lots - Labo CQ
Recherche rétrospective par numéro de lot, chaîne MP → Produit fini
"""
import tkinter as tk
from tkinter import ttk, messagebox
from core.database import get_connection, has_permission, LABOS


class Tracabilite(ttk.Frame):
    def __init__(self, parent, current_user, **kwargs):
        super().__init__(parent, **kwargs)
        self.current_user = current_user
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self,
                  text="Traçabilité / Lots",
                  font=("Helvetica", 14, "bold")).pack(pady=16, padx=16, anchor="w")
        ttk.Label(self,
                  text="Module en cours de développement (v2).",
                  foreground="gray").pack(padx=16, anchor="w")
