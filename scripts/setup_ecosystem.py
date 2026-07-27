# setup_ecosystem.py - Script Automatizado de Organización de Archivos
# Proyecto: Rompiendo Barreras (Marcos Barbosa & Joel)
#
# Instrucción: Pon este archivo en la carpeta raíz donde descargaste todos los archivos
# del proyecto y ejecútalo con: python setup_ecosystem.py

import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Definición de Directorios de Destino
DIRECTORIES = {
    "docs": os.path.join(BASE_DIR, "docs"),
    "config": os.path.join(BASE_DIR, "config"),
    "vps_backend": os.path.join(BASE_DIR, "vps_backend")
}

# 2. Mapeo de Archivos -> Directorio Destino
FILE_MAPPING = {
    # --- Carpeta: docs/ (Estrategia, Arquitectura, Guiones y Esquemas) ---
    "Rompiendo barreras.docx": "docs",
    "Rompiendo barreras - Documento Único-6.docx": "docs",
    "arquitecturaweb.md": "docs",
    "arquitectura-agentica-web.md": "docs",
    "notion_schema.md": "docs",
    "guiones_onboarding_mvp.md": "docs",

    # --- Carpeta: config/ (System Prompts para Orca) ---
    "prompts_agentes_orca.md": "config",

    # --- Carpeta: vps_backend/ (Código, Servidor VPS & Memoria) ---
    "vps_backend_spec.md": "vps_backend",
    "rompiendo_barreras_master_context.md": "vps_backend",
    "agent_scratchpad.json": "vps_backend",
    "memory_manager.py": "vps_backend",
    "orca_memory_bridge.py": "vps_backend"
}

def create_directories():
    print("📁 Creando estructura de carpetas del proyecto...")
    for folder_name, path in DIRECTORIES.items():
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            print(f"  └─ Creando carpeta: /{folder_name}/")
        else:
            print(f"  └─ Carpeta ya existente: /{folder_name}/")

def move_files():
    print("\n🚚 Moviendo archivos a sus ubicaciones oficiales...")
    moved_count = 0
    
    # Listar archivos en el directorio actual
    current_files = os.listdir(BASE_DIR)
    
    for filename in current_files:
        # Ignorar este script
        if filename == "setup_ecosystem.py" or filename.startswith("."):
            continue
            
        target_folder = FILE_MAPPING.get(filename)
        
        # Búsqueda por coincidencia parcial si los nombres varían ligeramente
        if not target_folder:
            if "Rompiendo" in filename and filename.endswith(".docx"):
                target_folder = "docs"
            elif "arquitectura" in filename and filename.endswith(".md"):
                target_folder = "docs"
            elif "memory_manager" in filename and filename.endswith(".py"):
                target_folder = "vps_backend"

        if target_folder:
            src_path = os.path.join(BASE_DIR, filename)
            dest_path = os.path.join(DIRECTORIES[target_folder], filename)
            
            # Mover archivo
            shutil.move(src_path, dest_path)
            print(f"  ✔ [{filename}]  ===>  /{target_folder}/{filename}")
            moved_count += 1

    print(f"\n✅ ¡Organización completada! Se movieron {moved_count} archivos.")

def create_root_readme():
    readme_content = """# Rompiendo Barreras - Ecosistema Operativo & Agentes de IA

Este repositorio contiene la arquitectura completa, guiones, esquemas de bases de datos, código de servidor backend y el motor de **Memoria Jerárquica con Compresión de Estado (Rolling Scratchpad)** para los agentes de Orca AI.

## 🗂️ Estructura del Repositorio

```text
rompiendo-barreras-ecosystem/
│
├── 📁 docs/                         <-- DOCUMENTACIÓN MAESTRA Y GUIONES
│   ├── Rompiendo barreras.docx                  # Estrategia, Precios, Oferta y 5 Anexos
│   ├── arquitecturaweb.md                       # Diagrama de Red, VPS y Bunny Stream
│   ├── notion_schema.md                         # Esquema de DBs y Payloads REST para Notion
│   └── guiones_onboarding_mvp.md                # 8 Guiones de Onboarding para Marcos
│
├── 📁 config/                       <-- CONFIGURACIÓN DE AGENTES EN ORCA
│   └── prompts_agentes_orca.md                  # System Prompts & Few-Shots (Agentes 1 a 4)
│
└── 📁 vps_backend/                  <-- CÓDIGO Y MEMORIA EN SERVIDOR DE $5 USD
    ├── vps_backend_spec.md                      # Especificación de DB SQL y REST API
    ├── rompiendo_barreras_master_context.md     # Base de Conocimiento Central (Level 1 Context)
    ├── agent_scratchpad.json                    # Estado Dinámico Activo (Level 2 Rolling Scratchpad)
    ├── memory_manager.py                        # Motor de Compresión y Caché de API Python
    └── orca_memory_bridge.py                    # API FastAPI que conecta Orca con el VPS
```

## 🚀 Puesta en Marcha Rápida
1. Sube la carpeta `vps_backend/` a tu servidor VPS ($5 USD/mes) con Ubuntu LTS.
2. Ejecuta `uvicorn orca_memory_bridge:app --host 0.0.0.0 --port 8000` para iniciar el backend API.
3. Conecta tus agentes en Orca apuntando al endpoint `POST /api/v1/orca/execute`.
"""
    readme_path = os.path.join(BASE_DIR, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("📄 Generado archivo README.md en la raíz del proyecto.")

if __name__ == "__main__":
    print("=========================================================")
    print("  ORGANIZADOR AUTOMÁTICO DE ARQUITECTURA - ROMPIENDO BARRERAS")
    print("=========================================================\n")
    create_directories()
    move_files()
    create_root_readme()
    print("\n🚀 El ecosistema está listo y estructurado para los Agentes de Orca.")
