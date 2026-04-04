"""
EagleVision Analytics Dashboard
A real-time Streamlit interface that consumes equipment utilization metrics 
from Kafka and visualizes them in an interactive dashboard.
"""

import streamlit as st
import pandas as pd
from confluent_kafka import Consumer
import json
import time

# --- Page Configuration ---
# Set up the dashboard title and wide layout for better data visibility
st.set_page_config(page_title="EagleVision Live Site Monitor", layout="wide")
st.title("🏗️ Construction Site Utilization Real-time Analytics")

# --- Session State Initialization ---
# Streamlit reruns the script on every update. We use session_state to persist 
# equipment data between reruns so the dashboard remains stable.
if 'data' not in st.session_state:
    st.session_state.data = {}

# --- Kafka Consumer Setup ---
# Group ID is set to 'ui-group-final' to ensure it gets the latest data independently
KAFKA_CONF = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'ui-group-final',
    'auto.offset.reset': 'latest' # Always start from the newest message
}

def get_kafka_consumer():
    """ Initializes and subscribes the Kafka consumer. """
    try:
        consumer = Consumer(KAFKA_CONF)
        consumer.subscribe(['equipment_stats'])
        return consumer
    except Exception as e:
        st.error(f"❌ Failed to connect to Kafka: {e}")
        return None

# --- UI Layout Elements ---
# Using an 'empty' container to overwrite the table in place (preventing page flicker)
placeholder = st.empty()

def run_dashboard():
    """
    Continuous loop to poll Kafka and refresh the Streamlit UI components.
    """
    consumer = get_kafka_consumer()
    if not consumer:
        return

    print("📊 Dashboard UI loop started...")

    while True:
        # Poll Kafka for new messages (0.5s timeout to reduce CPU overhead)
        msg = consumer.poll(0.5)
        
        if msg is not None and not msg.error():
            try:
                # Decode and load the JSON payload
                payload = json.loads(msg.value().decode('utf-8'))
                # Store the latest data point for each Equipment ID
                st.session_state.data[payload['id']] = payload
            except Exception as parse_err:
                print(f"⚠️ Data parsing error: {parse_err}")

        # Update the UI table within the placeholder container
        with placeholder.container():
            if st.session_state.data:
                # Transform dictionary to a list of dicts for Pandas DataFrame
                display_list = []
                for eq_id, v in st.session_state.data.items():
                    # Calculate Utilization Percentage safely (avoiding div by zero)
                    active = v['analytics']['active']
                    idle = v['analytics']['idle']
                    utilization = round((active / (active + idle + 0.1)) * 100, 1)

                    display_list.append({
                        "Equipment ID": eq_id,
                        "Activity": v.get('activity', 'WORKING'),
                        "Status": v['status'],
                        "Dwell Time (s)": v.get('dwell_time', 0),
                        "Total Active (s)": active,
                        "Total Idle (s)": idle,
                        "Utilization %": f"{utilization}%"
                    })

                # Create DataFrame and display as a clean table
                df = pd.DataFrame(display_list)
                st.table(df)
            else:
                # Show waiting message if no data has arrived yet
                st.info("⌛ Waiting for telemetry data from Kafka... Ensure CV microservice is running.")
        
        # Small delay to throttle UI refreshes for better browser performance
        time.sleep(0.1)

if __name__ == "__main__":
    run_dashboard()