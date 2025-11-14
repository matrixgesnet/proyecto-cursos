from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
# NUEVO: Importamos las herramientas de Login
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import secrets # <--- NUEVO
from datetime import datetime, timedelta # <--- NUEVO

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# --- LÓGICA DE BASE DE DATOS (PRODUCCIÓN vs LOCAL) ---
# Variable de entorno que Render nos dará (secreta)
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Si estamos en PRODUCCIÓN (Render)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Si estamos en LOCAL (tu PC)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'cursos.db')


app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# NUEVO: Necesitamos una "llave secreta" para que las sesiones sean seguras
app.config['SECRET_KEY'] = 'mi_palabra_secreta_super_segura' 

db = SQLAlchemy(app)

# NUEVO: Configuración del Gestor de Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # A donde ir si no estás logueado

# --- MODELOS (TABLAS) ---

# NUEVO: Agregamos "UserMixin" dentro del paréntesis. 
# Esto le da poderes al usuario para manejar la sesión.
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # NUEVO CAMPO: Por defecto es False (usuario normal)
    is_admin = db.Column(db.Boolean, default=False)

    # --- NUEVOS CAMPOS PARA RECUPERACIÓN ---
    reset_token = db.Column(db.String(100), nullable=True) # El código secreto
    token_expiration = db.Column(db.DateTime, nullable=True) # Cuándo caduca

    inscripciones = db.relationship('Inscripcion', back_populates='usuario')

# NUEVO: Esta función ayuda a Flask a buscar al usuario conectado por su ID
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ... (El resto de modelos: Categoria, Curso, Video, Inscripcion siguen igual) ...
class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    cursos = db.relationship('Curso', backref='categoria', lazy=True)

class Curso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    videos = db.relationship('Video', backref='curso', lazy=True)
    inscritos = db.relationship('Inscripcion', back_populates='curso')

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    url_video = db.Column(db.String(200), nullable=False)
    curso_id = db.Column(db.Integer, db.ForeignKey('curso.id'), nullable=False)

class Inscripcion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    curso_id = db.Column(db.Integer, db.ForeignKey('curso.id'), nullable=False)
    usuario = db.relationship('Usuario', back_populates='inscripciones')
    curso = db.relationship('Curso', back_populates='inscritos')


# --- RUTAS ---

# NUEVO: Ruta Principal (Home)

