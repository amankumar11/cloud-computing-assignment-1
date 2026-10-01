import os
import boto3

from opensearchpy import (
    OpenSearch,
    RequestsHttpConnection,
    AWSV4SignerAuth,
)

REGION = "us-east-1"
SERVICE = "es"

LF2_ROLE_ARN = os.getenv("LF2_ROLE_ARN")

endpoint = os.getenv("OPENSEARCH_ENDPOINT")

if not endpoint:
    raise ValueError("OPENSEARCH_ENDPOINT is not set")

host = endpoint.replace("https://", "").rstrip("/")

session = boto3.Session()
credentials = session.get_credentials()

auth = AWSV4SignerAuth(
    credentials,
    REGION,
    SERVICE
)

client = OpenSearch(
    hosts=[
        {
            "host": host,
            "port": 443
        }
    ],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
)


# -------------------------------------
# 1. Create OpenSearch security role
# -------------------------------------

role_body = {
    "cluster_permissions": [],
    "index_permissions": [
        {
            "index_patterns": [
                "restaurants"
            ],
            "allowed_actions": [
                "read"
            ]
        }
    ],
    "tenant_permissions": []
}

response = client.transport.perform_request(
    method="PUT",
    url="/_plugins/_security/api/roles/lf2_restaurant_search",
    body=role_body
)

print("Role creation response:")
print(response)


# -------------------------------------
# 2. Map Lambda execution role
# -------------------------------------

mapping_body = {
    "backend_roles": [
        LF2_ROLE_ARN
    ],
    "hosts": [],
    "users": []
}

response = client.transport.perform_request(
    method="PUT",
    url="/_plugins/_security/api/rolesmapping/lf2_restaurant_search",
    body=mapping_body
)

print("\nRole mapping response:")
print(response)

print("\nLF2 OpenSearch permissions configured successfully.")