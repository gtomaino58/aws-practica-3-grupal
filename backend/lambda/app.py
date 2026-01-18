import os
import json
import boto3
from botocore.exceptions import ClientError

# DynamoDB table name passed via Lambda environment variables
TABLE_NAME = os.environ.get("TABLE_NAME", "")
if not TABLE_NAME:
    # Fail fast if not configured
    raise RuntimeError("Missing required environment variable: TABLE_NAME")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

ITEM_ID = os.environ.get("ITEM_ID", "home")  # optional: allow customization


def _response(status_code: int, body: dict):
    """Helper to build a consistent JSON response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            # CORS (adjust origin if you want to restrict later)
            "access-control-allow-origin": "*",
            "access-control-allow-methods": "GET,OPTIONS",
            "access-control-allow-headers": "*",
        },
        "body": json.dumps(body),
    }


def handler(event, context):
    # Handle preflight CORS for browser calls (optional but nice)
    method = (event.get("requestContext", {})
                  .get("http", {})
                  .get("method", "")).upper()

    if method == "OPTIONS":
        return _response(200, {"ok": True})

    try:
        # Atomic counter update: ADD visits 1
        resp = table.update_item(
            Key={"id": ITEM_ID},
            UpdateExpression="ADD #v :inc",
            ExpressionAttributeNames={"#v": "visits"},
            ExpressionAttributeValues={":inc": 1},
            ReturnValues="UPDATED_NEW",
        )
        visits = int(resp["Attributes"]["visits"])
        return _response(200, {"visits": visits})

    except ClientError as e:
        # Return a clean error payload (don’t leak too much internal detail)
        code = e.response.get("Error", {}).get("Code", "ClientError")
        return _response(500, {"error": "DynamoDBError", "code": code})

    except Exception as e:
        return _response(500, {"error": "UnhandledError"})
