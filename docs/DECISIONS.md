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

## Décisions 2026-05-24 — Audit pipeline robustesse (PRs #202 #205 #206)

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| `total_seconds` text-to-audio | 180s (override décision précédente 45s) | 45s | Décision explicite : clips longs = moins d'appels fal.ai/h, expérience musicale plus continue. La décision 45s avait été prise suite à l'épuisement du solde fal.ai — situation résolue. |
| `total_seconds` audio-to-audio | `min(ref_duration, 180)` via ffprobe | 45s fixe | La durée de la référence est la bonne métrique : A2A doit reproduire la structure temporelle de la source. Cap 180s = limite API. |
| `pw()` dans `drift.py` | `math.tanh(pe / max(vol, 0.01))` — borné à `[-1, 1]` | Division brute `pe / vol` — non bornée | Avec `vol=0.001`, `pw=10000` → `drift_momentum["bpm"] = 3333` → BPM rate-limit absorbait le pic mais le momentum persistait 100+ cycles. `tanh` borne à ±1 sans changer le signe ni la direction. |
| Reverb `wet_level` max | 0.20 (était 0.35) | Garder 0.35 | Les clips audio-to-audio ont la réverbération de la piste référence baked-in. Ajouter wet=0.35 créait une double-reverb audible. Max 0.20 = effet présent sans surcharger. |
| Reverb `room_size` max | 0.60 (était 1.0) | Garder 1.0 | `room_size=1.0` génère une queue de réverbération de plusieurs secondes. Sur des chunks de 93ms, la queue s'accumule sur toute la durée du clip → reverb perceptivement dominante. |
| Reverb `dry_level` | 0.85 (était 0.70) | Garder 0.70 | `dry_level=0.70` atténuait trop le signal sec. Avec `wet=0.35 + dry=0.70`, la reverb était proportionnellement plus forte que le source. 0.85 rend le source clairement audible. |
| Delay feedback/mix max | 0.35/0.25 (était 0.60/0.40) | Garder 0.60/0.40 | Avec `source_divergence=1.0`, 3 échos successifs à 60% = trail d'écho de 1.1s clairement audible, amplifié par la reverb en amont. |
| Journal intervalle | 15 min défaut, 3 min crise, 5 min min | 5 min défaut, 90s crise, 60s min | La fingerprint (`crisis_level:.1f`, `world_temperature:.1f`) changeait à presque chaque cycle → trigger `state_changed` se déclenchait toutes les 60s en pratique → ~60 appels GPT/h au lieu de 12. |
| Track namer system prompts | 7 prompts distincts avec références esthétiques (Kranky, Warp, Blue Note…) + `temperature=1.1` | 5 prompts génériques avec adjectifs seuls | Mêmes adjectifs → GPT-4o-mini converge vers le même espace lexical. Les références esthétiques (labels, artistes réels) contraignent le style de nommage à des vocabulaires distincts par territoire. |
| Audio feedback loop | `audio_bpm_delta`/`audio_key_match`/`audio_energy_level` passent dans `update_self_model()` | Laisser ces champs dans GlobalState sans les alimenter dans le self-model | Ces champs étaient émis par `_maybe_emit_audio_feedback()` et atteignaient GlobalState, mais `drift.py` ne les lisait jamais — boucle feedback morte. Brancher dans `compute_derived()` ferme la boucle sans modifier l'architecture. |
| `time_in_territory_h` dans drift | Signal de fatigue `(h/10 - 0.3).clamp(0, 0.5) * 0.1` ajouté à `bpm_force` | Ignorer (situation actuelle) | Un territoire actif 8h produit la même dérive qu'un territoire actif 1h — le temps musical n'existait pas. La contribution max (+0.05 sur `bpm_force`) est délibérément faible pour ne pas dominer les signaux PE réels. |
| Nitter RSS health tracking | `_last_ok_idx` module-level + rotation + `source_health["nitter_rss"]` | Ordre fixe + pas de tracking | Instances Nitter éphémères → retenter en premier celle qui a fonctionné = réduction des timeouts. `source_health` permet au monitoring de détecter une panne prolongée. |
| arXiv signal | Delta normalisé 7j : `(today - avg) / max(avg, 1)` | Count brut | Count brut = 0 pendant ~23h/24 → `arxiv_papers_today` PE plat la plupart du temps → `curiosity` non alimentée sauf 1h/jour. Delta normalisé = signal continu centré sur 0, positif quand au-dessus de la moyenne. |

