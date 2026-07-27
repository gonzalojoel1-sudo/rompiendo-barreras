# vps_backend_spec.md - Especificación Técnica de Backend y Base de Datos (VPS)

Este documento define la arquitectura técnica del servidor VPS ($5 USD/mes), el esquema de Base de Datos SQL, la autenticación de usuarios y las especificaciones de la API REST que conecta la web de alumnos con los agentes autónomos de **Orca**.

---

## 1. Arquitectura del Servidor VPS

```text
                                  [ INTERNET / ALUMNOS / ORCA ]
                                                |
                                      (HTTPS - Port 443 / SSL)
                                                |
                                                v
                                   +--------------------------+
                                   |   Nginx (Reverse Proxy)  |
                                   +--------------------------+
                                                |
                                  +-------------+-------------+
                                  |                           |
                                  v                           v
                      [ Frontend App (HTML/JS) ]     [ Node.js / Python API ]
                      - Landing Page pública         - Endpoints REST (/api/v1)
                      - Panel Alumnos (Private)      - Autenticación JWT
                                                              |
                                                              v
                                                    [ SQLite / PostgreSQL ]
                                                    - Tabla usuarios
                                                    - Tabla suscripciones
                                                    - Tabla envíos kit
```

### Reglas Innegociables de Infraestructura:
1. **Hosting Ligero:** Servidor Ubuntu 24.04 LTS (1 vCPU, 1 GB - 2 GB RAM).
2. **Cero Procesamiento de Video:** Queda estrictamente prohibido guardar, convertir o servir archivos de video `.mp4` en el VPS. Todo el contenido multimedia es servido desde **Bunny Stream**.
3. **CORS Restringido:** La API solo responde a llamadas originadas desde `https://tu-dominio.com` o desde las IP autenticadas de los agentes de Orca via `Bearer Token`.

---

## 2. Esquema de Base de Datos (SQL DDL)

### 2.1. Tabla: `usuarios`
Almacena la información de acceso de los estudiantes y administradores.

```sql
CREATE TABLE usuarios (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nombre_completo VARCHAR(255) NOT NULL,
    rol VARCHAR(20) DEFAULT 'alumno', -- 'alumno' | 'admin'
    plan_id VARCHAR(50) NOT NULL,    -- 'emp_mensual', 'est_mensual', 'eli_mensual', 'emp_anual', 'est_anual', 'eli_anual', 'beca'
    pilar_actual_desbloqueado INT DEFAULT 1, -- Control de Drip Content (1 al 7)
    estado VARCHAR(20) DEFAULT 'activo',    -- 'activo', 'pausado', 'cancelado'
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2. Tabla: `suscripciones_pagos`
Registra el historial de pagos y cobros procesados por WhatsApp/Transferencia o Link de Tarjeta.

```sql
CREATE TABLE suscripciones_pagos (
    id VARCHAR(36) PRIMARY KEY,
    usuario_id VARCHAR(36) NOT NULL,
    monto_usd DECIMAL(10,2) NOT NULL,
    metodo_pago VARCHAR(50) NOT NULL, -- 'transferencia', 'mercadopago', 'stripe', 'paypal'
    es_pago_anual BOOLEAN DEFAULT FALSE,
    comprobante_ref VARCHAR(255),
    fecha_pago TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);
```

### 2.3. Tabla: `envios_kits_fisicos`
Gestiona la logística de despacho del Kit Físico de Bienvenida para suscriptores del Pacto Anual V.I.P.

```sql
CREATE TABLE envios_kits_fisicos (
    id VARCHAR(36) PRIMARY KEY,
    usuario_id VARCHAR(36) NOT NULL,
    item_solicitado VARCHAR(100) NOT NULL, -- 'mate_laser', 'remera_reino'
    direccion_envio TEXT NOT NULL,
    ciudad VARCHAR(100) NOT NULL,
    pais VARCHAR(100) DEFAULT 'Argentina',
    estado_envio VARCHAR(30) DEFAULT 'pendiente', -- 'pendiente', 'despachado', 'entregado'
    codigo_seguimiento VARCHAR(100),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);
```

---

## 3. Especificación de Endpoints API REST (`/api/v1`)

### 3.1. Autenticación de Alumnos
* **Endpoint:** `POST /api/v1/auth/login`
* **Acceso:** Público.
* **Payload de Entrada:**
  ```json
  {
    "email": "alumno@gmail.com",
    "password": "PasswordTemporal123"
  }
  ```
* **Respuesta Exitosa (200 OK):**
  ```json
  {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "usuario": {
      "id": "usr_98765",
      "nombre": "Carlos Gómez",
      "email": "alumno@gmail.com",
      "plan_id": "est_anual",
      "pilar_actual_desbloqueado": 7
    }
  }
  ```

---

### 3.2. Aprovisionamiento / Alta de Alumno (Invocado por Agente 4 de Orca)
* **Endpoint:** `POST /api/v1/crear-usuario`
* **Acceso:** Privado (Requiere Header `Authorization: Bearer SERVER_ADMIN_SECRET`).
* **Payload de Entrada (JSON):**
  ```json
  {
    "email": "nuevo.alumno@gmail.com",
    "nombre": "Juan Pérez",
    "plan_id": "est_mensual",
    "metodo_pago": "transferencia",
    "pilar_inicial": 1,
    "acceso_total_inmediato": false,
    "requiere_envio_kit_fisico": false
  }
  ```
* **Lógica Interna del VPS:**
  1. Genera una contraseña aleatoria de 8 caracteres.
  2. Inserta el registro en la tabla `usuarios`.
  3. Si `requiere_envio_kit_fisico` es `true`, genera la fila en `envios_kits_fisicos`.
  4. Dispara un correo electrónico de bienvenida al alumno con sus credenciales iniciales.
* **Respuesta Exitosa (201 Created):**
  ```json
  {
    "status": "success",
    "mensaje": "Usuario creado correctamente",
    "usuario_id": "usr_12345",
    "password_generada": "Xy7#k9Pq"
  }
  ```

---

### 3.3. Obtención de Contenido de Clases (Plataforma Privada)
* **Endpoint:** `GET /api/v1/alumno/contenido/pilar/:pilar_id`
* **Acceso:** Privado (Requiere Token JWT del alumno).
* **Lógica de Seguridad (Drip Content):**
  El backend verifica que `pilar_id <= usuario.pilar_actual_desbloqueado`. Si un alumno en su primer mes intenta solicitar la URL del Pilar 3, la API responde con un error `403 Forbidden`.
* **Respuesta Exitosa (200 OK):**
  ```json
  {
    "pilar": 1,
    "nombre_pilar": "Casa de Gobierno",
    "lecciones": [
      {
        "id": "lec_101",
        "titulo": "Clase 1: Auditoría de Realidad y Renuncia",
        "duracion_min": 18,
        "bunny_embed_url": "https://iframe.mediadelivery.net/embed/123456/vid-pilar1-clase1",
        "pdf_entregable": "https://tu-dominio.com/assets/pdfs/auditoria_identidad.pdf"
      }
    ]
  }
  ```

---

### 3.4. Desbloqueo Progresivo de Módulos (Cron Job / Pago Recurrente)
* **Endpoint:** `PATCH /api/v1/admin/desbloquear-pilar`
* **Acceso:** Privado (Admin).
* **Payload:**
  ```json
  {
    "usuario_id": "usr_12345",
    "nuevo_pilar_desbloqueado": 2
  }
  ```
* **Efecto:** Incrementa la propiedad `pilar_actual_desbloqueado` permitiendo al alumno acceder al siguiente pilar en su panel.
