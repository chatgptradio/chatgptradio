# Workflow de développement — ChatGPT Radio

Chaîne canonique. Chaque tâche entre par l'un des cinq modes. Sauter des étapes produit du code incompatible, des failles de sécurité ou du scope drift.

**Toujours actifs (tous modes) :** `python-patterns` · `python-testing` · `git-workflow` · `security-review`

---

## Sélection du mode

```
Tâche ?
├── Nouvelle fonctionnalité / capacité ──── MODE A
├── Quelque chose est cassé ──────────────── MODE B
├── Comprendre / ré-architecturer / explorer MODE C
└── Issues AFK, batch autonome ──────────── MODE D
Fin de session ──────────────────────────── MODE E
```

---

## MODE A — Nouvelle fonctionnalité

```
1. search-first          → libs, prior art, rate limits — AVANT tout code
2. brainstorming         → design Socratique, 2-3 approches, approbation spec
3. plan-prd              → PRD : problème + hypothèse + scope → .claude/prds/
4. plan <prd>            → plan impl avec micro-tâches → .claude/plans/
5. to-issues             → vertical slices, HITL/AFK split, labellisation issues
```

⛔ **ARRÊT OBLIGATOIRE après l'étape 5** — une fois les issues labellisées `AFK` + `ready-for-agent` :
- Ne PAS continuer l'implémentation inline dans cette conversation
- Quitter MODE A → **Entrer en MODE D** immédiatement
- Les étapes 6-11 se passent **dans les subagents MODE D**, pas ici

```
6. using-git-worktrees   → (dans chaque subagent) workspace isolé
7. tdd-workflow          → RED / GREEN / REFACTOR, couverture pytest ≥ 80 %
8. subagent-review       → revue 2 étapes : conformité spec → qualité code
9. quality-gate          → build + pyright + ruff + pytest
10. security-review      → secrets, injections, env vars, clés API
11. pr                   → PR avec refs PRD + plan
12. gh pr merge N --squash → squash merge quand CI vert
```

**Gates dures :**
- Pas de code avant l'étape 4 — le plan doit exister dans `.claude/plans/`
- Pas d'implémentation inline après l'étape 5 — MODE D obligatoire
- Pas de PR avant que les étapes 9 + 10 passent

---

## MODE B — Correction de bug

```
1. systematic-debugging  → 4 phases : cause racine (pas symptôme)
2. tdd-workflow          → test échouant d'abord, puis correction minimale
3. verification          → valider que le fix fonctionne end-to-end
4. quality-gate          → gate complet, zéro régression
5. pr                    → PR + squash merge
```

Ne pas corriger avant le diagnostic de l'étape 1. Corriger les symptômes crée des bugs récurrents.

---

## MODE C — Architecture / Exploration

```
1. agent code-explorer   → tracer chemins d'exécution, couplage, points d'intégration
2. agent architect       → proposition de restructuration ; ADR si décision irréversible
3. plan                  → plan pour les changements approuvés
→ puis MODE A depuis l'étape 5
```

---

## MODE D — Batch autonome AFK

**Prérequis :** Les issues GitHub labellisées `AFK` + `ready-for-agent` doivent exister.
Sinon, exécuter MODE A étapes 1-5 d'abord.

### Graphe de dépendances en premier

Avant de spawner quoi que ce soit, construire le graphe de dépendances depuis les blockers :

```
Issues SANS blocker          → spawner en appels Agent parallèles (un message, N appels)
Issues AVEC blocker          → spawner après complétion des blockers
```

### Dispatch parallèle (obligatoire pour issues indépendantes)

Les issues indépendantes (aucun blocker partagé) DOIVENT être dispatchées dans **un seul message avec plusieurs appels `Agent`**. Ne jamais sérialiser des issues qui peuvent tourner en parallèle.

### Contenu obligatoire du prompt subagent

- Numéro d'issue + titre + critères d'acceptation (copie verbatim depuis GitHub)
- Branche de base (généralement `main` ou branche feature courante)
- Fichiers à toucher (depuis le plan)
- Commande quality gate : `uv run pytest && uv run pyright && uv run ruff check .`

### Exécution par issue (dans chaque subagent)

```
worktree → tdd-workflow → subagent-review → quality-gate → security-review → pr → merge
```

### Récupération de stall

Boucle gelée → `harness-audit` → réduire le scope → rejouer avec critères d'acceptation explicites.

---

## MODE E — Handoff de session

```
strategic-compact skill  → compacter l'état de session pour le prochain agent
```

Exécuter avant que le contexte soit perdu. Ne pas résumer manuellement.

---

## Routing modèle (cost-aware)

| Tâche | Modèle |
|---|---|
| Boilerplate, classification, éditions ciblées | Haiku |
| Implémentation, refactoring, debugging | Sonnet ← défaut |
| Architecture, root-cause, invariants multi-fichiers | Opus |

Escalader seulement quand le tier inférieur échoue avec un gap de raisonnement clair.

---

## Labels GitHub

| Label | Signification |
|---|---|
| `ready-for-agent` | Entièrement spécifié, peut être pris |
| `AFK` | L'agent peut implémenter sans input humain |
| `HITL` | Requiert une décision humaine avant de continuer |
| `in-progress` | Agent en cours de travail |
| `needs-review` | PR ouverte, en attente de revue humaine |

---

## Drapeaux rouges — Arrêter et re-entrer

- Code avant `.claude/plans/` → supprimer le code, re-entrer à l'étape 3
- **Implémenter des issues AFK inline après l'étape 5** → arrêter, entrer en MODE D, spawner des subagents Agent
- **Sérialiser des issues indépendantes** → vérifier le graphe de dépendances ; si pas de blocker, spawner en parallèle
- Sauter `search-first` ("je connais déjà l'API") → le faire quand même
- Sauter `brainstorming` ("feature simple") → même les features simples ont besoin d'approbation design
- Sauter `quality-gate` ("les tests semblent OK en local") → le lancer quand même
- Sauter `security-review` ("pas de secrets dans cette feature") → le lancer quand même
- Sauter `verification` sur un bug fix → toujours valider que le fix fonctionne
- MODE D sans issues GitHub labellisées `AFK` → créer les issues d'abord (MODE A étapes 2-5)
- Implémenter une feature Tier 3+ avant que les collecteurs Phase 2 soient mergés

---

## Contexte projet

- **Repo :** `x230png/chatgptradio` (public)
- **Stack :** Python 3.12, asyncio, aiosqlite, websockets, structlog, uv
- **Spec architecture :** `streaming/DIRECTION.md`
- **gh CLI :** `/home/stream/.local/bin/gh` (authentifié `x230png`)
- **Phase 0+1 :** terminée — tests verts — Phase 2 (audio, journal, collecteurs DSP) en cours
