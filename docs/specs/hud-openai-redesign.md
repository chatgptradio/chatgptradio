# HUD Redesign — Direction artistique OpenAI/ChatGPT

**Status** : BRAINSTORM EN COURS  
**Fichier cible** : `overlays/visualizer.html` (préview : `overlays/visualizer_dev.html`)  
**Contexte** : L'HUD actuel a une esthétique "terminal hacker" (Courier New, cyan néon saturé, labels en MAJUSCULES, symboles ASCII). L'objectif est de l'aligner avec la direction visuelle d'OpenAI/ChatGPT — minimaliste, propre, sans sacrifier la densité d'information.

---

## Recherche — Design Language OpenAI 2024-2025

### Palette officielle
| Token | Valeur | Usage |
|-------|--------|-------|
| Vert ChatGPT | `#10A37F` | États sains, connecté, live |
| Vert atténué | `#74aa9c` | Variante courante dans l'app |
| Pro purple | `#ab68ff` | Accents secondaires |
| Background dark | `#0d0d0d` | Fond principal |
| Surface dark | `#1a1a1a` | Cartes/panels |
| Text primary | `#ececf1` | Texte principal (dark mode) |
| Text secondary | `#9aa0a6` | Labels, métadonnées |
| Border dark | `rgba(255,255,255,0.08)` | Séparateurs, bordures |
| Warning | `#d97706` | Alertes, reconnexion |
| Error | `#ef4444` | Crise, erreurs |

### Typographie
- **Interface** : `Inter` (Google Fonts, open) — corps, labels, boutons
- **Branding officiel** : `OpenAI Sans` (ABC Dinamo, propriétaire) — non utilisable
- **Fallback** : `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
- **Données numériques** : `JetBrains Mono` — BPM, %, uptime (cohérence avec valeurs machines)
- **Poids** : 300 (léger, ambiant), 400 (corps), 500 (labels importants), 600 (titres)
- **Letter-spacing** : `0.02em` corps, `0.08–0.12em` labels uppercase

### Composants UI
- **Border-radius** : 8–12px (panels), 20px (pills/badges)
- **Grid** : base 8px
- **Glassmorphism** : `backdrop-filter: blur(12px)` + `background: rgba(13,13,13,0.55)` + `border: 1px solid rgba(255,255,255,0.06)`
- **Pas de gradient lourd** — couleurs plates avec transparence
- **Transitions** : `0.3–0.4s ease` (vs blinks brusques)

---

## État actuel → Cible

### Éléments HUD

| Élément | Actuel | Cible proposée | Statut |
|---------|--------|----------------|--------|
| **Police** | `Courier New` partout | `Inter` labels, `JetBrains Mono` valeurs | ✅ DÉCIDÉ |
| **#mode-indicator** | `◆ NEURAL` (top-left) | Supprimé | ✅ DÉCIDÉ (user) |
| **#on-air dot** | Rouge `#ff2222` pulsant | Vert `#10A37F` OU rouge — DÉBAT | 🔴 EN DISCUSSION |
| **ON AIR label** | Bold, `letter-spacing:2.5px`, rouge | `LIVE` ou `ON AIR` — petites caps, blanc | 🔴 EN DISCUSSION |
| **#ws-status** | `◌ connecting…` / `● connected` | Dots minimalistes, couleurs OpenAI | ✅ DÉCIDÉ |
| **#chat-status** | Orange vif si live | `d97706` orange chaud, même logique | ✅ DÉCIDÉ |
| **#drift panel** | Texte nu flottant, cyan | Panel glassmorphism, Inter, couleurs by type | ✅ DÉCIDÉ |
| **Labels drift** | `◈ CRISIS_LEVEL 45%` | `crisis 45%` (minuscules, valeur mono) | 🔴 EN DISCUSSION |
| **Labels drift** | `⬤ TEMP 60%` | `temp 60%` avec micro-barre de couleur | 🔴 EN DISCUSSION |
| **#sources panel** | Liste `●○ nom` verticale | Panel glassmorphism, pastilles colorées | ✅ DÉCIDÉ |
| **#journal** | Bordure gauche cyan, texte flottant | Texte gris secondaire, bordure subtile | ✅ DÉCIDÉ |
| **#event-banner** | Or `#FFD700`, glow lourd | Blanc, lettre-espacement, sans glow | ✅ DÉCIDÉ |
| **#track-info** | Cyan `#00D4FF` néon | Blanc cassé `#ececf1`, police Inter | ✅ DÉCIDÉ |
| **progress bar** | Cyan | Vert `#10A37F` | ✅ DÉCIDÉ |

---

## Points en discussion

### 1. ON AIR — rouge ou vert ?
- **Argument rouge** : Signal TV/broadcast universel. Les viewers reconnaissent immédiatement "en direct".
- **Argument vert** : Cohérence avec le vert OpenAI/ChatGPT. Visuellement plus doux sur fond noir.
- **Option hybride** : Garder le rouge pour le dot (signal direct), appliquer le vert pour `#ws-status` et les autres états.

### 2. Labels drift — niveau d'abréviation
- **Option A (minimal)** : `crisis 45%` — juste le nom du signal
- **Option B (avec unité)** : `crisis · 45%` — séparateur point médian style OpenAI
- **Option C (sans label)** : Juste une fine barre colorée sous la valeur, sans texte de label
- Question : faut-il conserver les icônes (♪ pour BPM, etc.) ou les supprimer ?

### 3. Panels glassmorphism
- Sur quels éléments : `#drift`, `#sources`, `#on-air` ? Pas `#journal` (texte seul) ?
- Padding uniforme 12px×16px, ou variable selon la densité ?

### 4. Sources health — liste vs pills
- **Liste verticale actuelle** : Lisible, beaucoup d'infos, mais verbeux
- **Rangée de pastilles** : Plus compact, moins lisible si >8 sources
- **Compteur + expand** : `✓ 6/8` cliquable → liste dépliante (mais l'overlay n'est pas interactif)

### 5. Couleur accent data vs accent interface
- Conserver `#00D4FF` cyan pour les **valeurs numériques** uniquement (BPM, %) — crée un lien visuel avec le graphe 3D
- Ou passer tout au vert `#10A37F` pour la cohérence ?

---

## Ce qui reste inchangé (NO_FAKE)
Aucune modification de la logique de mise à jour du HUD. Seuls les styles CSS et les labels textuels changent. Les signaux data-driven (`world_temperature → couleur`, `crisis_level → blink`, etc.) sont conservés — seule la couleur/police de rendu change.

---

## Implémentation prévue (après validation brainstorm)
1. Modifier CSS `visualizer.html` (police, couleurs, glassmorphism)
2. Mettre à jour `updateHUD()` — labels en minuscules, JetBrains Mono pour les valeurs
3. Ajuster positions top des éléments gauche (mode-indicator supprimé → décaler ws-status + chat-status)
4. Tests : ouvrir dans le navigateur, couper WS, vérifier NO_FAKE