---

## Décisions 2026-05-24 — DSP & Transitions (commits ef0a03a · dbf4f55 · db59462)

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Crossfade durée | Adaptatif 8-12s par territoire, equal-power (`sqrt(t)`) | 5s fixe | 5s fixe était trop court sur ambient/drone (coupure perceptible) et trop long sur industrial/crisis. Equal-power évite la baisse de niveau au centre du fondu. |
| Crossfade par territoire | ambient/drone 10s · jazz/electronic 6s · industrial 3s · crisis 2s | Durée unique pour tous | La nature musicale des territoires dicte la durée de transition ; appliquer la même durée à une intro de drone et à une rupture industrielle produit des transitions incorrectes. |
| Transition T1 — EQ bass cut | Supprimée | Conserver | Le boost/cut basses sur la fenêtre de crossfade créait une discontinuité spectrale audible en début et fin de fondu. L'effet sonique ne justifiait pas l'artefact. |
| Transition T3 — reverb throw | Supprimée | Conserver | Le reverb throw s'additionnait à la chaîne DSP principale (déjà reverb state-driven) → double-reverb et accumulation des queues sur les chunks 93ms → transitions boueuses. |
| `tail_reserve` calcul | Basé sur les samples restants dans le buffer de sortie | Durée fixe estimée | Calcul précédent sous-estimait la réserve disponible → le tail était tronqué avant la fin de la crossfade, causant un micro-silence en bout de clip. |
| Silence gap — fallback path | `_pending_tail` flushé via DSP vers FFmpeg pendant le chargement du clip suivant | Silence (comportement précédent) | Dans le path non-prefetch, la queue se vide 0.3–3s avant que le clip suivant soit chargé → gap silence audible. Le tail (3s finales déjà traitées) est disponible et suffisant pour couvrir la latence de chargement. |

---

## Décisions 2026-05-24 — Ops & Robustesse (commit ed9859c)

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Purge DB au démarrage | `DELETE` snapshots > 7j + history > 30j à chaque `run_audio_queue()` | Aucune purge au démarrage | Après plusieurs semaines de fonctionnement, la DB atteignait 800 MB+. La purge au démarrage garantit un état propre sans accumuler indéfiniment les cycles précédents. |
| Purge périodique toutes les 6h | Tâche asyncio planifiée dans `run_audio_queue()` | Purge uniquement au démarrage | Un stream actif 72h sans redémarrage accumule ~200 MB de snapshots sans purge périodique. 6h = compromis entre fréquence et overhead I/O. |
| Rétention snapshots | 7 jours | 30 jours (précédent) | 30j de snapshots GlobalState (toutes les 30s) = ~86 400 lignes = ~60 MB/mois avec aucune valeur analytique au-delà de 7j. |
| Rétention history | 30 jours | 90 jours (précédent) | 90j d'historique drift/territory non consulté depuis le lancement. 30j couvre une période de changement significative tout en maintenant la DB sous 50 MB. |
| Watchdog OOM restart | Redémarrage du service si RSS Python > 150 MB | Seuil mémoire absent (précédent) | Sans seuil, un leak mémoire progressif (librosa, asyncio tasks non collectées) déclenchait l'OOM killer du noyau → restart brutal sans cleanup des FFmpeg enfants. Le redémarrage contrôlé laisse le temps au cleanup. |

---

