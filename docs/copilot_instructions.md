# Ficha — Ignorar los `vite.config.ts.timestamp-*.mjs` huérfanos

> **Ejecutada por Claude, no por Copilot.** Es un cambio de configuración (`.gitignore`) y, según `claude.md`, lo hace Claude. No hay `docs/copilot_report.md` nuevo: el que hay es de la ficha anterior.

## Contexto mínimo

El 2026-11-24 apareció sin seguimiento `client/vite.config.ts.timestamp-*.mjs` tras detener `.\run.ps1 dev --no-bot`. El riesgo es que se cuele en un commit.

Causa, en el código de Vite 5.4.21 (`loadConfigFromBundledFile`, `node_modules/vite/dist/node/chunks/dep-*.js`): al arrancar, Vite compila `vite.config.ts`, lo escribe en `vite.config.ts.timestamp-<ms>-<hex>.mjs`, lo importa y lo borra en un `finally`. El archivo solo existe durante la carga de la configuración (milisegundos). Queda huérfano únicamente si el proceso muere justo entonces (por ejemplo, si se cierra la consola mientras Vite arranca). Desde `run.py` no se puede evitar: no hay ningún punto de apagado que cubra esa ventana.

Pendiente de origen: `docs/pendientes.md`, entrada del 2026-11-24 («Vite deja `client/vite.config.ts.timestamp-*.mjs` al detenerse»).

## Objetivo

Que un `timestamp-*.mjs` huérfano no aparezca en `git status` ni pueda entrar en un commit por accidente.

## Diseño

Añadir al final de `.gitignore`:
```gitignore

# Config temporal de Vite (vite.config.ts.timestamp-*.mjs); queda huerfano si Vite muere al cargar la config
client/*.timestamp-*.mjs
```

## Archivos permitidos

- `.gitignore`.

## Fuera de alcance

- `scripts/run.py` (el apagado de Vite ya es correcto; la ventana de carrera está dentro de Vite), `client/vite.config.ts`.

## Criterios de aceptación

### (a) Estáticos
1. `git check-ignore -v` sobre un `client/vite.config.ts.timestamp-<n>-<hex>.mjs` de prueba → lo ignora la regla nueva.
2. `git status --short` con ese archivo presente → no aparece.
3. `git ls-files -i -c --exclude-standard` → vacío (la regla no oculta ningún archivo versionado).

### (b) Integrados
Ninguno: `.gitignore` no afecta a la ejecución.

## Revisión (Claude)

**Veredicto:** hecho y verificado.

**Verificación:**
```
(a)1 .gitignore:24:client/*.timestamp-*.mjs    client/vite.config.ts.timestamp-1764100000000-abc123.mjs
(a)2 git status --short ->  M .gitignore |  M docs/pendientes.md   (el .mjs de prueba no aparece; se borró después)
(a)3 git ls-files -i -c --exclude-standard -> (vacío)
```

**Correcciones:** ninguna.

**Pendientes:** ninguno nuevo. Si algún día se pasa la configuración a `vite.config.mjs`/`.js`, Vite deja de generar ese archivo y la regla sobra, aunque no estorba.
