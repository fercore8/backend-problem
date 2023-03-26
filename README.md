## Installation
pip install -r requirements.txt

## Run application
python app.py
python client.py

## test application for POST and GET requests.
### used CURL for testing the post requests:
<br>curl -X POST -H "Content-Type: application/json" -d "{\"name\": \"Willo Woods\", \"location\": \"north\"}" http://localhost:8080/api/sites
<br>curl -X POST -H "Content-Type: application/json" -d "{\"site_id\": 1, \"battery\": {\"vendor\": \"Battery Vendor\", \"capacity_kwh\": 100, \"max_power_kw\": 10}, \"production_units\": [{\"unit_type\": \"Solar\", \"units\": 5, \"kwp\": 10}, {\"unit_type\": \"Wind\", \"units\": 2}]}" http://localhost:8080/api/configurations


### Example from get request after POST to /api/site
<br>http://localhost:8080/api/sites
[
  {
    "config": {},
    "id": 1,
    "live_data": {},
    "location": "north",
    "name": "Willo Woods"
  }
]


### test Get endpoints
<br>http://localhost:8080/api/configurations
<br> [
  {
    "battery": {
      "capacity_kwh": 3100,
      "id": 1,
      "max_power_kw": 400,
      "vendor": "Tesla"
    },
    "id": 1,
    "production_units": [
      {
        "id": 1,
        "kwp": 800,
        "unit_type": "Electric",
        "units": 2
      },
      {
        "id": 2,
        "kwp": 500,
        "unit_type": "Solar",
        "units": 2
      }
    ],
    "site": 1
  }
]

# Cloud Architecture
We can implement a nginx load balancer that listens to the requests of the clients, a server that gets the data from the load balancer and sends it to a queue such as RabbitMQ,
a client for sending data to the system , a parser to fetch data from the queue. In this manner we can take care of 
multiple requests and make sure our stress on the database is not excessive.

