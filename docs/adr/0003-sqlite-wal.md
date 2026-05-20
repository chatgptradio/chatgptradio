# ADR-0003 — SQLite WAL, connexion unique

**Statut :** VALIDÉ  
**Date :** 2026-05-17

## Contexte

Besoin de persistence légère pour snapshots d'état, historique des signaux, clips audio, journal, viewers. PostgreSQL serait overkill pour un service single-process.

## Décision

- SQLite en mode WAL (`PRAGMA journal_mode=WAL`) + `PRAGMA synchronous=NORMAL`
- Une seule connexion `aiosqlite` partagée, initialisée dans `main.py` et passée en paramètre
- Pas de connexion séparée par module

## Conséquences

- WAL permet lectures concurrentes sans bloquer les écritures
- Connexion unique évite les conflits de verrou SQLite
- Schema déclaré dans `core/db.py:_SCHEMA` — migrations idempotentes via `IF NOT EXISTS`
