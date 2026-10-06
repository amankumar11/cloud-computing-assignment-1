# Dining Concierge Chatbot – Project Structure

Cloud Computing and Big Data – Fall 2026  
Homework Assignment 1

## Project Overview

The Dining Concierge project is a serverless AWS application that allows a user to interact with a chatbot and receive restaurant recommendations over email.

The application collects dining preferences such as:

- Location
- Cuisine
- Dining Time
- Number of People
- Email Address

The chatbot processes these values and places the completed request into an SQS queue.

A separate Lambda function processes the queue, searches OpenSearch for restaurants matching the requested cuisine, retrieves full restaurant information from DynamoDB, and sends recommendations using Amazon SES.

The project also implements the extra-credit requirement by storing previous search information and previous restaurant recommendations in DynamoDB.

---

# Architecture

```text
                           +------------------+
                           |       User       |
                           +--------+---------+
                                    |
                                    v
                           +------------------+
                           |   S3 Frontend    |
                           +--------+---------+
                                    |
                                    v
                           +------------------+
                           |   API Gateway    |
                           +--------+---------+
                                    |
                                    v
                           +------------------+
                           |       LF0        |
                           |   Chat Lambda    |
                           +--------+---------+
                                    |
                                    v
                           +------------------+
                           |   Amazon Lex V2  |
                           +--------+---------+
                                    |
                                    v
                           +------------------+
                           |       LF1        |
                           | Lex Code Hook    |
                           +---+----------+---+
                               |          |
                               |          |
                               v          v
                        +----------+   +-------------------+
                        | SQS Q1   |   | user-search-state |
                        +----+-----+   |     DynamoDB      |
                             |         +-------------------+
                             |
                             v
                     +---------------+
                     |  EventBridge  |
                     | Every Minute  |
                     +-------+-------+
                             |
                             v
                     +---------------+
                     |      LF2      |
                     | Queue Worker  |
                     +-------+-------+
                             |
                +------------+-------------+
                |                          |
                v                          v
       +----------------+         +----------------------+
       |   OpenSearch   |         |   yelp-restaurants   |
       |  restaurants   |         |      DynamoDB        |
       +-------+--------+         +----------+-----------+
               |                             |
               +-------------+---------------+
                             |
                             v
                       +-----------+
                       | Amazon SES|
                       +-----+-----+
                             |
                             v
                       +-----------+
                       | User Email|
                       +-----------+
```

---

# 1. Frontend

Directory:

```text
frontend/
```

Main file:

```text
frontend/chat.html
```

The frontend provides the web interface used to communicate with the chatbot.

It is hosted using Amazon S3 static website hosting.

The frontend sends chatbot messages to API Gateway, which then forwards them to LF0.

A persistent session ID is stored in browser `sessionStorage`.

This allows the same Lex session to be maintained across multiple messages.

Example session ID format:

```text
session-1790995874887-ufa6mxvhakd
```

---

# 2. API Gateway

Amazon API Gateway exposes the chatbot API to the frontend.

The API configuration is based on the Swagger specification stored in:

```text
other-scripts/swagger.yaml
```

API Gateway receives chatbot messages from the frontend and invokes LF0.

CORS is enabled so that the S3-hosted frontend can communicate with the API.

---

# 3. LF0 – Chat API Lambda

Directory:

```text
lambda-functions/LF0/
```

File:

```text
lambda-functions/LF0/lambda_function.py
```

LF0 connects API Gateway with Amazon Lex.

Its responsibilities are:

1. Receive the request from API Gateway.
2. Extract the user's message.
3. Extract the persistent session ID.
4. Send the message to Amazon Lex using `recognize_text`.
5. Wait for the Lex response.
6. Return the Lex response to API Gateway.
7. API Gateway returns the response to the frontend.

The same session ID is reused across the conversation so Lex can maintain context.

---

# 4. Amazon Lex

Amazon Lex V2 provides the conversational interface for the Dining Concierge.

The chatbot contains the following intents:

