# Guía: Acceder desde Fuera de la Red Local

## Paso 1: Preparar la Aplicación
1. Instala las nuevas dependencias:
   ```bash
   pip install -r requirements.txt
   ```

2. Crea un archivo `.env` con una clave secreta fuerte:
   ```bash
   SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
   ```

## Paso 2: Configurar el Cortafuegos de Windows
1. Abre "Firewall de Windows Defender" → "Permitir que una aplicación atraviese el cortafuegos"
2. Permite Python (python.exe) para comunicaciones públicas y privadas
3. O abre el puerto 443 (HTTPS) / 5000 (pruebas)

## Paso 3: Obtener una IP o Dominio Estaticos
### Opción A: Ip Estática Local
- En Windows, configura tu PC con IP estática en Settings → Network & Internet

### Opción B: Dominio Dinámico (Recomendado)
- Usa DuckDNS (https://www.duckdns.org/) - Gratuito
- O Cloudflare DDNS

## Paso 4: Port Forwarding en el Router
1. Accede a tu router (generalmente 192.168.1.1)
2. Busca "Port Forwarding"
3. Redirige: Puerto Externo 443 → IP Local : Puerto 5000
   - O Puerto Externo 5000 → IP Local : Puerto 5000

## Paso 5: HTTPS/SSL (Muy Importante)
### Opción A: Let's Encrypt (Gratuito)
```bash
pip install certbot certbot-nginx
certbot certonly --standalone -d tu-dominio.duckdns.org
```

### Opción B: Usar Nginx como Proxy Inverso (Recomendado)
Nginx actúa como intermediario y maneja HTTPS automáticamente.

**Instalación en Windows:**
- Descargar desde http://nginx.org/en/download.html
- Guardar en `C:\nginx`

**Configuración básica (nginx.conf):**
```nginx
server {
    listen 443 ssl http2;
    server_name tu-dominio.duckdns.org;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Paso 6: Ejecutar en Producción
```bash
# Con Gunicorn
gunicorn --bind 0.0.0.0:5000 app:app

# O en background con nssm (NSSM permite ejecutar Python como servicio Windows)
nssm install MiApp "C:\ruta\a\python.exe" "C:\ruta\a\app.py"
nssm start MiApp
```

## Paso 7: Cambiar la URL de Login en Plantillas
En `templates/base.html` o donde sea necesario, cambia:
- `http://localhost:5000` → `https://tu-dominio.duckdns.org`

---

## ⚠️ Checklist de Seguridad
- [ ] Cambiar SECRET_KEY a un valor fuerte y único
- [ ] debug=False en producción
- [ ] HTTPS activado
- [ ] Cortafuegos configurado
- [ ] Contraseñas de usuarios con hash seguro (ya lo tienes)
- [ ] Validar inputs en formularios
- [ ] CORS configurados si es necesario
- [ ] Logs y monitoreo configurados

## Alternativa Simple: Cloud Hosting
Si no quieres configurar esto en tu PC:
- **Heroku** (gratis, pero requiere tarjeta)
- **PythonAnywhere** (gratuito con restricciones)
- **AWS, DigitalOcean, Linode** (pago)
