import boto3
import json
import random
import urllib.request
from urllib.error import HTTPError
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import os


REGION = os.getenv("AWS_REGION", "us-east-1")

QUEUE_URL = os.environ["QUEUE_URL"]
OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]

INDEX_NAME = os.getenv("OPENSEARCH_INDEX", "restaurants")
TABLE_NAME = os.getenv("DYNAMODB_TABLE", "yelp-restaurants")


sqs = boto3.client("sqs", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)
ses = boto3.client("ses", region_name=REGION)

SENDER_EMAIL = os.environ["SENDER_EMAIL"]


def search_restaurants(cuisine):
    """
    Search OpenSearch for restaurants matching the requested cuisine.
    """

    url = f"{OPENSEARCH_ENDPOINT}/{INDEX_NAME}/_search"

    query = {
        "size": 20,
        "query": {
            "term": {
                "Cuisine": cuisine
            }
        }
    }

    body = json.dumps(query).encode("utf-8")

    session = boto3.Session()
    credentials = session.get_credentials()

    request = AWSRequest(
        method="POST",
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json"
        }
    )

    SigV4Auth(
        credentials,
        "es",
        REGION
    ).add_auth(request)

    prepared = request.prepare()

    http_request = urllib.request.Request(
        url,
        data=body,
        headers=dict(prepared.headers),
        method="POST"
    )

    try:
        with urllib.request.urlopen(http_request) as response:
            result = json.loads(response.read().decode("utf-8"))

    except HTTPError as error:
        print("OpenSearch error:")
        print(error.read().decode("utf-8"))
        raise

    hits = result["hits"]["hits"]

    print(f"OpenSearch returned {len(hits)} restaurants")

    return hits


def get_restaurant_details(restaurant_id):
    """
    Retrieve complete restaurant information from DynamoDB.
    """

    response = table.get_item(
        Key={
            "businessId": restaurant_id
        }
    )

    return response.get("Item")

def send_email(recipient, request_data, restaurants):
    """
    Send restaurant recommendations using Amazon SES.
    """

    location = request_data["location"].title()
    cuisine = request_data["cuisine"].title()
    dining_time = request_data["diningTime"]
    number_of_people = request_data["numberOfPeople"]

    subject = f"Your {cuisine} Restaurant Suggestions"

    lines = [
        "Hello!",
        "",
        f"Here are your restaurant suggestions for {cuisine} food in {location},",
        f"for {number_of_people} people at {dining_time}.",
        ""
    ]

    for i, restaurant in enumerate(restaurants, start=1):
        lines.append(f"{i}. {restaurant.get('name', 'Unknown')}")
        lines.append(f"   Address: {restaurant.get('address', 'N/A')}")
        lines.append(f"   Rating: {restaurant.get('rating', 'N/A')}")
        lines.append(f"   Reviews: {restaurant.get('reviewCount', 'N/A')}")
        lines.append("")

    lines.append("Enjoy your meal!")
    lines.append("Dining Concierge")

    body = "\n".join(lines)

    response = ses.send_email(
        Source=SENDER_EMAIL,
        Destination={
            "ToAddresses": [recipient]
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

    print(f"SES MessageId: {response['MessageId']}")

    return response


def lambda_handler(event, context):

    print("LF2 invoked")

    # -----------------------------
    # 1. Read one request from Q1
    # -----------------------------

    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=0
    )

    messages = response.get("Messages", [])

    if not messages:
        print("No messages available in Q1")

        return {
            "statusCode": 200,
            "body": "No messages available"
        }

    message = messages[0]

    print("SQS message body:")
    print(message["Body"])

    request_data = json.loads(message["Body"])

    cuisine = request_data["cuisine"].title()
    location = request_data["location"]
    dining_time = request_data["diningTime"]
    number_of_people = request_data["numberOfPeople"]
    email = request_data["email"]

    print(f"Cuisine requested: {cuisine}")
    print(f"Location: {location}")
    print(f"Dining time: {dining_time}")
    print(f"Number of people: {number_of_people}")

    # -----------------------------
    # 2. Search OpenSearch
    # -----------------------------

    hits = search_restaurants(cuisine)

    if not hits:
        print("No matching restaurants found.")

        return {
            "statusCode": 404,
            "body": "No restaurants found"
        }

    # -----------------------------
    # 3. Randomly select restaurants
    # -----------------------------

    selected_hits = random.sample(
        hits,
        min(3, len(hits))
    )

    # -----------------------------
    # 4. Retrieve details from DynamoDB
    # -----------------------------

    restaurants = []

    for hit in selected_hits:

        restaurant_id = hit["_source"]["RestaurantID"]

        print(f"Looking up RestaurantID: {restaurant_id}")

        restaurant = get_restaurant_details(restaurant_id)

        if restaurant:
            restaurants.append(restaurant)

    print("\nRestaurant recommendations:")

    for restaurant in restaurants:
        print("-------------------------")
        print("Name:", restaurant.get("name"))
        print("Address:", restaurant.get("address"))
        print("Rating:", restaurant.get("rating"))
        print("Reviews:", restaurant.get("reviewCount"))
    
    if not restaurants:
        print("No restaurant details were retrieved.")
        return {
            "statusCode": 404,
            "body": "No restaurant details found"
        }

    send_email(
        recipient=email,
        request_data=request_data,
        restaurants=restaurants
    )

    print("Email sent successfully!")

    # Delete the SQS message only after the email was sent successfully
    sqs.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=message["ReceiptHandle"]
    )

    print("SQS message deleted successfully!")

    return {
        "statusCode": 200,
        "body": f"Sent {len(restaurants)} restaurant recommendations to {email}"
    }