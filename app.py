import os
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone

# En local, si existe un .env, lo carga (en Railway las variables ya vienen seteadas)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "Falta la variable de entorno DATABASE_URL (cadena de conexión de Postgres)."
    )
# Railway a veces entrega "postgres://"; psycopg2 espera "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def current_utc_isoformat():
    return datetime.now(timezone.utc).isoformat()

class DBWrapper:
    """Adapta una conexión psycopg2 para que se use igual que sqlite3.Connection:
    conn.execute(query, params).fetchone()/.fetchall(), con '?' como placeholder."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=None):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = query.replace('?', '%s')
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return DBWrapper(conn)

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        nombre_usuario TEXT UNIQUE NOT NULL,
        contrasena TEXT NOT NULL,
        nombre_completo TEXT,
        es_admin INTEGER DEFAULT 0,
        es_consulta INTEGER DEFAULT 0
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS actuaciones (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES usuarios(id),
        numero_actuacion TEXT NOT NULL,
        fecha_lugar TEXT NOT NULL,
        fecha_hecho TEXT,
        fecha_registro TEXT,
        dependencia TEXT,
        actuario TEXT,
        fecha_avocamiento TEXT,
        damnificado TEXT NOT NULL,
        acusado TEXT NOT NULL,
        relato TEXT,
        estado TEXT,
        color TEXT,
        created_at TEXT NOT NULL
    )''')
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
        created_at TEXT NOT NULL
    )''')
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
        created_at TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()

def ensure_db_schema():
    """Agrega columnas nuevas de forma idempotente (equivalente Postgres de los
    ALTER TABLE condicionales que antes se resolvían con PRAGMA table_info)."""
    conn = get_db()
    conn.execute('ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS es_consulta INTEGER DEFAULT 0')
    conn.execute('ALTER TABLE actuaciones ADD COLUMN IF NOT EXISTS caratula TEXT')
    conn.execute('ALTER TABLE actuaciones ADD COLUMN IF NOT EXISTS actuario TEXT')
    conn.execute('ALTER TABLE actuaciones ADD COLUMN IF NOT EXISTS fecha_hecho TEXT')
    conn.execute(
        "UPDATE actuaciones SET fecha_hecho=substr(created_at, 1, 10) "
        "WHERE fecha_hecho IS NULL AND created_at IS NOT NULL"
    )
    conn.execute('ALTER TABLE actuaciones ADD COLUMN IF NOT EXISTS fecha_registro TEXT')
    conn.execute(
        "UPDATE actuaciones SET fecha_registro=substr(created_at, 1, 10) "
        "WHERE fecha_registro IS NULL AND created_at IS NOT NULL"
    )
    conn.execute('ALTER TABLE allanamientos ADD COLUMN IF NOT EXISTS fecha_allanamiento TEXT')
    conn.execute(
        "UPDATE allanamientos SET fecha_allanamiento=substr(created_at, 1, 10) "
        "WHERE fecha_allanamiento IS NULL AND created_at IS NOT NULL"
    )
    conn.execute('ALTER TABLE oficios_judiciales ADD COLUMN IF NOT EXISTS pedido_allanamiento TEXT')
    conn.execute('ALTER TABLE oficios_judiciales ADD COLUMN IF NOT EXISTS resultado TEXT')
    conn.commit()
    conn.close()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-clave-insegura-cambiar')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class Usuario(UserMixin):
    def __init__(self, id, nombre_usuario, nombre_completo, es_admin=False, es_consulta=False):
        self.id = id
        self.nombre_usuario = nombre_usuario
        self.nombre_completo = nombre_completo
        self.es_admin = es_admin
        self.es_consulta = es_consulta

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM usuarios WHERE id=?', (user_id,)).fetchone()
    conn.close()
    if user:
        return Usuario(user['id'], user['nombre_usuario'], user['nombre_completo'], user['es_admin'], user['es_consulta'])
    return None

STATUSES = {
    'elevada': 'Elevada',
    'elevada_con_acusado': 'Elevada (con acusado)',
    'elevada_con_pedido_allanamiento': 'Elevada con pedido de allanamiento',
    'en_investigacion': 'En investigación',
    'elevada_a_fiscalia': 'Elevada a Fiscalía',
    'elevada_a_otra_dependencia': 'Elevada a otra dependencia'
}
COLORS = ['verde', 'amarillo', 'rojo']

init_db()
ensure_db_schema()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre_usuario = request.form.get('nombre_usuario')
        contrasena = request.form.get('contrasena')
        
        conn = get_db()
        user_data = conn.execute('SELECT * FROM usuarios WHERE nombre_usuario=?', (nombre_usuario,)).fetchone()
        conn.close()
        
        if user_data and check_password_hash(user_data['contrasena'], contrasena):
            user = Usuario(user_data['id'], user_data['nombre_usuario'], user_data['nombre_completo'], user_data['es_admin'], user_data['es_consulta'])
            login_user(user)
            if user.es_consulta and not user.es_admin:
                return redirect(url_for('estadisticas'))
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Usuario o contraseña incorrectos')

    success = None
    if request.args.get('recuperada') == '1':
        success = 'Contraseña actualizada correctamente. Ya puedes iniciar sesión.'

    return render_template('login.html', success=success)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        nombre_usuario = request.form.get('nombre_usuario')
        contrasena = request.form.get('contrasena')
        nombre_completo = request.form.get('nombre_completo')
        
        if not nombre_usuario or not contrasena:
            return render_template('registrar.html', error='Usuario y contraseña requeridos')
        
        conn = get_db()
        try:
            conn.execute('INSERT INTO usuarios (nombre_usuario, contrasena, nombre_completo) VALUES (?,?,?)',
                (nombre_usuario, generate_password_hash(contrasena), nombre_completo))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            conn.close()
            return render_template('registrar.html', error='El usuario ya existe')
    
    return render_template('registrar.html')

@app.route('/olvide-password', methods=['GET', 'POST'])
def olvide_password():
    if request.method == 'POST':
        nombre_usuario = request.form.get('nombre_usuario', '').strip()
        nueva_contrasena = request.form.get('nueva_contrasena', '')
        confirmar_contrasena = request.form.get('confirmar_contrasena', '')

        if not nombre_usuario or not nueva_contrasena or not confirmar_contrasena:
            return render_template('olvide_password.html', error='Debe completar usuario y ambas contraseñas')

        if nueva_contrasena != confirmar_contrasena:
            return render_template('olvide_password.html', error='Las contraseñas no coinciden')

        if len(nueva_contrasena) < 4:
            return render_template('olvide_password.html', error='La contraseña debe tener al menos 4 caracteres')

        conn = get_db()
        user_data = conn.execute(
            'SELECT id FROM usuarios WHERE nombre_usuario=?',
            (nombre_usuario,)
        ).fetchone()

        if not user_data:
            conn.close()
            return render_template('olvide_password.html', error='Usuario no encontrado')

        conn.execute(
            'UPDATE usuarios SET contrasena=? WHERE id=?',
            (generate_password_hash(nueva_contrasena), user_data['id'])
        )
        conn.commit()
        conn.close()

        return redirect(url_for('login', recuperada='1'))

    return render_template('olvide_password.html')

@app.route('/')
@login_required
def index():
    if current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('estadisticas'))
    conn = get_db()
    busqueda = request.args.get('q', '').strip()
    
    if current_user.es_admin:
        if busqueda:
            # Búsqueda general en múltiples campos
            patron = f'%{busqueda}%'
            filas = conn.execute('''SELECT a.*, u.nombre_completo FROM actuaciones a 
                                   JOIN usuarios u ON a.user_id=u.id 
                                   WHERE a.numero_actuacion ILIKE ? 
                                                  OR a.caratula ILIKE ?
                                      OR a.damnificado ILIKE ? 
                                      OR a.acusado ILIKE ? 
                                      OR a.dependencia ILIKE ?
                                   ORDER BY a.created_at DESC''', 
                                          (patron, patron, patron, patron, patron)).fetchall()
        else:
            filas = conn.execute('SELECT a.*, u.nombre_completo FROM actuaciones a JOIN usuarios u ON a.user_id=u.id ORDER BY a.created_at DESC').fetchall()
        
        # Agrupar actuaciones por usuario (nombre_completo)
        actuaciones_por_usuario = {}
        for fila in filas:
            nombre_usuario = fila['nombre_completo']
            if nombre_usuario not in actuaciones_por_usuario:
                actuaciones_por_usuario[nombre_usuario] = []
            actuaciones_por_usuario[nombre_usuario].append(fila)
    else:
        filas = conn.execute('SELECT a.*, u.nombre_completo FROM actuaciones a JOIN usuarios u ON a.user_id=u.id WHERE a.user_id=? ORDER BY a.created_at DESC', (current_user.id,)).fetchall()
        actuaciones_por_usuario = {}
    
    conn.close()
    return render_template('index.html', actuaciones=filas, actuaciones_por_usuario=actuaciones_por_usuario, statuses=STATUSES, colors=COLORS, es_admin=current_user.es_admin, busqueda=busqueda)

@app.route('/add', methods=['POST'])
@login_required
def add():
    if current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('estadisticas'))
    numero_actuacion = request.form.get('numero_actuacion','').strip()
    caratula = request.form.get('caratula','').strip()
    fecha_hecho = request.form.get('fecha_hecho', '').strip()
    fecha_registro = request.form.get('fecha_registro', '').strip() or current_utc_isoformat()[:10]
    dependencia = request.form.get('dependencia','').strip()
    actuario = request.form.get('actuario','').strip()
    fecha_avocamiento = request.form.get('fecha_avocamiento','').strip()
    damnificado = request.form.get('damnificado','').strip()
    acusado = request.form.get('acusado','').strip()
    relato = request.form.get('relato','').strip()
    estado = request.form.get('estado','')
    if estado is not None:
        estado = estado.strip()
    color = request.form.get('color','').strip()
    # Fallback automático: si no se indicó estado, asignar 'en_investigacion'
    if not estado:
        estado = 'en_investigacion'
    if numero_actuacion and fecha_hecho and damnificado and acusado:
        conn = get_db()
        conn.execute('INSERT INTO actuaciones (user_id, numero_actuacion, caratula, fecha_lugar, fecha_hecho, fecha_registro, dependencia, actuario, fecha_avocamiento, damnificado, acusado, relato, estado, color, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (current_user.id, numero_actuacion, caratula, '', fecha_hecho, fecha_registro, dependencia, actuario, fecha_avocamiento, damnificado, acusado, relato, estado, color, current_utc_isoformat()))
        conn.commit()
        conn.close()
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['GET','POST'])
@login_required
def edit(id):
    if current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('estadisticas'))
    conn = get_db()
    fila = conn.execute('SELECT * FROM actuaciones WHERE id=?', (id,)).fetchone()
    
    if not fila:
        conn.close()
        return redirect(url_for('index'))
    
    if fila['user_id'] != current_user.id and not current_user.es_admin:
        conn.close()
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        numero_actuacion = request.form.get('numero_actuacion', '').strip()
        caratula = request.form.get('caratula', '').strip()
        fecha_hecho = request.form.get('fecha_hecho', '').strip()
        fecha_registro = request.form.get('fecha_registro', '').strip() or fila['fecha_registro']
        dependencia = request.form.get('dependencia', '').strip()
        actuario = request.form.get('actuario', '').strip()
        fecha_avocamiento = request.form.get('fecha_avocamiento', '').strip()
        damnificado = request.form.get('damnificado', '').strip()
        acusado = request.form.get('acusado', '').strip()
        relato = request.form.get('relato', '').strip()

        if not numero_actuacion or not fecha_hecho or not damnificado or not acusado:
            conn.close()
            return render_template(
                'edit.html',
                a=fila,
                statuses=STATUSES,
                colors=COLORS,
                es_admin=current_user.es_admin,
                error='Número, fecha del hecho, damnificado y acusado son obligatorios'
            )

        if current_user.es_admin:
            estado = request.form.get('estado')
            if estado is not None:
                estado = estado.strip()
            color = request.form.get('color')
            if color is not None:
                color = color.strip()
            # Fallback automático: si el admin dejó el estado vacío, asignar 'en_investigacion'
            if not estado:
                estado = 'en_investigacion'
            conn.execute('''UPDATE actuaciones
                            SET numero_actuacion=?, caratula=?, fecha_hecho=?, fecha_registro=?, dependencia=?, actuario=?, fecha_avocamiento=?,
                                damnificado=?, acusado=?, relato=?, estado=?, color=?
                            WHERE id=?''',
                         (numero_actuacion, caratula, fecha_hecho, fecha_registro, dependencia, actuario, fecha_avocamiento,
                          damnificado, acusado, relato, estado, color, id))
        else:
            conn.execute('''UPDATE actuaciones
                            SET numero_actuacion=?, caratula=?, fecha_hecho=?, fecha_registro=?, dependencia=?, actuario=?, fecha_avocamiento=?,
                                damnificado=?, acusado=?, relato=?
                            WHERE id=?''',
                         (numero_actuacion, caratula, fecha_hecho, fecha_registro, dependencia, actuario, fecha_avocamiento,
                          damnificado, acusado, relato, id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
    conn.close()
    return render_template('edit.html', a=fila, statuses=STATUSES, colors=COLORS, es_admin=current_user.es_admin)

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    if current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('estadisticas'))
    conn = get_db()
    fila = conn.execute('SELECT user_id FROM actuaciones WHERE id=?', (id,)).fetchone()
    
    if fila and (fila['user_id'] == current_user.id or current_user.es_admin):
        conn.execute('DELETE FROM actuaciones WHERE id=?', (id,))
        conn.commit()
    
    conn.close()
    return redirect(url_for('index'))

def registros_propios_o_todos(conn, tabla):
    if current_user.es_admin:
        return conn.execute(f'SELECT * FROM {tabla} ORDER BY created_at DESC').fetchall()
    return conn.execute(
        f'SELECT * FROM {tabla} WHERE user_id=? ORDER BY created_at DESC',
        (current_user.id,)
    ).fetchall()

@app.route('/estadisticas')
@login_required
def estadisticas():
    if not current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('index'))

    conn = get_db()
    consultas = [
        ('Actuaciones', 'actuaciones', 'fecha_registro'),
        ('Allanamientos', 'allanamientos', 'fecha_allanamiento'),
        ('Oficios judiciales', 'oficios_judiciales', 'fecha_ingreso')
    ]
    por_anio = {}
    totales = {}
    actuaciones_por_caratula = []
    allanamientos_por_anio = []
    oficios_por_anio = []
    for etiqueta, tabla, columna_fecha in consultas:
        if etiqueta == 'Actuaciones':
            filas_caratulas = conn.execute(
                '''SELECT substr(fecha_registro, 1, 4) AS anio,
                          COALESCE(NULLIF(TRIM(caratula), ''), 'Sin carátula') AS caratula,
                          COUNT(*) AS cantidad
                   FROM actuaciones
                   WHERE fecha_registro IS NOT NULL AND fecha_registro != ''
                   GROUP BY anio, caratula
                   ORDER BY anio DESC, cantidad DESC, caratula'''
            ).fetchall()
            actuaciones_por_caratula = []
            for fila in filas_caratulas:
                actuaciones_por_caratula.append({
                    'anio': fila['anio'],
                    'caratula': fila['caratula'],
                    'cantidad': fila['cantidad'],
                    'mostrar_anio': (
                        not actuaciones_por_caratula
                        or actuaciones_por_caratula[-1]['anio'] != fila['anio']
                    )
                })
            for indice, fila in enumerate(actuaciones_por_caratula):
                if fila['mostrar_anio']:
                    fila['rowspan'] = sum(
                        siguiente['anio'] == fila['anio']
                        for siguiente in actuaciones_por_caratula[indice:]
                    )
        elif etiqueta == 'Allanamientos':
            allanamientos_por_anio = conn.execute(
                '''SELECT substr(fecha_allanamiento, 1, 4) AS anio,
                          COUNT(*) AS cantidad,
                          COALESCE(SUM(cantidad_domicilios), 0) AS domicilios,
                          COALESCE(SUM(cantidad_detenidos), 0) AS detenidos
                   FROM allanamientos
                   WHERE fecha_allanamiento IS NOT NULL AND fecha_allanamiento != ''
                   GROUP BY anio
                   ORDER BY anio DESC'''
            ).fetchall()
        elif etiqueta == 'Oficios judiciales':
            oficios_por_anio = conn.execute(
                '''SELECT substr(fecha_ingreso, 1, 4) AS anio,
                          COUNT(*) AS cantidad,
                          SUM(CASE WHEN UPPER(TRIM(resultado)) = 'POSITIVO' THEN 1 ELSE 0 END) AS positivos,
                          SUM(CASE
                                WHEN LOWER(TRIM(pedido_allanamiento)) LIKE 'si%'
                                  OR LOWER(TRIM(pedido_allanamiento)) LIKE 'sí%'
                                  OR LOWER(TRIM(pedido_allanamiento)) LIKE 'tiene%'
                                  OR LOWER(TRIM(pedido_allanamiento)) LIKE 'positivo%'
                                THEN 1 ELSE 0
                              END) AS con_allanamiento
                   FROM oficios_judiciales
                   WHERE fecha_ingreso IS NOT NULL AND fecha_ingreso != ''
                   GROUP BY anio
                   ORDER BY anio DESC'''
            ).fetchall()
        filas = conn.execute(
            f'''SELECT substr({columna_fecha}, 1, 4) AS anio, COUNT(*) AS cantidad
                FROM {tabla}
                WHERE {columna_fecha} IS NOT NULL AND {columna_fecha} != ''
                GROUP BY anio
                ORDER BY anio DESC'''
        ).fetchall()
        totales[etiqueta] = sum(fila['cantidad'] for fila in filas)
        for fila in filas:
            por_anio.setdefault(fila['anio'], {})[etiqueta] = fila['cantidad']
    conn.close()
    anios = sorted(por_anio, reverse=True)
    return render_template(
        'estadisticas.html',
        anios=anios,
        por_anio=por_anio,
        totales=totales,
        actuaciones_por_caratula=actuaciones_por_caratula,
        allanamientos_por_anio=allanamientos_por_anio,
        oficios_por_anio=oficios_por_anio,
        oficios_positivos_total=sum(fila['positivos'] or 0 for fila in oficios_por_anio),
        oficios_allanamiento_total=sum(fila['con_allanamiento'] or 0 for fila in oficios_por_anio)
    )

@app.route('/allanamientos', methods=['GET', 'POST'])
@login_required
def allanamientos():
    if current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('estadisticas'))
    conn = get_db()
    if request.method == 'POST':
        datos = (
            request.form.get('ap', '').strip(),
            request.form.get('causa', '').strip(),
            request.form.get('acusados', '').strip(),
            request.form.get('damnificado', '').strip(),
            request.form.get('esclarecido', '').strip(),
            request.form.get('cantidad_detenidos', '').strip() or None,
            request.form.get('cantidad_secuestros', '').strip() or None,
            request.form.get('tipo_secuestro', '').strip(),
            request.form.get('cantidad_domicilios', '').strip() or None,
            request.form.get('localidad', '').strip()
        )
        if not all(datos[index] for index in (0, 1, 2, 3)):
            registros = registros_propios_o_todos(conn, 'allanamientos')
            conn.close()
            return render_template('allanamientos.html', registros=registros, error='AP, causa, acusados y damnificado son obligatorios')
        conn.execute('''INSERT INTO allanamientos
            (user_id, ap, causa, acusados, damnificado, esclarecido, cantidad_detenidos,
             cantidad_secuestros, tipo_secuestro, cantidad_domicilios, localidad, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (current_user.id, *datos, current_utc_isoformat()))
        conn.commit()
    registros = registros_propios_o_todos(conn, 'allanamientos')
    conn.close()
    return render_template('allanamientos.html', registros=registros)

@app.route('/allanamientos/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_allanamiento(id):
    if current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('estadisticas'))
    conn = get_db()
    conn.execute('DELETE FROM allanamientos WHERE id=? AND (user_id=? OR ?=1)',
                 (id, current_user.id, int(current_user.es_admin)))
    conn.commit()
    conn.close()
    return redirect(url_for('allanamientos'))

@app.route('/oficios-judiciales', methods=['GET', 'POST'])
@login_required
def oficios_judiciales():
    if current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('estadisticas'))
    conn = get_db()
    if request.method == 'POST':
        datos = (
            request.form.get('fecha_ingreso', '').strip(),
            request.form.get('numero_expediente', '').strip(),
            request.form.get('fiscalia', '').strip(),
            request.form.get('acusado', '').strip(),
            request.form.get('diligencias', '').strip(),
            request.form.get('actuario', '').strip(),
            request.form.get('pedido_allanamiento', '').strip(),
            request.form.get('resultado', '').strip()
        )
        if not datos[0] or not datos[1]:
            conn.close()
            return render_template('oficios_judiciales.html', registros=[], error='Fecha de ingreso y número de expediente son obligatorios')
        conn.execute('''INSERT INTO oficios_judiciales
            (user_id, fecha_ingreso, numero_expediente, fiscalia, acusado, diligencias, actuario, pedido_allanamiento, resultado, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (current_user.id, *datos, current_utc_isoformat()))
        conn.commit()
    registros = registros_propios_o_todos(conn, 'oficios_judiciales')
    conn.close()
    return render_template('oficios_judiciales.html', registros=registros)

@app.route('/oficios-judiciales/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_oficio_judicial(id):
    if current_user.es_consulta and not current_user.es_admin:
        return redirect(url_for('estadisticas'))
    conn = get_db()
    conn.execute('DELETE FROM oficios_judiciales WHERE id=? AND (user_id=? OR ?=1)',
                 (id, current_user.id, int(current_user.es_admin)))
    conn.commit()
    conn.close()
    return redirect(url_for('oficios_judiciales'))

@app.route('/crear-admin', methods=['GET', 'POST'])
def crear_admin():
    conn = get_db()
    admin_exists = conn.execute('SELECT COUNT(*) as cnt FROM usuarios WHERE es_admin=1').fetchone()
    conn.close()
    
    if admin_exists['cnt'] >= 3:
        return "Ya existen 3 administradores", 403
    
    if request.method == 'POST':
        nombre_usuario = request.form.get('nombre_usuario')
        contrasena = request.form.get('contrasena')
        nombre_completo = request.form.get('nombre_completo', nombre_usuario)
        
        if not nombre_usuario or not contrasena:
            return render_template('crear_admin.html', error='Usuario y contraseña requeridos')
        
        conn = get_db()
        try:
            conn.execute('INSERT INTO usuarios (nombre_usuario, contrasena, nombre_completo, es_admin) VALUES (?,?,?,1)',
                (nombre_usuario, generate_password_hash(contrasena), nombre_completo))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            conn.close()
            return render_template('crear_admin.html', error='El usuario ya existe')
    
    return render_template('crear_admin.html')

@app.route('/usuarios')
@login_required
def usuarios():
    if not current_user.es_admin:
        return redirect(url_for('index'))
    
    conn = get_db()
    usuarios = conn.execute('SELECT id, nombre_usuario, nombre_completo, es_admin, es_consulta FROM usuarios ORDER BY nombre_completo').fetchall()
    conn.close()
    
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/crear-usuario-consulta', methods=['POST'])
@login_required
def crear_usuario_consulta():
    if not current_user.es_admin:
        return redirect(url_for('index'))
    nombre_usuario = request.form.get('nombre_usuario', '').strip()
    contrasena = request.form.get('contrasena', '')
    nombre_completo = request.form.get('nombre_completo', '').strip() or nombre_usuario
    if not nombre_usuario or not contrasena:
        return redirect(url_for('usuarios'))
    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO usuarios
               (nombre_usuario, contrasena, nombre_completo, es_admin, es_consulta)
               VALUES (?, ?, ?, 0, 1)''',
            (nombre_usuario, generate_password_hash(contrasena), nombre_completo)
        )
        conn.commit()
    except psycopg2.IntegrityError:
        conn.close()
        return redirect(url_for('usuarios', error='El usuario ya existe'))
    conn.close()
    return redirect(url_for('usuarios'))

@app.route('/convertir-a-consulta/<int:user_id>', methods=['POST'])
@login_required
def convertir_a_consulta(user_id):
    if not current_user.es_admin or user_id == current_user.id:
        return redirect(url_for('usuarios'))
    conn = get_db()
    conn.execute(
        'UPDATE usuarios SET es_admin=0, es_consulta=1 WHERE id=?',
        (user_id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('usuarios'))

@app.route('/resetear-password/<int:user_id>', methods=['GET', 'POST'])
@login_required
def resetear_password(user_id):
    if not current_user.es_admin:
        return redirect(url_for('index'))
    
    conn = get_db()
    usuario = conn.execute('SELECT id, nombre_usuario, nombre_completo FROM usuarios WHERE id=?', (user_id,)).fetchone()
    
    if not usuario:
        conn.close()
        return redirect(url_for('usuarios'))
    
    if request.method == 'POST':
        nueva_contrasena = request.form.get('nueva_contrasena')
        confirmar_contrasena = request.form.get('confirmar_contrasena')
        
        if not nueva_contrasena or not confirmar_contrasena:
            conn.close()
            return render_template('resetear_password.html', usuario=usuario, error='Debe completar ambos campos')
        
        if nueva_contrasena != confirmar_contrasena:
            conn.close()
            return render_template('resetear_password.html', usuario=usuario, error='Las contraseñas no coinciden')
        
        if len(nueva_contrasena) < 4:
            conn.close()
            return render_template('resetear_password.html', usuario=usuario, error='La contraseña debe tener al menos 4 caracteres')
        
        conn.execute('UPDATE usuarios SET contrasena=? WHERE id=?', 
                    (generate_password_hash(nueva_contrasena), user_id))
        conn.commit()
        conn.close()
        return redirect(url_for('usuarios'))
    
    conn.close()
    return render_template('resetear_password.html', usuario=usuario)

@app.route('/eliminar-usuario/<int:user_id>', methods=['POST'])
@login_required
def eliminar_usuario(user_id):
    if not current_user.es_admin:
        return redirect(url_for('index'))

    # No permitir que un admin se elimine a sí mismo
    if user_id == int(current_user.id):
        return redirect(url_for('usuarios'))

    conn = get_db()
    usuario = conn.execute('SELECT id, es_admin FROM usuarios WHERE id=?', (user_id,)).fetchone()

    if not usuario:
        conn.close()
        return redirect(url_for('usuarios'))

    # No permitir borrar al último administrador
    if usuario['es_admin']:
        total_admins = conn.execute('SELECT COUNT(*) AS cnt FROM usuarios WHERE es_admin=1').fetchone()
        if total_admins['cnt'] <= 1:
            conn.close()
            return redirect(url_for('usuarios'))

    conn.execute('DELETE FROM actuaciones WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM allanamientos WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM oficios_judiciales WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM usuarios WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('usuarios'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug, host='0.0.0.0', port=port)
