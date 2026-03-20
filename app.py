"""
LaboCQ Web — Application Flask de gestion laboratoire contrôle qualité
"""
import os
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Flask, render_template, redirect, url_for, request,
                   flash, jsonify, abort)
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)

from core.database import (init_database, authenticate, get_connection,
                            has_permission, LABOS, ROLES, hash_password, log_action)

# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'labocq-dev-secret-changeme')

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Veuillez vous connecter.'
login_manager.login_message_category = 'warning'


# ─── User class ───────────────────────────────────────────────────────────────
class WebUser(UserMixin):
    def __init__(self, d: dict):
        self.id = str(d['id'])
        self.login = d['login']
        self.nom = d['nom']
        self.prenom = d['prenom']
        self.role = d['role']
        self._d = d

    def perm(self, p: str) -> bool:
        return has_permission(self._d, p)

    @property
    def full_name(self):
        return f"{self.prenom} {self.nom}"

    @property
    def role_label(self):
        return ROLES.get(self.role, self.role)


@login_manager.user_loader
def load_user(user_id):
    conn = get_connection()
    row = conn.execute('SELECT * FROM utilisateurs WHERE id=?', (user_id,)).fetchone()
    conn.close()
    return WebUser(dict(row)) if row else None


# ─── Permission decorator ─────────────────────────────────────────────────────
def perm_required(permission):
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.perm(permission):
                flash('Accès refusé — droits insuffisants.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ─── Context processor ────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    return {'LABOS': LABOS, 'ROLES': ROLES}


# ═════════════════════════════════════════════════════════════════════════════
# AUTH
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        login_val = request.form.get('login', '').strip()
        pwd = request.form.get('password', '')
        user, err = authenticate(login_val, pwd)
        if user:
            web_user = WebUser(dict(user))
            login_user(web_user, remember=True)
            return redirect(url_for('dashboard'))
        error = err or 'Identifiants incorrects ou compte inactif.'
    return render_template('login.html', error=error)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Déconnexion réussie.', 'info')
    return redirect(url_for('login'))


# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def dashboard():
    conn = get_connection()
    kpis = {
        'echantillons_attente': conn.execute(
            "SELECT COUNT(*) FROM echantillons WHERE statut='En attente'"
        ).fetchone()[0],
        'ncr_ouvertes': conn.execute(
            "SELECT COUNT(*) FROM non_conformites WHERE statut='Ouverte'"
        ).fetchone()[0],
        'equip_alerte': conn.execute(
            """SELECT COUNT(*) FROM equipements WHERE actif=1
               AND prochaine_etalonnage IS NOT NULL
               AND prochaine_etalonnage <= date('now', '+30 days')"""
        ).fetchone()[0],
        'resultats_today': conn.execute(
            "SELECT COUNT(*) FROM resultats WHERE date(date_saisie)=date('now')"
        ).fetchone()[0],
        'competences_alerte': conn.execute(
            "SELECT COUNT(*) FROM competences_personnel WHERE statut IN ('Expirée','Alerte')"
        ).fetchone()[0],
    }
    ncr_list = conn.execute("""
        SELECT n.id, n.numero_ncr, n.gravite, n.statut, n.date_ouverture,
               e.code_echantillon, n.description
        FROM non_conformites n
        LEFT JOIN echantillons e ON n.echantillon_id=e.id
        WHERE n.statut='Ouverte'
        ORDER BY n.date_ouverture DESC LIMIT 10
    """).fetchall()
    equip_list = conn.execute("""
        SELECT e.id, e.nom, e.code_equipement, e.prochaine_etalonnage,
               CASE WHEN e.prochaine_etalonnage < date('now') THEN 'Dépassé'
                    ELSE 'Alerte' END as cal_statut
        FROM equipements e
        WHERE e.actif=1 AND e.prochaine_etalonnage IS NOT NULL
          AND e.prochaine_etalonnage <= date('now', '+30 days')
        ORDER BY e.prochaine_etalonnage
    """).fetchall()
    conn.close()
    return render_template('dashboard.html', kpis=kpis,
                           ncr_list=ncr_list, equip_list=equip_list)


# ═════════════════════════════════════════════════════════════════════════════
# ÉCHANTILLONS
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/echantillons')
@login_required
def echantillons_list():
    conn = get_connection()
    rows = conn.execute("""
        SELECT e.*, p.nom as produit_nom, f.nom as fournisseur_nom,
               u.nom || ' ' || u.prenom as operateur_nom
        FROM echantillons e
        LEFT JOIN produits p ON e.produit_id=p.id
        LEFT JOIN fournisseurs f ON e.fournisseur_id=f.id
        LEFT JOIN utilisateurs u ON e.operateur_id=u.id
        ORDER BY e.date_reception DESC LIMIT 200
    """).fetchall()
    conn.close()
    return render_template('echantillons/index.html', echantillons=rows)


@app.route('/echantillons/new', methods=['GET', 'POST'])
@login_required
def echantillons_new():
    if not (current_user.perm('register_samples') or current_user.perm('manage_samples')
            or current_user.perm('all')):
        flash('Accès refusé.', 'danger')
        return redirect(url_for('echantillons_list'))
    conn = get_connection()
    if request.method == 'POST':
        f = request.form
        code = f"ECH-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        conn.execute("""
            INSERT INTO echantillons (code_echantillon, numero_lot, produit_id,
                fournisseur_id, labo_id, type_analyse, date_reception,
                operateur_id, statut, priorite, commentaire, date_creation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'En attente', ?, ?, datetime('now'))
        """, (code, f.get('numero_lot', ''), f.get('produit_id') or None,
              f.get('fournisseur_id') or None, int(f['labo_id']),
              f.get('type_analyse', ''),
              f.get('date_reception') or date.today().isoformat(),
              int(current_user.id), f.get('priorite', 'Normale'),
              f.get('commentaire', '')))
        conn.commit()
        conn.close()
        flash(f'Échantillon {code} enregistré.', 'success')
        return redirect(url_for('echantillons_list'))
    produits = conn.execute(
        "SELECT id, code, nom FROM produits WHERE actif=1 ORDER BY nom"
    ).fetchall()
    fournisseurs = conn.execute(
        "SELECT id, nom FROM fournisseurs WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return render_template('echantillons/form.html',
                           produits=produits, fournisseurs=fournisseurs)


# ═════════════════════════════════════════════════════════════════════════════
# SAISIE RÉSULTATS
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/resultats')
@login_required
def resultats_list():
    conn = get_connection()
    rows = conn.execute("""
        SELECT r.*, e.code_echantillon, e.numero_lot,
               u.nom || ' ' || u.prenom as operateur_nom,
               v.nom || ' ' || v.prenom as validateur_nom
        FROM resultats r
        JOIN echantillons e ON r.echantillon_id=e.id
        LEFT JOIN utilisateurs u ON r.operateur_id=u.id
        LEFT JOIN utilisateurs v ON r.validateur_id=v.id
        ORDER BY r.date_saisie DESC LIMIT 200
    """).fetchall()
    conn.close()
    return render_template('resultats/index.html', resultats=rows)


@app.route('/resultats/new', methods=['GET', 'POST'])
@login_required
def resultats_new():
    if not (current_user.perm('write_results') or current_user.perm('all')):
        flash('Accès refusé.', 'danger')
        return redirect(url_for('resultats_list'))
    conn = get_connection()
    if request.method == 'POST':
        f = request.form
        val_num = f.get('valeur_numerique') or None
        conforme = 1
        ecart = 0
        if f.get('plan_controle_id') and val_num:
            plan = conn.execute(
                'SELECT * FROM plan_controle WHERE id=?', (f['plan_controle_id'],)
            ).fetchone()
            if plan:
                v = float(val_num)
                if (plan['limite_inf'] is not None and v < plan['limite_inf']) or \
                   (plan['limite_sup'] is not None and v > plan['limite_sup']):
                    conforme = 0
                    ecart = 1
        conn.execute("""
            INSERT INTO resultats (echantillon_id, plan_controle_id, parametre,
                valeur_numerique, valeur_texte, unite, conforme, ecart,
                operateur_id, date_saisie, commentaire, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, 'manuel')
        """, (int(f['echantillon_id']), f.get('plan_controle_id') or None,
              f['parametre'], val_num, f.get('valeur_texte', ''),
              f.get('unite', ''), conforme, ecart, int(current_user.id),
              f.get('commentaire', '')))
        conn.commit()
        conn.close()
        flash('Résultat enregistré.', 'success')
        if not conforme:
            flash('Résultat hors limites — vérifiez les non-conformités.', 'warning')
        return redirect(url_for('resultats_list'))
    echantillons = conn.execute("""
        SELECT id, code_echantillon, numero_lot FROM echantillons
        WHERE statut='En attente' ORDER BY date_reception DESC LIMIT 100
    """).fetchall()
    plans = conn.execute("""
        SELECT pc.id, pc.parametre, pc.unite, p.nom as produit_nom,
               pc.limite_inf, pc.limite_sup, pc.valeur_cible
        FROM plan_controle pc
        JOIN produits p ON pc.produit_id=p.id
        WHERE pc.actif=1 ORDER BY p.nom, pc.parametre
    """).fetchall()
    conn.close()
    return render_template('resultats/form.html',
                           echantillons=echantillons, plans=plans)


@app.route('/resultats/<int:rid>/validate', methods=['POST'])
@login_required
def resultats_validate(rid):
    if not (current_user.perm('validate_results') or current_user.perm('all')):
        abort(403)
    conn = get_connection()
    conn.execute("""
        UPDATE resultats SET validateur_id=?, date_validation=datetime('now')
        WHERE id=?
    """, (int(current_user.id), rid))
    conn.commit()
    conn.close()
    flash('Résultat validé.', 'success')
    return redirect(url_for('resultats_list'))


# ═════════════════════════════════════════════════════════════════════════════
# NON-CONFORMITÉS
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/ncr')
@login_required
def ncr_list():
    conn = get_connection()
    ncrs = conn.execute("""
        SELECT n.*, e.code_echantillon,
               u.nom || ' ' || u.prenom as ouvert_par_nom
        FROM non_conformites n
        LEFT JOIN echantillons e ON n.echantillon_id=e.id
        LEFT JOIN utilisateurs u ON n.ouvert_par_id=u.id
        ORDER BY n.date_ouverture DESC
    """).fetchall()
    conn.close()
    return render_template('ncr/index.html', ncrs=ncrs)


@app.route('/ncr/new', methods=['GET', 'POST'])
@login_required
def ncr_new():
    if not (current_user.perm('open_ncr') or current_user.perm('all')):
        flash('Accès refusé.', 'danger')
        return redirect(url_for('ncr_list'))
    conn = get_connection()
    if request.method == 'POST':
        f = request.form
        count = conn.execute("SELECT COUNT(*) FROM non_conformites").fetchone()[0] + 1
        numero = f"NCR-{date.today().year}-{count:04d}"
        conn.execute("""
            INSERT INTO non_conformites (numero_ncr, echantillon_id, labo_id,
                description, gravite, statut, lot_bloque, ouvert_par_id,
                date_ouverture)
            VALUES (?, ?, ?, ?, ?, 'Ouverte', ?, ?, datetime('now'))
        """, (numero, f.get('echantillon_id') or None, int(f['labo_id']),
              f['description'], f['gravite'],
              1 if f.get('lot_bloque') else 0, int(current_user.id)))
        conn.commit()
        ncr_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        flash(f'Non-conformité {numero} ouverte.', 'success')
        return redirect(url_for('ncr_detail', ncr_id=ncr_id))
    echantillons = conn.execute(
        "SELECT id, code_echantillon FROM echantillons ORDER BY date_reception DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return render_template('ncr/form.html', echantillons=echantillons)


@app.route('/ncr/<int:ncr_id>')
@login_required
def ncr_detail(ncr_id):
    conn = get_connection()
    ncr = conn.execute("""
        SELECT n.*, e.code_echantillon,
               u.nom || ' ' || u.prenom as ouvert_par_nom,
               c.nom || ' ' || c.prenom as clos_par_nom
        FROM non_conformites n
        LEFT JOIN echantillons e ON n.echantillon_id=e.id
        LEFT JOIN utilisateurs u ON n.ouvert_par_id=u.id
        LEFT JOIN utilisateurs c ON n.clos_par_id=c.id
        WHERE n.id=?
    """, (ncr_id,)).fetchone()
    if not ncr:
        conn.close()
        abort(404)
    causes = conn.execute("""
        SELECT c.*, u.nom || ' ' || u.prenom as auteur_nom
        FROM ncr_causes c
        LEFT JOIN utilisateurs u ON c.auteur_id=u.id
        WHERE c.ncr_id=? ORDER BY c.date_saisie
    """, (ncr_id,)).fetchall()
    actions = conn.execute("""
        SELECT a.*, u.nom || ' ' || u.prenom as responsable_nom
        FROM actions_correctives a
        LEFT JOIN utilisateurs u ON a.responsable_id=u.id
        WHERE a.ncr_id=? ORDER BY a.date_echeance
    """, (ncr_id,)).fetchall()
    users = conn.execute(
        "SELECT id, nom, prenom FROM utilisateurs WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return render_template('ncr/detail.html', ncr=ncr, causes=causes,
                           actions=actions, users=users)


@app.route('/ncr/<int:ncr_id>/cause', methods=['POST'])
@login_required
def ncr_add_cause(ncr_id):
    f = request.form
    conn = get_connection()
    conn.execute("""
        INSERT INTO ncr_causes (ncr_id, categorie, description, analyse_5m,
            auteur_id, date_saisie)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (ncr_id, f.get('categorie', ''), f['description'],
          f.get('analyse_5m', ''), int(current_user.id)))
    conn.commit()
    conn.close()
    flash('Cause ajoutée.', 'success')
    return redirect(url_for('ncr_detail', ncr_id=ncr_id))


