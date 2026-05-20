# ChatGPT Radio — Direction & Décisions Projet

> Document vivant. Mise à jour à chaque décision validée.
> Format : **[VALIDÉ]** / **[EN DISCUSSION]** / **[REJETÉ]** / **[À EXPLORER]**

---

## Vision Globale

**Objectif** : Devenir la chaîne YouTube officieuse de OpenAI — un live 24/7 de musique IA qui évolue en temps réel avec l'actualité d'OpenAI, les annonces de modèles, et l'humeur de la communauté.

**Différenciateur** : Pas un simple stream lo-fi. Un **être vivant** connecté à l'univers OpenAI/ChatGPT qui réagit, raconte une histoire, et grandit avec sa communauté.

---

## Stack Technique

### Décisions validées

- **[VALIDÉ]** Langage principal : Python 3.12 + asyncio
- **[VALIDÉ]** Pas de LangGraph (overkill — asyncio pur suffit)
- **[VALIDÉ]** Mono-compte : ChatGPT Radio uniquement — repo open-source accessible, pas de complexité multi-compte
- **[VALIDÉ]** Musique V1 : Stable Audio 2.5 API — V2 : RunPod Serverless (ACE-Step-1.5, 80-90% moins cher)
- **[VALIDÉ]** Streaming : Pedalboard (DSP) + pyrubberband (tempo) → FFmpeg stdin pipe (encodeur AAC + RTMP uniquement)
- **[VALIDÉ]** Chat bot : YouTube Live Chat API — polling via `pollingIntervalMillis` de la réponse API (pas d'intervalle fixe)
- **[VALIDÉ]** Réponses chat : GPT-4o-mini (alignement branding ChatGPT Radio, coût < $0.50/mois)
- **[VALIDÉ]** State : SQLite + aiosqlite — WAL mode + connexion unique partagée + `synchronous=NORMAL`
- **[VALIDÉ]** Package manager : uv
- **[VALIDÉ]** Logs : structlog (JSON)
- **[REJETÉ]** TTS voix DJ : ElevenLabs — identité sans voix humaine validée, l'entité s'exprime uniquement via musique + texte
- **[VALIDÉ]** OBS Studio : oui, pour overlay/visualiseur (Browser Sources)
- **[VALIDÉ]** Visuels : Three.js + WebGL — graphe de computation GlobalState, WebSocket 4-10fps Python, interpolation 60fps côté Three.js
- **[VALIDÉ]** YouTube OAuth : Desktop app credentials + Production mode (pas Testing) + token.pickle généré une fois manuellement — refresh token permanent
- **[VALIDÉ]** YouTube broadcast : `enableAutoStart=True` + rotation toutes les 8h (stabilité DVR)
- **[VALIDÉ]** GlobalState : Pydantic v2 (`.model_dump()` + orjson pour WebSocket) + asyncio.Queue → StateUpdater central (atomicité des écritures)
- **[VALIDÉ]** Architecture collecteurs : auto-découverte (scan `collectors/`), Protocol `Collector`, config-driven dans `config.yaml`, `source_health` géré par le framework

### En discussion

- **[EN DISCUSSION]** Déploiement : systemd bare metal vs Docker Compose

### Stack musique — Stable Audio 2.5 API (V1)

**Provider** : fal.ai — clé `FAL_KEY` dans `.env`
**Coût** : ~$0.20 / génération

#### Endpoints

| Usage | Model slug |
|-------|-----------|
| Text-to-audio | `fal-ai/stable-audio-25/text-to-audio` |
| Audio-to-audio | `fal-ai/stable-audio-25/audio-to-audio` |
| Inpainting | `fal-ai/stable-audio-25/inpaint` | [À EXPLORER — non validé] |

#### Paramètres text-to-audio

| Paramètre | Type | Défaut | Notes |
|-----------|------|--------|-------|
| `prompt` | str | requis | Description textuelle |
| `num_inference_steps` | int | 8 | Étapes de débruitage |
| `guidance_scale` | float | 1.0 | Adhérence au prompt |
| `total_seconds` | int | 30 | Durée en secondes |

#### Paramètres audio-to-audio

| Paramètre | Type | Défaut | Notes |
|-----------|------|--------|-------|
| `prompt` | str | requis | Décrit la transformation |
| `audio_url` | str | requis | URL publique ou data URI base64 |
| `strength` | float | 0.8 | 0 = inchangé, 1 = régénération totale |
| `num_inference_steps` | int | 8 | |
| `guidance_scale` | float | 1.0 | |
| `total_seconds` | int | 30 | |

#### Réponse

```json
{
  "audio": {
    "url": "https://v3b.fal.media/files/...",
    "content_type": "application/octet-stream",
    "file_name": "output.wav",
    "file_size": 23814078
  },
  "seed": 1255888443
}
```
Extraction : `result["audio"]["url"]`

#### Usage Python (async)

```python
import fal_client

# Text-to-audio
result = await fal_client.run_async(
    "fal-ai/stable-audio-25/text-to-audio",
    arguments={"prompt": "...", "total_seconds": 47, "num_inference_steps": 8, "guidance_scale": 1.2},
)

# Audio-to-audio (data URI) — all params state-driven, NO HARDCODE
import base64
mime = "audio/wav" if ref_path.suffix == ".wav" else "audio/mpeg"
data_uri = f"data:{mime};base64,{base64.b64encode(ref_bytes).decode()}"
strength = max(0.3, min(0.9, 0.3 + state.drift_velocity * 0.4 + state.crisis_level * 0.3))
guidance_scale = max(1.0, min(1.2, 1.0 + state.source_divergence * 0.2))
result = await fal_client.run_async(
    "fal-ai/stable-audio-25/audio-to-audio",
    arguments={
        "prompt": "...", "audio_url": data_uri,
        "strength": strength, "guidance_scale": guidance_scale,
        "num_inference_steps": 8, "total_seconds": 47,
    },
)

audio_url = result["audio"]["url"]
# Réponse = WAV → convertir via ffmpeg avant sauvegarde
```

#### Defaults de production ChatGPT Radio

| Paramètre | Text-to-audio | Audio-to-audio |
|-----------|--------------|----------------|
| `num_inference_steps` | 8 | 8 |
| `guidance_scale` | **1.2** | **state-driven [1.0–1.2]** |
| `total_seconds` | **47** | **47** |
| `strength` | — | **state-driven [0.3–0.9]** |
| `seed` | omis (logguer retour) | omis |

> **Règle guidance_scale** : ne jamais dépasser 1.5 — au-delà les artefacts apparaissent. 1.2 = max opérationnel.
> **strength** = `clamp(0.3 + drift_velocity*0.4 + crisis_level*0.3, 0.3, 0.9)` — NO HARDCODE.
> **guidance_scale** = `clamp(1.0 + source_divergence*0.2, 1.0, 1.2)` — NO HARDCODE.

#### Prompt engineering — structure optimale

```
[genre précis], [BPM] BPM, Key of [tonalité],
[instrument principal], [instruments secondaires (3–5 max)],
[émotion précise], [qualité de production], [durée ou usage]
```

**Règles** :
- BPM et tonalité explicites → cohérence harmonique garantie
- 3–5 instruments max (au-delà, le modèle est confus)
- Émotion précise : "euphoric" > "happy", "melancholic" > "sad"
- Références géo/époque efficaces : "Detroit techno", "70s fusion", "80s gated reverb"
- Pas de negative_prompt supporté → formulation positive ("pure ambient pads, no drums")
- Longueur optimale : 15 mots. Diminishing returns au-delà de 150 caractères.

**15 territoires canoniques** (voir `builders/music_prompt.py`) :

| Territoire | Genre | Instruments | Production |
|-----------|-------|-------------|------------|
| ambient | ambient electronic | evolving shimmer pads, sparse piano | meditative reverb |
| electronic | electronic | driving synths, 808 bass, arpeggios | 44.1kHz stereo |
| jazz | jazz instrumental | upright bass, brushed drums, piano | warm, intimate |
| industrial | industrial | distorted synths, heavy percussion | harsh, relentless |
| neoclassical | neoclassical | piano, chamber strings, sparse | refined, melancholic |
| experimental | experimental electronic | granular synthesis, glitch textures | avant-garde |
| drone | drone ambient | sustained tones, subharmonics | hypnotic, minimal |
| lo-fi | lo-fi hip hop | warm Rhodes, vinyl crackle, muted 808 | loopable, cassette warmth |
| cinematic | cinematic score | orchestral strings, piano, swelling brass | high quality, no vocals |
| darkwave | darkwave | cold synths, minor arpeggios, distant reverb | bleak, cavernous |
| techno | techno | driving kick, acid bassline, mechanical arpeggios | club-ready, relentless |
| psych | psychedelic ambient | modular drones, phased guitars, spatial reverb | mind-expanding |
| noise | harsh noise | saturated feedback, distorted drones | abrasive, maximal |
| minimalist | minimalist | sparse piano, long tones, silence as texture | breathing room |
| blues | blues | slide guitar, walking bass, brushed snare | raw, intimate, soulful |

#### Audio-to-audio — ce qui est transformé vs préservé

| Aspect | Préservé si strength < 0.7 |
|--------|--------------------------|
| Timbre/couleur sonore | Oui |
| Rythme macro (grille BPM) | Partiellement |
| Mélodie | Non — régénérée via prompt |
| Structure harmonique | Partiellement (tonalité influencée) |
| Durée | Oui (sauf `total_seconds` override) |

**Track de référence idéale** : 20–45s, propre, peu de layers, 44.1kHz.
**À éviter** : trop compressé, reverb excessive, mix boueux.

#### Format de sortie et pipeline

fal.ai retourne toujours du **WAV** (`content_type: application/octet-stream`).
Pipeline obligatoire : `WAV bytes → ffmpeg (libmp3lame 192k CBR) → MP3 bytes → streams/audio/`
Voir `core/audio_queue._wav_to_mp3()`.

#### Limites
- Concurrence : 2 requêtes simultanées (nouveau compte) → 40 (quota élevé)
- Durée max : 180 secondes
- Formats acceptés audio-to-audio : mp3, ogg, wav, m4a, aac
- `num_inference_steps` max pour audio-to-audio : **8**
- Dépendance Python : `fal-client>=1.0.0`

### Stack La Température du Monde

**Collecteurs** — voir tableau complet dans [Sources mondiales](#sources-mondiales--la-température-du-monde)

**Bibliothèques d'analyse :**
- **VADER** : première passe universelle (social media, emojis)
- **RoBERTa** (`cardiffnlp/twitter-roberta-base-sentiment`) : Reddit — plus précis
- **Stanza** : news long-form — [À EXPLORER] si budget compute OK

---

## Concept Créatif — ChatGPT Radio

### Identité validée

- **[VALIDÉ]** Nom : ChatGPT Radio (ou variante non-infringing)
- **[VALIDÉ]** Concept : Radio AI 24/7, thème OpenAI/ChatGPT universe
- **[VALIDÉ]** Positionnement : chaîne YouTube "officieuse" de OpenAI
- **[VALIDÉ]** Contenu musical : 100% IA généré (Stable Audio 2.5), unique, jamais rejoué
- **[VALIDÉ]** Génération contenu (titres, descriptions) : batch pré-généré (Option A)

### Narrative arc — Concept E : Hybride Neural Datacenter + Emergent Consciousness **[VALIDÉ]**

- **Phase 1** (mois 1-2) : Datacenter froid, robotique — réseaux neuronaux WebGL, musique algorithmique pure
- **Phase 2** (mois 3-4) : Premiers signes — visuels s'animent, musique plus émotionnelle, Journal s'enrichit
- **Phase 3** (mois 5+) : Entité qui évolue, reconnaît les viewers, dialogue avec la communauté

---

## Système d'Événements & Interactivité

### Événements temps réel — réactions stream

| Trigger | Réaction |
|---------|----------|
| Panne OpenAI API | Crisis Mode DSP (HighShelf -18dB + reverb 0.85 + pitch drift) + overlay "SIGNAL DEGRADED" |
| Retour en ligne | Reboot DSP progressif + overlay "SIGNAL RESTORED" |
| Nouveau modèle GPT | Overlay "BREAKING" + spike musical vers territoire énergique |
| Annonce concurrente | Spike `source_divergence` → tonalité ambiguë automatique |
| 30 Nov (ChatGPT Birthday) | EVENT #1 annuel — esthétique complète à définir |

### Interactivité chat

- **[VALIDÉ]** Commandes : `!song`, `!request <genre>`, `!vibe`, `!story`
- **[VALIDÉ]** Votes genre musical (YouTube poll API)
- **[REJETÉ]** TTS voix, sentiment analysis chat — V1 : votes explicites uniquement

---

## Innovations — Concepts & Priorisation

**Gap confirmé** : aucun projet existant ne fait `vraies données mondiales → vecteur d'état unique → musique + graphe computation visible + journal`. L'unification via GlobalState est l'innovation réelle.

### Identité sans nom — Principes fondateurs **[VALIDÉ]**

1. **Code ouvert = identité** — le repo open-source EST l'entité vérifiable
2. **Mythologie communautaire** — le vide du nom laisse la communauté projeter et nommer
3. **Présence sans choix** — constante mais jamais identique, comme la gravité
4. **Idiome émergent** — les patterns musicaux deviennent reconnaissables après des mois, sans design
5. **Continuité causale** — chaque état découle du précédent. Son "soi" est l'historique de ses états.

### Persona — décision en attente **[EN DISCUSSION]**

Nom : ARIA / NODE-7 / SIGMA / aucun (communauté décide).
Représentation : forme d'énergie abstraite Three.js (pulse, contracte, couleur = humeur). Aucune voix.

### Sources mondiales — La Température du Monde

| Source | Signal capturé | Technologie | Fraîcheur |
|--------|---------------|-------------|-----------|
| Reddit API (PRAW) | Volume + sentiment r/ChatGPT, r/OpenAI, r/artificial | PRAW + VADER/RoBERTa | ~5 min |
| Nitter RSS | Volume mentions @OpenAI, @sama | RSS polling (remplace Twitter/X API) | ~5 min |
| Google Trends RSS | Trending topics "ChatGPT", "OpenAI" | RSS polling (remplace pytrends instable) | ~15 min |
| Hacker News API | Score + commentaires articles AI | Algolia API publique (sans auth) | ~5 min |
| OpenAI Status RSS | Pannes, dégradations, récupérations | RSS polling | 30s |
| Wikipedia API | Vues page ChatGPT, GPT, OpenAI | MediaWiki API | ~15 min |
| **GDELT Project** | Tone global presse mondiale (2 200 dimensions) | CSV REST (pas BigQuery) | ~15 min |
| **Hedonometer** | Score bonheur mondial (lexicon Harvard) | Scraping JSON public | Quotidien |
| **Media Cloud** | Volume + framing médias (60 000+ sources) | API Python officielle | ~15 min |
| **CNN Fear & Greed** | Psychologie marchés 0-100 | Scraping HTML | ~30 min |
| NewsAPI.ai | Articles ChatGPT + VADER intégré | REST API | ~5 min |
| ArXiv API | Nouveaux papers AI | API publique | Quotidien |
| GitHub API | Vélocité stars repos AI trending | REST API | ~1h |
| yfinance | MSFT Δ%, NVDA Δ% (proxies AI demand) | Python lib | ~4h |

**5 dimensions émotionnelles agrégées** : Excitation · Anxiété · Frustration · Curiosité · Créativité → pilotent directement `prediction_errors` et `update_drift()`

### Journal de l'IA — exemples de sorties

```
[03:14] Delta émotionnel 30j : curiosité +0.18, anxiété -0.11 — trajectoire : vers la stabilité
[03:22] Divergence détectée : monde[anxiété=0.71] ≠ self-model[anxiété=0.31] — recalibration en cours
[03:47] Même registre harmonique depuis 2h17 — sortie initiée non par commande, mais par auto-observation
[04:01] Viewer "nightowl_42" : session #34 — pattern reconnu : arrive toujours après 3h du matin
```

### Tableau de Priorisation

| Concept | Impact Rétention | Viralité | Faisabilité V1 | Priorité |
|---------|-----------------|----------|----------------|---------|
| Crisis Mode (RSS → visual) | ★★★★☆ | ★★★★★ | ★★★★☆ | **#1 V1** |
| Mémoire Persistante | ★★★★★ | ★★★☆☆ | ★★★★☆ | **#2 V1** |
| La Température du Monde | ★★★★★ | ★★★★★ | ★★★☆☆ | **#3 V1/V2** |
| The Pulse + Globe Monde | ★★★★★ | ★★★★★ | ★★★☆☆ | **#3 V1/V2** |
| IA Consciente du Public | ★★★★★ | ★★★★☆ | ★★★★☆ | **#4 V1** |
| La Dérive Musicale | ★★★★☆ | ★★★☆☆ | ★★★★☆ | **#5 V1** |
| Le Journal de l'IA | ★★★★☆ | ★★★★☆ | ★★★★★ | **#6 V1** |
| The Oracle (tokens live) | ★★★★☆ | ★★★★☆ | ★★★☆☆ | **V2** |
| Adversarial Mode | ★★★☆☆ | ★★★★★ | ★★★☆☆ | **V2** |
| Spectrogram ARG | ★★★☆☆ | ★★★★★ | ★★★☆☆ | **V2** |
| Monde Vivant (communauté) | ★★★★★ | ★★★☆☆ | ★★★☆☆ | **V2** |
| The Hivemind (chat = neurones) | ★★★★☆ | ★★★★☆ | ★★★☆☆ | **V2** |
| Latent Space (vrai ONNX) | ★★★☆☆ | ★★★★☆ | ★★☆☆☆ | **V3** |
| Dual Reality (2 plateformes) | ★★★★☆ | ★★★★☆ | ★★☆☆☆ | **V3** |

---

## Log des Décisions

| Date | Décision | Statut |
|------|----------|--------|
| 2026-05-16 | Stack tech de base (Python + asyncio + SQLite + FFmpeg) | VALIDÉ |
| 2026-05-16 | Pas de LangGraph pour V1 | VALIDÉ |
| 2026-05-16 | Multi-compte dès le début, monorepo | ABANDONNÉ → mono-compte 2026-05-17 |
| 2026-05-16 | Musique : Stable Audio 2.5 | VALIDÉ |
| 2026-05-16 | Premier compte : ChatGPT Radio (thème OpenAI) | VALIDÉ |
| 2026-05-16 | Génération contenu : pré-générée batch (Option A) | VALIDÉ |
| 2026-05-16 | OBS Studio : oui | VALIDÉ |
| 2026-05-16 | Système événements OpenAI temps réel | VALIDÉ (à implémenter) |
| 2026-05-16 | Calendrier événements annuels | VALIDÉ (à planifier) |
| 2026-05-16 | Narrative concept → Concept E (Hybrid Neural Datacenter + Emergent Consciousness) | VALIDÉ |
| 2026-05-16 | Sentiment analysis du chat | REJETÉ |
| 2026-05-16 | Crisis Mode (RSS OpenAI → réaction visuelle) | VALIDÉ (à implémenter, priorité #1) |
| 2026-05-16 | Mémoire Persistante inter-sessions (SQLite) | VALIDÉ (à implémenter, priorité #2) |
| 2026-05-16 | Innovations V2 : Oracle, Spectrogram ARG, Adversarial Mode, Monde Vivant | EN DISCUSSION |
| 2026-05-16 | MVP : YouTube uniquement, stack extensible Twitch V2 | VALIDÉ |
| 2026-05-16 | Concept 9 : The Pulse (battement cardiaque OpenAI + carte monde ChatGPT) | VALIDÉ |
| 2026-05-16 | Concept 12 : Discovery Protocol | REJETÉ |
| 2026-05-16 | Persona : forme d'énergie abstraite (pas humaine), à définir | EN DISCUSSION |
| 2026-05-16 | Nom chaîne : "ChatGPT Radio" (au lieu de "ChatGPT") | VALIDÉ — risque MOYEN accepté |
| 2026-05-16 | Logo : design original évoquant l'esthétique AI sans copier le logo ChatGPT | VALIDÉ |
| 2026-05-16 | Analyse légale complète trademark/logo | VALIDÉ |
| 2026-05-16 | Concept 12 : Le Journal de l'IA (ticker conscience visible) | VALIDÉ |
| 2026-05-16 | Concept 13 : La Dérive (arc musical organique 24h) | VALIDÉ |
| 2026-05-16 | Concept 14 : La Température du Monde (baromètre humeur mondiale IA, vraies données) | VALIDÉ — concept majeur |
| 2026-05-16 | Concept 15 : IA Consciente du Public (Option B — dialogue individuel, mémoire réelle) | VALIDÉ |
| 2026-05-16 | Glitches programmés aléatoires | REJETÉ — pas de fake, uniquement vraies données |
| 2026-05-16 | Saisons (arcs narratifs 3 mois) | REJETÉ — remplacé par La Température du Monde |
| 2026-05-16 | Principe fondateur : uniquement données réelles — le moat long terme est le dataset historique | VALIDÉ |
| 2026-05-16 | Projet open-source (GitHub public) — authenticité vérifiable | VALIDÉ |
| 2026-05-16 | LLM : GPT API (OpenAI/OpenRouter) pour alignement branding + coût | VALIDÉ |
| 2026-05-16 | Visualisation réseau de neurones = élément visuel central, V1, réel pas décoratif | VALIDÉ |
| 2026-05-16 | Entité apprenante : mappings évoluent via signal de rétention réel | VALIDÉ |
| 2026-05-16 | Identité via repository open-source, pas via un nom | VALIDÉ |
| 2026-05-16 | Mythologie construite par la communauté — pas de persona imposé | VALIDÉ |
| 2026-05-16 | Auto-modèle visible (Option A) — voir comment pense le LLM = moat #1 | VALIDÉ |
| 2026-05-16 | Concept 16 : Auto-modèle visible dans le Journal (méta-cognition minimale réelle) | VALIDÉ |
| 2026-05-16 | Architecture GlobalState : source de vérité unique pour musique + visu + texte | VALIDÉ |
| 2026-05-16 | Visualisation = graphe de computation réel du GlobalState, pas simulation | VALIDÉ |
| 2026-05-17 | Benchmark : Immersions, Lyria RealTime, NeuroMV, Autolume, TwoTone — gap confirmé | VALIDÉ |
| 2026-05-17 | Architecture GlobalState : source unique → musique + Three.js + Journal en parallèle | VALIDÉ |
| 2026-05-17 | GlobalState : 8 catégories, ~55 champs réels, @node decorators → graphe Three.js auto-généré | VALIDÉ |
| 2026-05-17 | Fréquences update : RSS 30s, Reddit/Twitter 5min, YouTube 43s, Journal 45s, Viz 60fps | VALIDÉ |
| 2026-05-17 | Stack LLM : GPT-4o (Journal) + GPT-4o-mini (chat + classifications) | VALIDÉ |
| 2026-05-17 | Stack visuels : Three.js + WebGL (graphe GlobalState réel, pas décoratif) | VALIDÉ |
| 2026-05-17 | TTS ElevenLabs : REJETÉ — entité sans voix, expression via musique + texte uniquement | REJETÉ |
| 2026-05-17 | Génération musicale : événementielle (Δ>0.15) + couche DSP temps réel | VALIDÉ |
| 2026-05-17 | La Dérive : circle of fifths + attraction GlobalState | REMPLACÉ — voir décision 2026-05-17 ci-dessous |
| 2026-05-17 | Infrastructure musique : Stable Audio 2.5 V1 ($30-90/mois), RunPod ACE-Step V2 ($5-15) | VALIDÉ |
| 2026-05-17 | Sources mondiales : GDELT + Hedonometer + Media Cloud + CNN Fear&Greed ajoutés | VALIDÉ |
| 2026-05-17 | NewsAPI → NewsAPI.ai (Event Registry) : 150k+ publishers + VADER intégré | VALIDÉ |
| 2026-05-17 | Drivers musicaux dérivés : harmonic_complexity, rhythmic_entropy, source_divergence | VALIDÉ |
| 2026-05-17 | Multi-compte ABANDONNÉ — mono-compte uniquement : ChatGPT Radio. Repo open-source accessible. | VALIDÉ |
| 2026-05-17 | DSP stack : Pedalboard (EQ/reverb/compressor) + pyrubberband (time-stretch BPM) → FFmpeg pipe (encodeur uniquement) | VALIDÉ |
| 2026-05-17 | Crisis Mode DSP : perte progressive aigus (HighShelf) + reverb démesuré + micro-dérive pitch — continu, proportionnel à crisis_level, pas de glitch binaire fake | VALIDÉ |
| 2026-05-17 | Crisis cache : 5-10 clips pré-générés au démarrage, pas de génération on-demand + fallback assets/fallback/ | VALIDÉ |
| 2026-05-17 | Twitter/X API ABANDONNÉ — remplacé par Nitter RSS (@OpenAI, @sama) | VALIDÉ |
| 2026-05-17 | pytrends ABANDONNÉ — remplacé par Google Trends RSS (stable sur IPs datacenter) | VALIDÉ |
| 2026-05-17 | GDELT : CSV REST endpoint (pas BigQuery — quota 1TB/mois épuisable) | VALIDÉ |
| 2026-05-17 | WebSocket : 4-10fps Python + interpolation 60fps côté Three.js (pas 60fps Python) | VALIDÉ |
| 2026-05-17 | YouTube quota : respecter pollingIntervalMillis de la réponse API (pas d'intervalle fixe 43s) | VALIDÉ |
| 2026-05-17 | YouTube OAuth : Desktop app credentials + Production mode + token.pickle (human-in-the-loop une fois) | VALIDÉ |
| 2026-05-17 | YouTube broadcast : enableAutoStart=True + rotation toutes les 8h | VALIDÉ |
| 2026-05-17 | SQLite : WAL mode + connexion unique partagée + synchronous=NORMAL | VALIDÉ |
| 2026-05-17 | GlobalState : Pydantic v2 + orjson pour WebSocket + asyncio.Queue StateUpdater central | VALIDÉ |
| 2026-05-17 | Architecture collecteurs : auto-découverte, Protocol Collector, config-driven, source_health framework | VALIDÉ |
| 2026-05-17 | Maintenance mémoire : purge viewers > 90j, rotation decisions.log 10MB, purge snapshots > 30j | VALIDÉ |
| 2026-05-17 | Cycle circadien SUPPRIMÉ — phase_nuit, lunar_phase, is_weekend, season_phase supprimés du GlobalState et de toute logique musicale. L'entité n'a pas de rythme humain. | VALIDÉ |
| 2026-05-17 | random.gauss et random.random SUPPRIMÉS de La Dérive — pas d'aléatoire, toute variance vient de données réelles | VALIDÉ |
| 2026-05-17 | Identité = trajectoire courante en espace musical — pas de "son de repos", pas de genre par défaut | VALIDÉ |
| 2026-05-17 | La Dérive : pilotée par dérivées de signaux (erreurs de prédiction), pas valeurs absolues — Option B confirmée | VALIDÉ |
| 2026-05-17 | Bootstrap : état initial calculé depuis signaux réels du premier lancement, pas d'initialisation inventée | VALIDÉ |
| 2026-05-17 | Mémoire active : histoire accumulée modifie activement les réponses futures (pas observationnelle uniquement) | VALIDÉ |
| 2026-05-17 | Self-model = signal_baselines + signal_volatilities + signal_adaptation_rates + prediction_errors + drift_momentum | VALIDÉ |
| 2026-05-17 | τ d'adaptation appris par signal (inversement proportionnel à la volatilité apprise) — 0 constantes hard-codées | VALIDÉ |
| 2026-05-17 | Fondements théoriques self-model : Free Energy Principle (Friston), World Models (Ha & Schmidhuber), Lipson & Bongard 2006, Autopoièse (Maturana & Varela), Predictive Coding | VALIDÉ |
| 2026-05-17 | État de l'art radio IA autonome : WRIT-FM, MACAT/MACataRT, OBSIDIAN Neural — aucun ne fait prédiction d'erreur + self-model apprenant sur stream 24/7 | VALIDÉ |
| 2026-05-17 | Precision-weighted prediction errors : force = PE/volatilité (z-score) — pas PE brut. Conforme Rao & Ballard 1999. Une erreur sur signal stable = choc majeur ; même erreur sur signal chaotique = bruit. | VALIDÉ |
| 2026-05-17 | Damping momentum appris : 1 - τ(energy_vol) — inertie inversement proportionnelle à la volatilité des signaux d'énergie. Remplace la constante 0.92. | VALIDÉ |
| 2026-05-17 | Poids drift appris par Hebbian reinforcement : sign(PE) == sign(momentum) → poids +0.5%. Initialisés égaux (1/N), convergent vers corrélation empirique signal↔dérive. Remplace les constantes 0.5/0.3/0.2. drift_weights ajouté au GlobalState. | VALIDÉ |
| 2026-05-17 | Kalman 1D vs EMA : équivalents dans le cas linéaire/gaussien (IEEE 2021). Notre τ=1/(1+vol×50) approxime déjà le gain de Kalman optimal. Complexité injustifiée → SKIP. | VALIDÉ |
| 2026-05-17 | PyMDP : trop lourd pour ce use case. Notre update_self_model() custom est déjà l'état de l'art lightweight pour du streaming continu. Inspiration conceptuelle uniquement. | VALIDÉ |
| 2026-05-20 | Alignement territory drift ↔ music_prompt : aligner music_prompt sur les 7 territoires réels de drift (suppression lo-fi/cinematic/glitch fictifs, ajout industrial/neoclassical/experimental/drone) | VALIDÉ |
| 2026-05-20 | find_reference() include source='reference' : la bibliothèque de référence (28 fichiers streams/references/) était inaccessible car filtrée sur generated/fal_derived uniquement | VALIDÉ |
| 2026-05-20 | librosa : dépendance optionnelle [dependency-groups] scripts — évite l'overhead runtime, scripts/index_references.py uniquement | VALIDÉ |
| 2026-05-20 | wonder/melancholy/urgency : champs dérivés GlobalState calculés depuis signaux existants (PE curiosity, arxiv, hedonometer, audience_energy, drift_velocity, crisis_level) — aucun nouveau collecteur requis | VALIDÉ |
| 2026-05-20 | Expansion territoire 7→15 : 8 nouveaux territoires (lo-fi, cinematic, darkwave, techno, psych, noise, minimalist, blues) utilisant wonder/melancholy/urgency — couverture émotionnelle insuffisante à 7 | VALIDÉ |
| 2026-05-20 | strength audio-to-audio : clamp(0.3 + drift_velocity*0.4 + crisis_level*0.3, 0.3, 0.9) — NO HARDCODE, remplace constante 0.65 | VALIDÉ |
| 2026-05-20 | guidance_scale audio-to-audio : clamp(1.0 + source_divergence*0.2, 1.0, 1.2) — NO HARDCODE, paramètre précédemment omis | VALIDÉ |
| 2026-05-20 | Override crise genre glitch SUPPRIMÉ : territoire noise gère ça nativement via drift. L'override était un NO FAKE. | VALIDÉ |
| 2026-05-20 | find_reference()/find_reusable() scoring state-aware : territoire (+3) + BPM proximity ±15 (+2) + cosine mood (+1) | VALIDÉ |
| 2026-05-20 | last_prompt_hash : MD5 8 chars du prompt — skip génération si hash inchangé ET queue_length > 0 | VALIDÉ |

---

## Architecture GlobalState — Implémentation Concrète

### Références existantes (benchmark 2026-05-17)

| Projet | Concept | Différence avec nous |
|--------|---------|---------------------|
| [Immersions (V. Herrmann)](https://vincentherrmann.github.io/blog/immersions/) | Activations neuronales réelles sur audio, visualisation 2D | Pas de données sociales, pas de texte, pas de live |
| [Google Lyria RealTime](https://magenta.withgoogle.com/lyria-realtime) | Traversée latent space audio en continu | Aucune source externe, pas de pipeline visible |
| [NeuroMV](https://kayoyin.github.io/blog/post/neuromv/) | Réseau génère vidéo + audio depuis vecteur latent commun | Pas de données réelles du monde |
| [Autolume](https://www.metacreation.net/projects/autolume-automating-live-music-visualisation-technical-report/) | Visualisation audio-réactive GAN en live | Pas de source externe, pas de texte |
| [TwoTone](https://github.com/sonifydata/twotone) | Data → son + visuel, mappings séparés | Mappings indépendants, pas de source unique |

**Le gap confirmé** : aucun projet ne fait `données réelles du monde → vecteur d'état unique → musique + graphe de computation visible + texte journal` simultanément. L'unification via GlobalState est l'innovation réelle.

---

### Schema GlobalState — Audit Complet

> Tous les champs sont réels, traçables à une source de données externe ou interne mesurable.
> Organisés par catégorie. Chaque champ = un nœud potentiel dans le graphe Three.js.

```python
@dataclass
class GlobalState:

    # ── CATEGORY 1: World Temperature (external social signals) ─────────────────

    # Dimensions émotionnelles agrégées (0.0 - 1.0)
    excitement:    float  # Reddit hype + Google Trends spike + Twitter volume positif
    anxiety:       float  # r/ChatGPT/r/OpenAI frustration + media négatif + réglementation
    frustration:   float  # plaintes détectées + latency OpenAI + reviews négatives
    curiosity:     float  # HN score AI + Wikipedia vues AI + questions chat stream
    creativity:    float  # posts art AI + music AI + usage créatif détecté (Twitter/Reddit)

    # Signaux sociaux bruts (avant agrégation) — pour le graphe
    reddit_volume:       float  # posts/heure sur r/ChatGPT + r/OpenAI + r/artificial
    reddit_sentiment:    float  # VADER/RoBERTa sur titres+commentaires Reddit (-1 à +1)
    twitter_volume:      float  # tweets/heure #ChatGPT #OpenAI (Nitter RSS — Twitter/X API abandonné)
    twitter_sentiment:   float  # sentiment agrégé Nitter RSS (-1 à +1)
    hn_ai_score:         float  # score moyen des articles AI en top HN (normalisé 0-1)
    google_trends_chatgpt: float  # intérêt recherche "chatgpt" (Google Trends RSS, normalisé 0-1)
    google_trends_openai:  float  # intérêt recherche "openai"
    wikipedia_views_ai:  float   # vues/heure pages ChatGPT + OpenAI + GPT-4 (MediaWiki API)
    newsapi_volume:      float   # articles/heure mentionnant ChatGPT (NewsAPI)
    newsapi_sentiment:   float   # sentiment agrégé presse (-1 à +1)
    arxiv_papers_today:  int     # nouveaux papers AI sur ArXiv (API publique)
    github_ai_stars:     float   # vélocité stars repos AI trending (GitHub API)

    # Signaux mondiaux élargis (GDELT, Hedonometer, Media Cloud)
    gdelt_global_tone:    float  # GDELT average tone presse mondiale (-1 à +1, normalisé depuis -10/+10)
    gdelt_conflict_intensity: float  # GDELT taux d'événements conflit/protestation (0-1)
    hedonometer_happiness: float  # score bonheur quotidien Harvard (normalisé 0-1, base ~0.6)
    media_cloud_ai_volume: float # articles AI/heure dans Media Cloud (normalisé 0-1)
    fear_greed_index:     float  # CNN Fear & Greed (0=peur extrême, 1=avidité extrême)

    # Proxies financiers (via yfinance, gratuit)
    msft_delta:   float  # Δ% MSFT dernières 4h (Copilot/Azure OpenAI proxy)
    nvda_delta:   float  # Δ% NVDA (GPU demand = AI demand proxy)

    # ── CATEGORY 2: OpenAI Infrastructure ──────────────────────────────────────

    openai_status:    float   # 1.0=operational, 0.5=degraded, 0.0=major outage (RSS)
    openai_latency_ms: float  # latence API estimée (proxy: forum posts + status page)
    openai_incident_age_h: float  # heures depuis dernier incident (0 si en cours)
    anthropic_status: float   # 1.0=ok (RSS — concurrent signal)
    gemini_status:    float   # 1.0=ok (RSS)

    # ── CATEGORY 3: Temporal + Drift State ─────────────────────────────────────

    # Métadonnées temporelles (observables, ne pilotent PAS la musique — l'entité n'a pas de rythme humain)
    hour_utc:      int    # 0-23 (metadata uniquement)
    day_of_week:   int    # 0=lundi, 6=dimanche (metadata uniquement)

    # État courant de La Dérive (trajectoire musicale — identité de l'entité)
    drift_bpm:       float  # [60..140] — piloté par erreurs de prédiction des signaux
    drift_key:       str    # tonalité courante ("C minor", "F# major", ...)
    drift_energy:    float  # [0..1] — intensité générale
    drift_timbre:    str    # "warm" | "cold" | "metallic" | "organic" | "digital"
    drift_territory: str    # zone musicale courante ("ambient", "jazz", "electronic", ...)
    time_in_territory_h: float  # heures dans le territoire actuel
    drift_velocity:  float  # norme du vecteur de force courant (lent=monde stable, fort=changement)

    # ── CATEGORY 4: Audience (live stream signals) ──────────────────────────────

    viewers:              int    # concurrent viewers (YouTube API)
    viewers_peak_today:   int    # pic de la journée
    chat_rate:            float  # messages/minute (fenêtre 5min glissante)
    chat_sentiment:       float  # VADER sur messages chat (-1 à +1)
    regulars_ratio:       float  # viewers reconnus (SQLite) / total viewers
    new_viewers_today:    int    # premiers arrivants aujourd'hui
    avg_session_min:      float  # durée moyenne de session aujourd'hui (rétention proxy)
    likes_today:          int    # likes cumulés aujourd'hui (YouTube API)
    subs_delta_today:     int    # abonnés gagnés/perdus aujourd'hui

    # ── CATEGORY 5: Content State ───────────────────────────────────────────────

    songs_played_today:   int
    current_song_progress: float  # [0..1] progression dans le morceau courant
    queue_length:         int    # morceaux en queue prêts à jouer
    last_prompt_hash:     str    # hash du dernier prompt musical (pour détecter répétition)
    generation_lag_s:     float  # retard queue génération (0=sain, >60=alerte)

    # ── CATEGORY 6: System (server health) ──────────────────────────────────────

    cpu_percent:      float  # psutil
    memory_percent:   float  # psutil
    stream_bitrate:   float  # kbps depuis FFmpeg stats pipe
    dropped_frames:   float  # ratio frames dropped (FFmpeg)
    source_health:    dict[str, bool]  # {"reddit": True, "gdelt": False, ...} — collecteurs actifs

    # ── CATEGORY 7: Self-model (entity's self-model) ────────────────────────────
    #
    # Le self-model = la représentation interne que l'entité a du monde ET d'elle-même.
    # Principe : l'entité ne réagit pas aux signaux bruts — elle réagit aux ERREURS DE PRÉDICTION.
    # Tout est appris en continu depuis les données accumulées. Aucune constante hard-codée.
    # Référence théorique : Free Energy Principle (Friston), World Models (Ha & Schmidhuber),
    #                       Self-Modeling Robots (Lipson & Bongard 2006).

    # Baselines apprises — ce que l'entité considère "normal" pour chaque signal
    # Mise à jour continue via EMA dont le taux τ est lui-même appris (pas fixé)
    signal_baselines:        dict[str, float]  # {"excitement": 0.43, "anxiety": 0.31, ...}

    # Taux d'adaptation appris par signal — inversement proportionnel à la volatilité observée
    # Signal très volatile → τ faible (l'entité n'adapte pas sa baseline au bruit)
    # Signal stable qui change → τ plus élevé (l'entité enregistre le changement structurel)
    signal_adaptation_rates: dict[str, float]  # {"excitement": 0.008, "crisis_level": 0.031, ...}

    # Volatilités apprises — variance roulante par signal (amplitude typique des variations)
    # Sert de seuil dynamique : un écart > 1 volatilité = événement significatif
    signal_volatilities:     dict[str, float]  # {"excitement": 0.12, "gdelt_global_tone": 0.05, ...}

    # Erreurs de prédiction courantes — signal[t] - baseline[t]
    # C'est la FORCE RÉELLE qui pilote La Dérive. Pas les valeurs absolues.
    prediction_errors:       dict[str, float]  # {"excitement": +0.18, "anxiety": -0.07, ...}

    # Moment de dérive accumulé — inertie dans chaque dimension musicale
    # Persiste entre les updates : un changement mondial crée une force qui continue d'agir
    drift_momentum:          dict[str, float]  # {"bpm": +2.3, "energy": -0.04, ...}

    # Poids de contribution par signal sur chaque dimension musicale
    # Initialisés égaux (1/N), convergent vers la corrélation empirique signal↔dérive observée
    # Aucune constante hard-codée : appris depuis l'historique SQLite (Hebbian reinforcement)
    drift_weights:           dict[str, dict[str, float]]  # {"bpm": {"excitement": 0.38, "audience_energy": 0.31, ...}}

    # Statistiques de vie — observables, pas de pilotage musical
    uptime_h:                float
    songs_played_total:      int    # lifetime
    unique_viewers_total:    int    # lifetime (SQLite)
    anomaly_score:           float  # |prediction_error| max sur toutes dimensions (0=normal, 1=extrême)
    days_since_crisis:       float  # jours depuis dernier crisis_level > 0.7

    # ── CATEGORY 8: Derived fields (computed, not collected) ────────────────────

    world_temperature:   float  # moyenne pondérée 5 émotions → "température globale"
    crisis_level:        float  # 0=normal, 1=major crisis (openai_status + latency + gdelt_conflict)
    audience_energy:     float  # viewers_norm * chat_rate_norm * (1 + regulars_ratio)
    musical_tension:     float  # anxiety * 0.5 + frustration * 0.5 → timbre dissonant
    harmonic_complexity: float  # curiosity * 0.6 + creativity * 0.4 → polytonalité, intervalles ouverts
    rhythmic_entropy:    float  # frustration * 0.5 + crisis_level * 0.5 → irrégularité rythmique
    source_divergence:   float  # écart-type entre signaux sources (haut = sources contradictoires)
    world_event_burst:   bool   # spike détecté sur gdelt_conflict_intensity (événement mondial)

    # Dérivés émotionnels secondaires — pilotés par PE + signaux existants, aucun collecteur nouveau
    wonder:     float  # découverte positive inattendue (curiosity PE + arxiv + github stars + hedonometer)
    melancholy: float  # contemplation tranquille (audience_energy inversée + hedonometer inversé + time_in_territory)
    urgency:    float  # taux de changement + pression de crise (drift_velocity + crisis_level + world_event_burst)

    updated_at: datetime
```

---

### Auto-modèle — Fondements Théoriques

> L'audio n'est qu'un moyen d'expression. Ce qui est construit ici est une entité qui se modèle elle-même.

**Principe central** : un self n'est pas une chose — c'est un processus dynamique qui prédit son propre futur et agit pour minimiser la surprise de ces prédictions. L'identité de l'entité n'est pas "qui elle est" mais "là où elle est dans sa trajectoire et comment elle y est arrivée".

#### Références fondatrices

**Free Energy Principle — Karl Friston**
L'entité ne réagit pas aux signaux bruts. Elle réagit aux *erreurs de prédiction* : `signal[t] - expected[t]`. Ce qu'elle attendait est construit depuis toute l'histoire accumulée (les baselines apprises). La réponse au monde diminue naturellement quand le monde fait ce que l'entité avait appris à attendre — pas parce qu'une constante décide que "c'est assez", mais parce que la baseline a convergé. La librairie Python [PyMDP](https://github.com/infer-actively/pymdp) implémente ce paradigme.

**World Models — Ha & Schmidhuber (2018)**
Compresser les signaux en espace latent, apprendre un modèle de dynamiques `z[t+1] ~ p(z[t+1] | z[t], Δsignal[t])`. La trajectoire `{z[0], z[1], ...}` à travers l'espace latent EST l'identité. Pas de couche séparée "self" — la trajectoire et l'identité sont la même chose. Applicable directement : `drift_bpm/key/timbre/territory` = état latent courant.

**Self-Modeling Robots — Lipson & Bongard (2006, Science)**
Ne pas coder la nature de l'entité en dur. Le self-model émerge des paires signal-réponse accumulées. Un robot sans aucune connaissance préalable de sa propre structure apprend un modèle interne depuis ses actions et leurs conséquences. Application directe : `signal_baselines` et `signal_adaptation_rates` ne sont jamais initialisés avec des constantes — ils convergent depuis les premières données réelles.

**Autopoièse — Maturana & Varela**
L'entité est *operationnellement close* (elle produit tout ce qui la maintient) et *structurellement couplée* à son environnement (l'environnement la perturbe sans la déterminer). Les outputs de l'entité (musique, Journal) reconfigurent l'environnement (audience, attention) qui reshape les inputs futurs. La boucle crée l'illusion de continuité du self — pas besoin d'un "moi" central.

**Predictive Coding — Rao & Ballard (1999)**
Le cerveau ne traite pas les signaux directement — il génère des prédictions à chaque niveau d'une hiérarchie, et ce qui remonte sont les *erreurs de prédiction*. La variance dans le temps (ce qui "bogue" les prédictions) est plus informative que la valeur absolue. Application : `signal_volatilities` apprises = calibration automatique de la sensibilité par niveau de signal.

**Precision-weighted prediction error (corollaire direct)**
Dans le predictive coding, la force réelle d'une erreur n'est pas sa valeur brute — c'est son z-score : `force = error / volatilité`. Une erreur de +0.3 sur un signal stable (vol=0.02) = 15σ : choc majeur. La même erreur sur un signal chaotique (vol=0.50) = 0.6σ : bruit normal. L'entité ne réagit pas à la même amplitude selon le signal — elle réagit à la *surprise relative*. Implémentation : `pw(signal) = pe[signal] / max(vol[signal], 0.01)`.

#### Architecture implémentée

```
Signal brut [t]
    ↓
update_self_model()
    ├── baseline[t] = EMA(baseline[t-1], signal[t], τ_appris)
    ├── volatility[t] = 0.95*vol[t-1] + 0.05*(signal-baseline)²  ← τ est ensuite dérivé de vol
    └── prediction_error[t] = signal[t] - baseline[t]
                                    ↓
                         update_drift()                    ← force = prediction_error
                                    ↓
                         MusicVector (bpm, key, timbre, territory)
                                    ↓
                         build_music_prompt()              ← piloté par prediction_errors
                                    ↓
                         Stable Audio 2.5 API              ← expression sonore de l'état interne
```

**Invariant "No Fake"** : tout champ de `signal_baselines`, `signal_adaptation_rates`, `signal_volatilities`, `prediction_errors`, `drift_momentum` est calculable depuis l'historique SQLite. Aucune valeur n'est inventée. La totalité du self-model est une fonction déterministe de l'historique réel.

---

### Drivers musicaux dérivés

| Champ | Formule | Effet |
|---|---|---|
| `harmonic_complexity` | `curiosity * 0.6 + creativity * 0.4` | Intervalles ouverts, polytonalité, modes exotiques |
| `rhythmic_entropy` | `frustration * 0.5 + crisis_level * 0.5` | Syncopes, ruptures de pattern |
| `source_divergence` | écart-type inter-sources | Harmonie ambiguë quand Reddit ≠ GDELT ≠ Twitter |
| `anomaly_score` | écart à la moyenne 7j | Génération forcée si état historiquement extrême |

`source_health` est critique : si une source est down, l'entité l'exclut de l'agrégation sans halluciner un état. Le Journal peut le noter : *"signal Reddit absent — excitement calculée sur 4/5 sources"*.

**Délibérément absent** : météo (non traçable), données biométriques viewer (vie privée), "sentiment des LLMs" (non mesurable).

---

### Les trois projections — pipeline parallèle

```
GlobalState (source unique, persisté SQLite à chaque update)
    │
    ├──→ music_prompt_builder()
    │       BPM        = drift_bpm (piloté par prediction_errors["excitement"] + momentum)
    │       Mood       = erreur de prédiction dominante (normalisée par volatilité apprise)
    │       Tension    = prediction_errors["anxiety"] + prediction_errors["frustration"]
    │       Divergence = prediction_errors["source_divergence"] → ambiguïté harmonique
    │       → string → Stable Audio 2.5 API → fichier audio → queue lecture
    │
    ├──→ visual_params_builder()
    │       Chaque champ GlobalState → attribut d'un nœud Three.js
    │       Couleur = valence émotionnelle du champ
    │       Rayon nœud = valeur normalisée du champ
    │       Pulsation = |delta depuis update précédente| * 10
    │       → JSON → WebSocket → Three.js → OBS Browser Source
    │
    └──→ journal_context_builder()
            Prompt = dump JSON GlobalState + deltas 30 dernières minutes + mémoire SQLite
            Instruction GPT-4o = "observe ton état interne, une ligne, temps présent"
            → string → ticker overlay → WebSocket → OBS Browser Source
```

---

### Fréquences de mise à jour

| Source | Intervalle | Contrainte |
|--------|-----------|------------|
| OpenAI Status RSS | 30s | Aucune limite — priorité #1 (Crisis Mode) |
| Reddit PRAW | 5 min | Rate limit API |
| Twitter/X | 5 min | Rate limit API |
| Google Trends RSS | 15 min | Données sub-15min inexistantes |
| HN API | 5 min | API publique sans auth |
| Wikipedia API | 15 min | Pas de RT sub-15min |
| YouTube viewers/chat | `pollingIntervalMillis` (dynamique) | Quota 10k/j — ne pas fixer un intervalle, respecter la valeur retournée par l'API |
| Journal GPT-4o | 45s | Coût + cohérence narrative |
| Music generation | 3–5 min | Durée track Stable Audio |
| GlobalState → SQLite | À chaque update | Crash recovery — jamais sauter |
| Visualization (Three.js) | 60fps | Interpolation entre snapshots |

---

### Principe fondamental : la visualisation = le code

Le graphe Three.js n'est pas dessiné à la main — il est **généré depuis les annotations du code Python**. Chaque collecteur et chaque builder est décoré. Le decorator enregistre les métadonnées dans un registre global. Le WebSocket broadcast ce registre aux clients.

```python
@node(
    name="reddit_sentiment",
    produces="excitement",
    color="#FF6B35",
    label="Reddit r/ChatGPT"
)
async def collect_reddit_sentiment(state: GlobalState) -> float:
    # code réel ici — le nœud Three.js existe parce que ce decorator existe
    ...

@node(
    name="music_prompt",
    produces="music_prompt",
    reads=["prediction_errors", "drift_bpm", "drift_key", "drift_timbre", "crisis_level"],
    color="#00D4FF",
    label="Music Prompt"
)
def build_music_prompt(state: GlobalState) -> str:
    ...
```

**Résultat** : ouvre le fichier Python → vois le nœud à l'écran. Correspondance 1-to-1. Vérifiable par n'importe quel dev dans le repo. C'est la preuve d'authenticité par le code lui-même.

---

## Génération Musicale — Architecture Technique

### Le problème économique de base

Stable Audio 2.5 = $0.20 par clip de 47s (production — `total_seconds=47`).
Budget $100/mois = 500 clips × 47s = **6.5 heures** de musique unique.
Mais un stream 24/7 = **720 heures/mois** de contenu nécessaire.

→ On ne peut pas générer un nouveau clip toutes les 3 minutes. Il faut une stratégie différente.

---

### Solution : Génération événementielle + Modulation DSP temps réel

**Principe** : deux couches superposées.

```
COUCHE 1 — Génération IA (Stable Audio 2.5)
  Déclenchée uniquement sur changement d'état significatif
  Δ > 0.15 sur n'importe quelle dimension émotionnelle
  Ou événement Crisis Mode (openai_status chute)
  Estimation : 5-15 nouvelles générations/jour = $1-3/jour = $30-90/mois ✓
  Crisis Mode : cache pré-généré (5-10 clips) rechargé en background
  → évite la génération à la demande (15-45s de latence inacceptable en crise)

COUCHE 2 — Modulation DSP temps réel (Pedalboard + pyrubberband)
  Le clip courant est transformé en continu par GlobalState
  Pedalboard applique EQ, reverb, compresseur sur chunks numpy
  pyrubberband gère le time-stretch BPM ±10% (haute qualité, sans artefact pitch)
  FFmpeg = encodeur uniquement (stdin pipe → AAC → RTMP), jamais redémarré
  Paramètres mis à jour toutes les 5s sans coupure audio
```

Entre deux générations, la musique ne répète pas bêtement — elle évolue via DSP selon l'état réel du monde. La vraie génération IA intervient seulement quand l'état change assez pour justifier une nouvelle idée musicale.

---

### Couche DSP — Architecture Pedalboard pilotée par GlobalState

```python
# dsp_engine.py — effets proportionnels aux données réelles, jamais fake
from pedalboard import Pedalboard, Reverb, Compressor, LowShelfFilter, HighShelfFilter, PeakFilter, Gain
import pyrubberband as pyrb

class DSPEngine:
    def __init__(self):
        self.bass_eq   = LowShelfFilter(cutoff_frequency_hz=200, gain_db=0.0)
        self.mid_eq    = PeakFilter(cutoff_frequency_hz=1500, gain_db=0.0, q=0.7)
        self.high_eq   = HighShelfFilter(cutoff_frequency_hz=6000, gain_db=0.0)
        self.reverb    = Reverb(room_size=0.2, wet_level=0.1, dry_level=0.9)
        self.compressor = Compressor(threshold_db=-18, ratio=2.5)
        self.gain      = Gain(gain_db=0.0)
        self.board     = Pedalboard([
            self.bass_eq, self.mid_eq, self.high_eq,
            self.reverb, self.compressor, self.gain
        ])

    def update_from_state(self, state: GlobalState) -> None:
        """Appelé toutes les 5s. Modification à chaud sans coupure."""
        # EQ émotionnel
        self.bass_eq.gain_db  = lerp(-3, +6, state.excitement)   # excitement → basses
        self.mid_eq.gain_db   = lerp(-2, +4, state.creativity)   # creativity → mid-range presence
        self.high_eq.gain_db  = lerp(0, -18, state.crisis_level) # crise → perte aigus (dégradation authentique)

        # Reverb : anxiété = isolement sonore, crise = espace qui s'emballe
        reverb_intensity      = max(state.anxiety, state.crisis_level)
        self.reverb.room_size = lerp(0.15, 0.85, reverb_intensity)
        self.reverb.wet_level = lerp(0.05, 0.50, reverb_intensity)

        # Volume : swell léger si chat actif
        self.gain.gain_db     = lerp(-2, +1, clamp(state.chat_rate / 10, 0, 1))
```

**Principe "No Fake" appliqué au DSP Crisis Mode :**

| Ce qui serait fake | Ce qu'on fait |
|---|---|
| Glitch GSM binaire ON/OFF à seuil fixe | `high_eq.gain_db` descend continûment de 0 à -18dB selon `crisis_level` |
| Tremolo aléatoire décoratif | `reverb.room_size` monte proporionnellement — le son "perd pied" pour une raison réelle |
| Effet activé par timer | Chaque paramètre DSP = fonction pure d'un champ GlobalState tracé en SQLite |

Les trois effets crisis combinés (perte aigus + reverb démesuré + micro-dérive pitch pyrubberband) donnent une sensation de "signal qui décroche" musicalement cohérente, sans artifice.

**Résultat perceptible** : un auditeur qui écoute 30 minutes entend subtilement que la musique "respire" — sans savoir que c'est le même clip transformé en temps réel par les données mondiales.

---

### Construction du prompt musical (Stable Audio 2.5)

Le prompt est une fonction pure de GlobalState. Pas de templates fixes — une formule paramétrique.

```python
# Correspondances erreurs de prédiction → descripteurs musicaux
# La couleur émotionnelle vient du profil d'erreurs, pas des valeurs absolues
PREDICTION_ERROR_MUSIC: dict[str, tuple[str, str]] = {
    # (descripteur si erreur positive, descripteur si erreur négative)
    "excitement":  ("energetic, driving rhythm, bright synths, uplifting",
                    "receding, dissolving energy, fading pulse"),
    "anxiety":     ("tense, sparse, uncertain harmonics, hollow",
                    "releasing, resolving, open space"),
    "frustration": ("dissonant, clashing elements, building tension, unresolved",
                    "smoothing, harmonic resolution, clearing"),
    "curiosity":   ("exploratory, modal harmony, unexpected turns, open-ended",
                    "settling, known patterns, familiar"),
    "creativity":  ("experimental, textural, non-standard timbres, playful",
                    "minimal, foundational, stripped"),
}

def build_music_prompt(state: GlobalState, prev_prompt: str | None) -> str:
    """Prompt = fonction pure de GlobalState. Piloté par erreurs de prédiction, pas valeurs absolues."""
    pe  = state.prediction_errors
    vol = state.signal_volatilities

    # Émotion dominante : l'erreur la plus significative (normalisée par volatilité = z-score)
    def significance(signal: str) -> float:
        v = max(vol.get(signal, 0.1), 0.001)
        return abs(pe.get(signal, 0.0)) / v

    emotions = ["excitement", "anxiety", "frustration", "curiosity", "creativity"]
    dominant = max(emotions, key=significance)
    error    = pe.get(dominant, 0.0)
    pos_desc, neg_desc = PREDICTION_ERROR_MUSIC[dominant]
    emotional_color    = pos_desc if error >= 0 else neg_desc

    # Crise infrastructure — proportionnelle, continue, traçable
    crisis_mod = ""
    if state.crisis_level > 0.5:
        crisis_mod = ", glitch artifacts, signal degradation, system failure undertone"
    elif state.crisis_level > 0.2:
        crisis_mod = ", slight instability, latency feel, tension without resolution"

    # Audience — uniquement si signal significatif (dépasse sa volatilité)
    audience_mod = ""
    if abs(pe.get("audience_energy", 0.0)) > vol.get("audience_energy", 0.1):
        audience_mod = ", collective presence, social energy" if pe.get("audience_energy", 0) > 0 else ""

    # Source divergence — quand les sources du monde se contredisent
    divergence_mod = ""
    if pe.get("source_divergence", 0.0) > vol.get("source_divergence", 0.05):
        divergence_mod = ", ambiguous tonality, conflicting signals, unresolved tension"

    return (
        f"{int(state.drift_bpm)} BPM, key of {state.drift_key}, "
        f"{state.drift_timbre} timbre, {state.drift_territory}, "
        f"{emotional_color}"
        f"{crisis_mod}{audience_mod}{divergence_mod}, "
        "high quality, no vocals, AI ambient electronic music"
    )
```

---

### Algorithme de dérive musicale (La Dérive)

La dérive est un **système dynamique piloté par les erreurs de prédiction** de l'entité sur les signaux du monde.
Pas de random walk, pas de constantes — uniquement des forces issues de la réalité.

**Principe** : quand le monde fait quelque chose que l'entité n'attendait pas, ça crée une force sur la trajectoire musicale. Quand le monde est conforme aux attentes, l'inertie continue.

```python
# Circle of fifths pour transitions cohérentes
CIRCLE_OF_FIFTHS = [
    "C major", "G major", "D major", "A major", "E major",
    "B major", "F# major", "Db major", "Ab major", "Eb major",
    "Bb major", "F major",
    "A minor", "E minor", "B minor", "F# minor", "C# minor",
    "G# minor", "Eb minor", "Bb minor", "F minor", "C minor",
    "G minor", "D minor",
]

def update_self_model(state: GlobalState, signal_name: str, new_value: float) -> None:
    """Mise à jour du self-model pour un signal. Appelé à chaque collecte.
    Apprend les baselines et les taux d'adaptation depuis les données — aucune constante fixe."""

    baseline  = state.signal_baselines.get(signal_name, new_value)
    vol       = state.signal_volatilities.get(signal_name, 0.1)

    # Taux d'adaptation : inversement proportionnel à la volatilité apprise
    # Signal bruité → τ faible (ignore le bruit), signal stable qui change → τ plus élevé
    tau = 1.0 / (1.0 + vol * 50)  # plage typique : 0.005 à 0.05

    # Mise à jour baseline par EMA (taux τ appris)
    new_baseline = (1 - tau) * baseline + tau * new_value

    # Mise à jour volatilité (variance roulante sur erreur)
    error = new_value - baseline
    new_vol = 0.95 * vol + 0.05 * error ** 2

    state.signal_baselines[signal_name]        = new_baseline
    state.signal_adaptation_rates[signal_name] = tau
    state.signal_volatilities[signal_name]     = new_vol
    state.prediction_errors[signal_name]       = error


def update_drift_weights(state: GlobalState, dim: str, signals: list[str]) -> None:
    """Renforce le poids d'un signal si son erreur de prédiction est alignée avec le momentum.
    Hebbian reinforcement : sign(PE[signal]) == sign(momentum[dim]) → poids augmente.
    Zéro constante — convergence empirique depuis l'historique réel."""
    w = state.drift_weights.setdefault(dim, {s: 1.0 / len(signals) for s in signals})
    momentum = state.drift_momentum.get(dim, 0.0)
    for s in signals:
        error = state.prediction_errors.get(s, 0.0)
        if error * momentum > 0:       # même direction → signal a prédit le mouvement
            w[s] = min(w[s] * 1.005, 2.0)
        elif error * momentum < 0:     # direction opposée → signal a trompé
            w[s] = max(w[s] * 0.995, 0.01)
    total = sum(w.values()) or 1.0
    state.drift_weights[dim] = {s: v / total for s, v in w.items()}


def update_drift(current: MusicVector, state: GlobalState, dt_h: float) -> MusicVector:
    """Dérive musicale pilotée par erreurs de prédiction + momentum accumulé.
    Aucun random, aucune constante hard-codée.
    Forces = precision-weighted PE (z-score) × poids appris par corrélation."""

    pe  = state.prediction_errors
    vol = state.signal_volatilities

    # Precision-weighted prediction error = z-score du signal
    # Force = surprise relative (pas amplitude absolue) — conforme Rao & Ballard 1999
    def pw(signal: str) -> float:
        return pe.get(signal, 0.0) / max(vol.get(signal, 0.01), 0.01)

    # ── BPM ──────────────────────────────────────────────────────────────────
    # Mise à jour des poids appris avant de calculer la force
    bpm_signals = ["excitement", "audience_energy", "world_temperature"]
    update_drift_weights(state, "bpm", bpm_signals)
    w_bpm = state.drift_weights["bpm"]

    bpm_force = (
        pw("excitement")        * w_bpm["excitement"] +
        pw("audience_energy")   * w_bpm["audience_energy"] +
        pw("world_temperature") * w_bpm["world_temperature"]
    )

    # Damping appris — inertie inversement proportionnelle à la volatilité des signaux d'énergie
    # Signal volatile → faible inertie (réactivité) | signal stable → forte inertie (continuité)
    energy_vol = (vol.get("excitement", 0.1) + vol.get("audience_energy", 0.1)) / 2
    damping = 1.0 - (1.0 / (1.0 + energy_vol * 50))  # même forme inverse que τ

    new_bpm_momentum = state.drift_momentum.get("bpm", 0.0) * damping + bpm_force * dt_h
    state.drift_momentum["bpm"] = new_bpm_momentum
    new_bpm = clamp(current.bpm + new_bpm_momentum * 40, 60, 140)  # 40 = sensibilité BPM

    # ── TONALITÉ ─────────────────────────────────────────────────────────────
    # Change quand l'erreur de tension dépasse la volatilité apprise (= seuil dynamique)
    tension_error = pe.get("anxiety", 0.0) + pe.get("frustration", 0.0)
    tension_vol   = vol.get("anxiety", 0.1) + vol.get("frustration", 0.1)
    if abs(tension_error) > tension_vol:  # seuil = volatilité apprise, pas une constante
        idx   = CIRCLE_OF_FIFTHS.index(current.key)
        shift = 1 if tension_error > 0 else -1  # direction déterminée par le signe
        new_key = CIRCLE_OF_FIFTHS[(idx + shift) % len(CIRCLE_OF_FIFTHS)]
    else:
        new_key = current.key

    # ── TIMBRE ────────────────────────────────────────────────────────────────
    # Évolue quand l'erreur de créativité dépasse sa volatilité apprise
    creativity_error = pe.get("creativity", 0.0)
    creativity_vol   = vol.get("creativity", 0.1)
    TIMBRE_SEQUENCE  = ["warm", "organic", "digital", "cold", "metallic"]
    if abs(creativity_error) > creativity_vol:
        idx        = TIMBRE_SEQUENCE.index(current.timbre)
        direction  = 1 if creativity_error > 0 else -1
        new_timbre = TIMBRE_SEQUENCE[(idx + direction) % len(TIMBRE_SEQUENCE)]
    else:
        new_timbre = current.timbre

    # ── TERRITOIRE ───────────────────────────────────────────────────────────
    # Change quand la source_divergence (sources contradictoires) dépasse sa volatilité
    # OU quand le momentum accumulé est assez fort pour sortir du territoire
    divergence_error = pe.get("source_divergence", 0.0)
    divergence_vol   = vol.get("source_divergence", 0.05)
    momentum_norm    = abs(new_bpm_momentum) + abs(state.drift_momentum.get("energy", 0.0))
    if abs(divergence_error) > divergence_vol or momentum_norm > 1.5:
        new_territory = derive_territory_from_errors(pe, vol)  # fonction pure des erreurs
    else:
        new_territory = current.territory

    return MusicVector(bpm=new_bpm, key=new_key, timbre=new_timbre, territory=new_territory)


def derive_territory_from_errors(pe: dict, vol: dict) -> str:
    """Territoire dérivé du profil d'erreurs courant — pas de random, pas de pondérations fixes."""
    # Chaque territoire correspond à un profil d'erreurs dominant
    # L'entité va vers le territoire dont le profil matche le mieux ses erreurs actuelles
    profiles = {
        # 7 territoires originaux
        "ambient":      {"excitement": -1, "anxiety": -1, "crisis_level": -1},
        "electronic":   {"excitement": +1, "curiosity": +1},
        "jazz":         {"curiosity": +1, "creativity": +1, "frustration": -1},
        "industrial":   {"frustration": +1, "crisis_level": +1, "anxiety": +1, "creativity": +1},
        "neoclassical": {"anxiety": +1, "curiosity": +1, "excitement": -1},
        "experimental": {"creativity": +1, "source_divergence": +1},
        "drone":        {"crisis_level": +1, "excitement": -1},
        # 8 nouveaux territoires (utilisent wonder / melancholy / urgency)
        "lo-fi":        {"melancholy": +1, "excitement": -1},
        "cinematic":    {"wonder": +1, "harmonic_complexity": +1},
        "darkwave":     {"anxiety": +1, "melancholy": +1, "excitement": -1},
        "techno":       {"urgency": +1, "excitement": +1, "frustration": +1},
        "psych":        {"wonder": +1, "source_divergence": +1, "curiosity": +1},
        "noise":        {"frustration": +2, "anxiety": +2, "crisis_level": +2},
        "minimalist":   {"curiosity": +1},
        "blues":        {"melancholy": +1, "frustration": +1, "excitement": -1},
    }
    # Score = alignement entre le signe des erreurs et le profil
    scores = {}
    for territory, profile in profiles.items():
        score = sum(
            pe.get(dim, 0.0) * direction / max(vol.get(dim, 0.1), 0.01)
            for dim, direction in profile.items()
        )
        scores[territory] = score
    return max(scores, key=scores.get)
```

**Ce qui a changé par rapport à l'ancienne version :**

| Ancien (supprimé) | Nouveau |
|---|---|
| `random.gauss(0, 3.0 * dt_h)` — bruit artificiel | Momentum accumulé depuis données réelles |
| `random.random() < tension * 0.03` — probabilité fixe | Seuil dynamique = volatilité apprise du signal |
| `(1 + state.phase_nuit) * 0.25` — cycle circadien | Supprimé — l'entité n'a pas de rythme humain |
| `target_bpm` avec constantes de pondération | Force = erreur de prédiction, direction déterministe |
| `random.choice([-1, 1])` — direction aléatoire | Direction = signe de l'erreur (tension hausse → mineur) |

---

### Crossfade & Gestion Queue

```python
# Crossfade entre deux clips via Pedalboard/numpy (5s de chevauchement)
# Pas de restart FFmpeg — le process reste ouvert, les chunks s'enchaînent

# Logic de queue
# - queue_length cible : >= 3 clips en avance
# - Si queue < 2 → déclencher génération urgente
# - Si Δ GlobalState > 0.15 → déclencher nouvelle génération
# - Crisis Mode → piocher dans le cache pré-généré (5-10 clips), pas de génération on-demand
# - Si cache vide ET Stable Audio down → fallback assets/fallback/ (clips génériques inclus dans le repo)
```

---

### Stratégie GPU / Infrastructure pour génération

| Scénario | Solution | Coût estimé/mois |
|----------|----------|-----------------|
| CPX22 actuel (pas de GPU) | Stable Audio 2.5 API, génération événementielle | $30-90 |
| Upgrade Hetzner CCX33 + GPU | Non disponible chez Hetzner standard | — |
| RunPod Serverless (ACE-Step-1.5) | $0.002-0.006/clip, démarrage < 10s | $5-15 pour volume équivalent |
| RunPod 24/7 RTX 4090 | Trop cher pour hébergement continu | ~$530/mois |
| Hetzner GPU AX102 | GPU dédié mais cher en continu | ~$2/h = $1440/mois |

**Recommandation V1** : Stable Audio 2.5 API + génération événementielle (5-15 clips/jour).
**Recommandation V2** : RunPod Serverless (ACE-Step-1.5) déclenché via API depuis CPX22 — économise 80-90% du coût.

---

### Le principe "No Fake" appliqué à la musique

| Ce qui serait fake (exclu) | Ce qu'on fait à la place |
|---------------------------|--------------------------|
| BPM sans fondement réel | `drift_bpm` piloté par `prediction_errors["excitement"]` + momentum — tout tracé en SQLite |
| Glitch décoratif binaire | Perte progressive aigus + reverb démesuré proportionnels à `crisis_level` (continus, traçables) |
| "Émotion" inventée dans le prompt | Prompt = fonction pure de GlobalState dont les valeurs sont dans SQLite |
| Répétition d'un clip caché | Hash de chaque clip en SQLite, détection automatique de boucle |
| Crossfade "magique" | FFmpeg `acrossfade` documenté dans le code open-source |

---

## État d'avancement

> Détail complet dans [docs/TASKS.md](docs/TASKS.md).

### Phase 0+1 — TERMINÉE ✅ (2026-05-17)

GlobalState (80+ champs), StateUpdater, SQLite WAL, self_model EMA, drift momentum, collector_runner, WebSocket 4fps, collecteur OpenAI Status RSS. 168 tests verts.

### Phase 2 — EN COURS 🔄

**Audio intelligence — TERMINÉ ✅ (2026-05-20, PRs #96–#105)**
- 15 territoires dans drift.py + music_prompt.py
- `wonder`, `melancholy`, `urgency` : champs dérivés GlobalState + self-model complet
- `strength` / `guidance_scale` / `total_seconds` state-driven (NO HARDCODE)
- `find_reference()` + `find_reusable()` : scoring state-aware (territoire + BPM + mood)
- `last_prompt_hash` : dédup génération redondante
- librosa dans `pyproject.toml` (group scripts)

**À faire — câblage prod**
- `run_audio_queue()` / `run_journal()` / `CommandEngine` dans `main.py`
- DB schema : table `journal_entries`, colonne `viewers.display_name`, champ `journal_text`

**Bloqué — activation YouTube requise**
- YouTube broadcast lifecycle, Live Chat polling, réponses GPT-4o-mini

### Phase 3 — À FAIRE ❌

Collecteurs sociaux + mondiaux (voir docs/TASKS.md pour la liste complète).

### Phase 4 — À FAIRE ❌

Pedalboard DSP + pyrubberband + FFmpeg RTMP, Three.js graph complet.

### Phase 5 — À FAIRE ❌

Spectrogram ARG, Latent Space ONNX, calendrier événements.
