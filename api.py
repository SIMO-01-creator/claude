"""
LaboCQ REST API — Compatible with Glide and other no-code platforms.

Authentication flow:
  1. POST /api/auth/login  { "login": "...", "password": "..." }
     → returns { "token": "...", "user": {...} }
  2. Include  Authorization: Bearer <token>  on every subsequent request.

In Glide:
  - Add a "Custom Integration" pointing to your deployed backend URL.
  - Use the login action once to store the token, then pass it as a header.
"""
import secrets
from datetime import date, datetime

from flask import Blueprint, jsonify, request

from core.database import (LABOS, authenticate, get_connection,
                           has_permission, log_action)

api = Blueprint('api', __name__, url_prefix='/api')


# ── Auth helper ───────────────────────────────────────────────────────────────

def _current_user():
    """Return user dict from Bearer token, or None."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM utilisateurs WHERE api_token=? AND actif=1", (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _unauth():
    return jsonify({'error': 'Unauthorized — missing or invalid Bearer token'}), 401


def _forbidden():
    return jsonify({'error': 'Forbidden — insufficient permissions'}), 403


# ═════════════════════════════════════════════════════════════════════════════
# AUTH
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/auth/login', methods=['POST'])
def api_login():
    """
    POST /api/auth/login
    Body: { "login": "admin", "password": "Admin2024!" }
    Returns: { "token": "...", "user": { id, nom, prenom, role } }
    """
    data = request.get_json(force=True, silent=True) or {}
    login_val = data.get('login', '').strip()
    password = data.get('password', '')

    if not login_val or not password:
        return jsonify({'error': 'login and password are required'}), 400

    user, error = authenticate(login_val, password)
    if not user:
        return jsonify({'error': error or 'Invalid credentials or inactive account'}), 401

    token = secrets.token_urlsafe(32)
    conn = get_connection()
    conn.execute("UPDATE utilisateurs SET api_token=? WHERE id=?",
                 (token, user['id']))
    conn.commit()
    conn.close()

    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'nom': user['nom'],
            'prenom': user['prenom'],
            'login': user['login'],
            'role': user['role'],
        }
    })


@api.route('/auth/logout', methods=['POST'])
def api_logout():
    user = _current_user()
    if user:
        conn = get_connection()
        conn.execute("UPDATE utilisateurs SET api_token=NULL WHERE id=?",
                     (user['id'],))
        conn.commit()
        conn.close()
    return jsonify({'ok': True})


# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD — KPIs
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/dashboard', methods=['GET'])
def api_dashboard():
    """GET /api/dashboard — Returns KPI counts for the main dashboard."""
    user = _current_user()
    if not user:
        return _unauth()

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
    conn.close()
    return jsonify(kpis)


# ═════════════════════════════════════════════════════════════════════════════
# RÉFÉRENTIELS (read-only)
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/labos', methods=['GET'])
def api_labos():
    """GET /api/labos — List of labs."""
    if not _current_user():
        return _unauth()
    return jsonify([{'id': k, 'nom': v} for k, v in LABOS.items()])


@api.route('/produits', methods=['GET'])
def api_produits():
    """GET /api/produits — Active products/references."""
    if not _current_user():
        return _unauth()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, code, nom, type_produit, labo_id FROM produits WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api.route('/fournisseurs', methods=['GET'])
def api_fournisseurs():
    """GET /api/fournisseurs — Active suppliers."""
    if not _current_user():
        return _unauth()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, nom, pays, contact FROM fournisseurs WHERE actif=1 ORDER BY nom"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api.route('/plan-controle', methods=['GET'])
def api_plan_controle():
    """GET /api/plan-controle — Active control plans."""
    if not _current_user():
        return _unauth()
    conn = get_connection()
    rows = conn.execute("""
        SELECT pc.id, pc.parametre, pc.unite, pc.methode, pc.frequence,
               pc.valeur_cible, pc.limite_inf, pc.limite_sup,
               pc.limite_alerte_inf, pc.limite_alerte_sup,
               pc.labo_id, p.nom as produit_nom
        FROM plan_controle pc
        JOIN produits p ON pc.produit_id=p.id
        WHERE pc.actif=1 ORDER BY p.nom, pc.parametre
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ═════════════════════════════════════════════════════════════════════════════
# ÉCHANTILLONS
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/echantillons', methods=['GET'])
def api_echantillons_list():
    """
    GET /api/echantillons
    Query params: labo_id, statut, limit (default 200)
    """
    user = _current_user()
    if not user:
        return _unauth()

    labo_id = request.args.get('labo_id')
    statut = request.args.get('statut')
    limit = min(int(request.args.get('limit', 200)), 500)

    where = []
    params = []
    if labo_id:
        where.append("e.labo_id=?")
        params.append(labo_id)
    if statut:
        where.append("e.statut=?")
        params.append(statut)
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_connection()
    rows = conn.execute(f"""
        SELECT e.id, e.code_echantillon, e.numero_lot, e.statut, e.priorite,
               e.type_analyse, e.date_reception, e.commentaire, e.labo_id,
               p.nom as produit_nom, p.code as produit_code,
               f.nom as fournisseur_nom,
               u.nom || ' ' || u.prenom as operateur_nom
        FROM echantillons e
        LEFT JOIN produits p ON e.produit_id=p.id
        LEFT JOIN fournisseurs f ON e.fournisseur_id=f.id
        LEFT JOIN utilisateurs u ON e.operateur_id=u.id
        {where_clause}
        ORDER BY e.date_reception DESC LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api.route('/echantillons', methods=['POST'])
def api_echantillons_create():
    """
    POST /api/echantillons
    Body: { numero_lot, produit_id?, fournisseur_id?, labo_id, type_analyse,
            date_reception?, priorite?, commentaire? }
    """
    user = _current_user()
    if not user:
        return _unauth()
    if not (has_permission(user, 'register_samples') or
            has_permission(user, 'manage_samples') or
            has_permission(user, 'all')):
        return _forbidden()

    data = request.get_json(force=True, silent=True) or {}
    if not data.get('labo_id'):
        return jsonify({'error': 'labo_id is required'}), 400

    code = f"ECH-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    conn = get_connection()
    conn.execute("""
        INSERT INTO echantillons (code_echantillon, numero_lot, produit_id,
            fournisseur_id, labo_id, type_analyse, date_reception,
            operateur_id, statut, priorite, commentaire, date_creation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'En attente', ?, ?, datetime('now'))
    """, (code, data.get('numero_lot', ''), data.get('produit_id'),
          data.get('fournisseur_id'), int(data['labo_id']),
          data.get('type_analyse', ''),
          data.get('date_reception') or date.today().isoformat(),
          user['id'], data.get('priorite', 'Normale'),
          data.get('commentaire', '')))
    conn.commit()
    eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return jsonify({'id': eid, 'code_echantillon': code}), 201


@api.route('/echantillons/<int:eid>', methods=['GET'])
def api_echantillons_detail(eid):
    """GET /api/echantillons/<id> — Single sample with its results."""
    user = _current_user()
    if not user:
        return _unauth()
    conn = get_connection()
    row = conn.execute("""
        SELECT e.*, p.nom as produit_nom, f.nom as fournisseur_nom
        FROM echantillons e
        LEFT JOIN produits p ON e.produit_id=p.id
        LEFT JOIN fournisseurs f ON e.fournisseur_id=f.id
        WHERE e.id=?
    """, (eid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    resultats = conn.execute("""
        SELECT r.parametre, r.valeur_numerique, r.valeur_texte,
               r.unite, r.conforme, r.date_saisie
        FROM resultats r WHERE r.echantillon_id=? ORDER BY r.date_saisie
    """, (eid,)).fetchall()
    conn.close()
    sample = dict(row)
    sample['resultats'] = [dict(r) for r in resultats]
    return jsonify(sample)


# ═════════════════════════════════════════════════════════════════════════════
# RÉSULTATS
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/resultats', methods=['GET'])
def api_resultats_list():
    """
    GET /api/resultats
    Query params: labo_id, conforme (0/1), limit (default 200)
    """
    user = _current_user()
    if not user:
        return _unauth()

    labo_id = request.args.get('labo_id')
    conforme = request.args.get('conforme')
    limit = min(int(request.args.get('limit', 200)), 500)

    where = []
    params = []
    if labo_id:
        where.append("e.labo_id=?")
        params.append(labo_id)
    if conforme is not None:
        where.append("r.conforme=?")
        params.append(int(conforme))
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_connection()
    rows = conn.execute(f"""
        SELECT r.id, r.parametre, r.valeur_numerique, r.valeur_texte,
               r.unite, r.conforme, r.ecart, r.date_saisie, r.commentaire,
               r.source, e.code_echantillon, e.numero_lot, e.labo_id,
               u.nom || ' ' || u.prenom as operateur_nom,
               v.nom || ' ' || v.prenom as validateur_nom
        FROM resultats r
        JOIN echantillons e ON r.echantillon_id=e.id
        LEFT JOIN utilisateurs u ON r.operateur_id=u.id
        LEFT JOIN utilisateurs v ON r.validateur_id=v.id
        {where_clause}
        ORDER BY r.date_saisie DESC LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api.route('/resultats', methods=['POST'])
def api_resultats_create():
    """
    POST /api/resultats
    Body: { echantillon_id, parametre, valeur_numerique?, valeur_texte?,
            unite?, plan_controle_id?, commentaire? }
    """
    user = _current_user()
    if not user:
        return _unauth()
    if not (has_permission(user, 'write_results') or has_permission(user, 'all')):
        return _forbidden()

    data = request.get_json(force=True, silent=True) or {}
    if not data.get('echantillon_id') or not data.get('parametre'):
        return jsonify({'error': 'echantillon_id and parametre are required'}), 400

    val_num = data.get('valeur_numerique')
    conforme, ecart = 1, 0

    conn = get_connection()
    if data.get('plan_controle_id') and val_num is not None:
        plan = conn.execute('SELECT * FROM plan_controle WHERE id=?',
                            (data['plan_controle_id'],)).fetchone()
        if plan:
            v = float(val_num)
            if (plan['limite_inf'] is not None and v < plan['limite_inf']) or \
               (plan['limite_sup'] is not None and v > plan['limite_sup']):
                conforme, ecart = 0, 1

    conn.execute("""
        INSERT INTO resultats (echantillon_id, plan_controle_id, parametre,
            valeur_numerique, valeur_texte, unite, conforme, ecart,
            operateur_id, date_saisie, commentaire, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, 'glide')
    """, (int(data['echantillon_id']), data.get('plan_controle_id'),
          data['parametre'], val_num, data.get('valeur_texte', ''),
          data.get('unite', ''), conforme, ecart, user['id'],
          data.get('commentaire', '')))
    conn.commit()
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    resp = {'id': rid, 'conforme': conforme}
    if not conforme:
        resp['warning'] = 'Result out of limits — check non-conformities'
    return jsonify(resp), 201


@api.route('/resultats/<int:rid>/validate', methods=['POST'])
def api_resultats_validate(rid):
    """POST /api/resultats/<id>/validate — Mark result as validated."""
    user = _current_user()
    if not user:
        return _unauth()
    if not (has_permission(user, 'validate_results') or has_permission(user, 'all')):
        return _forbidden()
    conn = get_connection()
    conn.execute("""UPDATE resultats SET validateur_id=?, date_validation=datetime('now')
                    WHERE id=?""", (user['id'], rid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'validateur_id': user['id']})


# ═════════════════════════════════════════════════════════════════════════════
# NON-CONFORMITÉS
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/ncr', methods=['GET'])
def api_ncr_list():
    """
    GET /api/ncr
    Query params: labo_id, statut, gravite, limit (default 200)
    """
    user = _current_user()
    if not user:
        return _unauth()

    labo_id = request.args.get('labo_id')
    statut = request.args.get('statut')
    gravite = request.args.get('gravite')
    limit = min(int(request.args.get('limit', 200)), 500)

    where = []
    params = []
    if labo_id:
        where.append("n.labo_id=?")
        params.append(labo_id)
    if statut:
        where.append("n.statut=?")
        params.append(statut)
    if gravite:
        where.append("n.gravite=?")
        params.append(gravite)
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_connection()
    rows = conn.execute(f"""
        SELECT n.id, n.numero_ncr, n.gravite, n.statut, n.date_ouverture,
               n.description, n.lot_bloque, n.labo_id, n.date_cloture,
               e.code_echantillon,
               u.nom || ' ' || u.prenom as ouvert_par_nom
        FROM non_conformites n
        LEFT JOIN echantillons e ON n.echantillon_id=e.id
        LEFT JOIN utilisateurs u ON n.ouvert_par_id=u.id
        {where_clause}
        ORDER BY n.date_ouverture DESC LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api.route('/ncr', methods=['POST'])
def api_ncr_create():
    """
    POST /api/ncr
    Body: { description, labo_id, gravite?, echantillon_id?, lot_bloque? }
    """
    user = _current_user()
    if not user:
        return _unauth()
    if not (has_permission(user, 'open_ncr') or has_permission(user, 'all')):
        return _forbidden()

    data = request.get_json(force=True, silent=True) or {}
    if not data.get('description') or not data.get('labo_id'):
        return jsonify({'error': 'description and labo_id are required'}), 400

    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM non_conformites").fetchone()[0] + 1
    numero = f"NCR-{date.today().year}-{count:04d}"
    conn.execute("""
        INSERT INTO non_conformites (numero_ncr, echantillon_id, labo_id,
            description, gravite, statut, lot_bloque, ouvert_par_id,
            date_ouverture)
        VALUES (?, ?, ?, ?, ?, 'Ouverte', ?, ?, datetime('now'))
    """, (numero, data.get('echantillon_id'), int(data['labo_id']),
          data['description'], data.get('gravite', 'Mineure'),
          1 if data.get('lot_bloque') else 0, user['id']))
    conn.commit()
    ncr_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    log_action(user['id'], 'CREATE_NCR', 'non_conformites', ncr_id,
               f"Via Glide API: {numero}")
    return jsonify({'id': ncr_id, 'numero_ncr': numero}), 201


@api.route('/ncr/<int:ncr_id>/close', methods=['POST'])
def api_ncr_close(ncr_id):
    """POST /api/ncr/<id>/close — Close an NCR."""
    user = _current_user()
    if not user:
        return _unauth()
    if not (has_permission(user, 'open_ncr') or has_permission(user, 'all')):
        return _forbidden()
    conn = get_connection()
    conn.execute("""UPDATE non_conformites SET statut='Clôturée',
                    date_cloture=date('now'), clos_par_id=? WHERE id=?""",
                 (user['id'], ncr_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ═════════════════════════════════════════════════════════════════════════════
# ÉQUIPEMENTS
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/equipements', methods=['GET'])
def api_equipements_list():
    """
    GET /api/equipements
    Query params: labo_id, alerte_only (1 = only overdue/alert items)
    """
    user = _current_user()
    if not user:
        return _unauth()

    labo_id = request.args.get('labo_id')
    alerte_only = request.args.get('alerte_only')

    where = ["e.actif=1"]
    params = []
    if labo_id:
        where.append("e.labo_id=?")
        params.append(labo_id)
    if alerte_only:
        where.append("e.prochaine_etalonnage <= date('now', '+30 days')")

    conn = get_connection()
    rows = conn.execute(f"""
        SELECT e.id, e.code_equipement, e.nom, e.marque, e.modele,
               e.statut, e.labo_id, e.prochaine_etalonnage,
               e.prochaine_verification, e.notes,
               CASE WHEN e.prochaine_etalonnage < date('now') THEN 'Dépassé'
                    WHEN e.prochaine_etalonnage <= date('now','+30 days') THEN 'Alerte'
                    ELSE 'OK' END as cal_statut
        FROM equipements e
        WHERE {' AND '.join(where)}
        ORDER BY e.labo_id, e.nom
    """, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ═════════════════════════════════════════════════════════════════════════════
# TENDANCES (chart data)
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/tendances/data', methods=['GET'])
def api_tendances_data():
    """
    GET /api/tendances/data?plan_id=<id>
    Returns time-series data for a control plan parameter.
    """
    user = _current_user()
    if not user:
        return _unauth()

    plan_id = request.args.get('plan_id')
    if not plan_id:
        return jsonify({'error': 'plan_id is required'}), 400

    conn = get_connection()
    plan = conn.execute('SELECT * FROM plan_controle WHERE id=?', (plan_id,)).fetchone()
    rows = conn.execute("""
        SELECT date(r.date_saisie) as jour,
               AVG(r.valeur_numerique) as moy,
               MIN(r.valeur_numerique) as min_v,
               MAX(r.valeur_numerique) as max_v,
               COUNT(*) as nb
        FROM resultats r
        WHERE r.plan_controle_id=? AND r.valeur_numerique IS NOT NULL
        GROUP BY jour ORDER BY jour DESC LIMIT 60
    """, (plan_id,)).fetchall()
    conn.close()
    rows = list(reversed(rows))
    return jsonify({
        'parametre': plan['parametre'] if plan else '',
        'unite': plan['unite'] if plan else '',
        'limite_inf': plan['limite_inf'] if plan else None,
        'limite_sup': plan['limite_sup'] if plan else None,
        'alerte_inf': plan['limite_alerte_inf'] if plan else None,
        'alerte_sup': plan['limite_alerte_sup'] if plan else None,
        'cible': plan['valeur_cible'] if plan else None,
        'data': [
            {
                'date': r['jour'],
                'moyenne': round(r['moy'], 4) if r['moy'] else None,
                'min': r['min_v'],
                'max': r['max_v'],
                'nb_mesures': r['nb'],
            }
            for r in rows
        ],
    })


# ═════════════════════════════════════════════════════════════════════════════
# TRAÇABILITÉ
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/tracabilite', methods=['GET'])
def api_tracabilite():
    """
    GET /api/tracabilite?lot=<numero_lot>
    Returns all samples matching the lot number with their NCR counts.
    """
    user = _current_user()
    if not user:
        return _unauth()

    lot = request.args.get('lot', '').strip()
    if not lot:
        return jsonify({'error': 'lot query param is required'}), 400

    conn = get_connection()
    results = conn.execute("""
        SELECT e.id, e.code_echantillon, e.numero_lot, e.statut,
               e.date_reception, e.labo_id,
               p.nom as produit_nom, f.nom as fournisseur_nom,
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
    return jsonify([dict(r) for r in results])


# ═════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═════════════════════════════════════════════════════════════════════════════

@api.route('/health', methods=['GET'])
def api_health():
    """GET /api/health — No auth required. Used by Glide to verify connectivity."""
    return jsonify({'status': 'ok', 'app': 'LaboCQ', 'version': '2.0'})
