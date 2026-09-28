import json
import os
import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["Q1_QUEUE_URL"]


def lambda_handler(event, context):
    print(json.dumps(event))

    intent_name = event["sessionState"]["intent"]["name"]

    if intent_name == "GreetingIntent":
        return close(
            event,
            "Hi there, how can I help?"
        )

    if intent_name == "ThankYouIntent":
        return close(
            event,
            "You're welcome! Have a great day."
        )

    if intent_name == "DiningSuggestionsIntent":
        return handle_dining_suggestions(event)

    return close(
        event,
        "Sorry, I didn't understand that."
    )


def handle_dining_suggestions(event):
    intent = event["sessionState"]["intent"]
    slots = intent.get("slots") or {}

    # ---------------------------
    # Validate location
    # ---------------------------

    location = get_slot_value(slots, "Location")

    if location and location.lower() != "manhattan":

        slots["Location"] = None

        return {
            "sessionState": {
                "dialogAction": {
                    "type": "ElicitSlot",
                    "slotToElicit": "Location"
                },
                "intent": {
                    "name": "DiningSuggestionsIntent",
                    "slots": slots,
                    "state": "InProgress"
                }
            },
            "messages": [
                {
                    "contentType": "PlainText",
                    "content":
                        "Sorry, I can only provide restaurant "
                        "suggestions for Manhattan. Please enter Manhattan."
                }
            ]
        }

    # ---------------------------
    # Check whether all slots exist
    # ---------------------------

    required_slots = [
        "Location",
        "Cuisine",
        "DiningTime",
        "NumberOfPeople",
        "EmailType"
    ]

    all_slots_filled = all(
        get_slot_value(slots, slot)
        for slot in required_slots
    )

    # Lex still needs to collect information
    if not all_slots_filled:
        return {
            "sessionState": {
                "dialogAction": {
                    "type": "Delegate"
                },
                "intent": intent
            }
        }

    # ---------------------------
    # Extract completed request
    # ---------------------------

    request = {
        "location": get_slot_value(slots, "Location"),
        "cuisine": get_slot_value(slots, "Cuisine"),
        "diningTime": get_slot_value(slots, "DiningTime"),
        "numberOfPeople": get_slot_value(slots, "NumberOfPeople"),
        "email": get_slot_value(slots, "EmailType")
    }

    print("Dining request:")
    print(json.dumps(request))

    # ---------------------------
    # Send request to SQS
    # ---------------------------

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(request)
    )

    return close(
        event,
        "You're all set. I received your request and "
        "will send you restaurant suggestions by email shortly!"
    )


def get_slot_value(slots, slot_name):

    slot = slots.get(slot_name)

    if not slot:
        return None

    value = slot.get("value")

    if not value:
        return None

    return value.get("interpretedValue")


def close(event, message):

    intent = event["sessionState"]["intent"]
    intent["state"] = "Fulfilled"

    return {
        "sessionState": {
            "dialogAction": {
                "type": "Close"
            },
            "intent": intent
        },
        "messages": [
            {
                "contentType": "PlainText",
                "content": message
            }
        ]
    }