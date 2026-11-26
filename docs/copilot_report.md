# Reporte de Copilot — Cierre de Edge sin espera

## Cambios realizados
scripts/run.py:442-466 → reemplazado el bucle `for force in (False, True)` por un `taskkill /T /F` directo en `stop_window()`. Actualizado docstring para reflejar el cambio.
scripts/test_run.py:3,24 → añadidas importaciones `MagicMock` y `patch` de unittest.mock, e import `scripts.run as run`.
scripts/test_run.py:241-262 → añadidos tests `test_stop_window_forces_once_on_windows` y `test_stop_window_skips_finished_process`.

## (a)1 unittest scripts.test_run -v
```
test_build_window_args (scripts.test_run.TestRun.test_build_window_args) ... ok
test_build_window_args_tiktok (scripts.test_run.TestRun.test_build_window_args_tiktok) ... ok
test_find_edge_none (scripts.test_run.TestRun.test_find_edge_none) ... ok
test_find_edge_path (scripts.test_run.TestRun.test_find_edge_path) ... ok
test_find_edge_programfiles (scripts.test_run.TestRun.test_find_edge_programfiles) ... ok
test_open_parent_missing_pid (scripts.test_run.TestRun.test_open_parent_missing_pid) ... ok
test_parent_alive_tracks_real_process (scripts.test_run.TestRun.test_parent_alive_tracks_real_process) ... ok
test_parse_args_parent_pid (scripts.test_run.TestRun.test_parse_args_parent_pid) ... ok
test_parse_args_tiktok (scripts.test_run.TestRun.test_parse_args_tiktok) ... ok
test_parse_args_window (scripts.test_run.TestRun.test_parse_args_window) ... ok
test_shutdown_order_and_targets (scripts.test_run.TestRun.test_shutdown_order_and_targets) ... ok
test_start_backend_args (scripts.test_run.TestRun.test_start_backend_args) ... [run] Iniciando backend en http://127.0.0.1:8000 ...
ok
test_start_client_exits_when_node_not_found (scripts.test_run.TestRun.test_start_client_exits_when_node_not_found) ... [run] No se encontro node en el PATH. Instala Node.js 22 (README -> Requisitos).
ok
test_start_client_spawns_with_node_and_vite_bin (scripts.test_run.TestRun.test_start_client_spawns_with_node_and_vite_bin) ... [run] Iniciando overlay Vite en http://localhost:5173 ...
ok
test_stop_window_forces_once_on_windows (scripts.test_run.TestRun.test_stop_window_forces_once_on_windows) ... [run] Cerrando ventana Edge (PID 1234) ...
ok
test_stop_window_skips_finished_process (scripts.test_run.TestRun.test_stop_window_skips_finished_process) ... ok
test_window_specs (scripts.test_run.TestRun.test_window_specs) ... ok
test_with_layout (scripts.test_run.TestRun.test_with_layout) ... ok

----------------------------------------------------------------------
Ran 18 tests in 0.012s

OK
```

## (a)2 'for force in' ya no está
```
(no output)
```

## (a)3 git status --short
```
 M docs/copilot_instructions.md
 M docs/copilot_report.md
 M scripts/run.py
 M scripts/test_run.py
```

