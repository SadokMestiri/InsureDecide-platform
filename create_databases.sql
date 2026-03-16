-- ============================================================
-- InsureDecide — Init bases de données séparées
-- À exécuter UNE FOIS après docker compose up postgres
-- Évite les conflits de migrations entre Airflow et MLflow
-- ============================================================

-- Base dédiée Airflow
CREATE DATABASE airflow_db;
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO insuredecide_user;

-- Base dédiée MLflow
CREATE DATABASE mlflow_db;
GRANT ALL PRIVILEGES ON DATABASE mlflow_db TO insuredecide_user;

-- Vérification
\l
