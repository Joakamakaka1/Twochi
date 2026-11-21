# 0001. Fijar las versiones de las herramientas con mise

- Estado: aceptada
- Fecha: 2026-11-21

## Contexto

La forma de trabajo pide que las herramientas tengan su versión fijada en el repositorio (uv y Python, Node y pnpm, just, Terraform, tflint, actionlint, zizmor…), pero no dice cómo. El repositorio se trabaja en Windows, en WSL2 y en CI, y los tres deben usar las mismas versiones para que `just check` dé el mismo resultado en local que en CI.

## Decisión

Un único `mise.toml` en la raíz fija la versión exacta de cada herramienta. mise funciona en Windows, en Linux (WSL2) y en CI con su acción oficial, y en un solo fichero cubre lenguajes (Python, Node), gestores (uv, pnpm) y binarios sueltos (just, Terraform, tflint, actionlint). zizmor se instala con el backend `pipx` de mise, que usa `uv tool install` con la versión fijada.

Las versiones respetan la misma espera de siete días que `exclude-newer` en uv: no se adopta una versión publicada hace menos de una semana.

## Consecuencias

- `mise install` deja la máquina lista; `mise trust` es necesario la primera vez.
- Las dependencias de Python y de JavaScript siguen fijadas en `uv.lock` y `pnpm-lock.yaml`; mise solo fija las herramientas.
- Subir una herramienta es cambiar una línea de `mise.toml` en su propio PR.
- Quedan fuera por ahora AWS CLI, Supabase CLI, `bws`, `gh` y Gitleaks (este último lo fija el pre-commit): entran cuando una tarea los necesite.