## Décisions 2026-05-25 — Optimisation coûts fal.ai

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| `total_seconds` text-to-audio | 180s (conservé) | 90s | 180s × moins d'appels/h (reuse amélioré) = coût total comparable ou inférieur à 90s × appels fréquents. Clips longs = meilleure continuité musicale ; chaque clip généré est plus "rentable" en temps de lecture. Reuse cooldown réduit à 2h pour maximiser les reprises. |
| `num_inference_steps` | 6 par défaut / 8 si `crisis_level > 0.6` | 8 fixe | 8 steps à chaque clip alors que la qualité perceptive de la musique de fond ne justifie pas le surcoût. La crise est le seul contexte où la qualité maximale est auditivement pertinente. |
| Crisis cache au démarrage | Conditionnel : uniquement si `crisis_level > 0.5` | Inconditionnelle | 3 appels API à chaque redémarrage même quand `crisis_level=0` — coût pur sans valeur. |
| Crisis cache rebuild cooldown | 1 800s (30 min) entre deux rebuilds | Aucun cooldown (précédent) | Si `crisis_level` monte de 0 à 0.9 progressivement (par paliers de 0.15 toutes les 5s), le rebuild se déclenchait 5× = 15 appels API en 35s. Le cooldown 30 min garantit un seul rebuild par épisode de crise. |
| `find_reusable` cooldown | 7 200s (2h) | 36 000s (10h, précédent) | 10h de cooldown forçait la génération dès que le stock de clips était consommé (~60 clips × 180s = 3h). 2h = les clips reviennent en rotation après 2h, réduisant fortement le taux de génération. Diversité perceptive préservée sur une session d'écoute standard. |
| `_pending_ref` bypass reuse | Supprimé | Bypass actif (précédent) | Quand des références non traitées existaient, `find_reusable()` était systématiquement bypassé → génération forcée à chaque itération au lieu de réutiliser les clips existants. Les références sont désormais converties via A2A lors du passage normal en génération (quand le reuse échoue), sans bloquer la bibliothèque. |

---

## Décisions 2026-05-25 — Fixes production

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Chromium `nice` value | 5 | 10 (précédent) | Sur une machine 2 vCPU, nice=10 donnait au process GPU Chromium une priorité trop faible — le scheduler le préemptait systématiquement pendant les séquences de charge FFmpeg. Chromium utilisait 170% CPU (85% des 2 cœurs) mais ses timeslices arrivaient trop tard → drops FPS perceptibles sur l'overlay. nice=5 = légère concession à FFmpeg sans starvation. |
| `mark_played` après `index_clip` | Appelé immédiatement après `index_clip()` avant `playback_queue.put()` | Seulement en fin de lecture (précédent) | `index_clip()` initialise `last_played_at=0.0`, ce qui passe toujours le cooldown 2h de `find_reusable()`. Sans `mark_played` immédiat, le clip généré était re-sélectionné 5s plus tard par le poll suivant → même clip joué 2 fois d'affilée. Le chemin de réutilisation appelait déjà `mark_played` au bon moment ; le chemin de génération ne le faisait pas. |

---

