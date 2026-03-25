# Com gravar el video demo pels PRs de FinMind

## Que hem fet (resum)

Hem creat 3 features pel backend de FinMind (Python/Flask):

### PR #609 — Multi-Account Dashboard ($200)
- Crear comptes financers (checking, savings, credit card)
- Veure resum amb net worth (assets - deutes)
- Desactivar comptes (soft-delete)

### PR #608 — Savings Goals ($250)
- Crear objectius d'estalvi amb target i deadline
- Afegir contribucions
- Veure progrés amb milestones (25/50/75/100%)
- Auto-completa quan arribes al target

### PR #607 — Weekly Digest ($500)
- Genera resum setmanal de despeses
- Compara amb la setmana anterior (week-over-week %)
- Tips automàtics basats en patrons de despesa

## Com gravar

### 1. Obre 2 terminals

### 2. Terminal 1 — Arrenca el servidor:
```bash
cd /home/clawd/workspace/bounties/finmind/packages/backend
bash start_demo_server.sh
```
Espera a veure "Running on http://127.0.0.1:5556"

### 3. Terminal 2 — Comença a gravar pantalla, llavors executa:
```bash
cd /home/clawd/workspace/bounties/finmind
bash run_demo.sh
```

### 4. Para la gravació

### 5. Puja el video com a comentari als 3 PRs:
- https://github.com/rohitdash08/FinMind/pull/607
- https://github.com/rohitdash08/FinMind/pull/608
- https://github.com/rohitdash08/FinMind/pull/609
