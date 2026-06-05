# Spec — Panel "OpenAI News" (HUD overlay)

**Status** : VALIDÉ  
**Fichier cible** : `overlays/visualizer_dev.html` (puis `visualizer.html` après validation)  
**Date** : 2026-05-27

---

## Objectif

Ajouter un panel "openai news" dans l'HUD, sur la gauche, qui affiche les 3 dernières publications du blog OpenAI. Le panel s'ouvre en accordéon automatiquement toutes les 15 min, reste visible 2 min, puis se referme.

---

## Source de données

**Client-side fetch** (aucun changement backend / GlobalState) via RSS2JSON :

```
https://api.rss2json.com/v1/api.json?rss_url=https://openai.com/blog/rss.xml&count=3
```

Champs utilisés par item : `title`, `thumbnail`, `pubDate`, `link`  
Fallback image : gradient CSS si `thumbnail` vide ou erreur de chargement  
En cas d'erreur fetch : panel reste collapsed, `console.warn` silencieux

---

## Layout retenu

**Option B** — feed compact avec vignettes :
- 3 items en liste verticale
- Chaque item : thumbnail 34×34px (border-radius 5px) + titre (10px, `#ececf1`) + date relative (9px, `#6b7280`)
- Header toujours visible : dot vert `#10A37F` + label `openai news`

---

## Position

`position:absolute; top:130px; left:24px`  
Sous `#status-panel` (qui finit vers ~110px), au-dessus de l'espace libre jusqu'au `#drift` panel (bottom:24px).  
Même glass style que tous les autres panels : `rgba(250,250,250,0.06)` + `blur(16px) saturate(160%)` + border `rgba(255,255,255,0.10)`.

---

## Behaviour accordéon

| Moment | Action |
|--------|--------|
| Chargement page | `fetchNews()` → expand → timer collapse 2 min |
| Toutes les 15 min | `fetchNews()` → re-expand → timer collapse 2 min |
| Après 2 min | collapse (CSS `max-height:0`) |
| Erreur fetch | panel reste collapsed, données précédentes conservées |

---

## HTML

```html
<div id="news">
  <div id="news-summary">
    <span class="status-dot dot-ok"></span>
    <span id="news-label">openai news</span>
    <span id="news-age"></span>
  </div>
  <div id="news-detail"></div>
</div>
```

---

## Invariants

- **NO_FAKE** : panel n'existe que si des données réelles ont été reçues. Zéro animation autonome.
- `source_health` non affecté (fetch indépendant du pipeline Python)
- Aucun `Math.random()` en RAF
- Images via `<img src>` — pas de `fetch()` → pas de CORS issue pour l'affichage
