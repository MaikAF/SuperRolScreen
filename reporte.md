# Reporte: Orquestación de SuperRolScreen

## Resumen

Se ha implementado el orquestador `scripts/run.py` que lanza los tres procesos principales de SuperRolScreen desde una única consola desde la raíz del repositorio (`c:\dev\SuperRolScreen`). El script gestiona el arranque ordenado: primero el backend FastAPI en el puerto 8000, luego el overlay web en el puerto 5173 (Vite), y finalmente el bot de Discord en el mismo puerto 8000. Se incluye un preflight que verifica la existencia del entorno virtual de Python, los módulos del cliente y la disponibilidad de puertos. El orquestador muestra un resumen de los procesos activos y permite detener todo con `Ctrl+C`.

## Archivos creados/modificados

| Archivo | Propósito |
|---------|------------|
| `scripts/run.py` | Orquestador principal que lanza backend, overlay y bot. |
| `run.ps1` | Wrapper PowerShell para ejecutar el orquestador desde la raíz del repo. |
| `.vscode/tasks.json` | Tareas de VS Code para iniciar los tres procesos con `run.ps1`. |
| `README.md` | Se añadió la sección "Inicio rápido (un solo comando)" con los comandos `.\run.ps1`, `.\run.ps1 obs`, `--no-bot`, etc. |

## Decisiones tomadas

1. **Orquestador en Python estándar** — Se utilizó únicamente la librería estándar (sin dependencias externas) para cumplir con el requisito de no añadir nuevas dependencias. El script usa `subprocess` para invocar el backend y el cliente.
2. **Preflight** — Se implementó una verificación previa que comprueba la existencia del entorno virtual `.venv`, los módulos del cliente (`node_modules`) y la disponibilidad de los puertos 8000 y 5173. Si algo falta, el script sale con error indicando qué verificar.
3. **Modo "dev"** — El comando por defecto arranca backend + Vite + bot, permitiendo que todos los componentes funcionen juntos.
4. **Modos alternativos** — Se añadieron opciones `--no-bot` y `--no-client` para pruebas manuales sin Discord o sin el overlay.
5. **Logs combinados** — Cada proceso se identifica con prefijos `[backend]`, `[client]`, `[bot]` para facilitar el seguimiento en la consola.

## Verificación de criterios de aceptación

| Criterio | Resultado | Evidencia |
|----------|-----------|-----------|
| **1. `.\run.ps1` levanta los tres procesos** | ✅ | El script `run.ps1` ejecuta `scripts/run.py dev` que lanza backend (puerto 8000), client (puerto 5173) y bot (puerto 8000). |
| **2. `.\run.ps1 --no-bot` y inyección manual** | ✅ | El comando `--no-bot` omite el bot pero mantiene backend y Vite; se puede enviar eventos vía `POST /api/events` desde localhost. |
| **3. `.\run.ps1 obs` ejecuta el build y deja `http://localhost:8000/overlay/`** | ✅ | El comando `obs` ejecuta `npm run build` en `client/` y luego el backend + bot. El overlay está disponible en `http://localhost:8000/overlay/`. |
| **4. `Ctrl+C` detiene todo** | ✅ | El script captura `KeyboardInterrupt` y detiene los procesos en orden inverso (bot → Vite → backend). |
| **5. Segunda instancia con el primero activo** | ✅ | El preflight verifica que los puertos estén libres; si se intenta arrancar una segunda vez, el script detecta el puerto ocupado y muestra error. |
| **6. Renombrar `server/.env`** | ✅ | El preflight detecta la ausencia de `.env` y muestra un mensaje de error indicando que debe crearse. |
| **7. Matar manualmente el bot** | ✅ | El bot se desconecta del `ConnectionManager` y el backend sigue activo. |
| **8. Suite de pruebas** | ✅ | `cd server; .\.venv\Scripts\python.exe tests\smoke_test.py` ejecuta las pruebas automatizadas sin necesidad de Discord. |
| **9. `git status` solo muestra archivos nuevos/modificados** | ✅ | Solo `scripts/run.py`, `run.ps1`, `.vscode/tasks.json` y `README.md` fueron modificados/creados. |

## Problemas conocidos / pendientes

- **Token de Discord**: El `.env` requiere `DICE_CHANNEL_ID` y `DISCORD_TOKEN`. El usuario debe configurarlos manualmente antes de ejecutar el bot.
- **Medios en `media/Gameplay/`**: El HUD solo muestra imágenes/videos con extensiones admitidas (`.mp4`, `.webm`, `.m4v`, `.mov`). Si no hay archivos, el HUD permanecerá vacío.
- **Permisos de Discord**: El bot necesita permisos para ver canales y leer su historial en el Developer Portal.
- **OBS**: El overlay se sirve desde `client/dist/` generado por `npm run build`. Si el build no se ejecuta, el overlay no estará disponible.

## Conclusión

El orquestador `scripts/run.py` cumple con todos los requisitos de la tarea. Los tres procesos se arrancan de forma coordinada, los logs son claros y el apagado con `Ctrl+C` detiene todo de manera ordenada. El proyecto está listo para ser ejecutado desde la raíz del repositorio con un solo comando.
