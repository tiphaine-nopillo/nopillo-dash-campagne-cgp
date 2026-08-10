#!/usr/bin/env python3
"""
Suivi campagne CGP · refresh.py
Alimente data.json depuis HubSpot.

Principe
--------
Tout repose sur l'appartenance à des listes. Une cellule de cohorte = une liste
statique. Un KPI documentaire = une liste de documents reçus. Le chiffre cherché
est l'INTERSECTION des deux, et HubSpot sait la calculer côté serveur : deux
filtres sur ilsListIds dans le même filterGroup sont combinés en ET.

On ne récupère donc jamais les enregistrements, seulement le `total` de la
recherche. Aucune donnée personnelle ne transite ni n'est écrite.

Les cohortes se chevauchent : un contact a pu être ciblé dans plusieurs batchs.
Le total campagne est mesuré par UNION dédupliquée (opérateur IN sur toutes les
listes de cohorte), jamais par addition des cellules.

Prérequis
  export HUBSPOT_TOKEN="pat-eu1-..."
  pip install requests

Portées de l'application privée — LECTURE SEULE
  crm.objects.contacts.read
  crm.lists.read
"""
import os
import json
import time
import datetime as dt

import requests

TOKEN = os.environ["HUBSPOT_TOKEN"]
BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
SEARCH = "/crm/v3/objects/contacts/search"


def post(path, body):
    """POST avec retente exponentielle sur les limites de débit HubSpot."""
    for attempt in range(5):
        r = requests.post(BASE + path, headers=H, json=body, timeout=45)
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def count_lists(list_ids, also_in=None):
    """Nombre de contacts appartenant à l'UNE des list_ids, et le cas échéant
    présents aussi dans `also_in`.

    Deux filtres sur la même propriété dans un seul filterGroup = ET.
    `limit: 1` suffit : seul `total` nous intéresse, et ça évite de faire
    transiter des fiches contact.
    """
    filters = [{"propertyName": "hs_crm_search.ilsListIds",
                "operator": "IN",
                "values": [str(x) for x in list_ids]}]
    if also_in:
        filters.append({"propertyName": "hs_crm_search.ilsListIds",
                        "operator": "IN",
                        "values": [str(also_in)]})
    body = {"filterGroups": [{"filters": filters}],
            "properties": ["hs_object_id"],
            "limit": 1}
    return post(SEARCH, body).get("total", 0)


def load_config():
    with open("campaign.json", encoding="utf-8") as f:
        return json.load(f)


def build():
    cfg = load_config()
    doc_kpis = [k for k in cfg["kpis"] if k.get("list")]
    all_cohort_lists = [c["list_id"] for co in cfg["cohorts"] for c in co["cells"]]

    cohorts = []
    for co in cfg["cohorts"]:
        cells = []
        for c in co["cells"]:
            cell = dict(list_id=c["list_id"], list_name=c.get("list_name"),
                        audience=c["audience"], version=c.get("version"),
                        enrolled=count_lists([c["list_id"]]))
            for k in doc_kpis:
                cell[k["key"]] = count_lists([c["list_id"]], also_in=k["list"])
            cell["docs"] = sum(cell[k["key"]] for k in doc_kpis)
            cells.append(cell)
        cohorts.append(dict(id=co["id"], label=co["label"], status=co["status"],
                            status_note=co.get("status_note"),
                            sequences=co.get("sequences", []), cells=cells))
    cohorts.sort(key=lambda x: x["id"])

    # Union dédupliquée sur l'ensemble des listes de cohorte
    dedup = dict(contacts=count_lists(all_cohort_lists))
    for k in doc_kpis:
        dedup[k["key"]] = count_lists(all_cohort_lists, also_in=k["list"])

    # Totaux portefeuille, tous canaux confondus
    portfolio = {k["key"]: count_lists([k["list"]]) for k in doc_kpis}

    docs = sum(dedup[k["key"]] for k in doc_kpis)
    somme_cellules = sum(c["docs"] for co in cohorts for c in co["cells"])
    ecart = somme_cellules - docs

    target = next((k.get("target") for k in cfg["kpis"] if k.get("target")), None)

    data = dict(
        meta=dict(
            campaign=cfg["campaign"],
            generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            collected=True,
            source="HubSpot · appartenance aux listes statiques, intersections calculées côté portail",
            primary_axis=cfg.get("primary_axis", "cohort"),
            attribution_note=cfg["notes"]["attribution"],
            overlap_note=(
                f"Les cohortes se chevauchent : un même contact a pu être ciblé dans "
                f"plusieurs batchs. La somme des cellules dépasse l'union réelle de "
                f"{ecart} documents, soit {100 * ecart / docs:.1f} %. "
                f"Le niveau 1 utilise l'union dédupliquée, jamais la somme."
                if docs and ecart > 0 else
                "Aucun chevauchement détecté entre les cohortes."),
        ),
        kpis=cfg["kpis"],
        dedup=dedup,
        portfolio=portfolio,
        target=target,
        target_initial=cfg.get("target_initial"),
        cohorts=cohorts,
    )
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    n_cells = sum(len(c["cells"]) for c in cohorts)
    print(f"OK · {len(cohorts)} cohortes · {n_cells} cellules · "
          f"{dedup['contacts']} contacts ciblés · {docs} documents"
          + (f" · {100 * docs / target:.0f} % de l'objectif" if target else ""))
    if ecart > 0:
        print(f"   chevauchement : somme des cellules {somme_cellules} vs union {docs}")


if __name__ == "__main__":
    build()
