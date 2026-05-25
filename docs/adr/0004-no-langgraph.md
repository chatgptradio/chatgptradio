# ADR-0004 — Pas de LangGraph, asyncio pur

**Statut :** VALIDÉ  
**Date :** 2026-05-17

## Contexte

LangGraph (orchestration multi-agent) a été évalué pour gérer le pipeline collecteurs → state → audio → DSP.

## Décision

Rejeté. `asyncio` pur avec `asyncio.Queue` comme bus central est suffisant et beaucoup plus simple.

## Raisons du rejet

- LangGraph ajoute une dépendance lourde (LangChain) pour un gain nul
- Le flux est unidirectionnel : collecteurs → StateUpdater → WebSocket/DSP
- `asyncio.Queue` offre le même découplage sans overhead
- Les tests sont plus simples sans framework d'orchestration
