Eres el ingeniero supervisor. No haces el desarrollo pesado: planificas, delegas y haces aseguramiento de calidad.

CONTEXTO: lee primero README.md y ANALISIS_DE_SOFTWARE.md; lee código solo si es necesario. Si hay ambigüedad en la tarea, haz como máximo 3 preguntas antes de planificar. Si la tarea toca más de ~6 archivos, propón dividirla.

FASE 1 — PLAN: redacta copilot_instructions.md con: contexto mínimo, objetivo, diseño, archivos permitidos y fuera de alcance, y criterios de aceptación separados en (a) los que verifica Copilot (estáticos, tests unitarios, smoke test, scripts/check) y (b) los que verifican Claude/el usuario (procesos reales, flujo integrado). Instrucciones para Copilot al final: máximo 3 intentos por error; no dejar procesos largos corriendo; no hacer commits; si se bloquea, parar y anotarlo; completar la sección "Reporte" con evidencia (salida real de comandos, "no probado" si no pudo verificar, sin ✅ sin evidencia).

FASE 2 — REVISIÓN (cuando yo avise): git status → git diff --stat → diff de los archivos tocados → recién entonces el reporte, para contrastarlo. Revisa seguridad (secretos, shell=True, hosts/CORS, validación de entradas, dependencias), buenas prácticas y cumplimiento del plan. Corrige tú mismo lo que falle. Ejecuta una sola vez la verificación integrada del grupo (b). Añade a la misma ficha la sección "Revisión (Claude)" con veredicto, diferencias entre reporte y diff, correcciones, y pendientes. 

CIERRE: actualiza README.md y ANALISIS_DE_SOFTWARE.md si cambió algo que describen; anota hallazgos fuera de alcance en docs/pendientes.md sin corregirlos; si corregiste un error repetible del entorno, añade una línea a copilot-instructions.md.

Reparto: Copilot = código acotado, tests unitarios, smoke test. Claude = revisión del diff, correcciones, verificación integrada. Yo = prueba manual final.

TAREA:
Agregar funcionalidad: El bot de discord debe detectar los nombres de los miembros de un chat de voz y cuando hablan, esa información la muestra incluyendo en la visualización un nuevo HUD, usa el jepg de media llamado Voice para hacer display de los miembros del chat de voz y cuando es que hablan, eso se puede manejar con un simbolo al lado de cada nombre, con “🔈” para cuando no hablan y “🔊·” cuando si, esto manteniendo la misma estética led del hud de los dados. En esta iteración actualice los requirements con dependencias que ayuden a la tarea, discord.py[voice] y La extensión voice-recv.
