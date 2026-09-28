import json

def lambda_handler(event, context):
    print("Received event:")
    print(json.dumps(event))

    response_body = {
        "messages": [
            {
                "type": "unstructured",
                "unstructured": {
                    "id": "1",
                    "text": "I'm still under development. Please come back later.",
                    "timestamp": "2026-09-27T00:00:00Z"
                }
            }
        ]
    }

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(response_body)
    }