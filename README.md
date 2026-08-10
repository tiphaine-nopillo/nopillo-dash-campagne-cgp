# Suivi de performance — campagne CGP Avis IRPP

Dashboard statique de suivi de la collecte de documents fiscaux, hébergé sur GitHub Pages, sans backend.

```
index.html      ← la vue (statique, jamais régénérée)
campaign.json   ← la config métier : cohortes, audiences, versions, KPI
data.json       ← la donnée (seul fichier réécrit par le workflow)
refresh.py      ← le collecteur HubSpot
```

## Ajouter une cohorte

Un bloc dans `campaign.json`, rien d'autre :

```json
{
 "id": "2026-09-02",
 "label": "Batch du 2 septembre 2026",
 "status": "EN_COURS",
 "sequences": ["8XXXXXXXX"],
 "cells": [
  {"list_id": "14XXX", "audience": "Nouveaux clients", "version": "A", "list_name": "..."}
 ]
}
```

Deux règles impératives :

- **`list_id` obligatoire sur chaque cellule.** Sans liste, aucun document ne peut être rattaché et la cellule afficherait des zéros trompeurs.
- **La liste doit être statique.** Une liste active se recalcule en continu : le dénominateur dériverait et toutes les comparaisons entre cohortes seraient fausses.

### Le statut est dérivé de HubSpot, pas saisi

`"status": "AUTO"` dans la config. À chaque refresh, le collecteur compte les contacts de chaque cellule encore activement enrôlés (`hs_sequences_is_enrolled`) et en déduit le statut :

| Statut | Signification |
|---|---|
| `TERMINE` | Plus aucun contact en séquence. La cellule alimente le taux de référence. |
| `EN_COURS` | Des contacts sont encore en séquence. Chiffres provisoires. |
| `PARTIEL` | *(cohorte)* certaines cellules ont fini, d'autres pas. |

**Le statut porte sur la cellule, pas sur la cohorte.** C'est important : le batch du 1er août a sa cellule Nouveaux clients terminée alors que sa cellule Déjà clients envoie encore. La première alimente donc déjà la référence — restreindre à la cohorte entière aurait perdu 388 contacts d'observation.

Forcer `"TERMINE"` ou `"EN_COURS"` à la place d'`AUTO` reste possible si la détection se trompe.

Deux réserves documentées dans l'onglet Méthodo :

- `hs_sequences_is_enrolled` vaut vrai pour **n'importe quelle** séquence. Un contact réenrôlé ailleurs maintient artificiellement sa cellule en cours.
- **Les documents continuent d'arriver après le dernier e-mail.** Une cellule fraîchement terminée sous-estime encore son résultat final.

## Changer les KPI

Le bloc `kpis` déclare ce qui est mesuré. Un KPI documentaire = une liste HubSpot de documents reçus :

```json
{"key": "attestation", "label": "Attestations", "list": "14XXX"}
```

Le collecteur calcule automatiquement l'intersection avec chaque cellule, l'union dédupliquée et le total portefeuille. Aucune ligne de code à modifier.

## Comment les chiffres sont obtenus

Deux filtres `ilsListIds` dans un même `filterGroup` sont combinés en **ET** par HubSpot : l'intersection est calculée côté serveur. Le collecteur ne lit que le `total` de la recherche, avec `limit: 1` — aucune fiche contact ne transite, aucune donnée personnelle n'est écrite dans `data.json`.

Le total campagne est mesuré par **union dédupliquée** (opérateur `IN` sur toutes les listes de cohorte), jamais par addition des cellules : les cohortes se chevauchent, et la somme surévalue de 13,6 % sur les données actuelles.

## Mise en ligne

1. Dépôt GitHub **public** (Pages n'est pas disponible sur dépôt privé en plan gratuit, et le site publié reste public dans tous les cas)
2. Envoyer les fichiers, en créant `.github/workflows/refresh.yml` via **Add file → Create new file** pour préserver le chemin
3. `Settings` → `Pages` → branche `main`, dossier `/ (root)`
4. `Settings` → `Secrets and variables` → `Actions` → secret `HUBSPOT_TOKEN`

## Rafraîchissement automatique

Le workflow tourne à 6 h UTC du lundi au vendredi et ne committe que si `data.json` a changé. Bouton `Run workflow` dans l'onglet Actions pour forcer une mise à jour immédiate.

## Portées de l'application privée

`crm.objects.contacts.read` et `crm.lists.read`. **Lecture seule, aucune écriture.**

## Limites assumées

- **Attribution sans date.** L'intersection dit qu'un contact ciblé a transmis un document, pas qu'il l'a transmis à cause de la campagne. Sur l'audience Déjà clients, surestimation probable. L'historique de propriété HubSpot permettrait de dater rétroactivement — chantier suivant.
- **Cohortes non exclusives.** Un contact peut appartenir à plusieurs batchs.
- **Le dispositif n'est pas un plan factoriel.** Chaque batch ne permet pas la même comparaison ; le dashboard l'écrit plutôt que d'afficher un tableau vide.

## L'objectif est cumulatif

Les 1 600 documents couvrent les viviers actuels **et à venir**. Le compteur progresse à chaque batch ajouté à `campaign.json` — il n'est jamais rapporté au seul vivier déjà ciblé.

Le bloc « Vivier nécessaire » traduit les documents restants en contacts à cibler, au taux de retour observé sur les cohortes terminées. C'est une estimation, pas une prévision : elle suppose que les prochains batchs se comportent comme les précédents.

Le facteur dominant est la **composition du vivier**, pas le message : les Nouveaux clients rendent nettement plus que les Déjà clients. Un batch orienté nouveaux clients demande donc moins de contacts pour le même résultat.

**Réserve actuelle :** une seule cohorte est terminée, et elle ne contient que des Nouveaux clients. Le taux de référence est donc mesuré sur une audience et appliqué à une population majoritairement composée de l'autre. Le dashboard affiche un bandeau « projection provisoire » et présente le chiffre comme une **borne optimiste**. Il se fiabilisera dès qu'un batch Déjà clients aura fini d'envoyer.
