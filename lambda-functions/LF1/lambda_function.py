import json
import os
import boto3

sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

QUEUE_URL = os.environ["Q1_QUEUE_URL"]
STATE_TABLE_NAME = "user-search-state"

state_table = dynamodb.Table(STATE_TABLE_NAME)


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
    # Check whether normal slots exist
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

    # Lex still needs to collect normal information
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

    # ---------------------------
    # Check previous search state
    # ---------------------------

    session_id = event["sessionId"]

    previous_search = get_previous_search(session_id)

    repeat_previous = get_slot_value(
        slots,
        "RepeatPrevious"
    )

    same_previous_search = False

    if previous_search:
        previous_location = previous_search.get(
            "location",
            ""
        ).lower()

        previous_cuisine = previous_search.get(
            "cuisine",
            ""
        ).lower()

        same_previous_search = (
            previous_location
            == request["location"].lower()
            and
            previous_cuisine
            == request["cuisine"].lower()
        )

    # ---------------------------
    # Ask whether user wants
    # previous recommendations
    # ---------------------------

    if same_previous_search and not repeat_previous:

        return {
            "sessionState": {
                "dialogAction": {
                    "type": "ElicitSlot",
                    "slotToElicit": "RepeatPrevious"
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
                        "You previously searched for the same location "
                        "and cuisine. Would you like the same restaurant "
                        "recommendations as last time?"
                }
            ]
        }

    # ---------------------------
    # Add repeat choice to request
    # ---------------------------

    reuse_previous = False

    if repeat_previous:
        reuse_previous = (
            repeat_previous.lower() == "yes"
        )

    request["reusePrevious"] = reuse_previous
    request["sessionId"] = session_id

    print("Dining request:")
    print(json.dumps(request))

    # ---------------------------
    # Save latest search state
    # ---------------------------

    save_search_state(
        session_id,
        request["location"],
        request["cuisine"]
    )

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


def get_previous_search(session_id):
    """
    Retrieve the user's previous search state.
    """

    response = state_table.get_item(
        Key={
            "sessionId": session_id
        }
    )

    return response.get("Item")


def save_search_state(
    session_id,
    location,
    cuisine
):
    """
    Save the user's latest location and cuisine
    without removing stored restaurant IDs.
    """

    state_table.update_item(
        Key={
            "sessionId": session_id
        },
        UpdateExpression=(
            "SET #location = :location, "
            "#cuisine = :cuisine"
        ),
        ExpressionAttributeNames={
            "#location": "location",
            "#cuisine": "cuisine"
        },
        ExpressionAttributeValues={
            ":location": location.lower(),
            ":cuisine": cuisine.lower()
        }
    )


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