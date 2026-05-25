# NO FAKE — Checklist & Patterns conformes

> **Invariant fondamental** : tout ce qui bouge à l'écran doit être justifiable par un signal réel de GlobalState.
> Source de vérité : `DIRECTION.md` · Appliqué à tous les fichiers de `overlays/`.

---

## Test obligatoire avant tout commit

```
1. Ouvrir l'overlay dans le navigateur
2. Couper le WebSocket (onglet Network → bloquer ws://localhost:8765)
   OU figer GlobalState côté Python (Ctrl+C main.py)
3. Attendre 5 secondes
4. Si quelque chose bouge encore → FAKE → corriger ou supprimer
```

---

## Ce qui EST autorisé

| Pattern | Exemple | Justification |
|---------|---------|---------------|
| **Lerp CSS/JS vers destination data-driven** | `current = lerp(current, target, 0.05)` où `target` vient de GlobalState | L'animation converge vers un état défini par des données |
| **Temps intégré par activité** | `activityTime += signals * dt` | Le temps n'avance que si les données sont actives |
| **Porteur conditionnel** | `Math.sin(uTime * speed) * uSignal` | La vague n'existe QUE si `uSignal > 0` |
| **Base floor ≤ 5% du range** | `amp = 3 + signal * 80` (base 3 sur range 83) | Évite un écran mort total — doit être commenté explicitement |
| **`Math.random()` à l'initialisation** | Positions initiales des particules | OK une seule fois à l'init, jamais dans la boucle d'animation |
| **OrbitControls autoRotate** | `controls.autoRotate = true` à vitesse constante | Rotation caméra orbitale — mouvement de présentation, pas data-driven |

---

## Ce qui N'EST PAS autorisé

| Anti-pattern | Pourquoi | Correction |
|-------------|---------|------------|
| `Math.sin(time * constant)` comme source primaire | Mouvement indépendant des données | Multiplier par un signal : `Math.sin(time) * uSignal` |
| `Math.random()` dans la boucle RAF | Bruit visuel non tracé | OK seulement à l'init |
| Oscillateurs/attracteurs indépendants de GlobalState | Les boucles mathématiques tournent même signal=0 | Conditionner l'amplitude : `amplitude * signal` |
| Amplitude de base produisant du mouvement visible quand tous les signaux sont à zéro | Fake permanent | Base floor ≤ 5% du range max |
| Caméra orbitale temporelle `Math.sin(t * 0.04)` | Mouvement non tracé | Utiliser OrbitControls.autoRotate à vitesse fixe |
| Couleurs qui changent sans signal | Décoration non tracée | Interpoler vers couleur dérivée d'un champ GlobalState |

---

## Patterns conformes par type de scène

### Réseau neuronal (NeuralMode)
```javascript
// ✅ Taille nœud = signal normalisé
node.scale.setScalar(0.3 + signalValue * 1.2);

// ✅ Couleur = lerp vers destination data-driven
node.material.color.lerp(targetColor, 0.05);

// ✅ Pulse conditionnel
const pulse = Math.sin(time * freq) * Math.max(0, predictionError);
```

### Particules (ParticlesMode / ChaosMode)
```javascript
// ✅ Attracteur actif seulement si signal > 0
const attractorStrength = uCrisisLevel * 0.8;  // 0 si pas de crise

// ✅ Amplitude mouvement = f(signal)
const dx = (attractor.x - pos.x) * attractorStrength;

// ❌ Interdit — attracteur actif en permanence
const dx = (attractor.x - pos.x) * 0.003;
```

### Synapse / Flux (SynapseMode)
```javascript
// ✅ Vitesse flux = chat_rate
const speed = 0.1 + st.chat_rate * 0.05;

// ✅ Opacité edge = source_health
edge.material.opacity = st.source_health[sourceName] ? 0.6 : 0.1;
```

---

## Erreurs passées — ne pas répéter

| Fichier | Erreur | Correction appliquée |
|---------|--------|---------------------|
| `breathing.html` | `amp1 = 60 * (1 + excitation * 0.9)` — base 60 fake | → `amp1 = 3 + excitation * 80` |
| `psychedelic_neurons.html` | `sin(t + hash)` dans GetPos — oscillateur permanent | → signal-to-node mapping |
| `nebula.html` | `sin(time * 0.25)` micro-perturbation permanente | → PE-driven perturbation |
| `neural_network.html` | Caméra orbitale `Math.sin(t * 0.04)` | → `source_divergence` pilote l'angle |
| `visualizer.html` (NeuralMode) | FilmPass — grain permanent non tracé | → Supprimé (PR #150) |

---

## Checklist commit overlay

- [ ] Test WebSocket coupé : aucun mouvement après 5s
- [ ] Aucun `Math.random()` dans RAF/update loop
- [ ] Aucun `sin(time * constante)` sans multiplication par un signal
- [ ] Toute couleur dynamique = f(GlobalState)
- [ ] Toute vitesse/amplitude = f(GlobalState) ou constante d'affichage documentée
- [ ] Base floor commenté si utilisé : `// floor 3% — évite écran mort`