## Décisions 2026-05-25 — Diversité track names + journal

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Track namer : style constraint rotatif | 12 `_STYLE_HINTS` (haiku, geographic, biologique, cinématique, numérique, found-text, temporel, architectural, chimique, linguistique, cosmologique, taxonomique) — sélectionné par MD5(`current_track_name + territory`) | Prompt statique ou random.choice | MD5 garantit la rotation déterministe à chaque nouveau clip (le hash change dès que `current_track_name` change) sans état interne ni appel à random |
| Track namer : contexte user message enrichi | Ajout de `urgency`, `anomaly_score`, style hint, et "do not reuse words from previous track" dans le message user | Laisser le message court (territory/BPM/key/emotions) | Quand territory/BPM/key/emotions ne bougent pas, GPT-4o-mini reçoit un contexte identique → espace lexical convergent ; le style hint force un vocabulaire orthogonal à chaque clip |
| Journal : 6 system prompts (était 3) | Ajout de `_SYSTEM_TRANSITION` (drift_velocity > 0.5), `_SYSTEM_EVENT` (event_label + intensity > 0.5), `_SYSTEM_URGENCY` (urgency > 0.7) | Garder 3 prompts | 3 prompts ne couvraient pas les états intermédiaires (montée d'urgence sans crise, transition de territoire, événement nommé) — voix uniforme quel que soit l'état |
| Journal : anti-répétition ouvertures | Instruction explicite dans chaque system prompt : interdit "I notice"/"I observe", varie structure syntaxique (nombre, signal name, clause subordonnée) | Laisser GPT choisir librement | GPT-4o-mini avec temp par défaut converge vers "I notice X is Y" à 70%+ des entrées ; la contrainte négative suffit à forcer la variance sans changer le contenu |
| Journal : rotation angle d'observation | 7 `_OBSERVATION_ANGLES` (deltas, émotion tracée, prediction errors, persistance temporelle, musique/territoire, signaux externes, anomalie) — MD5(`journal_text + drift_bpm`) | Laisser le modèle choisir l'angle | Sans contrainte, le modèle observe systématiquement dominant_emotion + crisis_level — 5 angles sur 7 ne sont jamais couverts |
| `_SYSTEM = _SYSTEM_DEFAULT` alias | Alias backward-compat dans `journal.py` | Mettre à jour le test | Le test `test_system_prompt_is_english` référençait `_SYSTEM` (nom avant refactoring) — l'alias corrige sans casser l'intent du test |

---

## Décisions 2026-05-26 — Correctifs pipeline B1–B17

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| `NodeMeta.produces` type | `str \| list[str]` | Garder `str`, dupliquer les nœuds | 6 collecteurs émettent 2+ champs — un nœud par champ multiplierait les entrées registre sans valeur. La liste est plus honnête vis-à-vis du graphe réel. |
| B10 : `wonder`/`excitement` calendar | Retirer du payload calendar, amplifier via `event_intensity` dans `_synthesize_emotions` et calcul `wonder` | Garder le push calendar, ne pas appeler `compute_derived` après | `compute_derived` est appelé à chaque tick du StateUpdater — il écrase les valeurs poussées avant même un cycle de rendu. La seule façon de persister l'effet calendaire est de le lire depuis `event_intensity` (persisté, lui) au moment de la synthèse. |
| B11 : dead code `!vibe` | Supprimé | Implémenter `!vibe` dans `chat_commands.py` | Aucun `push("vibe", ...)` n'existe nulle part. Le branch était mort depuis la réécriture de chat_commands. Ajouter la commande sans PRD = feature non planifiée. |
| B17 : `stream_bitrate` / `dropped_frames` | Option A : retirer du payload DSP (valeurs restent 0.0 — honnête) | Option B : parser le stderr FFmpeg | Le parsing FFmpeg est correct mais hors scope — il appartient à un ticket moniteur FFmpeg dédié. Laisser des constantes fausses est pire que 0.0 réel. |
| B4 : annotation check | `field_info.annotation in (float, int) or str(field_info.annotation) in ("float", "int")` | Comparaison directe `== float` | Pydantic v2 retourne parfois `"float"` comme string dans l'annotation selon le contexte de résolution du modèle. La double vérification couvre les deux formes. |

---

## Décisions 2026-05-27 — FPS & Robustesse

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Startup VACUUM | `_periodic_purge()` — délai 90s + `wal_checkpoint(TRUNCATE)` avant VACUUM, puis toutes les 6h | VACUUM bloquant au démarrage (précédent) | Après kill -9 répétés, le WAL peut atteindre 7+ GB. VACUUM au démarrage reconstruit toute la DB depuis le WAL avant la première ligne de log → démarrage bloqué indéfiniment. Le délai 90s laisse le stream opérationnel avant toute opération DB lourde. |
| Chromium GPU backend | SwiftShader (`--enable-unsafe-swiftshader --use-gl=swiftshader`) maintenu | EGL + virglrenderer (`--use-gl=egl --enable-gpu-rasterization`) — testé, rejeté | virglrenderer rend via `/dev/dri/renderD128` en bypassant le framebuffer Xvfb. x11grab capture l'arbre X11 du display `:99`, pas le rendu DRI. Résultat : Three.js WebGL context creation échoue sur le display X11 → overlay bloqué sur "connecting...". EGL serait compatible uniquement avec une capture DMA-BUF ou un pipeline sans x11grab. |
| `powerPreference` WebGL | `'high-performance'` | `'low-power'` (précédent) | `'low-power'` permet au scheduler de downclockler le process GPU sur charge intermittente. Sur SwiftShader (100% CPU), downclock = chutes FPS. `'high-performance'` maintient la clock et évite les drops sur les transitions de scène. |
| `renderer.debug.checkShaderErrors` | `false` | `true` (défaut Three.js) | La validation GLSL runtime est utile en dev, inutile en prod — les shaders sont stables. Désactiver économise ~5% CPU sur les recompilations. |
| `-vf fps=30` FFmpeg | Supprimé | Conservé (précédent) | x11grab capture déjà à `-framerate 30`. Le filtre `-vf fps=30` appliqué en aval recalculait les timestamps inutilement. `force-cfr=1` dans `-x264opts` garantit le CFR côté encodeur. Double filtrage = travail redondant sans bénéfice. |
| WebSocket broadcast fps | 10fps | 4fps (précédent) | À 4fps (250ms entre updates), les lerps Three.js interpolaient sur des intervalles trop longs → saccades visibles sur les transitions d'émotions. À 10fps (100ms) les animations suivent les signaux sans artefact. Coût CPU Python négligeable (JSON GlobalState ~2KB). |

---

## Décisions 2026-05-28 — Bot Telegram bidirectionnel

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Architecture bot | Processus séparé (`chatgpt-radio-tg.service`) lisant le WebSocket | Bot intégré dans `main.py` via `asyncio.create_task` | Si `main.py` crashe, le bot intégré crashe aussi — impossible d'alerter sur les pannes. Le processus séparé survit au crash et détecte le DOWN via déconnexion WebSocket. |
| Framework bot | `python-telegram-bot` v20 (PTB) — natif asyncio | `aiogram` / `telebot` | PTB v20 est l'implémentation de référence Telegram pour Python asyncio ; `ApplicationBuilder` + `post_init` = lifecycle clean sans thread séparé. |
| Détection DOWN | Debounce 30s via `time.monotonic()` | `asyncio.sleep(30)` bloquant | `asyncio.sleep` bloquant suspendrait la reconnexion pendant 30s — l'alerte arriverait jusqu'à 60s après la panne. Le timestamp permet de tenter la reconnexion immédiatement tout en respectant le debounce. |
| Backoff reconnexion | Exponentiel 1→2→4→8→16→30s (cap 30s) | Intervalle fixe | Un intervalle fixe court (1s) génère des logs parasites et charge inutilement le processus principal s'il essaie de redémarrer. Le backoff réduit la pression tout en restant réactif à la reconnexion rapide. |
| Allowlist | `filters.Chat(CHAT_ID)` PTB + `_allowlist_filter` silencieux | Pas d'allowlist (bot public) | Le bot contrôle `systemctl restart` — accès à n'importe quel chat_id = vecteur d'attaque. Un seul CHAT_ID, messages inconnus ignorés sans réponse (pas de signal d'existence). |
| `/restart` — injection | `asyncio.create_subprocess_exec("bash", RESTART_SCRIPT, ...)` | `subprocess.run(shell=True, cmd=f"bash {script}")` | `shell=True` avec chemin variable = injection de commande possible. La liste d'args explicite élimine le risque à la source. |
| Source de données commandes | `_state_cache` global mis à jour par le WebSocket | Requêtes directes à `state.db` | SQLite direct = couplage fort au schéma DB interne + contention d'écriture. Le WebSocket expose déjà l'état sérialisé ; le bot est un client de monitoring, pas un composant du pipeline. |

