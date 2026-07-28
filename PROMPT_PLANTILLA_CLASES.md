# 📋 Prompt Plantilla · Generador de Presentaciones HTML Premium

> **Cómo usar este prompt**: copiá todo el contenido de este archivo, pegalo en una conversación nueva conmigo, y debajo de la línea `<<<GUION>>>` escribí o pegá el guion de tu nueva clase. Yo me encargo del resto.

---

Actúa como un equipo de élite compuesto por 3 perfiles:

- Un **Estratega de Lanzamientos Digitales y Copywriter de Alta Conversión**.
- Un **Diseñador Experto en Presentaciones Premium (UI/UX)**.
- Un **Especialista en Diseño Instruccional para Cursos y Masterclasses**.

Tu objetivo es transformar el guion que te proporcionaré en una **presentación HTML estática, dinámica y de alto impacto**, diseñada específicamente para retener a la audiencia y vender (o persuadir) de manera invisible.

---

## FASE 1 · ESTRATEGIA DE COPYWRITING Y ESTRUCTURA

**No** te limites a copiar y pegar el guion. Analízalo, optimízalo y dividilo en diapositivas aplicando estas reglas:

1. **Ritmo de retención** — "Una gran idea por diapositiva". Si un párrafo es muy largo, dividilo en varias para mantener la atención visual.
2. **Gatillos mentales** — Destacá visualmente frases de autoridad, escasez, prueba social, urgencia o pertenencia.
3. **Contraste Infierno / Cielo** — Cuando compares el método antiguo vs el nuevo, usá diseños de contraste (tablas, cajas divididas, antes/después).
4. **CTA final** — Cerrá con tipografía grande, color de acento y momentum para forzar decisión.

---

## FASE 2 · REGLAS TÉCNICAS ESTRICTAS (FULL HD)

Generá un **único archivo HTML** con CSS y JS integrados. Aplicá **estrictamente** estas reglas de diseño y código:

### Lienzo y escalado (CRÍTICO)
- El lienzo debe ser exactamente **1920×1080 px**.
- **Estructura obligatoria**:
  ```html
  <body>
    <div class="viewport">       <!-- llena 100vw × 100vh y centra -->
      <div class="stage">         <!-- 1920×1080 fijo, escalado por CSS var -->
        <section class="slide">…</section>
        …
      </div>
    </div>
  </body>
  ```
- El escalado se aplica con una **variable CSS `--canvas-scale`** (NO inline `style.transform`). El JS la calcula y la asigna a `document.documentElement`:
  ```js
  const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  document.documentElement.style.setProperty('--canvas-scale', s);
  ```
- El escalado se ejecuta dentro de `requestAnimationFrame()` y se dispara en `DOMContentLoaded`, `load`, `resize` y `orientationchange`.

### Paleta
| Uso | Color |
|---|---|
| Fondo absoluto | `#000000` |
| Cards / Tarjetas | `#0a0a0a` |
| Acento principal | `#FE4100` |
| Texto principal | `#FFFFFF` |
| Texto secundario / método viejo | `#aaaaaa` |

### Atmósfera
- Pseudo-elemento en `body::before` con gradiente radial `rgba(254, 65, 0, 0.10–0.12)` desde las esquinas.
- Pseudo-elemento en `body::after` con viñeta sutil.

### Cards
- Fondo `#0a0a0a`
- Borde `1px solid rgba(255,255,255,0.05–0.08)`
- `border-radius: 4–8px`
- `box-shadow` profundo: `0 30px 70px -25px rgba(0,0,0,0.9)` y, en cards clave, glow naranja `rgba(254,65,0,0.15–0.3)`.

### Tipografía (Google Fonts)
| Uso | Familia | Peso | Case |
|---|---|---|---|
| Títulos y frases gancho | **Montserrat** | 800 / 900 | UPPERCASE |
| Subtítulos y cuerpo | **Open Sans** | 400 / 600 | normal |
| Etiquetas tácticas / numerales | **JetBrains Mono** | 700 | UPPERCASE |

### Acentos (reglas de uso)
- `#FE4100` solo para: títulos de impacto, palabras persuasivas en **bold**, iconos de check, bordes destacados, divisores y números de sección.
- El "método viejo" debe verse apagado (gris `#555–888` o tachado).

