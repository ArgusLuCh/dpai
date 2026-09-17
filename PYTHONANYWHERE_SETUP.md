# 🚀 Guía: Configurar tu App en PythonAnywhere

## Paso 1: Crear Cuenta
1. Ve a [pythonanywhere.com](https://www.pythonanywhere.com)
2. Haz clic en "Create a Beginner account" (es gratis)
3. Completa el registro y verifica tu email

## Paso 2: Subir tu Código
Opción A: Usando Git (Recomendado)
```bash
# En PythonAnywhere, abre una consola Bash y ejecuta:
cd ~
git clone https://github.com/tu-usuario/tu-repositorio.git
cd tu-repositorio
```

Opción B: Subir manualmente
1. En tu PC, crea un ZIP con toda la carpeta (app.py, templates/, static/, requirements.txt, etc)
2. En PythonAnywhere, ve a la sección "Files"
3. Sube el ZIP y descomprime

## Paso 3: Instalar Dependencias
En la **Consola Bash** de PythonAnywhere:
```bash
cd ~/tu-carpeta-app
pip install -r requirements.txt
```

## Paso 4: Crear la Base de Datos Inicial
En la **Consola Bash**:
```bash
cd ~/tu-carpeta-app
python3 -c "from app import init_db; init_db()"
```

## Paso 5: Crear la Web App
1. Ve al menu **"Web"** en PythonAnywhere
2. Haz clic en **"Add a new web app"**
3. Selecciona:
   - Dominio: usa el que te ofrece (ejemplo: tu-usuario.pythonanywhere.com)
   - Framework: **Manual configuration**
   - Python version: **Python 3.9** o superior
4. Haz clic en **"Next"**

## Paso 6: Configurar el Archivo WSGI
1. En tipo "Web" → **"Code"** → **"WSGI configuration file"**
2. El archivo debe ser algo como: `/home/tu-usuario/tu-carpeta/wsgi.py`
3. Abre ese archivo y reemplaza TODO el contenido con:

```python
import sys
from pathlib import Path

# Ruta a tu carpeta de app
project_dir = '/home/tu-usuario/tu-carpeta'
sys.path.insert(0, project_dir)

from app import app
```

⚠️ **IMPORTANTE:** Reemplaza `tu-usuario` y `tu-carpeta` con tus valores reales

## Paso 7: Configurar Variables Estáticas (CSS, JS)
1. En la sección "Web":
   - URL: `/static/`
   - Directory: `/home/tu-usuario/tu-carpeta/static`
2. Guarda

## Paso 8: Reiniciar la Web App
En la sección "Web", haz clic en el botón **verde de "Reload"** en la parte superior

## Paso 9: Acceder a tu App
Tu app estará en: `https://tu-usuario.pythonanywhere.com`

---

## 🔧 Verifying que Funciona
- Abre tu navegador y ve a: `https://tu-usuario.pythonanywhere.com/login`
- Deberías ver la página de login
- Si ves un error, revisa el **Error log** en la sección "Web"

## 🐛 Solving Problemas Comunes

### Error: "No module named 'app'"
✅ Solución: Verifica que el WSGI file tenga la ruta correcta a tu carpeta

### Error: Database locked
✅ Solución: Reinicia el sitio web en la sección "Web"

### El CSS no carga
✅ Solución: Asegúrate de configurar la ruta `/static/` correctamente

### ImportError
✅ Solución: Instala paquetes: `pip install -r requirements.txt`

## 📝 Cambios Necesarios en tu Código (IMPORTANTE)

En [app.py](app.py):
- Línea ~45: `app.config['SECRET_KEY']` manten con un valor seguro
- debug debe estar en **False** cuando subas a producción
- `host='0.0.0.0'` es correcto para PythonAnywhere

## 🔐 Crear un Admin en PythonAnywhere
1. Ve a `https://tu-usuario.pythonanywhere.com/crear-admin`
2. Crea un usuario administrador
3. Usa esas credenciales para acceder

## 📊 Monitorear Logs
En la sección "Web":
- **Server log**: Errores del servidor
- **Error log**: Errores de la aplicación
- **Access log**: Quién accede y cuándo

## 🆘 Soporte
- Si tienes problemas, revisa el **Error log** del sitio
- Lee el error completo, generalmente dice qué está mal
- En PythonAnywhere tienes documentación: https://www.pythonanywhere.com/help/

---

## ✅ Checklist Final
- [ ] Cuenta creada en PythonAnywhere
- [ ] Código subido
- [ ] Dependencies instaladas
- [ ] Base de datos inicializada
- [ ] Web app creada
- [ ] WSGI file configurado
- [ ] Static files configurados
- [ ] Sitio reloadado
- [ ] Accesible desde https://tu-usuario.pythonanywhere.com
- [ ] Admin usuario creado
- [ ] Login funciona

¡Listo! Tu app está en línea 🎉
