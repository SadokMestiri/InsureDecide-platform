from minio import Minio

client = Minio(
    "localhost:9000",
    access_key="insuredecide_minio",
    secret_key="insuredecide_minio_pass",
    secure=False
)

if not client.bucket_exists("mlflow"):
    client.make_bucket("mlflow")
    print("✅ Bucket 'mlflow' créé")
else:
    print("ℹ️  Bucket 'mlflow' existe déjà")
