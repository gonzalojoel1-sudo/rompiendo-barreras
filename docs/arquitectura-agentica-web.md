# arquitecturaweb.md - Arquitectura Técnica y Operativa del Ecosistema "Rompiendo Barreras"

Este documento constituye la especificación maestra de la arquitectura tecnológica, el flujo de operaciones y la integración de agentes de Inteligencia Artificial (Orca) para el proyecto **Rompiendo Barreras**, liderado por **Marcos Barbosa** y **Joel**.

---

## 1. Diagrama de Arquitectura General

```text
                                [ TU DOMINIO (Ej: rompiendobarreras.com) ]
                                                    |
                                         (DNS - Record A / SSL)
                                                    |
                                                    v
                                  +-----------------------------------+
                                  |     SERVIDOR VPS ($5 / mes)       |
                                  |  (Ubuntu + Nginx + App / Backend)  |
                                  +-----------------------------------+
                                    /                                                                  /                                                   [ LANDING PAGE PUBLIC ]                     [ ÁREA DE ALUMNOS (Privada) ]
                  - Presentación del Programa                 - Login / Registro
                  - Testimonio de Marcos                      - Módulos / Pilares
                  - CTA: "Hablar por WhatsApp"                - Reproductor Bunny (Embed)
                               |                                           ^
                               v                                           |
                    [ CHAT DE WHATSAPP ]                                   |
                  - Cierre de venta manual                                 |
                  - Cobro (Transferencia/Tarjeta)                          |
                  - Validación de pago                                     |
                               |                                           |
                               +---- (Creación de usuario manual) ---------+
                               
                                                                           |
                                                      [ BUNNY STREAM (CDN Video) ]
                                                      - Guarda los videos ($1/mes)
                                                      - Streaming fluido (HLS)
                                                      - Dominio restringido (Seguridad)
```

---

## 2. Contexto del Negocio y Filosofía del Ecosistema

### 2.1. Propósito de "Rompiendo Barreras"
Rompiendo Barreras es un programa y ecosistema de formación integral de 6 meses de duración (24 semanas), diseñado para emprendedores y líderes cristianos. Su objetivo es transformar vidas, alinear finanzas y negocios con principios bíblicos, elevar la mentalidad de escasez a la abundancia de Reino y formar "Josés de Arimatea": empresarios influyentes que financian la expansión del Evangelio.

### 2.2. Roles del Equipo Humano
* **Marcos Barbosa (Líder / Rostro / Mentor):** Pastor, ex-integrante de fuerzas especiales, consultor empresarial. Encargado de la creación conceptual de las clases, impartir el contenido, grabar los videos apoyándose en diapositivas, realizar el cierre de ventas por WhatsApp y dirigir las mentorías en vivo.
* **Joel (Director de Operaciones / Arquitecto Técnico):** Encargado de la maquetación y diseño de diapositivas, edición rápida de videos, administración de la infraestructura técnica (VPS, Dominio, Nginx, Bunny.net), gestión de herramientas de IA (Orca) y estructuración de contenidos en Notion.

### 2.3. Rol de la Inteligencia Artificial (Agentes en Orca)
Los agentes autónomos en Orca actúan como el "equipo de soporte 24/7" para Joel y Marcos, automatizando la generación de guiones, copywriting para anuncios, creación de tareas en el Roadmap, procesamiento de inscripciones y gestión de bases de datos operativas en Notion o la app propia via API Keys.

---

## 3. Análisis Exhaustivo de Componentes e Infraestructura

