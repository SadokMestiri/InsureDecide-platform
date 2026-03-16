from pydantic import BaseModel
from typing import Optional, List
from datetime import date

# ── KPI mensuel individuel
class KPIMensuel(BaseModel):
    departement: str
    annee: int
    mois: int
    periode: str
    nb_contrats_actifs: int
    primes_acquises_tnd: float
    cout_sinistres_tnd: float
    nb_sinistres: int
    frequence_sinistres_pct: float
    cout_moyen_sinistre_tnd: float
    frais_gestion_tnd: float
    ratio_combine_pct: float
    taux_resiliation_pct: float
    provision_totale_tnd: float
    nb_suspicions_fraude: int

    class Config:
        from_attributes = True

# ── Résumé global (toutes départements confondus)
class KPISummary(BaseModel):
    total_contrats_actifs: int
    total_primes_tnd: float
    total_sinistres: int
    total_cout_sinistres_tnd: float
    ratio_combine_moyen_pct: float
    taux_resiliation_moyen_pct: float
    total_provisions_tnd: float
    total_suspicions_fraude: int
    periode_label: str

# ── KPI par département (dernière période)
class KPIDepartement(BaseModel):
    departement: str
    periode: str
    nb_contrats_actifs: int
    primes_acquises_tnd: float
    cout_sinistres_tnd: float
    nb_sinistres: int
    frequence_sinistres_pct: float
    cout_moyen_sinistre_tnd: float
    ratio_combine_pct: float
    taux_resiliation_pct: float
    provision_totale_tnd: float
    nb_suspicions_fraude: int
    tendance_ratio: Optional[str] = None   # "hausse" | "baisse" | "stable"
    variation_ratio_pct: Optional[float] = None

# ── Point de données pour graphique temporel
class EvolutionPoint(BaseModel):
    periode: str
    annee: int
    mois: int
    valeur: float
    departement: str

# ── Réponse évolution temporelle
class EvolutionResponse(BaseModel):
    indicateur: str
    unite: str
    departements: List[str]
    series: List[EvolutionPoint]

# ── Point comparaison barres
class ComparaisonPoint(BaseModel):
    departement: str
    primes_acquises_tnd: float
    cout_sinistres_tnd: float
    frais_gestion_tnd: float
    ratio_combine_pct: float
    taux_resiliation_pct: float
    nb_sinistres: int
    nb_contrats_actifs: int

# ── Alerte anomalie
class Alerte(BaseModel):
    id: str
    departement: str
    type_alerte: str          # "ratio_eleve" | "fraude" | "resiliation" | "sinistres"
    severite: str             # "critique" | "warning" | "info"
    message: str
    valeur_actuelle: float
    seuil: float
    periode: str
    recommandation: str

# ── Réponse dashboard principal
class DashboardResponse(BaseModel):
    summary: KPISummary
    par_departement: List[KPIDepartement]
    alertes: List[Alerte]
    derniere_mise_a_jour: str
