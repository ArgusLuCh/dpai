"""
Archivo WSGI para PythonAnywhere
No modificar a menos que sea necesario
"""
import sys
from pathlib import Path

# Agregar el directorio de la app al path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from app import app

if __name__ == "__main__":
    app.run()