### 3.1. Dominio y Capa DNS
* **Función:** Es la puerta de entrada oficial del negocio (`tu-dominio.com`).
* **Configuración:**
  * **Registro A (Root `@`):** Apunta directamente a la dirección IP pública fija otorgada por el proveedor del VPS (ejemplo: `198.51.100.45`).
  * **Registro A (`www`):** Apunta a la misma IP pública para redireccionar `www.tu-dominio.com` a la raíz.
  * **Seguridad SSL/TLS:** Certificado HTTPS emitido e instalado de forma gratuita y auto-renovable mediante **Certbot (Let's Encrypt)** en el VPS.
* **Procesamiento:** Garantiza comunicación cifrada de punto a punto para la landing page, el panel de login del alumno y las llamadas API.

---

### 3.2. Servidor VPS ($5 USD / mes)
* **Especificaciones:** Servidor Virtual Privado (Ubuntu 24.04 LTS, 1 vCPU, 1 GB - 2 GB RAM, 20-40 GB SSD) en proveedores como Hetzner, DigitalOcean, Linode o Vultr.
* **Servidor Web y Proxy Inverso:** **Nginx** (o Caddy). Se encarga de:
  1. Servir los archivos web de la Landing Page pública.
  2. Gestionar la aplicación web privada (Área de Alumnos) e interfaces de administración.
  3. Ejecutar los endpoints / webhooks API que escuchan peticiones de los Agentes de Orca (ej. `/api/v1/crear-usuario`).
* **Regla Innegociable de Infraestructura:** **PROHIBIDO procesar o guardar archivos de video `.mp4` locales en el VPS.**
  * *Razón Técnica:* La CPU (1 vCPU) y la RAM se saturarían al intentar procesar o transmitir video a múltiples alumnos simultáneamente. La transcodificación HLS consumirá el 100% de la CPU, haciendo caer la landing page y el sistema de login. El VPS se utiliza **exclusivamente para lógica web, base de datos de usuarios y enrutamiento**.

---

### 3.3. Landing Page Pública y Embudo de Ventas
* **Función:** Presentar la propuesta de valor irresistible del programa, la historia y autoridad de Marcos Barbosa, la diferenciación "Ellos vs Nosotros", el desglose de los 7 pilares y la oferta de $100 USD (con un valor real percibido de $1,491 USD).
* **Llamado a la Acción (CTA) Estratégico:**
  * No utiliza pasarela de pago automatizada en la landing para evitar tasas/comisiones altas y reducir la fricción inicial.
  * El botón principal redirige directamente al **WhatsApp de Cierre** (`https://wa.me/...`) con un texto predefinido:  
    *“Hola Marcos y Joel, quiero inscribirme a Rompiendo Barreras y coordinar el pago de mi acceso.”*

---

### 3.4. Venta Directa por WhatsApp y Procesamiento de Pagos
* **Rol en el Ecosistema:** Estrategia de venta consultiva de alta conversión para Latinoamérica. Permite construir una relación de confianza directa entre Marcos/Joel y el alumno antes de la transacción.
* **Métodos de Pago Soportados:**
  * Transferencias bancarias locales / Alias (Argentina o país origen).
  * Enlaces de pago con tarjeta de crédito/débito (Mercado Pago, Stripe Link, Wise, Zelle, PayPal).
* **Verificación de Pago:** El alumno envía el comprobante de pago en el chat.
* **Aprovisionamiento de Usuario (Dos vías):**
  1. **Manual:** Joel o Marcos ingresan al panel de administración `/admin` en la web y registran el email del alumno.
  2. **Vía Agente de Orca:** Marcos/Joel envían un mensaje al bot del agente en Telegram/WhatsApp: `/alta alumno@email.com Nombre`. El agente de Orca ejecuta un `POST` al VPS en `/api/v1/crear-usuario` para generar credenciales y enviar el email de bienvenida automáticamente.

---

### 3.5. Área de Alumnos (Plataforma Privada / App)
* **Función:** Panel privado donde el alumno accede al contenido estructurado tras iniciar sesión (`tu-dominio.com/login`).
* **Estructura del Contenido (Release Mixto / Drip Content):**
  * **Módulo 0 (Onboarding):** 8 videos iniciales (Bienvenida, Misión, Visión, Propósito, Metodología, Áreas de Control, Código de Honor, Primera Victoria) desbloqueados de forma inmediata.
  * **Pilar 1 (Casa de Gobierno):** Disponible en la semana 1.
  * **Pilares 2 al 7:** Desbloqueo progresivo semana a semana para garantizar la ejecución y evitar la parálisis por análisis.
* **Integración de Entregables:** Bajo cada reproductor de video se adjuntan los botones de descarga de archivos PDF/Excel (Auditoría de Identidad, Centro de Mando Financiero, Presupuesto Base Cero, etc.).

---

### 3.6. Red de Distribución de Video: Bunny Stream (Bunny.net)
* **Función:** Almacenamiento externo masivo de alta velocidad y distribución global de video por streaming.
* **Estructura de Costos:**
  * Almacenamiento: **$0.01 USD / GB al mes** (~$1 USD por 100 GB de clases).
  * Streaming: **$0.005 a $0.01 USD / GB reproducido** (~$1 USD por 100-200 GB de reproducción).
  * Costo total proyectado: **$1 a $3 USD / mes**.
* **Integración con la Web:**
  * Joel sube las clases editadas en formato MP4 a la biblioteca de Bunny Stream.
  * Bunny transcodifica el video automáticamente a protocolo HLS (resolución adaptativa 1080p, 720p, 480p según el internet del alumno).
  * Joel copia el código `<iframe>` de embed y lo pega en el HTML/código de la clase en la web.
* **Mecanismos Anti-Piratería y Seguridad:**
  1. **Restricción por Dominio (`Allowed Domains`):** Configurado estrictamente para responder solo a `https://tu-dominio.com`. Si alguien intenta copiar la URL del video o incrustarlo en otra web, Bunny bloquea la reproducción.
  2. **Deshabilitación de Descargas Directas:** Impide que los usuarios descarguen los videos originales desde el navegador.

---

## 4. Conexión de Agentes de IA (Orca) con la Infraestructura

### 4.1. Canales de Integración de Orca
Los agentes de Orca interactúan con el ecosistema mediante dos vías principales:
1. **Notion API REST (`api.notion.com`):** Para leer/escribir en las bases de datos de *Fábrica de Clases*, *Matriz de Anuncios* y *Roadmap de Tareas*.
2. **VPS Backend API (`tu-dominio.com/api/v1/...`):** Para consultar usuarios, activar accesos a alumnos o disparar notificaciones.

### 4.2. Definición de Agentes Especializados
* **Agente 1: Creador de Guiones y Diapositivas**
  * *Input:* Notas de voz o guion técnico de Marcos en Notion.
  * *Output:* Estructura maquetada de diapositivas en Notion/Markdown para que Joel arme la presentación en Canva/Gamma.
* **Agente 2: Copywriter de Anuncios y Marketing**
  * *Input:* Matriz de dolores/deseos de los Avatares 1 y 2.
  * *Output:* Creación de 3-5 variaciones de copy de anuncios por día basados en Hooks Emocionales, Lógicos e Identidad ("José de Arimatea").
* **Agente 3: PM / Gestor del Roadmap de Lanzamiento**
  * *Input:* Consultas diarias al calendario del Roadmap.
  * *Output:* Recordatorios automatizados por Telegram a Joel y Marcos sobre clases pendientes de grabar, editar o publicar.
* **Agente 4: Asistente de Alta de Alumnos**
  * *Input:* Comando del administrador en chat de WhatsApp/Telegram post-pago.
  * *Output:* Llamada HTTP `POST` a `/api/v1/crear-usuario` en el VPS, registrando al alumno y enviándole credenciales.

---

## 5. Resumen Financiero y Operativo Mensual de la Infraestructura

| Componente | Proveedor Recomendado | Función en el Ecosistema | Costo Estimado / Mes |
| :--- | :--- | :--- | :--- |
| **Dominio Web** | Cloudflare / Namecheap / DonWeb | Identidad (`tu-dominio.com`) | ~$0.83 USD ($10/año) |
| **Servidor VPS** | Hetzner / DigitalOcean | Hosting Web, App, API Backend, SSL | **$5.00 USD / mes** |
| **Video CDN** | **Bunny.net (Bunny Stream)** | Almacenamiento y Streaming HLS seguro | **$1.00 - $3.00 USD / mes** |
| **Plataforma IA** | Orca (vía API Keys) | Automatizaciones y agentes inteligentes | Según consumo de API |
| **Procesamiento Pagos**| WhatsApp + Transferencia | Cierre de ventas directo, cero comisiones | **$0.00 USD** |
| **TOTAL ESTIMADO** | -- | **Infraestructura Completa de Alto Rendimiento** | **~$6.83 - $8.83 USD / mes** |

---

## 6. Instrucciones de Lectura Directa para Agentes de IA

Cualquier agente de IA que lea este archivo (`arquitecturaweb.md`) debe asimilar las siguientes reglas de comportamiento:

1. **Comprensión del Negocio:** Comprender que "Rompiendo Barreras" vende una formación de $100 USD con enfoque cristiano de alto impacto en finanzas, liderazgo y propósito.
2. **Separación de Servicios:** El VPS solo procesa código web y datos; Bunny Stream procesa y sirve videos. Nunca sugerir guardar o convertir videos dentro del VPS.
3. **Respeto a la Privacidad:** Mantener los accesos de los alumnos seguros y validar pagos mediante interacción previa en WhatsApp.
4. **Flujo de Producción de Clases:** Apoyar la cadena: Marcos (Nota/Audio) -> Agente IA (Guion/Puntos Diapositiva) -> Joel (Diseño PPT + Edición Video) -> Bunny Stream (Alojamiento) -> Área de Alumnos (Publicación).