---

## Décisions 2026-05-31 — Optimisation RAM & stabilité FPS

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Throttle `persist_snapshot` | 1 snapshot toutes les 30s (timestamp monotonic dans `StateUpdater`) | Snapshot à chaque signal (précédent) | `persist_snapshot` appelée ~3 800×/h générait 805 MB/jour → DB 5,5 GB en 7j → WAL/checkpoint constant → iowait 5% → swap reads lents → drops de frames. 30s = granularité suffisante pour rejouer l'historique, 32× moins d'I/O disque. |
| Rétention snapshots | 1 jour | 7 jours (précédent) | 7j × 120 snapshots/h × 9 KB = 800 MB de DB à régime (avec le throttle). 1j = 25 MB, la DB tient en page cache sans pression swap. L'historique 7j n'avait aucun usage analytique actif. |
| Rétention signal_history | 7 jours | 30 jours (précédent) | 30j d'historique de signaux représentait ~100 MB additionnel sans usage. 7j couvre une semaine complète de patterns pour d'éventuelles analyses. |
| VACUUM périodique | Supprimé des runs périodiques — uniquement au startup (délai 90s) | VACUUM toutes les 6h sur DB live (précédent) | VACUUM sur 5,5 GB = lecture complète du fichier + écriture d'une copie compactée → sature `sda` pendant 5–10 min → swap reads bloqués → drops de frames toutes les 6h exactement. Avec throttle + rétention 1j, la DB reste <100 MB → VACUUM startup est rapide et sans impact live. |
| Purge périodique intervalle | 1h | 6h (précédent) | Avec 25 MB/j de croissance, purger toutes les 6h = 6 MB delta/purge — opération triviale. 6h n'avait de sens que pour amortir le coût du VACUUM, qui est supprimé. |
| x11grab framerate | 30fps | 40fps (précédent) | 40fps = 33% de frames capturées et encodées inutilement. YouTube recommande 30fps. Sur SwiftShader déjà à 80% CPU, les 10fps supplémentaires préemptaient ffmpeg et Python. Gain : −25% charge encodeur x264. |
| `thread_queue_size` pipe audio | 512 packets | 10 000 000 (précédent) | 10M AVPacket slots = ~80 MB de ring buffer. La profondeur réelle en régime est ≤ 4 packets (PCM à 94% real-time, mux à 90%). 512 = headroom ×128 sans overhead mémoire. |
| `CPUWeight` systemd | 800 (cgroup v2, 8× le poids default=100) | `renice -n -5` (besoin root, non disponible) | Sans root, `renice` ne peut pas aller en négatif (ulimit -e = 0). cgroup v2 `CPUWeight` fonctionne en user service sans privilèges et s'applique au cgroup entier (main.py + ffmpeg enfants). Appliqué en live sans restart via `systemctl set-property`. |
| Chromium GPU nice | +10 au startup (via `restart.sh`) | nice -n 5 dans `browser_display.py` (précédent) | SwiftShader à 80% CPU concurrence ffmpeg sur les mêmes cores. nice +10 garantit que ffmpeg (nice 0) gagne les timeslices lors de la contention sans starver Chromium. Persisté dans `restart.sh` pour survivre aux redémarrages. |