## (a)4 git diff scripts/run.py scripts/test_run.py
```
warning: in the working copy of 'scripts/test_run.py', LF will be replaced by CRLF the next time Git touches it
diff --git a/scripts/run.py b/scripts/run.py
index c6e7f76..451e797 100644
--- a/scripts/run.py
+++ b/scripts/run.py
@@ -440,11 +440,12 @@ def stop_process(proc: subprocess.Popen[str] | None, name: str) -> None:
 
 
 def stop_window(proc: subprocess.Popen[str] | None) -> None:
-    """Cierra la ventana de Edge.
+    """Cierra la ventana de Edge con taskkill /T /F.
 
     No usa stop_process(): Edge no tiene grupo de consola propio y un
     CTRL_BREAK a su PID podria llegar a la consola del orquestador.
-    taskkill sin /F envia WM_CLOSE (cierre normal); /F solo si no basta.
+    WM_CLOSE (taskkill sin /F) nunca cerraba Edge: siempre acababa en /F
+    tras 5 s de espera, asi que se va directo a /F.
     """
     if proc is None or proc.poll() is not None:
         return
@@ -456,15 +457,17 @@ def stop_window(proc: subprocess.Popen[str] | None) -> None:
         except subprocess.TimeoutExpired:
             proc.kill()
         return
-    for force in (False, True):
-        cmd = ["taskkill", "/PID", str(proc.pid), "/T"] + (["/F"] if force else [])
-        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
-        try:
-            proc.wait(timeout=5)
-            return
-        except subprocess.TimeoutExpired:
-            continue
-    log_run(f"No se pudo cerrar Edge (PID {proc.pid}).")
+    # WM_CLOSE (taskkill sin /F) nunca cerraba Edge: siempre se acababa en /F
+    # tras 5 s de espera. El perfil es propio de la app; no hay nada que perder.
+    subprocess.run(
+        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
+        stdout=subprocess.DEVNULL,
+        stderr=subprocess.DEVNULL,
+    )
+    try:
+        proc.wait(timeout=5)
+    except subprocess.TimeoutExpired:
+        log_run(f"No se pudo cerrar Edge (PID {proc.pid}).")
 
 
 def shutdown(
diff --git a/scripts/test_run.py b/scripts/test_run.py
index 25ebdc2..f933981 100644
--- a/scripts/test_run.py
+++ b/scripts/test_run.py
@@ -1,5 +1,5 @@
 import unittest
-from unittest.mock import patch
+from unittest.mock import MagicMock, patch
 from pathlib import Path
 import os
 import shutil
@@ -9,6 +9,7 @@ import sys
 REPO_ROOT = Path(__file__).resolve().parent.parent
 sys.path.append(str(REPO_ROOT))
 
+import scripts.run as run
 from scripts.run import (
     build_window_args,
     GAMEPLAY_WINDOW_SIZE,
@@ -238,6 +239,30 @@ class TestRun(unittest.TestCase):
         self.assertIsNone(open_parent(0x7FFFFFF0))
         self.assertIsNone(open_parent(0))
 
+    @patch.object(run, "IS_WINDOWS", True)
+    @patch("scripts.run.subprocess.run")
+    def test_stop_window_forces_once_on_windows(self, mock_subprocess_run):
+        proc = MagicMock()
+        proc.poll.return_value = None
+        proc.pid = 1234
+        run.stop_window(proc)
+        mock_subprocess_run.assert_called_once_with(
+            ["taskkill", "/PID", "1234", "/T", "/F"],
+            stdout=subprocess.DEVNULL,
+            stderr=subprocess.DEVNULL,
+        )
+        proc.wait.assert_called_once_with(timeout=5)
+
+    @patch("scripts.run.subprocess.run")
+    def test_stop_window_skips_finished_process(self, mock_subprocess_run):
+        proc = MagicMock()
+        proc.poll.return_value = 0
+        run.stop_window(proc)
+        mock_subprocess_run.assert_not_called()
+
+        run.stop_window(None)
+        mock_subprocess_run.assert_not_called()
+
 
 if __name__ == "__main__":
     unittest.main()
```

## Repaso de la tabla ⚠️ (filas 1 a 8)
1. Toqué pendientes.md: no
2. Toqué la ficha: no
3. Comandos de verificación ejecutados: sí (todas las salidas están pegadas arriba, completas)
4. No afirmar sin probar: sí (todos los tests pasan, git status y git diff verificados)
5. Salidas completas: sí (todas las salidas de terminal se pegaron sin recortar ni reescribir)
6. Reporte no vacío: sí (todos los campos de la plantilla están rellenos)
7. Tests que pueden pasar: sí (ejecuté unittest y los 18 tests pasan, incluido los dos nuevos)
8. Sin salir del alcance: sí (solo edité scripts/run.py y scripts/test_run.py, más docs/copilot_report.md)

## Bloqueos / notas
ninguno