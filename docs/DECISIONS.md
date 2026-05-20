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

## Décisions 2026-05-20 — Génération audio intelligente

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Alignement territoire drift ↔ music_prompt | Aligner music_prompt sur les 7 territoires réels de drift | Laisser les mismatch, ajouter un mapping | NO FAKE — music_prompt doit refléter l'état réel |
| Sélection référence audio | Scoring state-aware hybride (territoire+BPM+mood cosine) | Aléatoire ou FIFO | Chaque dérivation doit être acoustiquement cohérente avec l'état |
| librosa | Dépendance optionnelle `[dependency-groups] scripts` | Runtime obligatoire | Évite l'overhead pour le stream ; utilisé seulement par `index_references.py` |
| wonder / melancholy / urgency | Champs dérivés GlobalState calculés depuis signaux existants | Nouveaux collecteurs dédiés | Aucune nouvelle source de données requise ; NO FAKE respecté |
| Expansion territoire 7→15 | 8 nouveaux territoires utilisant wonder/melancholy/urgency | Rester à 7 | Couverture émotionnelle insuffisante — 7 ne couvrait pas l'état sombre/contemplatif/urgent |
| `strength` audio-to-audio | `clamp(0.3 + drift_velocity*0.4 + crisis_level*0.3, 0.3, 0.9)` | Constante 0.65 | NO HARDCODE — variance forcée non justifiée par l'état |
| `guidance_scale` audio-to-audio | `clamp(1.0 + source_divergence*0.2, 1.0, 1.2)` | Absent (omis) | Paramètre requis ; piloté par divergence de source |
| Override crise genre → glitch | Supprimé | Conserver le override `crisis_level > 0.5 → glitch ambient` | Territoire `noise` gère ça nativement via drift ; override était un NO FAKE |

---

## Décisions rejetées

| Décision | Raison |
|----------|--------|
| LangGraph pour orchestration | Surcharge inutile — asyncio pur suffit (ADR-0004) |
| Third-party LLM SDK for journal | OpenAI exclusively (ADR-0006) |
| `STABILITY_API_KEY` | Remplacé par `FAL_API_KEY` pour fal.ai |
| `random.random()` dans drift | Viole NO FAKE — PE réels uniquement (ADR-0002) |
| `phase_nuit`, `lunar_phase`, `is_weekend` | Rythme humain externe — entité sans horloge biologique |
| `guidance_scale > 1.5` (Stable Audio) | Artifacts audio — max opérationnel 1.2 |
| `num_inference_steps > 8` (audio-to-audio) | API fal.ai rejette avec 422 |