---

## Décisions 2026-05-31 — Debug FPS saccades (session 2)

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Fix `NetworkMode.dispose()` | `traverse()` complet sur `_group` + `material.dispose()` sur `_starField` + `bm.geometry.dispose()` immédiat après BoxHelper | Réduire l'intervalle de restart Chromium à 50min | L'enquête ffmpeg log a montré le pattern exact : 30fps stable jusqu'à 57min, effondrement à partir de 67min sur 2 runs. Délai de 10min correspond à la latence GC V8 après la 3ème visite "network" (55-60min). Root cause = fuite WebGL, pas SwiftShader en général — corriger la fuite est propre et permanent. |
| `bm.geometry.dispose()` immédiat | Dispose juste après `new THREE.BoxHelper(bm, ...)` | Garder une référence `this._bm` pour dispose plus tard | Three.js `BoxHelper` copie les sommets AABB dans sa propre géométrie `LineSegments` au moment de la construction — `bm.geometry` n'est plus référencé ensuite. Dispose immédiat = zéro leak sans stocker une référence inutile. |
| Watchdog check port | `ss -tnl \| grep ':8765'` | `nc -z localhost 8765` (précédent) | `nc -z` établit une vraie connexion TCP. Le serveur WebSocket reçoit une connexion sans handshake HTTP valide → lève `InvalidMessage` loggé comme erreur toutes les 2min. `ss` interroge le kernel sans connexion réseau = aucune erreur générée. |
| Chromium restart interval | Maintenu à 3h | 50min (envisagé) | Avec le fix dispose(), la dégradation FPS n'est plus causée par SwiftShader/V8 heap. Réduire à 50min aurait introduit des coupures overlay inutiles toutes les 50min. Monitoring à faire sur la prochaine session de 4h+ pour confirmer la stabilité. |
| Renice GPU après restart périodique | `os.setpriority(PRIO_PROCESS, int(pid), 10)` dans `browser_display.py` après chaque restart | `restart.sh` uniquement (précédent) | `restart.sh` renicait le GPU process au démarrage initial mais pas après les restarts périodiques. Après chaque restart Chromium (toutes les 3h), le nouveau GPU process tournait à priorité normale, concurrençant ffmpeg. Fix dans `browser_display.py` couvre tous les cas. |

