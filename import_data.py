"""
InsureDecide — Import des CSV dans PostgreSQL
Colonnes alignées sur les vrais CSV générés.
Exécuter : python import_data.py
"""
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os, sys

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "database": "insuredecide",
    "user": "insuredecide_user",
    "password": "insuredecide_pass"
}
DATASETS_DIR = r"C:\Users\LENOVO\Desktop\PFE\DataSets"

def connect():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Connexion PostgreSQL OK")
        return conn
    except Exception as e:
        print(f"❌ Erreur connexion : {e}"); sys.exit(1)

def run(conn, sql, data, label):
    cur = conn.cursor()
    execute_values(cur, sql, data)
    conn.commit(); cur.close()
    print(f"   ✅ {len(data)} {label} importés")

def main():
    print("=" * 55)
    print("  InsureDecide — Import des données")
    print("=" * 55)
    conn = connect()

    # Recréer les tables adaptées aux vrais CSV
    print("\n🔧 Création des tables adaptées aux CSV...")
    cur = conn.cursor()
    cur.execute("""
        DROP TABLE IF EXISTS sinistres, provisions, kpis_mensuels,
            contrats_automobile, contrats_vie, contrats_immobilier, clients CASCADE;

        CREATE TABLE clients (
            client_id VARCHAR PRIMARY KEY,
            prenom VARCHAR, nom VARCHAR, age INTEGER,
            gouvernorat VARCHAR, profession VARCHAR,
            revenu_mensuel_tnd NUMERIC, date_inscription DATE
        );

        CREATE TABLE contrats_automobile (
            contrat_id VARCHAR PRIMARY KEY, client_id VARCHAR,
            departement VARCHAR, marque VARCHAR,
            annee_vehicule INTEGER, puissance_fiscale INTEGER,
            valeur_vehicule_tnd NUMERIC, prime_annuelle_tnd NUMERIC,
            date_debut DATE, date_fin DATE,
            statut VARCHAR, gouvernorat VARCHAR
        );

        CREATE TABLE contrats_vie (
            contrat_id VARCHAR PRIMARY KEY, client_id VARCHAR,
            departement VARCHAR, type_contrat VARCHAR,
            duree_ans INTEGER, capital_assure_tnd NUMERIC,
            prime_annuelle_tnd NUMERIC, valeur_rachat_tnd NUMERIC,
            date_debut DATE, date_fin DATE,
            statut VARCHAR, age_souscription INTEGER
        );

        CREATE TABLE contrats_immobilier (
            contrat_id VARCHAR PRIMARY KEY, client_id VARCHAR,
            departement VARCHAR, type_contrat VARCHAR,
            surface_m2 NUMERIC, valeur_bien_tnd NUMERIC,
            prime_annuelle_tnd NUMERIC, date_debut DATE,
            date_fin DATE, statut VARCHAR, gouvernorat VARCHAR
        );

        CREATE TABLE sinistres (
            sinistre_id VARCHAR PRIMARY KEY, contrat_id VARCHAR,
            client_id VARCHAR, departement VARCHAR,
            type_sinistre VARCHAR, date_sinistre DATE,
            cout_sinistre_tnd NUMERIC, statut VARCHAR,
            delai_reglement_jours NUMERIC,
            suspicion_fraude BOOLEAN, gouvernorat VARCHAR
        );

        CREATE TABLE provisions (
            id SERIAL PRIMARY KEY,
            departement VARCHAR, annee INTEGER, mois INTEGER,
            nb_sinistres_ouverts INTEGER,
            provision_rbns_tnd NUMERIC, provision_ibnr_tnd NUMERIC,
            provision_totale_tnd NUMERIC
        );

        CREATE TABLE kpis_mensuels (
            id SERIAL PRIMARY KEY,
            departement VARCHAR, annee INTEGER, mois INTEGER,
            periode VARCHAR, nb_contrats_actifs INTEGER,
            primes_acquises_tnd NUMERIC, cout_sinistres_tnd NUMERIC,
            nb_sinistres INTEGER, frequence_sinistres_pct NUMERIC,
            cout_moyen_sinistre_tnd NUMERIC, frais_gestion_tnd NUMERIC,
            ratio_combine_pct NUMERIC, taux_resiliation_pct NUMERIC,
            provision_totale_tnd NUMERIC, nb_suspicions_fraude INTEGER
        );
    """)
    conn.commit(); cur.close()
    print("   ✅ Tables créées")

    print("\n📂 Chargement des CSV...")
    D = DATASETS_DIR
    clients       = pd.read_csv(f"{D}/clients.csv")
    c_auto        = pd.read_csv(f"{D}/contrats_automobile.csv")
    c_vie         = pd.read_csv(f"{D}/contrats_vie.csv")
    c_immo        = pd.read_csv(f"{D}/contrats_immobilier.csv")
    s_auto        = pd.read_csv(f"{D}/sinistres_automobile.csv")
    s_vie         = pd.read_csv(f"{D}/sinistres_vie.csv")
    s_immo        = pd.read_csv(f"{D}/sinistres_immobilier.csv")
    provisions    = pd.read_csv(f"{D}/provisions.csv")
    kpis          = pd.read_csv(f"{D}/kpis_mensuels.csv")
    print("   ✅ Tous les CSV chargés\n")

    # ── CLIENTS
    print(f"📥 Import clients ({len(clients)} lignes)...")
    run(conn, """
        INSERT INTO clients VALUES %s ON CONFLICT DO NOTHING
    """, [tuple(r) for r in clients[["client_id","prenom","nom","age",
        "gouvernorat","profession","revenu_mensuel_tnd","date_inscription"]].itertuples(index=False)],
    "clients")

    # ── CONTRATS AUTO
    print(f"📥 Import contrats automobile ({len(c_auto)} lignes)...")
    run(conn, "INSERT INTO contrats_automobile VALUES %s ON CONFLICT DO NOTHING",
        [tuple(r) for r in c_auto[["contrat_id","client_id","departement","marque",
        "annee_vehicule","puissance_fiscale","valeur_vehicule_tnd","prime_annuelle_tnd",
        "date_debut","date_fin","statut","gouvernorat"]].itertuples(index=False)],
    "contrats auto")

    # ── CONTRATS VIE
    print(f"📥 Import contrats vie ({len(c_vie)} lignes)...")
    run(conn, "INSERT INTO contrats_vie VALUES %s ON CONFLICT DO NOTHING",
        [tuple(r) for r in c_vie[["contrat_id","client_id","departement","type_contrat",
        "duree_ans","capital_assure_tnd","prime_annuelle_tnd","valeur_rachat_tnd",
        "date_debut","date_fin","statut","age_souscription"]].itertuples(index=False)],
    "contrats vie")

    # ── CONTRATS IMMO
    print(f"📥 Import contrats immobilier ({len(c_immo)} lignes)...")
    run(conn, "INSERT INTO contrats_immobilier VALUES %s ON CONFLICT DO NOTHING",
        [tuple(r) for r in c_immo[["contrat_id","client_id","departement","type_contrat",
        "surface_m2","valeur_bien_tnd","prime_annuelle_tnd","date_debut",
        "date_fin","statut","gouvernorat"]].itertuples(index=False)],
    "contrats immo")

    # ── SINISTRES (fusion des 3 fichiers)
    total_sin = len(s_auto) + len(s_vie) + len(s_immo)
    print(f"📥 Import sinistres ({total_sin} lignes)...")
    cols_auto = ["sinistre_id","contrat_id","client_id","departement",
                 "type_sinistre","date_sinistre","cout_sinistre_tnd",
                 "statut","delai_reglement_jours","suspicion_fraude","gouvernorat"]
    # vie et immo n'ont pas toutes ces colonnes — on ajoute les manquantes
    for df in [s_vie, s_immo]:
        if "delai_reglement_jours" not in df.columns:
            df["delai_reglement_jours"] = None
        if "gouvernorat" not in df.columns:
            df["gouvernorat"] = None
    all_sin = pd.concat([s_auto[cols_auto], s_vie[cols_auto], s_immo[cols_auto]])
    all_sin["suspicion_fraude"] = all_sin["suspicion_fraude"].fillna(0).astype(bool)
    all_sin["delai_reglement_jours"] = pd.to_numeric(all_sin["delai_reglement_jours"], errors="coerce")
    all_sin = all_sin.where(pd.notnull(all_sin), None)
    run(conn, "INSERT INTO sinistres VALUES %s ON CONFLICT DO NOTHING",
        [tuple(r) for r in all_sin.itertuples(index=False)], "sinistres")

    # ── PROVISIONS
    print(f"📥 Import provisions ({len(provisions)} lignes)...")
    run(conn, """
        INSERT INTO provisions (departement,annee,mois,nb_sinistres_ouverts,
            provision_rbns_tnd,provision_ibnr_tnd,provision_totale_tnd) VALUES %s
    """, [tuple(r) for r in provisions[["departement","annee","mois",
        "nb_sinistres_ouverts","provision_rbns_tnd","provision_ibnr_tnd",
        "provision_totale_tnd"]].itertuples(index=False)], "provisions")

    # ── KPIs
    print(f"📥 Import KPIs ({len(kpis)} lignes)...")
    run(conn, """
        INSERT INTO kpis_mensuels (departement,annee,mois,periode,nb_contrats_actifs,
            primes_acquises_tnd,cout_sinistres_tnd,nb_sinistres,frequence_sinistres_pct,
            cout_moyen_sinistre_tnd,frais_gestion_tnd,ratio_combine_pct,
            taux_resiliation_pct,provision_totale_tnd,nb_suspicions_fraude) VALUES %s
    """, [tuple(r) for r in kpis[["departement","annee","mois","periode",
        "nb_contrats_actifs","primes_acquises_tnd","cout_sinistres_tnd","nb_sinistres",
        "frequence_sinistres_pct","cout_moyen_sinistre_tnd","frais_gestion_tnd",
        "ratio_combine_pct","taux_resiliation_pct","provision_totale_tnd",
        "nb_suspicions_fraude"]].itertuples(index=False)], "KPIs")

    conn.close()
    print("\n" + "=" * 55)
    print("  🎉 Import terminé avec succès !")
    print("=" * 55)

if __name__ == "__main__":
    main()