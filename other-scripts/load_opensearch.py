import os
import boto3

from opensearchpy import (
    OpenSearch,
    RequestsHttpConnection,
    AWSV4SignerAuth,
    helpers,
)

REGION = "us-east-1"
SERVICE = "es"
INDEX_NAME = "restaurants"
TABLE_NAME = "yelp-restaurants"

endpoint = os.getenv("OPENSEARCH_ENDPOINT")

if not endpoint:
    raise ValueError("OPENSEARCH_ENDPOINT environment variable is not set")

host = endpoint.replace("https://", "").rstrip("/")

session = boto3.Session()
credentials = session.get_credentials()
auth = AWSV4SignerAuth(credentials, REGION, SERVICE)

client = OpenSearch(
    hosts=[{"host": host, "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
)

dynamodb = session.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)


def get_all_restaurants():
    """Scan the entire DynamoDB table, handling pagination."""
    restaurants = []

    response = table.scan()
    restaurants.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.scan(
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        restaurants.extend(response.get("Items", []))

    return restaurants


def create_index():
    if client.indices.exists(index=INDEX_NAME):
        print(f"Index already exists: {INDEX_NAME}")
        return

    client.indices.create(
        index=INDEX_NAME,
        body={
            "mappings": {
                "properties": {
                    "RestaurantID": {
                        "type": "keyword"
                    },
                    "Cuisine": {
                        "type": "keyword"
                    }
                }
            }
        },
    )

    print(f"Created index: {INDEX_NAME}")


def load_restaurants(restaurants):
    actions = []

    for restaurant in restaurants:
        business_id = restaurant.get("businessId")
        cuisine = restaurant.get("cuisine")

        if not business_id or not cuisine:
            continue

        actions.append(
            {
                "_index": INDEX_NAME,
                "_id": business_id,
                "_source": {
                    "RestaurantID": business_id,
                    "Cuisine": cuisine
                }
            }
        )

    success, errors = helpers.bulk(
        client,
        actions,
        refresh=True,
        raise_on_error=False
    )

    print(f"Successfully indexed: {success}")

    if errors:
        print(f"Failed documents: {len(errors)}")
    else:
        print("Failed documents: 0")


def verify_index():
    count = client.count(index=INDEX_NAME)

    print("\n==============================")
    print(f"Documents in OpenSearch: {count['count']}")
    print("==============================")

    result = client.search(
        index=INDEX_NAME,
        body={
            "size": 5,
            "query": {
                "term": {
                    "Cuisine": "Indian"
                }
            }
        },
    )

    print("\nSample Indian restaurants:")

    for hit in result["hits"]["hits"]:
        print(hit["_source"])


def main():
    create_index()

    print("\nReading restaurants from DynamoDB...")
    restaurants = get_all_restaurants()

    print(f"Restaurants read from DynamoDB: {len(restaurants)}")

    print("\nLoading restaurants into OpenSearch...")
    load_restaurants(restaurants)

    if client.exists(
        index=INDEX_NAME,
        id="test-restaurant-001"
    ):
        client.delete(
            index=INDEX_NAME,
            id="test-restaurant-001",
            refresh=True
        )
        print("Removed test restaurant.")

    verify_index()


if __name__ == "__main__":
    main()