@app.route('/')
def index():
    if current_user.is_authenticated:
        # Buscamos todas las categorías en la BD
        categorias = Categoria.query.all()
        # Se las enviamos al archivo HTML
        return render_template('inicio.html', categorias=categorias)
    else:
        return redirect(url_for('login'))

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = Usuario.query.filter_by(email=email).first()
        if user:
            flash('El correo ya existe.')
            return redirect(url_for('registro'))
        
        new_user = Usuario(email=email, password_hash=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        
        flash('Cuenta creada. Por favor inicia sesión.')
        return redirect(url_for('login'))
        
    return render_template('registro.html')

# NUEVO: Ruta de Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Buscamos al usuario en la BD
        usuario = Usuario.query.filter_by(email=email).first()
        
        # Verificamos si existe Y si la contraseña coincide con el hash
        if usuario and check_password_hash(usuario.password_hash, password):
            login_user(usuario) # ¡Magia! Esto inicia la sesión
            return redirect(url_for('index'))
        else:
            flash('Correo o contraseña incorrectos.')
            
    return render_template('login.html')
# # # # # # # # # # #   
@app.route('/categoria/<int:id_categoria>')
@login_required
def ver_categoria(id_categoria):
    # 1. Buscamos la categoría por su ID
    categoria = Categoria.query.get_or_404(id_categoria)
    # 2. Como definimos la relación en el Paso 1, podemos acceder a .cursos fácilmente
    cursos = categoria.cursos 
    return render_template('categoria.html', categoria=categoria, cursos=cursos)

# NUEVO: Ruta para Cerrar Sesión
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


############################
# --- RUTA PARA INSCRIBIRSE (Simula comprar el curso) ---
@app.route('/inscribirse/<int:id_curso>')
@login_required
def inscribirse(id_curso):
    curso = Curso.query.get_or_404(id_curso)
    
    # Verificamos si ya está inscrito para no duplicarlo
    inscripcion_existente = Inscripcion.query.filter_by(usuario_id=current_user.id, curso_id=id_curso).first()
    
    if not inscripcion_existente:
        nueva_inscripcion = Inscripcion(usuario_id=current_user.id, curso_id=id_curso)
        db.session.add(nueva_inscripcion)
        db.session.commit()
        flash(f'¡Te has inscrito en {curso.titulo} exitosamente!')
    else:
        flash('Ya estás inscrito en este curso.')
        
    return redirect(url_for('ver_curso', id_curso=id_curso))

# --- RUTA PANEL DE ADMINISTRADOR ---
@app.route('/admin')
@login_required
def admin_dashboard():
    # Verificamos si el usuario actual TIENE el permiso de admin
    if not current_user.is_admin:
        flash("¡Alto ahí! No tienes permisos de administrador.")
        return redirect(url_for('index'))
    
    # NUEVO: Consultamos todo para mostrarlo en las tablas
    categorias = Categoria.query.all()
    cursos = Curso.query.all()
    videos = Video.query.all()
    
    return render_template('admin_dashboard.html', categorias=categorias, cursos=cursos, videos=videos)


# --- RUTA PARA CREAR CATEGORÍA ---
@app.route('/admin/crear-categoria', methods=['GET', 'POST'])
@login_required
def crear_categoria():
    # 1. Seguridad: Solo el admin puede entrar aquí
    if not current_user.is_admin:
        return redirect(url_for('index'))

    # 2. Si envió el formulario (POST)
    if request.method == 'POST':
        nombre_categoria = request.form['nombre']
        
        # Verificamos si ya existe para no repetir
        categoria_existente = Categoria.query.filter_by(nombre=nombre_categoria).first()
        if categoria_existente:
            flash('¡Esa categoría ya existe!')
        else:
            # Guardamos en la Base de Datos
            nueva_cat = Categoria(nombre=nombre_categoria)
            db.session.add(nueva_cat)
            db.session.commit()
            flash(f'Categoría "{nombre_categoria}" creada correctamente.')
            # Lo enviamos de vuelta al panel
            return redirect(url_for('admin_dashboard'))

    # 3. Si solo está entrando a la página (GET)
    return render_template('crear_categoria.html')



# --- RUTA DEL SALÓN DE CLASES (Solo para inscritos) ---
@app.route('/curso/<int:id_curso>')
@login_required
def ver_curso(id_curso):
    curso = Curso.query.get_or_404(id_curso)
    
    # --- AQUÍ ESTÁ LA SEGURIDAD (Punto 4) ---
    # Buscamos si existe una "Inscripción" entre ESTE usuario y ESTE curso
    tiene_permiso = Inscripcion.query.filter_by(usuario_id=current_user.id, curso_id=id_curso).first()

    if not tiene_permiso:
        # Si no tiene permiso, le mostramos una página de "Venta" o error
        flash("Debes inscribirte para ver este contenido.")
        return render_template('curso_no_autorizado.html', curso=curso)
    
    # Si tiene permiso, le mostramos los videos
    return render_template('ver_curso.html', curso=curso)
#####################################################################

# --- RUTA PARA CREAR CURSO ---
@app.route('/admin/crear-curso', methods=['GET', 'POST'])
@login_required
def crear_curso():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    # Si el usuario está guardando el formulario
    if request.method == 'POST':
        titulo_curso = request.form['titulo']
        id_categoria = request.form['categoria_id'] # Aquí recuperamos el ID del select
        
        # Crear y guardar el curso
        nuevo_curso = Curso(titulo=titulo_curso, categoria_id=id_categoria)
        db.session.add(nuevo_curso)
        db.session.commit()
        
        flash(f'Curso "{titulo_curso}" creado exitosamente.')
        return redirect(url_for('admin_dashboard'))

    # Si el usuario solo está entrando a la página
    # 1. Necesitamos todas las categorías para ponerlas en el menú desplegable
    categorias = Categoria.query.all()
    
    # 2. Se las enviamos a la plantilla
    return render_template('crear_curso.html', categorias=categorias)

###########################################################################
# --- RUTA PARA AGREGAR VIDEO ---
@app.route('/admin/crear-video', methods=['GET', 'POST'])
@login_required
def crear_video():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    if request.method == 'POST':
        titulo = request.form['titulo']
        url_original = request.form['url']
        curso_id = request.form['curso_id']
        
        # --- EL TRUCO DE YOUTUBE ---
        # Transformamos el link normal en un link "embed" (incrustable)
        # Cambia "watch?v=" por "embed/"
        if "watch?v=" in url_original:
            url_final = url_original.replace("watch?v=", "embed/")
        # Opción por si copias el link corto "youtu.be/"
        elif "youtu.be/" in url_original:
            url_final = url_original.replace("youtu.be/", "www.youtube.com/embed/")
        else:
            url_final = url_original # Si ya viene bien, lo dejamos así

        # Guardamos
        nuevo_video = Video(titulo=titulo, url_video=url_final, curso_id=curso_id)
        db.session.add(nuevo_video)
        db.session.commit()
        
        flash(f'Video "{titulo}" agregado al curso.')
        return redirect(url_for('admin_dashboard'))

    # Si es GET, necesitamos la lista de cursos para el select
    cursos = Curso.query.all()
    return render_template('crear_video.html', cursos=cursos)


# --- RUTAS DE BORRADO ---

@app.route('/admin/borrar-curso/<int:id>')
@login_required
def borrar_curso(id):
    if not current_user.is_admin: return redirect(url_for('index'))
    
    curso = Curso.query.get_or_404(id)
    
    # OJO: Al borrar un curso, deberíamos borrar sus videos primero para limpiar la BD
    # O simplemente los borramos:
    db.session.delete(curso)
    db.session.commit()
    flash(f'Curso "{curso.titulo}" eliminado.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/borrar-categoria/<int:id>')
@login_required
def borrar_categoria(id):
    if not current_user.is_admin: return redirect(url_for('index'))
    
    cat = Categoria.query.get_or_404(id)
    db.session.delete(cat)
    db.session.commit()
    flash(f'Categoría "{cat.nombre}" eliminada.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/borrar-video/<int:id>')
@login_required
def borrar_video(id):
    if not current_user.is_admin: return redirect(url_for('index'))
    
    video = Video.query.get_or_404(id)
    db.session.delete(video)
    db.session.commit()
    flash('Video eliminado correctamente.')
    return redirect(url_for('admin_dashboard'))


# --- RUTA DE EDICIÓN (Solo Cursos por ahora) ---
@app.route('/admin/editar-curso/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_curso(id):
    if not current_user.is_admin: return redirect(url_for('index'))
    
    curso = Curso.query.get_or_404(id) # Buscamos el curso viejo
    
    if request.method == 'POST':
        # Actualizamos los datos con lo que venga del formulario
        curso.titulo = request.form['titulo']
        curso.categoria_id = request.form['categoria_id']
        
        db.session.commit() # Guardamos cambios
        flash('Curso actualizado exitosamente.')
        return redirect(url_for('admin_dashboard'))
    
    # Si es GET, necesitamos las categorías para el select
    categorias = Categoria.query.all()
    return render_template('editar_curso.html', curso=curso, categorias=categorias)

# --- RUTAS DE RECUPERACIÓN DE CONTRASEÑA ---

# 1. Página donde pones tu email
@app.route('/olvide-password', methods=['GET', 'POST'])
def olvide_password():
    if request.method == 'POST':
        email = request.form['email']
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario:
            # Generamos un token único
            token = secrets.token_urlsafe(16)
            # Le damos 1 hora de validez
            usuario.reset_token = token
            usuario.token_expiration = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            
            # --- SIMULACIÓN DE ENVÍO DE EMAIL ---
            # En lugar de mandar un email, creamos el link aquí
            link_recuperacion = url_for('reset_password', token=token, _external=True)
            
            print("="*30)
            print("📧 EMAIL SIMULADO DE RECUPERACIÓN")
            print(f"Para: {email}")
            print(f"Link: {link_recuperacion}")
            print("="*30)
            
            flash('Te hemos enviado un correo con las instrucciones (¡Revisa la terminal!).')
            return redirect(url_for('login'))
        else:
            # Por seguridad, a veces no se dice si el correo existe o no, 
            # pero para aprender, avisaremos.
            flash('Ese correo no está registrado.')
            
    return render_template('olvide_password.html')



# 2. Página donde pones la NUEVA contraseña (llega aquí desde el link)
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Buscamos al usuario que tenga ese token Y que aún no haya expirado
    usuario = Usuario.query.filter_by(reset_token=token).first()
    
    # Verificamos si el token existe y si aún es válido (por tiempo)
    if not usuario or usuario.token_expiration < datetime.utcnow():
        flash('El enlace es inválido o ha expirado.')
        return redirect(url_for('olvide_password'))
    
    if request.method == 'POST':
        nueva_pass = request.form['password']
        
        # Actualizamos la contraseña
        usuario.password_hash = generate_password_hash(nueva_pass)
        
        # Limpiamos el token para que no se pueda usar dos veces
        usuario.reset_token = None
        usuario.token_expiration = None
        db.session.commit()
        
        flash('¡Contraseña actualizada! Ahora puedes iniciar sesión.')
        return redirect(url_for('login'))
        
    return render_template('reset_password.html', token=token)


# Comando para crear la DB
@app.cli.command('create-db')
def create_db():
    db.create_all()
    print('Base de datos creada')


# --- COMANDO PARA CREAR DATOS DE PRUEBA ---
@app.cli.command('init-data')
def init_data():
    """Crea categorías, cursos y videos de prueba"""
    
    # 1. Crear Categorías
    cat_sql = Categoria(nombre='SQL y Bases de Datos')
    cat_python = Categoria(nombre='Python desde Cero')
    cat_web = Categoria(nombre='Desarrollo Web')
    
    db.session.add_all([cat_sql, cat_python, cat_web])
    db.session.commit() # Guardamos para que tengan ID

    # 2. Crear Cursos dentro de esas categorías
    curso1 = Curso(titulo='SQL para Principiantes', categoria_id=cat_sql.id)
    curso2 = Curso(titulo='Consultas Avanzadas MySQL', categoria_id=cat_sql.id)
    curso3 = Curso(titulo='Introducción a Python', categoria_id=cat_python.id)
    
    db.session.add_all([curso1, curso2, curso3])
    db.session.commit()
    
    # 3. Crear Videos (Usaremos enlaces "embed" de YouTube)
    # Nota: Para que funcionen en tu web, los links de youtube deben tener "/embed/"
    vid1 = Video(titulo='Instalación de MySQL', url_video='https://www.youtube.com/embed/WuBcTJnIuzo', curso_id=curso1.id)
    vid2 = Video(titulo='Select y From', url_video='https://www.youtube.com/embed/yPu6qV5byu4', curso_id=curso1.id)
    vid3 = Video(titulo='Hola Mundo en Python', url_video='https://www.youtube.com/embed/DcojabcVqTE', curso_id=curso2.id)

    db.session.add_all([vid1, vid2, vid3])
    db.session.commit()

    # --- PARTE NUEVA: CREAR EL ADMINISTRADOR ---
    # Creamos un usuario específico para ti
    admin = Usuario(email='admin@cursos.com', password_hash=generate_password_hash('admin123'), is_admin=True)
    
    db.session.add(admin)
    db.session.commit()
    
    print("¡Datos creados! Usuario Admin: admin@cursos.com / Clave: admin123")

