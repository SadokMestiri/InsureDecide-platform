-- ============================================================
--  InsureDecide — Schéma PostgreSQL Initial
--  Exécuté automatiquement au premier démarrage du conteneur
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ─────────────────────────────────────────
-- TABLE : CLIENTS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clients (
    client_id           VARCHAR(10) PRIMARY KEY,
    prenom              VARCHAR(50) NOT NULL,
    nom                 VARCHAR(50) NOT NULL,
    age                 INTEGER CHECK (age >= 18 AND age <= 100),
    gouvernorat         VARCHAR(50),
    profession          VARCHAR(50),
    revenu_mensuel_tnd  DECIMAL(10,2),
    date_inscription    DATE,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- TABLE : CONTRATS AUTOMOBILE
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contrats_automobile (
    contrat_id              VARCHAR(12) PRIMARY KEY,
    client_id               VARCHAR(10) REFERENCES clients(client_id),
    departement             VARCHAR(20) DEFAULT 'Automobile',
    marque                  VARCHAR(30),
    annee_vehicule          INTEGER,
    puissance_fiscale       INTEGER,
    valeur_vehicule_tnd     DECIMAL(12,2),
    prime_annuelle_tnd      DECIMAL(10,2),
    date_debut              DATE,
    date_fin                DATE,
    statut                  VARCHAR(15) CHECK (statut IN ('Actif','Résilié','Suspendu')),
    gouvernorat             VARCHAR(50),
    created_at              TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- TABLE : CONTRATS VIE
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contrats_vie (
    contrat_id              VARCHAR(12) PRIMARY KEY,
    client_id               VARCHAR(10) REFERENCES clients(client_id),
    departement             VARCHAR(20) DEFAULT 'Vie',
    type_contrat            VARCHAR(30),
    duree_ans               INTEGER,
    capital_assure_tnd      DECIMAL(12,2),
    prime_annuelle_tnd      DECIMAL(10,2),
    valeur_rachat_tnd       DECIMAL(12,2),
    date_debut              DATE,
    date_fin                DATE,
    statut                  VARCHAR(15) CHECK (statut IN ('Actif','Racheté','Échu','Suspendu')),
    age_souscription        INTEGER,
    created_at              TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- TABLE : CONTRATS IMMOBILIER
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contrats_immobilier (
    contrat_id              VARCHAR(12) PRIMARY KEY,
    client_id               VARCHAR(10) REFERENCES clients(client_id),
    departement             VARCHAR(20) DEFAULT 'Immobilier',
    type_contrat            VARCHAR(40),
    surface_m2              DECIMAL(8,2),
    valeur_bien_tnd         DECIMAL(12,2),
    prime_annuelle_tnd      DECIMAL(10,2),
    date_debut              DATE,
    date_fin                DATE,
    statut                  VARCHAR(15) CHECK (statut IN ('Actif','Résilié','Suspendu')),
    gouvernorat             VARCHAR(50),
    created_at              TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- TABLE : SINISTRES (unifiée tous départements)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sinistres (
    sinistre_id             VARCHAR(20) PRIMARY KEY,
    contrat_id              VARCHAR(12) NOT NULL,
    client_id               VARCHAR(10) REFERENCES clients(client_id),
    departement             VARCHAR(20) CHECK (departement IN ('Automobile','Vie','Immobilier')),
    type_sinistre           VARCHAR(40),
    date_sinistre           DATE,
    cout_sinistre_tnd       DECIMAL(12,2),
    statut                  VARCHAR(20) CHECK (statut IN ('Ouvert','Clôturé','En expertise','Rejeté')),
    delai_reglement_jours   INTEGER,
    suspicion_fraude        SMALLINT DEFAULT 0 CHECK (suspicion_fraude IN (0,1)),
    gouvernorat             VARCHAR(50),
    created_at              TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- TABLE : PROVISIONS (IBNR + RBNS)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS provisions (
    id                      SERIAL PRIMARY KEY,
    departement             VARCHAR(20),
    annee                   INTEGER,
    mois                    INTEGER CHECK (mois >= 1 AND mois <= 12),
    nb_sinistres_ouverts    INTEGER,
    provision_rbns_tnd      DECIMAL(14,2),
    provision_ibnr_tnd      DECIMAL(14,2),
    provision_totale_tnd    DECIMAL(14,2),
    created_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (departement, annee, mois)
);

-- ─────────────────────────────────────────
-- TABLE : KPIs MENSUELS (pré-calculés)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kpis_mensuels (
    id                          SERIAL PRIMARY KEY,
    departement                 VARCHAR(20),
    annee                       INTEGER,
    mois                        INTEGER,
    periode                     VARCHAR(7),  -- ex: "2024-03"
    nb_contrats_actifs          INTEGER,
    primes_acquises_tnd         DECIMAL(14,2),
    cout_sinistres_tnd          DECIMAL(14,2),
    nb_sinistres                INTEGER,
    frequence_sinistres_pct     DECIMAL(8,4),
    cout_moyen_sinistre_tnd     DECIMAL(12,2),
    frais_gestion_tnd           DECIMAL(14,2),
    ratio_combine_pct           DECIMAL(8,2),
    taux_resiliation_pct        DECIMAL(8,4),
    provision_totale_tnd        DECIMAL(14,2),
    nb_suspicions_fraude        INTEGER,
    created_at                  TIMESTAMP DEFAULT NOW(),
    UNIQUE (departement, annee, mois)
);

-- ─────────────────────────────────────────
-- TABLE : ÉVÉNEMENTS / ALERTES (Feed CEO)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evenements (
    id                  SERIAL PRIMARY KEY,
    departement         VARCHAR(20),
    type_evenement      VARCHAR(50),   -- 'ALERTE_KPI', 'ANOMALIE', 'INFO'
    severite            VARCHAR(10) CHECK (severite IN ('CRITIQUE','AVERTISSEMENT','INFO','POSITIF')),
    titre               TEXT NOT NULL,
    description         TEXT,
    kpi_concerne        VARCHAR(50),
    valeur_actuelle     DECIMAL(12,4),
    valeur_seuil        DECIMAL(12,4),
    decision_agent      TEXT,          -- Recommandation générée par le LLM
    est_lu              BOOLEAN DEFAULT FALSE,
    est_approuve        BOOLEAN,       -- NULL = pas encore traité
    date_evenement      TIMESTAMP DEFAULT NOW(),
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- TABLE : HISTORIQUE CONVERSATIONS AGENT
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations_agent (
    id              SERIAL PRIMARY KEY,
    session_id      UUID DEFAULT uuid_generate_v4(),
    role            VARCHAR(10) CHECK (role IN ('user','assistant')),
    contenu         TEXT NOT NULL,
    contexte_kpis   JSONB,            -- snapshot KPIs au moment de la question
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- INDEX pour performances
-- ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sinistres_departement ON sinistres(departement);
CREATE INDEX IF NOT EXISTS idx_sinistres_date ON sinistres(date_sinistre);
CREATE INDEX IF NOT EXISTS idx_sinistres_statut ON sinistres(statut);
CREATE INDEX IF NOT EXISTS idx_kpis_periode ON kpis_mensuels(departement, annee, mois);
CREATE INDEX IF NOT EXISTS idx_evenements_severite ON evenements(severite, est_lu);
CREATE INDEX IF NOT EXISTS idx_evenements_date ON evenements(date_evenement DESC);
CREATE INDEX IF NOT EXISTS idx_contrats_auto_client ON contrats_automobile(client_id);
CREATE INDEX IF NOT EXISTS idx_contrats_vie_client ON contrats_vie(client_id);
CREATE INDEX IF NOT EXISTS idx_contrats_imm_client ON contrats_immobilier(client_id);

-- ─────────────────────────────────────────
-- VUE : KPIs Consolidés (tous départements)
-- ─────────────────────────────────────────
CREATE OR REPLACE VIEW vue_kpis_consolides AS
SELECT
    periode,
    annee,
    mois,
    SUM(primes_acquises_tnd)        AS total_primes_tnd,
    SUM(cout_sinistres_tnd)         AS total_sinistres_tnd,
    SUM(nb_sinistres)               AS total_sinistres,
    SUM(nb_contrats_actifs)         AS total_contrats,
    AVG(ratio_combine_pct)          AS ratio_combine_moyen_pct,
    SUM(provision_totale_tnd)       AS total_provisions_tnd,
    SUM(nb_suspicions_fraude)       AS total_suspicions_fraude
FROM kpis_mensuels
GROUP BY periode, annee, mois
ORDER BY annee, mois;

COMMENT ON TABLE evenements IS 'Fil d événements internes détectés par les agents IA';
COMMENT ON TABLE kpis_mensuels IS 'KPIs pré-calculés mensuellement par département';
COMMENT ON TABLE conversations_agent IS 'Historique des conversations CEO avec l agent décisionnel';