---

## Décisions 2026-05-31 — Debug FPS (session 2 — cause racine NetworkMode)

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| Fix fps dégradé | `NetworkMode.dispose()` — `traverse()` + material dispose | Réduire `_CHROMIUM_RESTART_INTERVAL` 3h→50min | Le log ffmpeg confirme que les deux runs (avant et après les fixes DB) montrent exactement le même onset à ~67min. La cause est dans le JS de l'overlay, pas dans Chromium lui-même. Réduire le restart masquerait le symptôme sans corriger la fuite mémoire WebGL. |
| Périmètre du fix dispose | `_group.traverse()` pour disposer tous les enfants (boxHelper + pointCloud + linesMesh) + `_starField.material.dispose()` + `bm.geometry.dispose()` après BoxHelper | Ne corriger que le material starField | Laisser les deux ShaderMaterials (`pMat`, `lMat`) non disposés laisse des programmes GLSL compilés en heap SwiftShader. Sans `traverse()`, la fuite principale persist. |
| `_CHROMIUM_RESTART_INTERVAL` | Maintenu à 3h | Réduit à 50min | Avec le dispose correctement implémenté, pas d'accumulation inter-visites. 3h est un filet de sécurité pour d'éventuelles fuites non identifiées dans les autres modes (ChaosMode, GlobeMode, LogoMode semblent corrects à l'audit). |
| watchdog health-check WS | `ss -tnl \| grep ':8765 '` (pas de connexion TCP) | `nc -z localhost 8765` (précédent) | `nc -z` ouvre une connexion TCP sans handshake WebSocket → la librairie `websockets` logue `InvalidMessage` à chaque check (toutes les 2min). `ss` vérifie si le port est en écoute sans aucune connexion. |
| GPU renice restart périodique | `os.setpriority(PRIO_PROCESS, pid, 10)` après chaque restart Chromium interne | Uniquement dans `restart.sh` (précédent) | Le restart périodique `browser_display.py` spawne un nouveau GPU process non renicé → compète avec ffmpeg à priorité égale entre deux restarts service complets. |

---

## Décisions 2026-06-01 — Debug FPS persistant (session 3)

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| **Fréquence render loop overlay** | `_FRAME_MS = 1000/30` (30fps) | 40fps (précédent) | x11grab capture à 30fps (`-framerate 30` dans ffmpeg). Avec 40fps JS, dès que SwiftShader dépasse 25ms/frame, le buffer IPC se sature et x11grab manque ses créneaux. Synchro 30fps/30fps élimine ce beat-frequency effect. |
| **Suppression WAL/SHM après VACUUM INTO** | Supprimer `state.db-wal` et `state.db-shm` après `os.replace(compact, db)` | Garder les fichiers WAL existants | Après VACUUM INTO + os.replace, le nouveau `state.db` est un fichier frais sans WAL. L'ancien `-wal` référence les pages de l'ancien DB (361MB) → incompatible avec le nouveau (68MB) → `database disk image is malformed` au prochain démarrage. |
| **Suppression du `.compact` stale** | `os.remove(tmp)` avant VACUUM INTO si le fichier existe | Laisser VACUUM INTO échouer avec "table already exists" | Si un VACUUM INTO précédent a échoué après la création du fichier `.compact` mais avant `os.replace`, le fichier reste. VACUUM INTO vers un fichier non vide provoque `OperationalError: table X already exists`. Nettoyage préventif. |
| **Check fps dans watchdog** | Restart si fps < 15 pendant 3 checks consécutifs (6min) | Watchdog uniquement basé sur la liveness des processus | Les processus restaient vivants à 7fps pendant des heures. Un check fps détecte la dégradation silencieuse que les checks liveness manquent. Seuil 15fps et délai 6min pour éviter les faux positifs pendant le démarrage ou les transitions. |

---

## Décisions 2026-06-03 — Debug FPS persistant (session 4)

| Décision | Choix retenu | Alternative rejetée | Raison |
|----------|-------------|---------------------|--------|
| **`gl_PointSize` clampé dans tous les shaders** | `clamp(sz * K / -mv.z, min, max)` dans ChaosMode (4→64px), NetworkMode (4→80px), LogoMode (1→48px) | Pas de clamp (précédent) | Sans clamp, un nœud proche de la caméra → gl_PointSize = sz × 1200 / 0.5 = 2400px. SwiftShader remplit π×1200² = 4.5M pixels par point en AdditiveBlending → fill rate ×5 la surface de l'écran. Sur 2 vCPU à 2200MHz, render time dépasse 125ms/frame → fps=8. ChaosMode et LogoMode avaient aussi des shaders non bornés découverts lors de l'audit. |
| **Chromium restart interval 3h → 55min** | `_CHROMIUM_RESTART_INTERVAL = 55 * 60` dans `browser_display.py` | 3h (précédent, aussi 50min envisagé) | Analyse ffmpeg log sur 3 runs consécutifs : fps=30 stable 0-60min, dégradation onset à t=60min exact (drops de 37→528→4475 en 10min). Chromium restart à 3h laissait 2h de fps dégradé. 55min = restart avant le seuil de dégradation, avec 5min de marge. La cause racine du seuil 60min reste non identifiée (accumulation SwiftShader, growth GlobalState via anomaly_score=952, ou les deux). |
| **Watchdog fps : delta frame/time (instantané)** | Calcul `(frame2-frame1)/(time2-time1)` entre deux checks watchdog successifs, stocké dans `/tmp/stream_watchdog_fps_prev` | Lecture du champ `fps=` ffmpeg (EMA) | L'EMA ffmpeg restait à 18-19fps pendant que l'instantané était à 5-8fps : watchdog affichait "OK" pendant 47min de stream dégradé. Le delta entre deux checks watchdog (2min d'intervalle) reflète le fps instantané réel et déclenche le restart quand fps_inst < 15fps pendant 3 checks (6min). |

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

## Décisions 2026-06-04 — Debug FPS persistant (session 5)

### D-2026-06-04-1 : Suppression des `backdrop-filter: blur()` du HUD overlay

**Décision** : Supprimer tous les `backdrop-filter: blur(Xpx)` et `-webkit-backdrop-filter` du CSS de `visualizer.html`.

**Contexte** : 10 éléments HUD (drift panel, sources panel, journal, on-air badge, status panel, news panel, event banner, emotion wheel, restart banner, fade) utilisaient `backdrop-filter: blur(14-24px)`.

**Root cause** : SwiftShader (renderer WebGL software) gère aussi le compositing CSS via le GPU process. `backdrop-filter: blur()` force le compositor à calculer un flou Gaussien software sur tout le contenu WebGL derrière chaque élément — à chaque frame du compositor (60fps). Avec 10 éléments et des zones de blur de 200×300px à 82 samples par pixel, le GPU process saturait à 101% CPU → fps chutait à 10fps.

**Pourquoi l'onset à 60min** : La complexité de la scène WebGL croît pendant les 60 premières minutes (signaux GlobalState partant de zéro). En dessous d'un seuil de complexité, le compositor pouvait optimiser les backdrop-filters (contenu très sombre ≈ blur trivial). Au-dessus du seuil (~t=60min), le calcul devenait complet et saturait le CPU.

**Vérification empirique** :
- Avant fix : GPU CPU=101%, fps_ema=10fps
- Après fix : GPU CPU=51%, fps=30fps stable, drops=34 stables

**Impact visuel** : Les éléments HUD perdent l'effet "verre dépoli" mais conservent leur background semi-transparent (`rgba(255,255,255,0.08)`). Compromis acceptable pour un stream 24/7 en software rendering.

**Fichiers** : `overlays/visualizer.html` (10 lignes supprimées), `overlays/visualizer_dev.html` (sync).

