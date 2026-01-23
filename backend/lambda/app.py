import os
import json
import boto3
from botocore.exceptions import ClientError

# ============ Config para contador (visitas) ============
TABLE_NAME = os.environ.get("TABLE_NAME", "")
ITEM_ID = os.environ.get("ITEM_ID", "home")  # optional

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

# ============ Config para predicción (SageMaker) ============
ENDPOINT_NAME = os.environ.get("ENDPOINT_NAME", "")  # requerido para /predict
sm_runtime = boto3.client("sagemaker-runtime")

FEATURES = [
    "Pregnancies", "Glucose", "BloodPressure", "SkinThickness",
    "Insulin", "BMI", "DiabetesPedigreeFunction", "Age"
]


def _response(status_code: int, body: dict, allow_methods: str):
    """Helper to build a consistent JSON response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
            "access-control-allow-methods": allow_methods,
            "access-control-allow-headers": "*",
        },
        "body": json.dumps(body),
    }


def _get_method(event) -> str:
    # HTTP API v2
    m = (event.get("requestContext", {})
             .get("http", {})
             .get("method", ""))
    # REST API v1 fallback (por si acaso)
    if not m:
        m = event.get("httpMethod", "")
    return str(m).upper()


# =======================
#  Handler existente: /visits (GET)
# =======================
def handler(event, context):
    method = _get_method(event)

    if method == "OPTIONS":
        return _response(200, {"ok": True}, "GET,OPTIONS")

    if method != "GET":
        return _response(405, {"error": "MethodNotAllowed"}, "GET,OPTIONS")

    if not TABLE_NAME:
        return _response(500, {"error": "Missing TABLE_NAME env var"}, "GET,OPTIONS")

    try:
        resp = table.update_item(
            Key={"id": ITEM_ID},
            UpdateExpression="ADD #v :inc",
            ExpressionAttributeNames={"#v": "visits"},
            ExpressionAttributeValues={":inc": 1},
            ReturnValues="UPDATED_NEW",
        )
        visits = int(resp["Attributes"]["visits"])
        return _response(200, {"visits": visits}, "GET,OPTIONS")

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "ClientError")
        return _response(500, {"error": "DynamoDBError", "code": code}, "GET,OPTIONS")
    except Exception:
        return _response(500, {"error": "UnhandledError"}, "GET,OPTIONS")


# =======================
#  Nuevo handler: /predict (POST)
# =======================
def predict_handler(event, context):
    method = _get_method(event)

    if method == "OPTIONS":
        return _response(200, {"ok": True}, "POST,OPTIONS")

    if method != "POST":
        return _response(405, {"error": "MethodNotAllowed"}, "POST,OPTIONS")

    if not ENDPOINT_NAME:
        return _response(500, {"error": "Missing ENDPOINT_NAME env var"}, "POST,OPTIONS")

    try:
        body = event.get("body") or "{}"
        payload = json.loads(body) if isinstance(body, str) else body

        missing = [k for k in FEATURES if k not in payload]
        if missing:
            return _response(400, {"error": "MissingFeatures", "missing": missing}, "POST,OPTIONS")

        # Normaliza tipos
        clean = {k: float(payload[k]) for k in FEATURES}
        for k in ["Pregnancies","Glucose","BloodPressure","SkinThickness","Insulin","Age"]:
            clean[k] = int(clean[k])

        resp = sm_runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType="application/json",
            Accept="application/json",
            Body=json.dumps(clean).encode("utf-8"),
        )

        out = json.loads(resp["Body"].read().decode("utf-8"))
        # out esperado: {"prediction": 0/1, "probability": float}
        return _response(200, out, "POST,OPTIONS")

    except json.JSONDecodeError:
        return _response(400, {"error": "InvalidJSON"}, "POST,OPTIONS")
    except Exception as e:
        return _response(500, {"error": "PredictError", "detail": str(e)}, "POST,OPTIONS")
