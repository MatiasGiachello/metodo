"""
Presigned URLs con S3: descargar un reporte y subir evidencia de contracargo
sin pasar el archivo por nuestros servidores y sin hacer público el bucket.

Requiere:  pip install boto3   (y credenciales AWS del servicio de Archivos)
La firma se calcula localmente: generar la URL no hace ninguna llamada de red.
"""
import boto3
from botocore.config import Config

s3 = boto3.client("s3", region_name="sa-east-1",
                  config=Config(signature_version="s3v4"))  # firma SigV4
BUCKET = "pagoglobal-sa-files-prod"


def url_descarga_reporte(merchant_id: str, periodo: str) -> str:
    # Antes de firmar, el servicio verifica que el usuario pertenece al comercio.
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": f"reportes/{merchant_id}/{periodo}.csv"},
        ExpiresIn=300,  # 5 minutos
    )


def url_subida_evidencia(merchant_id: str, disputa_id: str) -> dict:
    # POST prefirmado: permite imponer condiciones (tamaño y tipo de archivo).
    return s3.generate_presigned_post(
        Bucket=BUCKET,
        Key=f"disputas/{merchant_id}/{disputa_id}/${{filename}}",
        Conditions=[
            ["content-length-range", 1, 10 * 1024 * 1024],  # máx. 10 MB
            ["starts-with", "$Content-Type", "application/pdf"],
        ],
        ExpiresIn=300,
    )


if __name__ == "__main__":
    print(url_descarga_reporte("tienda_a", "2026-10"))
    # https://pagoglobal-sa-files-prod.s3.amazonaws.com/reportes/tienda_a/2026-10.csv
    #   ?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...
    #   &X-Amz-Expires=300&X-Amz-Signature=3f9a...
    print(url_subida_evidencia("tienda_a", "dp_123"))
