import boto3
import json
import random
import urllib.request
from urllib.error import HTTPError
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


REGION = "us-east-1"

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/453388807351/Q1"

# OpenSearch domain endpoint
OPENSEARCH_ENDPOINT = (
    "https://search-restaurants-dutb6ogkgn4tyn5npj5k2tgzke."
    "us-east-1.es.amazonaws.com"
)

INDEX_NAME = "restaurants"
TABLE_NAME = "yelp-restaurants"
STATE_TABLE_NAME = "user-search-state"


# -------------------------------------
# AWS clients/resources
# -------------------------------------

sqs = boto3.client(
    "sqs",
    region_name=REGION
)

dynamodb = boto3.resource(
    "dynamodb",
    region_name=REGION
)

restaurant_table = dynamodb.Table(
    TABLE_NAME
)

state_table = dynamodb.Table(
    STATE_TABLE_NAME
)

ses = boto3.client(
    "ses",
    region_name=REGION
)

SENDER_EMAIL = "ak12378@nyu.edu"


# -------------------------------------
# OpenSearch
# -------------------------------------

def search_restaurants(cuisine):
    """
    Search OpenSearch for restaurants matching
    the requested cuisine.
    """

    url = (
        f"{OPENSEARCH_ENDPOINT}/"
        f"{INDEX_NAME}/_search"
    )

    query = {
        "size": 20,
        "query": {
            "term": {
                "Cuisine": cuisine
            }
        }
    }

    body = json.dumps(
        query
    ).encode("utf-8")

    session = boto3.Session()

    credentials = (
        session.get_credentials()
    )

    request = AWSRequest(
        method="POST",
        url=url,
        data=body,
        headers={
            "Content-Type":
                "application/json"
        }
    )

    SigV4Auth(
        credentials,
        "es",
        REGION
    ).add_auth(request)

    prepared = request.prepare()

    http_request = (
        urllib.request.Request(
            url,
            data=body,
            headers=dict(
                prepared.headers
            ),
            method="POST"
        )
    )

    try:
        with urllib.request.urlopen(
            http_request
        ) as response:

            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except HTTPError as error:

        print("OpenSearch error:")
        print(
            error.read().decode(
                "utf-8"
            )
        )

        raise

    hits = (
        result["hits"]["hits"]
    )

    print(
        f"OpenSearch returned "
        f"{len(hits)} restaurants"
    )

    return hits


# -------------------------------------
# Restaurant DynamoDB
# -------------------------------------

def get_restaurant_details(
    restaurant_id
):
    """
    Retrieve complete restaurant details
    from DynamoDB.
    """

    response = (
        restaurant_table.get_item(
            Key={
                "businessId":
                    restaurant_id
            }
        )
    )

    return response.get("Item")


# -------------------------------------
# Extra-credit state functions
# -------------------------------------

def get_previous_restaurant_ids(
    session_id
):
    """
    Retrieve the restaurant IDs sent during
    the user's previous recommendation.
    """

    response = state_table.get_item(
        Key={
            "sessionId": session_id
        }
    )

    item = response.get("Item")

    if not item:
        return []

    return item.get(
        "restaurantIds",
        []
    )


def save_restaurant_ids(
    session_id,
    restaurant_ids
):
    """
    Store the restaurant IDs that were
    successfully emailed to the user.
    """

    state_table.update_item(
        Key={
            "sessionId": session_id
        },
        UpdateExpression=(
            "SET restaurantIds = :ids"
        ),
        ExpressionAttributeValues={
            ":ids": restaurant_ids
        }
    )

    print(
        "Previous restaurant "
        "recommendations saved."
    )


# -------------------------------------
# SES
# -------------------------------------

def send_email(
    recipient,
    request_data,
    restaurants
):
    """
    Send restaurant recommendations
    using Amazon SES.
    """

    location = (
        request_data["location"]
        .title()
    )

    cuisine = (
        request_data["cuisine"]
        .title()
    )

    dining_time = (
        request_data["diningTime"]
    )

    number_of_people = (
        request_data["numberOfPeople"]
    )

    subject = (
        f"Your {cuisine} "
        f"Restaurant Suggestions"
    )

    lines = [
        "Hello!",
        "",
        (
            f"Here are your restaurant "
            f"suggestions for {cuisine} "
            f"food in {location},"
        ),
        (
            f"for {number_of_people} "
            f"people at {dining_time}."
        ),
        ""
    ]

    for i, restaurant in enumerate(
        restaurants,
        start=1
    ):

        lines.append(
            f"{i}. "
            f"{restaurant.get('name', 'Unknown')}"
        )

        lines.append(
            "   Address: "
            f"{restaurant.get('address', 'N/A')}"
        )

        lines.append(
            "   Rating: "
            f"{restaurant.get('rating', 'N/A')}"
        )

        lines.append(
            "   Reviews: "
            f"{restaurant.get('reviewCount', 'N/A')}"
        )

        lines.append("")

    lines.append(
        "Enjoy your meal!"
    )

    lines.append(
        "Dining Concierge"
    )

    body = "\n".join(lines)

    response = ses.send_email(
        Source=SENDER_EMAIL,

        Destination={
            "ToAddresses": [
                recipient
            ]
        },

        Message={
            "Subject": {
                "Data": subject
            },

            "Body": {
                "Text": {
                    "Data": body
                }
            }
        }
    )

    print(
        "SES MessageId:",
        response["MessageId"]
    )

    return response