```text
GreetingIntent
ThankYouIntent
DiningSuggestionsIntent
FallbackIntent
```

## GreetingIntent

Handles greetings such as:

```text
Hello
Hi
Hey
```

Example response:

```text
Hi there, how can I help?
```

## ThankYouIntent

Handles user messages such as:

```text
Thank you
Thanks
```

Example response:

```text
You're welcome! Have a great day.
```

## DiningSuggestionsIntent

The main intent used for restaurant recommendations.

The following slots are collected:

```text
Location
Cuisine
DiningTime
NumberOfPeople
EmailType
RepeatPrevious
```

The first five are part of the normal dining request.

`RepeatPrevious` is used for the extra-credit implementation.

## Slot Types

### Location

Uses:

```text
AMAZON.City
```

The application currently validates that the location is Manhattan.

### Cuisine

Uses the custom slot type:

```text
CuisineType
```

Example values include:

```text
Chinese
Indian
Italian
Japanese
Mexican
```

### DiningTime

Uses:

```text
AMAZON.Time
```

### NumberOfPeople

Uses:

```text
AMAZON.Number
```

### EmailType

Uses:

```text
AMAZON.EmailAddress
```

### RepeatPrevious

Uses the custom slot type:

```text
YesNoType
```

Values:

```text
Yes
No
```

This slot is optional.

It is only elicited by LF1 when the user searches for the same location and cuisine as their previous search.

---

# 5. LF1 – Lex Code Hook

Directory:

```text
lambda-functions/LF1/
```

File:

```text
lambda-functions/LF1/lambda_function.py
```

LF1 acts as the Lambda code hook for Amazon Lex.

It handles:

- GreetingIntent
- ThankYouIntent
- DiningSuggestionsIntent
- Location validation
- Slot processing
- SQS message creation
- Previous-search detection
- Extra-credit state handling

## Location Validation

LF1 validates the location before processing the request.

Only Manhattan is currently accepted.

If another location is entered, Lex asks the user again.

Example:

```text
User:
New Delhi

Bot:
Sorry, I can only provide restaurant suggestions for Manhattan.
Please enter Manhattan.
```

## Dining Request

Once all required slots are filled, LF1 creates a request similar to:

```json
{
  "location": "Manhattan",
  "cuisine": "Indian",
  "diningTime": "19:00",
  "numberOfPeople": "3",
  "email": "user@example.com",
  "sessionId": "session-example",
  "reusePrevious": false
}
```

The request is then sent to SQS Q1.

---

# 6. Amazon SQS

Queue:

```text
Q1
```

SQS separates the chatbot conversation from the restaurant recommendation process.

LF1 places completed requests into Q1.

LF2 later reads requests from the queue.

This means the chatbot does not have to wait for OpenSearch, DynamoDB, and SES processing before responding to the user.

The chatbot can immediately confirm:

```text
You're all set. I received your request and will send you restaurant suggestions by email shortly!
```

---

# 7. Yelp Restaurant Dataset

Restaurant data is collected using the Yelp API.

Script:

```text
other-scripts/yelp_scraper.py
```

The script collects restaurant data from Manhattan across multiple cuisine categories.

The final dataset contains approximately:

```text
1,175 restaurants
```

The implementation collects at least five cuisine categories with approximately 200 restaurants per cuisine where available.

Duplicate restaurants are avoided by using the Yelp business ID.

---

# 8. DynamoDB – yelp-restaurants

Table:

```text
yelp-restaurants
```

Partition key:

```text
businessId
```

The table stores complete restaurant information.

Example fields:

```text
businessId
name
address
coordinates
reviewCount
rating
zipCode
cuisine
insertedAtTimestamp
```

---

# 9. OpenSearch

OpenSearch index:

```text
restaurants
```

OpenSearch stores only the information required for cuisine-based restaurant lookup.

Each document contains:

```text
RestaurantID
Cuisine
```

Example:

```json
{
  "RestaurantID": "restaurant-id",
  "Cuisine": "Indian"
}
```

The full restaurant information is not duplicated in OpenSearch.

