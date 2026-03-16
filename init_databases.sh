#!/bin/bash
# ============================================================
# InsureDecide — Création des bases dédiées
# Exécuté automatiquement par PostgreSQL au premier démarrage
# ============================================================
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Base dédiée Airflow
    SELECT 'CREATE DATABASE airflow_db'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow_db')\gexec

    GRANT ALL PRIVILEGES ON DATABASE airflow_db TO $POSTGRES_USER;

    -- Base dédiée MLflow
    SELECT 'CREATE DATABASE mlflow_db'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mlflow_db')\gexec

    GRANT ALL PRIVILEGES ON DATABASE mlflow_db TO $POSTGRES_USER;
EOSQL

echo "✅ Bases airflow_db et mlflow_db créées"
