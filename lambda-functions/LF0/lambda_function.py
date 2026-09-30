import json
import os
import boto3
import uuid
from datetime import datetime, timezone


lex_client = boto3.client("lexv2-runtime")

BOT_ID = os.environ["LEX_BOT_ID"]
BOT_ALIAS_ID = os.environ["LEX_BOT_ALIAS_ID"]
LOCALE_ID = os.environ.get("LEX_LOCALE_ID", "en_US")


def lambda_handler(event, context):
    print("Received API event:")
    print(json.dumps(event))

    try:
        # API Gateway proxy integration sends the request body as a string
        body = event.get("body", event)

        if isinstance(body, str):
            body = json.loads(body)

        # Request format defined by the starter API
        messages = body.get("messages", [])

        if not messages:
            return api_response(400, "No message was provided.")

        user_message = messages[0]["unstructured"]["text"]

        # Use the frontend message ID as the Lex session when available.
        # This can be improved later if your frontend supplies a persistent
        # session identifier.
        session_id = (
            messages[0]["unstructured"].get("id")
            or str(uuid.uuid4())
        )

        print("User message:", user_message)
        print("Lex session:", session_id)

        # Send user's text to Amazon Lex
        lex_response = lex_client.recognize_text(
            botId=BOT_ID,
            botAliasId=BOT_ALIAS_ID,
            localeId=LOCALE_ID,
            sessionId=session_id,
            text=user_message
        )

        print("Lex response:")
        print(json.dumps(lex_response, default=str))

        # Lex may return one or more messages
        lex_messages = lex_response.get("messages", [])

        if lex_messages:
            bot_text = " ".join(
                message.get("content", "")
                for message in lex_messages
                if message.get("content")
            )
        else:
            bot_text = "Sorry, I didn't understand that."

        return api_response(200, bot_text)

    except Exception as e:
        print("ERROR:", str(e))

        return api_response(
            500,
            "Sorry, something went wrong while processing your request."
        )


def api_response(status_code, text):
    response_body = {
        "messages": [
            {
                "type": "unstructured",
                "unstructured": {
                    "id": str(uuid.uuid4()),
                    "text": text,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
        ]
    }

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(response_body)
    }