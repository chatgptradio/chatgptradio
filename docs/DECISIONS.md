# ChatGPT Radio — Index des Décisions

> Toutes les décisions architecturales, avec lien vers l'ADR détaillé.
> Cross-refs : [TASKS.md](TASKS.md) · [DIRECTION.md](../DIRECTION.md)

---

## Décisions actives

| ID | Titre | Statut | ADR |
|----|-------|--------|-----|
| ADR-0001 | GlobalState comme seule source de vérité | VALIDÉ | [adr/0001](adr/0001-global-state-source-of-truth.md) |
| ADR-0002 | Zéro constante hardcodée dans drift/self-model | VALIDÉ | [adr/0002](adr/0002-no-hardcoded-constants.md) |
| ADR-0003 | SQLite WAL — une connexion partagée | VALIDÉ | [adr/0003-sqlite-wal.md](adr/0003-sqlite-wal.md) |
| ADR-0004 | Pas de LangGraph — asyncio pur | VALIDÉ | [adr/0004](adr/0004-no-langgraph.md) |
| ADR-0005 | Connexion DB unique partagée — pas d'écriture directe depuis collecteurs | VALIDÉ | [adr/0005](adr/0005-single-db-connection.md) |
| ADR-0006 | fal.ai Stable Audio 2.5 — endpoints et paramètres canoniques | VALIDÉ | [adr/0006](adr/0006-fal-stable-audio.md) |

---

## Décisions rejetées

| Décision | Raison |
|----------|--------|
| LangGraph pour orchestration | Surcharge inutile — asyncio pur suffit (ADR-0004) |
| `anthropic` SDK pour journal | OpenAI exclusivement (ADR-0006) |
| `STABILITY_API_KEY` | Remplacé par `FAL_API_KEY` pour fal.ai |
| `random.random()` dans drift | Viole NO FAKE — PE réels uniquement (ADR-0002) |
| `phase_nuit`, `lunar_phase`, `is_weekend` | Rythme humain externe — entité sans horloge biologique |
| `guidance_scale > 1.5` (Stable Audio) | Artifacts audio — max opérationnel 1.2 |
| `num_inference_steps > 8` (audio-to-audio) | API fal.ai rejette avec 422 |