@app.route('/ncr/<int:ncr_id>/action', methods=['POST'])
@login_required
def ncr_add_action(ncr_id):
    f = request.form
    conn = get_connection()
    conn.execute("""
        INSERT INTO actions_correctives (ncr_id, type_action, description,
            responsable_id, date_echeance, statut)
        VALUES (?, ?, ?, ?, ?, 'Planifiée')
    """, (ncr_id, f.get('type_action', 'Corrective'), f['description'],
          f.get('responsable_id') or None, f.get('date_echeance') or None))
    conn.commit()
    conn.close()
    flash('Action ajoutée.', 'success')
    return redirect(url_for('ncr_detail', ncr_id=ncr_id))


@app.route('/ncr/<int:ncr_id>/action/<int:act_id>/done', methods=['POST'])
@login_required
def ncr_action_done(ncr_id, act_id):
    conn = get_connection()
    conn.execute("""
        UPDATE actions_correctives SET statut='Réalisée',
            date_realisation=date('now') WHERE id=?
    """, (act_id,))
    conn.commit()
    conn.close()
    flash('Action marquée réalisée.', 'success')
    return redirect(url_for('ncr_detail', ncr_id=ncr_id))


@app.route('/ncr/<int:ncr_id>/close', methods=['POST'])
@login_required
def ncr_close(ncr_id):
    conn = get_connection()
    conn.execute("""
        UPDATE non_conformites SET statut='Clôturée', date_cloture=date('now'),
            clos_par_id=? WHERE id=?
    """, (int(current_user.id), ncr_id))
    conn.commit()
    conn.close()
    flash('Non-conformité clôturée.', 'success')
    return redirect(url_for('ncr_detail', ncr_id=ncr_id))


