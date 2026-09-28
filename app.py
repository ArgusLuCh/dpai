import hmac
import os
from datetime import datetime, timezone

import click
import psycopg2
import psycopg2.extras
from flask import Flask, abort, redirect, render_template, request, url_for
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL.")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

EN_PRODUCCION = os.environ.get("FLASK_ENV") == "production"
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if EN_PRODUCCION:
        raise RuntimeError("Falta SECRET_KEY en producción.")
    SECRET_KEY = "dev-only-clave-insegura"

# Token del link público de estadísticas: /estadisticas/<STATS_TOKEN>
STATS_TOKEN = os.environ.get("STATS_TOKEN", "")

STATUSES = {
    'elevada': 'Elevada',
    'elevada_con_acusado': 'Elevada (con acusado)',
    'elevada_con_pedido_allanamiento': 'Elevada con pedido de allanamiento',
    'en_investigacion': 'En investigación',
    'elevada_a_fiscalia': 'Elevada a Fiscalía',
    'elevada_a_otra_dependencia': 'Elevada a otra dependencia',
}


# ---------- Base de datos ----------

class DBWrapper:
    """Conexión psycopg2 con '?' como placeholder y filas tipo diccionario."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=None):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query.replace('?', '%s'), params or None)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db():
    return DBWrapper(psycopg2.connect(DATABASE_URL))


def hoy():
    return datetime.now(timezone.utc).date().isoformat()


def ahora():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        nombre_usuario TEXT UNIQUE NOT NULL,
        contrasena TEXT NOT NULL,
        nombre_completo TEXT,
        es_admin INTEGER DEFAULT 0,
        es_consulta INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS actuaciones (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES usuarios(id),
        numero_actuacion TEXT NOT NULL,
        caratula TEXT,
        fecha_lugar TEXT NOT NULL DEFAULT '',
        fecha_hecho TEXT,
        fecha_registro TEXT,
        dependencia TEXT,
        actuario TEXT,
        fecha_avocamiento TEXT,
        damnificado TEXT NOT NULL,
        acusado TEXT NOT NULL,
        relato TEXT,
        estado TEXT,
        created_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS allanamientos (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES usuarios(id),
        fecha_allanamiento TEXT,
        ap TEXT NOT NULL,
        causa TEXT NOT NULL,
        acusados TEXT NOT NULL,
        damnificado TEXT NOT NULL,
        esclarecido TEXT,
        cantidad_detenidos INTEGER,
        cantidad_secuestros INTEGER,
        tipo_secuestro TEXT,
        cantidad_domicilios INTEGER,
        localidad TEXT,
        created_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS oficios_judiciales (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES usuarios(id),
        fecha_ingreso TEXT NOT NULL,
        numero_expediente TEXT NOT NULL,
        fiscalia TEXT,
        acusado TEXT,
        diligencias TEXT,
        actuario TEXT,
        pedido_allanamiento TEXT,
        resultado TEXT,
        created_at TEXT NOT NULL)''')
    # Filas viejas cargadas sin fecha de allanamiento: usar la fecha de carga
    conn.execute("UPDATE allanamientos SET fecha_allanamiento=substr(created_at,1,10) "
                 "WHERE fecha_allanamiento IS NULL OR fecha_allanamiento=''")
    conn.commit()
    conn.close()


# ---------- App y login ----------

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
if EN_PRODUCCION:
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax')

login_manager = LoginManager(app)
login_manager.login_view = 'login'


class Usuario(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.nombre_usuario = row['nombre_usuario']
        self.nombre_completo = row['nombre_completo']


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM usuarios WHERE id=? AND es_admin=1', (user_id,)).fetchone()
    conn.close()
    return Usuario(row) if row else None


init_db()


@app.cli.command('crear-admin')
@click.argument('usuario')
@click.option('--nombre', default=None, help='Nombre completo')
@click.password_option()
def crear_admin(usuario, nombre, password):
    """Crea un admin, o si ya existe le da rol admin y cambia la contraseña."""
    conn = get_db()
    existe = conn.execute('SELECT id FROM usuarios WHERE nombre_usuario=?', (usuario,)).fetchone()
    hash_ = generate_password_hash(password)
    if existe:
        conn.execute('UPDATE usuarios SET contrasena=?, es_admin=1, es_consulta=0 WHERE id=?',
                     (hash_, existe['id']))
    else:
        conn.execute('INSERT INTO usuarios (nombre_usuario, contrasena, nombre_completo, es_admin) '
                     'VALUES (?,?,?,1)', (usuario, hash_, nombre or usuario))
    conn.commit()
    conn.close()
    click.echo(f"Admin '{usuario}' listo.")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        row = conn.execute('SELECT * FROM usuarios WHERE nombre_usuario=? AND es_admin=1',
                           (request.form.get('nombre_usuario', ''),)).fetchone()
        conn.close()
        if row and check_password_hash(row['contrasena'], request.form.get('contrasena', '')):
            login_user(Usuario(row))
            return redirect(url_for('index'))
        return render_template('login.html', error='Usuario o contraseña incorrectos')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------- Actuaciones ----------

def form_actuacion():
    f = request.form
    g = lambda k: f.get(k, '').strip()
    estado = g('estado') or 'en_investigacion'
    datos = dict(numero_actuacion=g('numero_actuacion'), caratula=g('caratula'),
                 fecha_hecho=g('fecha_hecho'), fecha_registro=g('fecha_registro') or hoy(),
                 dependencia=g('dependencia'), actuario=g('actuario'),
                 fecha_avocamiento=g('fecha_avocamiento'), damnificado=g('damnificado'),
                 acusado=g('acusado'), relato=g('relato'), estado=estado)
    valido = all(datos[k] for k in ('numero_actuacion', 'fecha_hecho', 'damnificado', 'acusado'))
    return datos, valido


@app.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    conn = get_db()
    if q:
        p = f'%{q}%'
        filas = conn.execute(
            '''SELECT * FROM actuaciones
               WHERE numero_actuacion ILIKE ? OR caratula ILIKE ? OR damnificado ILIKE ?
                  OR acusado ILIKE ? OR dependencia ILIKE ?
               ORDER BY created_at DESC''', (p, p, p, p, p)).fetchall()
    else:
        filas = conn.execute('SELECT * FROM actuaciones ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('index.html', actuaciones=filas, statuses=STATUSES,
                           busqueda=q, hoy=hoy())


@app.route('/add', methods=['POST'])
@login_required
def add():
    d, valido = form_actuacion()
    if valido:
        conn = get_db()
        conn.execute(
            '''INSERT INTO actuaciones (user_id, numero_actuacion, caratula, fecha_lugar, fecha_hecho,
               fecha_registro, dependencia, actuario, fecha_avocamiento, damnificado, acusado, relato,
               estado, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (current_user.id, d['numero_actuacion'], d['caratula'], '', d['fecha_hecho'],
             d['fecha_registro'], d['dependencia'], d['actuario'], d['fecha_avocamiento'],
             d['damnificado'], d['acusado'], d['relato'], d['estado'], ahora()))
        conn.commit()
        conn.close()
    return redirect(url_for('index'))


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    conn = get_db()
    fila = conn.execute('SELECT * FROM actuaciones WHERE id=?', (id,)).fetchone()
    if not fila:
        conn.close()
        return redirect(url_for('index'))
    if request.method == 'POST':
        d, valido = form_actuacion()
        if not valido:
            conn.close()
            return render_template('edit.html', a=fila, statuses=STATUSES, hoy=hoy(),
                                   error='Número, fecha del hecho, damnificado y acusado son obligatorios')
        conn.execute(
            '''UPDATE actuaciones SET numero_actuacion=?, caratula=?, fecha_hecho=?, fecha_registro=?,
               dependencia=?, actuario=?, fecha_avocamiento=?, damnificado=?, acusado=?, relato=?,
               estado=? WHERE id=?''',
            (d['numero_actuacion'], d['caratula'], d['fecha_hecho'], d['fecha_registro'],
             d['dependencia'], d['actuario'], d['fecha_avocamiento'], d['damnificado'],
             d['acusado'], d['relato'], d['estado'], id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    conn.close()
    return render_template('edit.html', a=fila, statuses=STATUSES, hoy=hoy())


@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    conn = get_db()
    conn.execute('DELETE FROM actuaciones WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))


# ---------- Allanamientos y oficios (listar, agregar, editar, borrar) ----------

def int_o_none(v):
    v = (v or '').strip()
    return int(v) if v.isdigit() else None


def datos_allanamiento():
    g = lambda k: request.form.get(k, '').strip()
    return (g('fecha_allanamiento') or hoy(), g('ap'), g('causa'), g('acusados'), g('damnificado'),
            g('esclarecido'), int_o_none(g('cantidad_detenidos')), int_o_none(g('cantidad_secuestros')),
            g('tipo_secuestro'), int_o_none(g('cantidad_domicilios')), g('localidad'))


def datos_oficio():
    g = lambda k: request.form.get(k, '').strip()
    return (g('fecha_ingreso'), g('numero_expediente'), g('fiscalia'), g('acusado'),
            g('diligencias'), g('actuario'), g('pedido_allanamiento'), g('resultado'))


def listar(tabla, template, editar_id=None, error=None):
    conn = get_db()
    registros = conn.execute(f'SELECT * FROM {tabla} ORDER BY created_at DESC').fetchall()
    r = None
    if editar_id:
        r = conn.execute(f'SELECT * FROM {tabla} WHERE id=?', (editar_id,)).fetchone()
        if not r:
            conn.close()
            abort(404)
    conn.close()
    return render_template(template, registros=registros, r=r, hoy=hoy(), error=error)


@app.route('/allanamientos', methods=['GET', 'POST'])
@app.route('/allanamientos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def allanamientos(id=None):
    if request.method == 'POST':
        d = datos_allanamiento()
        if not all(d[1:5]):
            return listar('allanamientos', 'allanamientos.html', id,
                          'AP, causa, acusados y damnificado son obligatorios')
        conn = get_db()
        if id:
            conn.execute('''UPDATE allanamientos SET fecha_allanamiento=?, ap=?, causa=?, acusados=?,
                damnificado=?, esclarecido=?, cantidad_detenidos=?, cantidad_secuestros=?,
                tipo_secuestro=?, cantidad_domicilios=?, localidad=? WHERE id=?''', (*d, id))
        else:
            conn.execute('''INSERT INTO allanamientos (fecha_allanamiento, ap, causa, acusados,
                damnificado, esclarecido, cantidad_detenidos, cantidad_secuestros, tipo_secuestro,
                cantidad_domicilios, localidad, user_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', (*d, current_user.id, ahora()))
        conn.commit()
        conn.close()
        return redirect(url_for('allanamientos'))
    return listar('allanamientos', 'allanamientos.html', id)


@app.route('/allanamientos/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_allanamiento(id):
    conn = get_db()
    conn.execute('DELETE FROM allanamientos WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('allanamientos'))


@app.route('/oficios-judiciales', methods=['GET', 'POST'])
@app.route('/oficios-judiciales/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def oficios_judiciales(id=None):
    if request.method == 'POST':
        d = datos_oficio()
        if not d[0] or not d[1]:
            return listar('oficios_judiciales', 'oficios_judiciales.html', id,
                          'Fecha de ingreso y número de expediente son obligatorios')
        conn = get_db()
        if id:
            conn.execute('''UPDATE oficios_judiciales SET fecha_ingreso=?, numero_expediente=?,
                fiscalia=?, acusado=?, diligencias=?, actuario=?, pedido_allanamiento=?, resultado=?
                WHERE id=?''', (*d, id))
        else:
            conn.execute('''INSERT INTO oficios_judiciales (fecha_ingreso, numero_expediente, fiscalia,
                acusado, diligencias, actuario, pedido_allanamiento, resultado, user_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''', (*d, current_user.id, ahora()))
        conn.commit()
        conn.close()
        return redirect(url_for('oficios_judiciales'))
    return listar('oficios_judiciales', 'oficios_judiciales.html', id)


@app.route('/oficios-judiciales/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_oficio_judicial(id):
    conn = get_db()
    conn.execute('DELETE FROM oficios_judiciales WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('oficios_judiciales'))


# ---------- Estadísticas ----------

def calcular_estadisticas():
    conn = get_db()
    caratulas = conn.execute(
        '''SELECT substr(fecha_registro,1,4) AS anio,
                  COALESCE(NULLIF(TRIM(caratula),''),'Sin carátula') AS caratula, COUNT(*) AS cantidad
           FROM actuaciones WHERE fecha_registro IS NOT NULL AND fecha_registro != ''
           GROUP BY anio, caratula ORDER BY anio DESC, cantidad DESC, caratula''').fetchall()
    por_anio = {}
    for fila in caratulas:
        por_anio.setdefault(fila['anio'], []).append(fila)
    allan = conn.execute(
        '''SELECT substr(fecha_allanamiento,1,4) AS anio, COUNT(*) AS cantidad,
                  COALESCE(SUM(cantidad_domicilios),0) AS domicilios,
                  COALESCE(SUM(cantidad_detenidos),0) AS detenidos
           FROM allanamientos WHERE fecha_allanamiento IS NOT NULL AND fecha_allanamiento != ''
           GROUP BY anio ORDER BY anio DESC''').fetchall()
    oficios = conn.execute(
        '''SELECT substr(fecha_ingreso,1,4) AS anio, COUNT(*) AS cantidad,
                  SUM(CASE WHEN UPPER(TRIM(resultado))='POSITIVO' THEN 1 ELSE 0 END) AS positivos,
                  SUM(CASE WHEN LOWER(TRIM(pedido_allanamiento)) LIKE 'si%'
                             OR LOWER(TRIM(pedido_allanamiento)) LIKE 'sí%'
                             OR LOWER(TRIM(pedido_allanamiento)) LIKE 'tiene%'
                             OR LOWER(TRIM(pedido_allanamiento)) LIKE 'positivo%'
                           THEN 1 ELSE 0 END) AS con_allanamiento
           FROM oficios_judiciales WHERE fecha_ingreso IS NOT NULL AND fecha_ingreso != ''
           GROUP BY anio ORDER BY anio DESC''').fetchall()
    conn.close()
    s = lambda filas, k: sum(f[k] or 0 for f in filas)
    return dict(
        actuaciones_por_anio=por_anio, allanamientos=allan, oficios=oficios,
        total_actuaciones=s(caratulas, 'cantidad'), total_allanamientos=s(allan, 'cantidad'),
        total_oficios=s(oficios, 'cantidad'), domicilios=s(allan, 'domicilios'),
        detenidos=s(allan, 'detenidos'), positivos=s(oficios, 'positivos'),
        con_allanamiento=s(oficios, 'con_allanamiento'))


@app.route('/estadisticas')
@login_required
def estadisticas():
    link = url_for('estadisticas_publicas', token=STATS_TOKEN, _external=True) if STATS_TOKEN else None
    return render_template('estadisticas.html', publico=False, link=link, **calcular_estadisticas())


@app.route('/estadisticas/<token>')
def estadisticas_publicas(token):
    if not STATS_TOKEN or not hmac.compare_digest(token, STATS_TOKEN):
        abort(404)
    return render_template('estadisticas.html', publico=True, link=None, **calcular_estadisticas())


@app.after_request
def no_indexar(resp):
    if request.path.startswith('/estadisticas'):
        resp.headers['X-Robots-Tag'] = 'noindex, nofollow'
        resp.headers['Cache-Control'] = 'no-store'
    return resp


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=not EN_PRODUCCION, host='0.0.0.0', port=port)