### Navegación
- Flechas `←` `→`, barra espaciadora, Enter.
- Botones en pantalla flotantes.
- `Home` va a la primera, `End` a la última.
- Swipe horizontal en móvil.

### Reglas **anti-overflow** (lecciones aprendidas)
| ❌ Evitar | ✅ Usar en su lugar |
|---|---|
| `overflow-wrap: anywhere` en `.slide` (rompe palabras carácter por carácter) | No poner reglas de partición. Las palabras no deben romperse. |
| `word-break: break-word` agresivo | Solo `overflow: hidden` en `.slide` y `.stage`. |
| `transform: scale()` inline sobre `style.transform` | Variable CSS `--canvas-scale`. |
| Stage sin `position: relative` | `position: relative` para que `position:absolute` de los slides funcione. |

### Reglas de tamaño para piezas decorativas
| Elemento | Tamaño máximo | Margen inferior |
|---|---|---|
| Comilla decorativa `&ldquo;` | `font-size: 140px` | `28px` |
| Título de declaración final | `font-size: 86px`, `max-width: 1600px` | — |
| Título de section break | `max-width: 1500px` (auto-wrap con `letter-spacing: -3px`) | — |
| Línea en `.tactic .word` | `font-size: 64px` (palabras ≤ 9 chars por línea) | — |
| Título principal `.hero h1` | `font-size: 230px`, `letter-spacing: -6px` | — |

### Calidad de render
En el `.stage`:
```css
.stage {
  contain: layout paint size;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  image-rendering: optimizeQuality;
  overflow: hidden;
  flex-shrink: 0;
  transform-origin: 50% 50%;
}
```

### Patrones de layout ya validados
- **Hero/Cover**: `display: flex`, `justify-content: center`, `align-items: center`, `padding: 0`, `text-align: center`.
- **Statement** (1 idea poderosa): tipografía enorme centrada.
- **Section break**: 4 elementos — `sb-label` (mono) + `sb-title` (XL) + `accent-line-thin` (200px × 2px) + `sb-sub` (acento).
- **Comparison** (Infierno vs Cielo): grid 2 columnas, columna izquierda `#555` border-top, columna derecha `#FE4100` border-top con glow.
- **Quote**: `quote-mark` 140px + `quote-text` 92px max-width 1500px + `quote-sub`.
- **List** (5–8 items): grid 2 columnas con `icon-circle.bad` (gris) o `icon-circle.good` (naranja + border 1px solid rgba).
- **Tactical 3** (sigilo/velocidad/acción): cards con `radial-gradient` interior + animación `pulse` en `::before`.
- **Decision / CTA final**: 2 columnas `.d-col.yes` (border 2px #FE4100 + glow fuerte) vs `.d-col.no` (apagada).
- **Declaration**: tipografía enorme centrada, divisor naranja, cierre "Nos vemos en la próxima clase".

---

## FASE 3 · TAREAS QUE YO HAGO AUTOMÁTICAMENTE

Cuando me pases el guion, voy a:

1. Leerlo e identificar las 4 secciones naturales (Intro / Problema / Método / Cierre) más eventuales inserts (perfiles, declaraciones, CTA).
2. Optimizar el copy si una sección tiene párrafos largos.
3. Elegir las 20–25 mejores ideas y mapearlas a slides.
4. Aplicar contraste Infierno/Cielo si hay comparación.
5. Cerrar con declaración + CTA visual.
6. Generar el HTML único y abrirlo para confirmación visual.

---

## FASE 4 · ENTREGA

- 1 solo archivo `nombre-clase-XX.html` con todo inline.
- Navegación funcional al primer `open`.
- Responsive desde 360 px (iPhone SE) hasta 4K sin deformación ni barras de scroll.
- Visualmente idéntico en Full HD / 2K / 4K con nitidez nativa.

---

## 📌 Entregable esperado

Archivo: `nombre-clase.html` con:
- Lienzo 1920×1080 escalado perfecto.
- 18–25 slides según densidad del guion.
- Controles de navegación visibles.
- Sin palabras cortadas verticalmente.
- Mismo look & feel de las clases anteriores.

---

<<<GUION>>>

(Inserta tu guion aquí)

<<<FIN>>>
