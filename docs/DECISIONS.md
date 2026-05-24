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
| ADR-0007 | Couche de synthèse émotionnelle (_synthesize_emotions) | VALIDÉ | [adr/0007](adr/0007-emotion-synthesis.md) |

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

## Décisions 2026-05-21 — Fixes stream production

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| FFmpeg x11grab thread_queue_size | 512 (vs défaut 8) | Augmenter bufsize vidéo | Queue de 8 frames remplie au démarrage → x11grab bloque → FFmpeg ne reçoit plus de vidéo → seul l'audio (192 Kbps) atteint RTMP. Cause racine découverte via `ffmpeg_stderr` logs. |
| FFmpeg CBR enforcement | `nal-hrd=cbr:force-cfr=1` | `-minrate/-maxrate` seuls | libx264 sans filler NAL units n'atteint pas le CBR sur contenu statique — 200–500 Kbps malgré `-minrate 2500k`. Force-cfr=1 garantit les filler NAL. |
| Bloom / EffectComposer | Suppression complète | Réduction résolution | SwiftShader n'accélère pas les passes GPU — chaque pass = 1 render complet CPU. 4–5 passes/frame = charge ×4. `renderer.render()` direct = 1 passe. |
| RAF throttle visualizer | 10fps | Garder 30fps (PR #141) | 30fps injustifiable sans GPU. 10fps suffit pour perception fluide des données GlobalState. Combiné bloom off → Chromium ~90% CPU stable. |
| ChaosMode géométrie | 3 000 particules / 1 000 étoiles | 15 000 / 5 000 | Réduction proportionnelle pour SwiftShader. L'esthétique est préservée ; la charge CPU non. |
| Modes Three.js | 4 modes | 6 modes | Globe (OrbitControls + shaders sphère) et Nebula (bruit volumétrique) trop coûteux sur SwiftShader. 4 modes confirmés sans bloom fonctionnent à ~90% CPU. |
| Upgrade VPS | CX33 (4 vCPU / 8 GB) | Rester CX23 (2 vCPU) | 2 vCPU insuffisants pour Chromium SwiftShader + Python asyncio + FFmpeg simultanément. Load avg montait à 1.8–2.1 sous charge normale. |

---

## Décisions 2026-05-23 — Hotfixes production

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| `viewers` via YouTube API | `videos.list?part=liveStreamingDetails`, cache 120 s | pytchat (pas d'attribut viewer_count) | pytchat expose uniquement les messages chat ; l'API coûte 1 unité/req — 720 req/jour sur 120 s |
| `system_metrics` activation | `COLLECTOR_META` + entrée `config.yaml` | Laisser le décorateur `@node` seul | `_discover_collectors()` filtre sur `COLLECTOR_META` ; le `@node` seul ne suffit pas |
| `!vibe` suppression | Supprimé | Conserver en doublon de `!request` | Identique fonctionnellement à `!request` ; confondait les viewers |
| `!song` suppression | Supprimé | Log only | Nom de piste déjà visible sur le HUD — commande redondante |
| Cooldowns commandes chat | Globaux par type (`!mood` 30 s, `!replay` 120 s) | Per-user tracking | Pas de système d'authentification viewer ; global suffit pour l'anti-spam |
| SYNAPSE bloom | Alpha réduit 0.9→0.45, power 1.5→2.2, node size 0.4–0.7, scale max 1.0 | Désactiver la scène | Scène lisible requise ; réduction alpha suffit sans changer l'esthétique |
| pytchat channel ID bypass | Monkey-patch `ptutil.get_channelid` → lambda env | Patch User-Agent / `httpx.follow_redirects` | YouTube retourne JSON hex-encodé aux scrapers mobiles ; `YOUTUBE_CHANNEL_ID` est déjà connu |

---

## Décisions 2026-05-23 — Optimisation coût + stabilité ops

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| `total_seconds` text-to-audio | 45s | Garder 47s | Réduction coût fal.ai (~4%) ; la différence perceptive est nulle ; audio-to-audio garde la durée de la référence (cohérence musicale prioritaire) |
| `find_reusable` max_play_count | 999 (illimité) | Garder 10 | 94 clips en bibliothèque, tous à play_count ≥ 10 → find_reusable() retournait None systématiquement → génération inutile à chaque itération |
| `find_reusable` cooldown_s | 1800s (30 min) | 300s (5 min) | Avec 94 clips × 45s = ~70 min de contenu, un cooldown 5 min créait des répétitions fréquentes ; 30 min = ~38 clips en rotation active, les 56 autres toujours disponibles |
| Script restart | `restart.sh` standalone (kill ordonné + vérification) | Dépendre uniquement de systemd restart | systemd `Restart=always` ne tue pas les FFmpeg orphelins ni ne libère les ports → double-instances et streams zombies |
| Watchdog | `watchdog.sh` 5 checks | Garder `check_stream.sh` (1 check systemd) | check_stream.sh ne détecte pas : FFmpeg mort, Chromium crashé, WebSocket KO — visuels gelés passaient inaperçus |
| `KillMode` systemd | `control-group` | Défaut (`control-group` déjà le défaut, mais explicite) + `TimeoutStopSec=15` | FFmpeg enfants orphelins survivaient à l'arrêt du service ; le rendre explicite + ExecStartPre kill FFmpeg garantit un état propre |

---

## Décisions 2026-05-23 — Pipeline A2A + drift PE + bibliothèque

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| `find_reference()` play_count | `AND play_count = 0` — une seule utilisation par référence humaine | Cooldown ou utilisation illimitée | Réutilisations multiples = A2A-sur-A2A → bibliothèque remplie de clips soniquement identiques (confirmé : Metroid Prime 2 utilisé 6×, Metroid Fusion 5×) |
| `find_reference()` source restreint | `WHERE source = 'reference'` uniquement | Inclure `fal_derived/generated` à `play_count ≥ 1` | A2A-sur-A2A crée une cascade exponentielle de copies dégénérées — l'A2A ne doit dériver que d'enregistrements humains originaux |
| Déduplication bibliothèque | Suppression physique (91 clips, MFCC cosine ≥ 0.88) via script `dedup_clips.py` | Conservation avec flag ou rotation naturelle | 91/93 clips étaient soniquement identiques (similarity ≥ 0.88) — conserver = bibliothèque trompeuse + rotation perçue comme répétitive |
| `find_reusable()` cooldown | 36 000 s (10 h) | 1 800 s (30 min) | 30 min + 34 clips = même clip revient toutes les ~25 min ; 10 h = diversité maximale, génération fraîche dès que le stock est consommé |
| Bug drift PE — correction | `update_self_model()` pour 8 champs dérivés dans `compute_derived()` | Lire `state.excitement` directement dans `drift.py` | Maintient le pipeline PE unifié (ADR-0001) ; les émotions participent aux mises à jour Hebbian des poids ; la correction dans `drift.py` aurait cassé le flux self-model |
| `!mood` réponse | GPT-4o-mini in-character (max 12 mots, données réelles) avec fallback mécanique | Chaîne mécanique `"dominant (σ)"` uniquement | La commande chat représente la personnalité de l'entité aux viewers — une réponse mécanique est informatiquement exacte mais entitativement vide |
| `SCENE_CYCLE` live | `["neural","synapse","chaos","globe"]` — kinect retiré | Garder kinect dans la rotation | KinectMode jugé instable/expérimental ; 4 modes stables suffisent ; kinect conservé dans le code pour dev |
| Test `_mfcc_dist` défaut | Fingerprints MFCC orthogonaux explicites dans le test | Garder `_mfcc_dist = 1.0` par défaut | La valeur `1.0` par défaut causait un skip A2A systématique sur les nouvelles références sans analyse librosa — faux positif silencieux |

---

## Décisions 2026-05-24 — System prompts, transitions, watchdog

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| System prompts LLM contextuels | 3–5 variantes par module (`journal.py`, `chat_commands.py`, `track_namer.py`) sélectionnées par `crisis_level` et `drift_territory` | Prompt unique statique | Un seul prompt produit une voix uniforme quel que soit l'état — l'entité en crise doit sonner différemment de l'entité contemplative ; NO FAKE s'applique aussi à la personnalité textuelle |
| Silence inter-clip — fallback path | Flush `_pending_tail` via DSP vers FFmpeg pendant le chargement du clip suivant | Silence (ancien comportement) ou crossfade forcé | La queue vide → chargement = 0.3–3 s de silence audible ; le tail (3 s finales) est déjà processé et disponible — le jouer élimine le gap sans coût additionnel |
| `!replay` recherche display_name | Espaces → wildcards : `%echo%frontier%chasing%shadows%` | LIKE exact `%echo frontier chasing shadows%` | Les titres générés par GPT-4o-mini incluent un séparateur ` - ` entre artiste et titre (`"Echo Frontier - Chasing Shadows"`) — la chaîne sans séparateur ne matchait jamais |
| `!replay` display_name en queue | Requête DB au moment du `pop_all()` pour récupérer le vrai nom | `""` (vide, ancien comportement) | Display_name vide → HUD affiche rien pendant la lecture du replay — brise la cohérence visuelle |
| Watchdog crash-loop | Compteur de skips consécutifs persisté dans `/tmp` ; force checks après 3 skips (6 min) | Grace period 60 s inconditionnelle | Si systemd redémarre le service toutes les 30 s (OOM loop), le watchdog skipait indéfiniment — la boucle de crash passait inaperçue des heures |
| Watchdog zombie cleanup | `pgrep pytest` + `pgrep bash.*shell-snapshot` tués à chaque run | Nettoyage manuel | Les sessions Claude Code accumulent des processus pytest et des shell-snapshots qui survivent à la session — 20 processus × 50 MB = 1 GB RAM → OOM stream |

---

## Décisions 2026-05-24 — Reverb + cooldown replays + total_seconds

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Reverb `wet_level` max | `clamp(cr*0.25 + anxiety*0.1, 0, 0.35)` | `clamp(cr*0.4 + anxiety*0.15, 0, 0.7)` | pedalboard Reverb a `dry_level=0.4` par défaut — avec `wet=0.7`, reverb 1.75× plus forte que le signal dry ; le Limiter compensait en écrasant le dry → reverb suramplifié perceptible |
| Reverb `dry_level` explicite | `dry_level=0.7` dans le constructeur | Laisser le défaut 0.4 | Comportement implicite dangereux : `wet_level` seul insuffisant pour caractériser le mix reverb/dry ; explicite = prédictible |
| Reverb throw transition | `wet=0.5, dry=0.5` | `wet=0.7, dry=0.3` | Transition DJ intentionnellement dramatique mais 0.3 dry effaçait trop le signal source ; 0.5/0.5 = effet perceptible sans écraser le contenu |
| Bypass cooldown 10h | Supprimé du main loop | `find_reusable(cooldown_s=0)` avant génération | Le bypass s'exécutait à chaque itération dès que tous les clips dépassaient 10h → play_count montait à 17+ sur les mêmes clips ; génération fresh = comportement voulu quand le stock est consommé |
| `total_seconds` text-to-audio | 45s | 180s (régressé) | Code avait 180s au lieu de 45s — clips de 3 minutes générés → coût fal.ai ×4 → solde épuisé ; LUFS intégré sur 180s peu représentatif → égalisation perceptivement incohérente entre clips |
| `total_seconds` audio-to-audio | 45s fixe | `min(max(ref_secs, 30), 190)` | Références game soundtrack = 3-5 min → A2A générait jusqu'à 190s de contenu ; 45s fixe = coût prévisible, cohérent avec text-to-audio |

---

## Décisions 2026-05-24 — Égalisation audio (mixage constant)

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| `Compressor` + `Gain` hors de `_build_chain` | Déplacés dans `_build_level_chain()` appliqué une seule fois sur le clip complet + LUFS re-normalisé | Garder dans la chaîne temps-réel par chunk | `Compressor(threshold=-18dB, ratio=4.0)` sans makeup réduisait le niveau de 5–9 dB selon les dynamiques du clip. La LUFS pre-DSP était annulée par la compression variable → clips à des volumes très différents. Isoler dans un pré-bake permet de re-normaliser après compression. |
| Double passe LUFS (pre-DSP + post-level-chain) | `normalize → level_chain → normalize` à l'ouverture du clip | LUFS uniquement pre-DSP | La normalisation pre-DSP garantit un point d'entrée cohérent ; la normalisation post-level-chain garantit un niveau de sortie cohérent indépendamment de l'état (musical_tension, audience_energy). La chaîne temps-réel (Reverb, HighShelf, Chorus, LadderFilter, Limiter) ne change le niveau moyen que de ±2 dB → acceptable. |
| Resample vers `_SR=44100` à la lecture | `AudioFile.resampled_to(_SR)` dans `_read_and_stretch` | Lire au taux natif du fichier | Si fal.ai ou ffmpeg retourne un fichier à 48000 Hz, pyrubberband recevait 48000 Hz traité comme 44100 Hz → vitesse et pitch incorrects de +8,8%. Resample défensif = no-op si déjà 44100 Hz. |
| `-ar 44100` dans `_wav_to_mp3` | Forcer la sortie MP3 à 44100 Hz | Laisser ffmpeg préserver le taux source | Garantit que les clips stockés sont toujours à 44100 Hz. Le `resampled_to` dans `_read_and_stretch` reste comme filet de sécurité. |
| `fill_ratio` dans `_analyze_clip_async` | `(trim_end_samp - trim_start_samp) / len(y)` | Non implémenté (toujours 1.0 par défaut) | `find_reference()` pénalisait les clips avec `fill_ratio < 0.7` mais la valeur n'était jamais calculée → pénalité morte. Le calcul via les indices de trim est cohérent avec librosa. |
| `top_db=60` dans `index_references.py` | 60 (identique à `_analyze_clip_async`) | 30 (valeur précédente) | `top_db=30` trimmait agressivement les intros/outros douces des références (~30 dB sous le pic). Incohérence avec les clips générés (top_db=60 implicite). Harmonisé à 60 → même comportement sur tous les types de fichiers. |

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