# ═════════════════════════════════════════════════════════════════════════════
# PLAN DE CONTRÔLE
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/plan-controle')
@login_required
def plan_controle_list():
    conn = get_connection()
    plans = conn.execute("""
        SELECT pc.*, p.nom as produit_nom, p.code as produit_code
        FROM plan_controle pc
        JOIN produits p ON pc.produit_id=p.id
        WHERE pc.actif=1 ORDER BY p.nom, pc.parametre
    """).fetchall()
    produits = conn.execute(
        "SELECT id, code, nom FROM produits WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return render_template('plan_controle/index.html', plans=plans, produits=produits)


@app.route('/plan-controle/new', methods=['GET', 'POST'])
@login_required
def plan_controle_new():
    if not (current_user.perm('admin') or current_user.perm('all')):
        flash('Accès refusé.', 'danger')
        return redirect(url_for('plan_controle_list'))
    conn = get_connection()
    if request.method == 'POST':
        f = request.form
        conn.execute("""
            INSERT INTO plan_controle (produit_id, parametre, unite, methode,
                frequence, valeur_cible, limite_inf, limite_sup,
                limite_alerte_inf, limite_alerte_sup, etape_process,
                labo_id, obligatoire, actif, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (int(f['produit_id']), f['parametre'], f.get('unite', ''),
              f.get('methode', ''), f.get('frequence', 'Par lot'),
              f.get('valeur_cible') or None, f.get('limite_inf') or None,
              f.get('limite_sup') or None, f.get('limite_alerte_inf') or None,
              f.get('limite_alerte_sup') or None, f.get('etape_process', ''),
              int(f['labo_id']), 1 if f.get('obligatoire') else 0,
              f.get('notes', '')))
        conn.commit()
        conn.close()
        flash('Plan de contrôle créé.', 'success')
        return redirect(url_for('plan_controle_list'))
    produits = conn.execute(
        "SELECT id, code, nom FROM produits WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return render_template('plan_controle/form.html', produits=produits)


# ═════════════════════════════════════════════════════════════════════════════
# ÉQUIPEMENTS
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/equipment')
@login_required
def equipment_list():
    if not (current_user.perm('manage_equipments') or
            current_user.perm('read_equipments') or current_user.perm('all')):
        flash('Accès refusé.', 'danger')
        return redirect(url_for('dashboard'))
    conn = get_connection()
    equip = conn.execute("""
        SELECT e.*, u.nom || ' ' || u.prenom as responsable_nom,
               CASE
                 WHEN e.prochaine_etalonnage < date('now') THEN 'Dépassé'
                 WHEN e.prochaine_etalonnage <= date('now', '+30 days') THEN 'Alerte'
                 ELSE 'OK'
               END as cal_statut
        FROM equipements e
        LEFT JOIN utilisateurs u ON e.responsable_id=u.id
        WHERE e.actif=1 ORDER BY e.labo_id, e.nom
    """).fetchall()
    conn.close()
    return render_template('equipment/index.html', equip=equip)


@app.route('/equipment/new', methods=['GET', 'POST'])
@perm_required('manage_equipments')
def equipment_new():
    if request.method == 'POST':
        f = request.form
        conn = get_connection()
        conn.execute("""
            INSERT INTO equipements (code_equipement, nom, marque, modele,
                numero_serie, labo_id, date_mise_en_service,
                prochaine_verification, prochaine_etalonnage, statut, notes, actif)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (f['code_equipement'], f['nom'], f.get('marque', ''),
              f.get('modele', ''), f.get('numero_serie', ''),
              int(f['labo_id']), f.get('date_mise_en_service') or None,
              f.get('prochaine_verification') or None,
              f.get('prochaine_etalonnage') or None,
              f.get('statut', 'Opérationnel'), f.get('notes', '')))
        conn.commit()
        conn.close()
        flash('Équipement créé.', 'success')
        return redirect(url_for('equipment_list'))
    return render_template('equipment/form.html', equipment=None)


@app.route('/equipment/<int:eid>')
@login_required
def equipment_detail(eid):
    if not (current_user.perm('manage_equipments') or
            current_user.perm('read_equipments') or current_user.perm('all')):
        abort(403)
    conn = get_connection()
    equip = conn.execute('SELECT * FROM equipements WHERE id=?', (eid,)).fetchone()
    if not equip:
        conn.close()
        abort(404)
    calibrations = conn.execute("""
        SELECT c.*, u.nom || ' ' || u.prenom as operateur_nom
        FROM etalonnages c
        LEFT JOIN utilisateurs u ON c.operateur_id=u.id
        WHERE c.equipement_id=? ORDER BY c.date_etalonnage DESC
    """, (eid,)).fetchall()
    conn.close()
    return render_template('equipment/detail.html', equip=equip,
                           calibrations=calibrations)


@app.route('/equipment/<int:eid>/calibrate', methods=['POST'])
@perm_required('manage_equipments')
def equipment_calibrate(eid):
    f = request.form
    conn = get_connection()
    conn.execute("""
        INSERT INTO etalonnages (equipement_id, date_etalonnage, type_operation,
            resultat, conforme, operateur_id, prochain_etalonnage,
            certificat_ref, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (eid, f['date_etalonnage'], f.get('type_operation', 'Étalonnage'),
          f.get('resultat', ''), 1 if f.get('conforme') else 0,
          int(current_user.id), f.get('prochain_etalonnage') or None,
          f.get('certificat_ref', ''), f.get('notes', '')))
    if f.get('prochain_etalonnage'):
        conn.execute('UPDATE equipements SET prochaine_etalonnage=? WHERE id=?',
                     (f['prochain_etalonnage'], eid))
    conn.commit()
    conn.close()
    flash('Étalonnage enregistré.', 'success')
    return redirect(url_for('equipment_detail', eid=eid))


# ═════════════════════════════════════════════════════════════════════════════
# TRAÇABILITÉ
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/tracabilite')
@login_required
def tracabilite():
    lot = request.args.get('lot', '').strip()
    results = []
    if lot:
        conn = get_connection()
        results = conn.execute("""
            SELECT e.*, p.nom as produit_nom, p.code as produit_code,
                   f.nom as fournisseur_nom,
                   COUNT(r.id) as nb_resultats,
                   SUM(CASE WHEN r.conforme=0 THEN 1 ELSE 0 END) as nb_nc,
                   (SELECT COUNT(*) FROM non_conformites n
                    WHERE n.echantillon_id=e.id AND n.statut='Ouverte') as ncr_ouvertes
            FROM echantillons e
            LEFT JOIN produits p ON e.produit_id=p.id
            LEFT JOIN fournisseurs f ON e.fournisseur_id=f.id
            LEFT JOIN resultats r ON e.id=r.echantillon_id
            WHERE e.numero_lot LIKE ?
            GROUP BY e.id ORDER BY e.date_reception DESC
        """, (f'%{lot}%',)).fetchall()
        conn.close()
    return render_template('tracabilite/index.html', results=results, lot=lot)


# ═════════════════════════════════════════════════════════════════════════════
# TENDANCES
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/tendances')
@login_required
def tendances():
    conn = get_connection()
    plans = conn.execute("""
        SELECT pc.id, pc.parametre, p.nom as produit_nom
        FROM plan_controle pc
        JOIN produits p ON pc.produit_id=p.id
        WHERE pc.actif=1 ORDER BY p.nom, pc.parametre
    """).fetchall()
    conn.close()
    return render_template('tendances/index.html', plans=plans)


@app.route('/tendances/data')
@login_required
def tendances_data():
    plan_id = request.args.get('plan_id')
    if not plan_id:
        return jsonify({'labels': [], 'values': []})
    conn = get_connection()
    plan = conn.execute('SELECT * FROM plan_controle WHERE id=?', (plan_id,)).fetchone()
    rows = conn.execute("""
        SELECT date(r.date_saisie) as jour, AVG(r.valeur_numerique) as moy,
               MIN(r.valeur_numerique) as min_v, MAX(r.valeur_numerique) as max_v
        FROM resultats r
        WHERE r.plan_controle_id=? AND r.valeur_numerique IS NOT NULL
        GROUP BY jour ORDER BY jour DESC LIMIT 60
    """, (plan_id,)).fetchall()
    conn.close()
    rows = list(reversed(rows))
    return jsonify({
        'labels': [r['jour'] for r in rows],
        'values': [round(r['moy'], 4) if r['moy'] else None for r in rows],
        'parametre': plan['parametre'] if plan else '',
        'unite': plan['unite'] if plan else '',
        'limit_inf': plan['limite_inf'] if plan else None,
        'limit_sup': plan['limite_sup'] if plan else None,
        'alerte_inf': plan['limite_alerte_inf'] if plan else None,
        'alerte_sup': plan['limite_alerte_sup'] if plan else None,
        'cible': plan['valeur_cible'] if plan else None,
    })


# ═════════════════════════════════════════════════════════════════════════════
# ONBOARDING / RH
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/onboarding')
@login_required
def onboarding():
    conn = get_connection()
    formations = conn.execute(
        "SELECT * FROM formations WHERE actif=1 ORDER BY titre"
    ).fetchall()
    competences = conn.execute("""
        SELECT cp.*, u.nom || ' ' || u.prenom as personnel_nom,
               f.titre as formation_titre
        FROM competences_personnel cp
        JOIN utilisateurs u ON cp.user_id=u.id
        JOIN formations f ON cp.formation_id=f.id
        ORDER BY cp.statut DESC, u.nom
    """).fetchall()
    users = conn.execute(
        "SELECT id, nom, prenom FROM utilisateurs WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return render_template('onboarding/index.html', formations=formations,
                           competences=competences, users=users)


@app.route('/onboarding/formation/new', methods=['POST'])
@perm_required('admin')
def onboarding_new_formation():
    f = request.form
    conn = get_connection()
    conn.execute("""
        INSERT INTO formations (titre, description, type_formation, labo_id,
            duree_heures, validite_mois, obligatoire, actif)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    """, (f['titre'], f.get('description', ''),
          f.get('type_formation', 'Interne'),
          f.get('labo_id') or None,
          f.get('duree_heures') or None,
          f.get('validite_mois') or None,
          1 if f.get('obligatoire') else 0))
    conn.commit()
    conn.close()
    flash('Formation créée.', 'success')
    return redirect(url_for('onboarding'))


@app.route('/onboarding/competence/new', methods=['POST'])
@login_required
def onboarding_new_competence():
    f = request.form
    conn = get_connection()
    formation = conn.execute(
        'SELECT validite_mois FROM formations WHERE id=?', (f['formation_id'],)
    ).fetchone()
    date_exp = None
    if formation and formation['validite_mois'] and f.get('date_formation'):
        d = datetime.strptime(f['date_formation'], '%Y-%m-%d')
        date_exp = (d + timedelta(days=30 * int(formation['validite_mois']))).strftime('%Y-%m-%d')
    conn.execute("""
        INSERT INTO competences_personnel (user_id, formation_id, date_formation,
            date_expiration, resultat, score, formateur, statut)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Valide')
    """, (int(f['user_id']), int(f['formation_id']),
          f.get('date_formation'),
          date_exp, f.get('resultat', 'Réussi'),
          f.get('score') or None, f.get('formateur', '')))
    conn.commit()
    conn.close()
    flash('Compétence enregistrée.', 'success')
    return redirect(url_for('onboarding'))


# ═════════════════════════════════════════════════════════════════════════════
# RAPPORTS
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/rapports')
@login_required
def rapports():
    if not (current_user.perm('read_reports') or current_user.perm('download_reports')
            or current_user.perm('all')):
        flash('Accès refusé.', 'danger')
        return redirect(url_for('dashboard'))
    conn = get_connection()
    stats = {
        'total_resultats': conn.execute("SELECT COUNT(*) FROM resultats").fetchone()[0],
        'total_nc': conn.execute(
            "SELECT COUNT(*) FROM resultats WHERE conforme=0"
        ).fetchone()[0],
        'total_ncr': conn.execute("SELECT COUNT(*) FROM non_conformites").fetchone()[0],
        'ncr_ouvertes': conn.execute(
            "SELECT COUNT(*) FROM non_conformites WHERE statut='Ouverte'"
        ).fetchone()[0],
    }
    ncr_by_gravite = conn.execute("""
        SELECT gravite, COUNT(*) as count
        FROM non_conformites GROUP BY gravite
    """).fetchall()
    ncr_by_labo = conn.execute("""
        SELECT labo_id, statut, COUNT(*) as count
        FROM non_conformites GROUP BY labo_id, statut
    """).fetchall()
    recent_resultats = conn.execute("""
        SELECT r.parametre, r.valeur_numerique, r.unite, r.conforme,
               r.date_saisie, e.code_echantillon, e.numero_lot
        FROM resultats r
        JOIN echantillons e ON r.echantillon_id=e.id
        ORDER BY r.date_saisie DESC LIMIT 20
    """).fetchall()
    conn.close()
    return render_template('rapports/index.html', stats=stats,
                           ncr_by_gravite=ncr_by_gravite,
                           ncr_by_labo=ncr_by_labo,
                           recent_resultats=recent_resultats)


# ═════════════════════════════════════════════════════════════════════════════
# UTILISATEURS
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/users')
@perm_required('admin')
def users_list():
    conn = get_connection()
    users = conn.execute("""
        SELECT u.*, GROUP_CONCAT(ul.labo_id) as labos
        FROM utilisateurs u
        LEFT JOIN user_labos ul ON u.id=ul.user_id
        GROUP BY u.id ORDER BY u.nom, u.prenom
    """).fetchall()
    conn.close()
    return render_template('users/index.html', users=users)


@app.route('/users/new', methods=['GET', 'POST'])
@perm_required('admin')
def users_new():
    if request.method == 'POST':
        f = request.form
        errors = []
        if not f.get('nom'): errors.append('Nom requis')
        if not f.get('prenom'): errors.append('Prénom requis')
        if not f.get('login'): errors.append('Login requis')
        if not f.get('password'): errors.append('Mot de passe requis')
        if not f.get('role'): errors.append('Rôle requis')
        if not errors:
            conn = get_connection()
            try:
                cur = conn.execute("""
                    INSERT INTO utilisateurs (nom, prenom, login, password, role,
                        email, telephone, notes, actif, date_creation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
                """, (f['nom'], f['prenom'], f['login'],
                      hash_password(f['password']), f['role'],
                      f.get('email', ''), f.get('telephone', ''),
                      f.get('notes', '')))
                uid = cur.lastrowid
                for labo in request.form.getlist('labos'):
                    conn.execute(
                        'INSERT INTO user_labos (user_id, labo_id) VALUES (?,?)',
                        (uid, int(labo)))
                conn.commit()
                log_action(int(current_user.id), 'CREATE_USER',
                           'utilisateurs', uid, f"Créé: {f['login']}")
                conn.close()
                flash('Utilisateur créé avec succès.', 'success')
                return redirect(url_for('users_list'))
            except Exception as e:
                conn.close()
                errors.append(str(e))
        for e in errors:
            flash(e, 'danger')
    return render_template('users/form.html', user=None, user_labos=[], action='new')


@app.route('/users/<int:uid>/edit', methods=['GET', 'POST'])
@perm_required('admin')
def users_edit(uid):
    conn = get_connection()
    user = conn.execute('SELECT * FROM utilisateurs WHERE id=?', (uid,)).fetchone()
    if not user:
        conn.close()
        abort(404)
    user_labos = [r['labo_id'] for r in
                  conn.execute('SELECT labo_id FROM user_labos WHERE user_id=?',
                               (uid,)).fetchall()]
    if request.method == 'POST':
        f = request.form
        pwd_hash = hash_password(f['password']) if f.get('password') else user['password']
        conn.execute("""
            UPDATE utilisateurs SET nom=?, prenom=?, login=?, password=?,
                role=?, email=?, telephone=?, notes=?, actif=?
            WHERE id=?
        """, (f['nom'], f['prenom'], f['login'], pwd_hash, f['role'],
              f.get('email', ''), f.get('telephone', ''), f.get('notes', ''),
              1 if f.get('actif') else 0, uid))
        conn.execute('DELETE FROM user_labos WHERE user_id=?', (uid,))
        for labo in request.form.getlist('labos'):
            conn.execute('INSERT INTO user_labos (user_id, labo_id) VALUES (?,?)',
                         (uid, int(labo)))
        conn.commit()
        conn.close()
        flash('Utilisateur mis à jour.', 'success')
        return redirect(url_for('users_list'))
    conn.close()
    return render_template('users/form.html', user=dict(user),
                           user_labos=user_labos, action='edit')


@app.route('/users/<int:uid>/toggle', methods=['POST'])
@perm_required('admin')
def users_toggle(uid):
    conn = get_connection()
    user = conn.execute('SELECT actif FROM utilisateurs WHERE id=?', (uid,)).fetchone()
    if user:
        new_status = 0 if user['actif'] else 1
        conn.execute('UPDATE utilisateurs SET actif=? WHERE id=?', (new_status, uid))
        conn.commit()
    conn.close()
    flash('Statut mis à jour.', 'success')
    return redirect(url_for('users_list'))


# ═════════════════════════════════════════════════════════════════════════════
# PRODUITS & FOURNISSEURS
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/produits')
@perm_required('admin')
def produits_list():
    conn = get_connection()
    produits = conn.execute(
        "SELECT * FROM produits WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return render_template('produits/index.html', produits=produits)


@app.route('/produits/new', methods=['POST'])
@perm_required('admin')
def produits_new():
    f = request.form
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO produits (code, nom, type_produit, labo_id, description, actif)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (f['code'], f['nom'], f.get('type_produit', ''),
              f.get('labo_id') or None, f.get('description', '')))
        conn.commit()
        flash('Produit créé.', 'success')
    except Exception as e:
        flash(str(e), 'danger')
    finally:
        conn.close()
    return redirect(url_for('produits_list'))


@app.route('/fournisseurs')
@perm_required('admin')
def fournisseurs_list():
    conn = get_connection()
    fournisseurs = conn.execute(
        "SELECT * FROM fournisseurs WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return render_template('fournisseurs/index.html', fournisseurs=fournisseurs)


@app.route('/fournisseurs/new', methods=['POST'])
@perm_required('admin')
def fournisseurs_new():
    f = request.form
    conn = get_connection()
    conn.execute("""
        INSERT INTO fournisseurs (nom, pays, contact, actif)
        VALUES (?, ?, ?, 1)
    """, (f['nom'], f.get('pays', ''), f.get('contact', '')))
    conn.commit()
    conn.close()
    flash('Fournisseur créé.', 'success')
    return redirect(url_for('fournisseurs_list'))


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)