# -------------------------------------
# Lambda handler
# -------------------------------------

def lambda_handler(
    event,
    context
):

    print("LF2 invoked")

    # ---------------------------------
    # 1. Read one message from Q1
    # ---------------------------------

    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=0
    )

    messages = response.get(
        "Messages",
        []
    )

    if not messages:

        print(
            "No messages available "
            "in Q1"
        )

        return {
            "statusCode": 200,
            "body":
                "No messages available"
        }

    message = messages[0]

    print(
        "SQS message body:"
    )

    print(
        message["Body"]
    )

    request_data = json.loads(
        message["Body"]
    )

    cuisine = (
        request_data["cuisine"]
        .title()
    )

    location = (
        request_data["location"]
    )

    dining_time = (
        request_data["diningTime"]
    )

    number_of_people = (
        request_data[
            "numberOfPeople"
        ]
    )

    email = (
        request_data["email"]
    )

    session_id = (
        request_data.get(
            "sessionId"
        )
    )

    reuse_previous = (
        request_data.get(
            "reusePrevious",
            False
        )
    )

    print(
        f"Cuisine requested: "
        f"{cuisine}"
    )

    print(
        f"Location: {location}"
    )

    print(
        f"Dining time: "
        f"{dining_time}"
    )

    print(
        f"Number of people: "
        f"{number_of_people}"
    )

    print(
        f"Reuse previous: "
        f"{reuse_previous}"
    )

    restaurants = []
    restaurant_ids = []

    # ---------------------------------
    # 2. Reuse previous restaurants
    # ---------------------------------

    if (
        reuse_previous
        and session_id
    ):

        print(
            "User requested previous "
            "restaurant recommendations."
        )

        previous_ids = (
            get_previous_restaurant_ids(
                session_id
            )
        )

        if previous_ids:

            print(
                f"Found "
                f"{len(previous_ids)} "
                f"previous restaurant IDs."
            )

            for restaurant_id in (
                previous_ids
            ):

                restaurant = (
                    get_restaurant_details(
                        restaurant_id
                    )
                )

                if restaurant:

                    restaurants.append(
                        restaurant
                    )

                    restaurant_ids.append(
                        restaurant_id
                    )

        else:

            print(
                "No previous restaurant "
                "IDs found. Generating "
                "new recommendations."
            )

    # ---------------------------------
    # 3. Generate new recommendations
    # ---------------------------------

    if not restaurants:

        print(
            "Generating new restaurant "
            "recommendations."
        )

        hits = search_restaurants(
            cuisine
        )

        if not hits:

            print(
                "No matching "
                "restaurants found."
            )

            return {
                "statusCode": 404,
                "body":
                    "No restaurants found"
            }

        selected_hits = (
            random.sample(
                hits,
                min(
                    3,
                    len(hits)
                )
            )
        )

        # -----------------------------
        # Retrieve full restaurant
        # details from DynamoDB
        # -----------------------------

        for hit in selected_hits:

            restaurant_id = (
                hit["_source"]
                ["RestaurantID"]
            )

            print(
                "Looking up "
                f"RestaurantID: "
                f"{restaurant_id}"
            )

            restaurant = (
                get_restaurant_details(
                    restaurant_id
                )
            )

            if restaurant:

                restaurants.append(
                    restaurant
                )

                restaurant_ids.append(
                    restaurant_id
                )

    # ---------------------------------
    # 4. Validate recommendations
    # ---------------------------------

    if not restaurants:

        print(
            "No restaurant details "
            "were retrieved."
        )

        return {
            "statusCode": 404,
            "body":
                "No restaurant "
                "details found"
        }

    print(
        "\nRestaurant "
        "recommendations:"
    )

    for restaurant in restaurants:

        print(
            "-------------------------"
        )

        print(
            "Name:",
            restaurant.get(
                "name"
            )
        )

        print(
            "Address:",
            restaurant.get(
                "address"
            )
        )

        print(
            "Rating:",
            restaurant.get(
                "rating"
            )
        )

        print(
            "Reviews:",
            restaurant.get(
                "reviewCount"
            )
        )

    # ---------------------------------
    # 5. Send recommendation email
    # ---------------------------------

    print(
        "\nSending restaurant "
        "recommendations..."
    )

    send_email(
        recipient=email,
        request_data=request_data,
        restaurants=restaurants
    )

    print(
        "Email sent successfully!"
    )

    # ---------------------------------
    # 6. Save restaurants as the
    #    latest recommendation
    # ---------------------------------

    if (
        session_id
        and restaurant_ids
    ):

        save_restaurant_ids(
            session_id,
            restaurant_ids
        )

    # ---------------------------------
    # 7. Delete SQS message only after
    #    successful processing
    # ---------------------------------

    sqs.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=(
            message[
                "ReceiptHandle"
            ]
        )
    )

    print(
        "SQS message deleted "
        "successfully!"
    )

    return {
        "statusCode": 200,
        "body": (
            f"Sent "
            f"{len(restaurants)} "
            "restaurant "
            "recommendations"
        )
    }