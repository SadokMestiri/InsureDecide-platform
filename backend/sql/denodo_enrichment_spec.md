# Denodo Enrichment Spec for InsureDecide

## Objectif
Garantir une parité fonctionnelle complete des dashboards en mode Denodo-first.

## Vues Denodo a enrichir

### 1) vue_kpis_enrichis
Utilisee par KPIs, dashboard principal, alertes, comparaisons, evolution.

Colonnes obligatoires:
- annee (int)
- mois (int)
- periode (string, format YYYY-MM)
- departement (Automobile, Vie, Immobilier)
- nb_contrats_actifs (int)
- primes_acquises_tnd (numeric)
- cout_sinistres_tnd (numeric)
- nb_sinistres (int)
- frais_gestion_tnd (numeric)
- ratio_combine_pct (numeric)
- taux_resiliation_pct (numeric)
- provision_totale_tnd (numeric)
- nb_suspicions_fraude (int)

Colonnes recommandees:
- frequence_sinistres_pct (numeric)
- cout_moyen_sinistre_tnd (numeric)

Regles utiles:
- ratio_combine_pct = (cout_sinistres_tnd + frais_gestion_tnd) / NULLIF(primes_acquises_tnd,0) * 100
- frequence_sinistres_pct = nb_sinistres / NULLIF(nb_contrats_actifs,0) * 100
- cout_moyen_sinistre_tnd = cout_sinistres_tnd / NULLIF(nb_sinistres,0)

---

### 2) vue_sinistres_enrichis
Utilisee par Carte, Risque, detail client, detail gouvernorat.

Colonnes obligatoires:
- sinistre_id (string)
- client_id (string)
- contrat_id (string)
- date_sinistre (date/timestamp)
- cout_sinistre_tnd (numeric)
- gouvernorat (string)
- departement (string)
- type_sinistre (string)
- suspicion_fraude (boolean)
- statut (string)
- nom (string)
- prenom (string)
- age (int)

Notes:
- client_id et contrat_id ne doivent pas etre null pour la majorite des lignes.
- departement doit etre renseigne pour eviter Inconnu sur la carte.

---

### 3) vue_contrats_unifies
Utilisee par Risque et Carte (taux de sinistralite par gouvernorat).

Colonnes obligatoires:
- contrat_id (string)
- client_id (string)
- departement (Automobile, Vie, Immobilier)
- date_debut (date)
- date_fin (date)
- prime_annuelle_tnd (numeric)
- statut (string, Actif attendu)
- gouvernorat (string)

Notes:
- gouvernorat est indispensable pour le calcul nb_contrats/taux_sinistralite sur la carte.
- Pour le departement Vie, si gouvernorat n est pas dans la table source, faire le join via clients.

---

### 4) vue_client_360
Utilisee par detail client (Risque).

Colonnes obligatoires:
- client_id (string)
- nom (string)
- prenom (string)
- age (int)
- gouvernorat (string)
- profession (string)
- revenu_mensuel_tnd (numeric)
- date_inscription (date)

Colonnes recommandees:
- nb_contrats_auto (int)
- nb_contrats_vie (int)
- nb_contrats_immo (int)
- nb_sinistres (int)

---

### 5) vue_geo_resume (optionnel)
Actuellement non bloquante dans le code, mais utile pour supervision geo.

Colonnes recommandees:
- gouvernorat
- nb_sinistres
- cout_total_tnd
- cout_moyen_tnd

## Mapping source recommande (exemple)
- kpis_mensuels -> vue_kpis_enrichis
- sinistres + clients -> vue_sinistres_enrichis
- contrats_automobile + contrats_vie + contrats_immobilier + clients -> vue_contrats_unifies
- clients + agregats contrats/sinistres -> vue_client_360

## Verifications rapides post-enrichissement

1. Sanity des colonnes:
- SELECT TOP 5 * FROM vue_kpis_enrichis
- SELECT TOP 5 * FROM vue_sinistres_enrichis
- SELECT TOP 5 * FROM vue_contrats_unifies
- SELECT TOP 5 * FROM vue_client_360

2. Null checks critiques:
- SELECT COUNT(*) FROM vue_sinistres_enrichis WHERE client_id IS NULL
- SELECT COUNT(*) FROM vue_sinistres_enrichis WHERE departement IS NULL
- SELECT COUNT(*) FROM vue_contrats_unifies WHERE gouvernorat IS NULL
- SELECT COUNT(*) FROM vue_kpis_enrichis WHERE nb_contrats_actifs IS NULL

3. Controle de cardinalite:
- KPI: 3 lignes par periode (Automobile, Vie, Immobilier)
- Risque: contrats Actif > 0 et client_id non null
- Carte: gouvernorats non null, departement renseigne

## Impact dashboards
- KPI dashboards: depend de vue_kpis_enrichis
- Carte: depend de vue_sinistres_enrichis + vue_contrats_unifies
- Risque: depend de vue_sinistres_enrichis + vue_contrats_unifies + vue_client_360
- Agent IA chiffrages/alertes: depend de vue_kpis_enrichis

## Definition of done
- Tous les endpoints dashboards repondent avec denodo source disponible.
- Plus de valeurs Inconnu significatives sur departement/gouvernorat.
- Les compteurs KPI ne retournent plus 0 sur nb_contrats_actifs quand des contrats existent.