Instead, LF2 uses the restaurant ID returned by OpenSearch to retrieve the complete record from DynamoDB.

The `restaurants` index contains approximately:

```text
1,175 documents
```

---

# 10. OpenSearch Loader

Script:

```text
other-scripts/load_opensearch.py
```

This script:

1. Reads restaurant records from DynamoDB.
2. Creates the `restaurants` OpenSearch index if required.
3. Extracts RestaurantID and Cuisine.
4. Bulk indexes the restaurant records into OpenSearch.
5. Verifies the number of indexed documents.

---

# 11. OpenSearch Fine-Grained Access Control

Script:

```text
other-scripts/configure_lf2_opensearch.py
```

The OpenSearch domain uses fine-grained access control.

LF2 requires both IAM permission to access the OpenSearch domain and OpenSearch security permission to read the `restaurants` index.

The configuration script creates an OpenSearch role and maps the LF2 Lambda execution role as a backend role.

Deployment-specific values are supplied using environment variables:

```text
OPENSEARCH_ENDPOINT
LF2_ROLE_ARN
```

---

# 12. EventBridge

LF2 is automatically invoked using Amazon EventBridge.

Schedule:

```text
Every 1 minute
```

EventBridge invokes LF2 so pending restaurant requests can be processed automatically.

---

# 13. LF2 – Recommendation Worker

Directory:

```text
lambda-functions/LF2/
```

File:

```text
lambda-functions/LF2/lambda_function.py
```

LF2 performs the restaurant recommendation processing.

The normal flow is:

```text
Read SQS message
      |
      v
Extract cuisine
      |
      v
Search OpenSearch
      |
      v
Select random restaurant IDs
      |
      v
Fetch complete details from DynamoDB
      |
      v
Format recommendations
      |
      v
Send email through SES
      |
      v
Save recommendation state
      |
      v
Delete SQS message
```

LF2 randomly selects up to three restaurants from the OpenSearch results.

OpenSearch only stores RestaurantID and Cuisine, so LF2 uses the returned IDs to retrieve full restaurant details from the `yelp-restaurants` DynamoDB table.

---

# 14. Amazon SES

Amazon SES is used to send restaurant recommendations to the email address collected by Lex.

A typical recommendation email contains three restaurants with:

- Name
- Address
- Rating
- Number of Reviews

---

# 15. Safe SQS Message Processing

LF2 only deletes a message from SQS after the recommendation email has been sent successfully.

This prevents failed requests from being permanently removed from the queue.

---

# 16. Extra Credit – Persistent Search State

The project implements the extra-credit state requirement using a second DynamoDB table.

Table:

```text
user-search-state
```

Partition key:

```text
sessionId
```

Example record:

```json
{
  "sessionId": "session-example",
  "location": "manhattan",
  "cuisine": "indian",
  "restaurantIds": [
    "restaurant-id-1",
    "restaurant-id-2",
    "restaurant-id-3"
  ]
}
```

## Extra Credit Flow

For the first search, LF1 checks the `user-search-state` table. If no matching previous search exists, LF2 generates new restaurant recommendations and stores the restaurant IDs.

If the user later searches for the same location and cuisine in the same browser session, LF1 asks:

```text
You previously searched for the same location and cuisine.
Would you like the same restaurant recommendations as last time?
```

If the user answers **Yes**, LF2 retrieves the stored restaurant IDs and sends the same restaurants again.

If the user answers **No**, LF2 generates a new set of recommendations and updates the stored restaurant IDs.

---

# 17. Python Dependencies

The root `requirements.txt` contains:

```text
boto3
opensearch-py
requests
```

Install dependencies using:

```bash
pip install -r requirements.txt
```

---

# 18. Environment Variables

The application uses environment variables for sensitive or deployment-specific configuration.

Examples include:

```text
YELP_API_KEY
Q1_QUEUE_URL
OPENSEARCH_ENDPOINT
LF2_ROLE_ARN
```

Lambda functions use IAM execution roles instead of hardcoded AWS credentials.
