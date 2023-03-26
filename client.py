import requests
import random
import time
from datetime import datetime

"""Here is a client that spits data every 10 seconds for the application to digest. 
The run will also create a site and a configuration"""

BASE_URL = "http://localhost:8080"


def generate_random_live_data(site_id: int) -> dict:
    data = {
        "site_id": site_id,
        "dt_stamp": datetime.now().isoformat(),
        "soc": random.uniform(0, 100),
        "load_kwh": random.uniform(0, 500),
        "net_load_kwh": random.uniform(0, 500),
        "pv_notification": random.choice([True, False]),
        "bio_notification": random.choice([True, False]),
        "cro_notification": random.choice([True, False]),
    }
    return data


def main():
    # create a new site
    site_data = {"name": "Willo Woods", "location": "north"}
    response = requests.post(f"{BASE_URL}/api/sites", json=site_data)
    if response.status_code == 201:
        site_id = response.json()["id"]
        print(f"New site created with ID {site_id}.")
    else:
        print(f"Error creating site: {response.status_code} - {response.text}")
        return

    # create a new configuration
    config_data = {
        "site_id": site_id,
        "battery": {
            "vendor": "Battery Vendor",
            "capacity_kwh": 100,
            "max_power_kw": 10
        },
        "production_units": [
            {"unit_type": "Solar", "units": 5, "kwp": 10},
            {"unit_type": "Wind", "units": 2}
        ]
    }
    response = requests.post(f"{BASE_URL}/api/configurations", json=config_data)
    if response.status_code == 200:
        print("New configuration created.")
    else:
        print(f"Error creating configuration: {response.status_code} - {response.text}")
        return

    site_id = 1  # this is our custom site id

    while True:
        live_data = generate_random_live_data(site_id)
        response = requests.post(f"{BASE_URL}/api/live_data", json=live_data)

        if response.status_code == 200:
            print("LiveData sent successfully.")
        else:
            print(f"Error sending LiveData: {response.status_code} - {response.text}")

        time.sleep(10)


if __name__ == "__main__":
    main()
