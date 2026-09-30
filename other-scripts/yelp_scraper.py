import os
import time
from datetime import datetime, timezone

import boto3
import requests
from botocore.exceptions import ClientError


API_KEY = os.getenv("YELP_API_KEY")

if not API_KEY:
    raise ValueError("YELP_API_KEY environment variable is not set")

YELP_URL = "https://api.yelp.com/v3/businesses/search"

CUISINES = [
    "Chinese",
    "Indian",
    "Italian",
    "Japanese",
    "Mexican",
    "Thai"
]

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table("yelp-restaurants")

seen_business_ids = set()


def fetch_restaurants(cuisine, offset):
    params = {
        "term": f"{cuisine} restaurants",
        "location": "Manhattan, New York, NY",
        "limit": 50,
        "offset": offset
    }

    response = requests.get(
        YELP_URL,
        headers=headers,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    return response.json().get("businesses", [])


def save_restaurant(restaurant, cuisine):
    business_id = restaurant["id"]

    location = restaurant.get("location", {})
    coordinates = restaurant.get("coordinates", {})

    item = {
        "businessId": business_id,
        "name": restaurant.get("name", ""),
        "address": ", ".join(location.get("display_address", [])),
        "coordinates": {
            "latitude": str(coordinates.get("latitude", "")),
            "longitude": str(coordinates.get("longitude", ""))
        },
        "reviewCount": restaurant.get("review_count", 0),
        "rating": str(restaurant.get("rating", "")),
        "zipCode": location.get("zip_code", ""),
        "cuisine": cuisine,
        "insertedAtTimestamp": datetime.now(timezone.utc).isoformat()
    }

    table.put_item(Item=item)


def main():
    total_inserted = 0

    for cuisine in CUISINES:
        print(f"\nCollecting {cuisine} restaurants...")

        cuisine_inserted = 0

        # Yelp allows up to 50 results per request.
        for offset in [0, 50, 100, 150]:
            try:
                restaurants = fetch_restaurants(cuisine, offset)

                if not restaurants:
                    break

                for restaurant in restaurants:
                    business_id = restaurant["id"]

                    if business_id in seen_business_ids:
                        continue

                    seen_business_ids.add(business_id)

                    save_restaurant(restaurant, cuisine)

                    cuisine_inserted += 1
                    total_inserted += 1

                print(
                    f"{cuisine}: {cuisine_inserted} unique restaurants collected"
                )

                if cuisine_inserted >= 200:
                    break

                time.sleep(0.2)

            except requests.RequestException as error:
                print(f"Yelp error for {cuisine}: {error}")
                break

            except ClientError as error:
                print(f"DynamoDB error: {error}")
                raise

        print(
            f"Finished {cuisine}: {cuisine_inserted} restaurants"
        )

    print("\n==============================")
    print(f"Total unique restaurants inserted: {total_inserted}")
    print("==============================")


if __name__ == "__main__":
    main()