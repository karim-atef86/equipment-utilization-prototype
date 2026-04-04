"""
Analytics Service - Database Consumer
This microservice consumes equipment utilization data from Kafka 
and persists it into a PostgreSQL database for long-term analytics.
"""

import json
import psycopg2
from confluent_kafka import Consumer

# --- Configuration Section ---
# Kafka Consumer settings
KAFKA_CONF = {
    'bootstrap.servers': '127.0.0.1:9092', 
    'group.id': 'db-storage-group', 
    'auto_offset_reset': 'earliest' # Ensures we don't miss data if the consumer is offline
}

# PostgreSQL connection parameters
DB_CONFIG = "dbname=equipment_db user=user password=password host=127.0.0.1 port=5432"

def run_consumer():
    """
    Main loop to poll Kafka messages and insert them into PostgreSQL.
    """
    # Initialize Kafka Consumer
    consumer = Consumer(KAFKA_CONF)
    consumer.subscribe(['equipment_stats'])

    print("📊 Analytics Consumer started. Waiting for data...")

    try:
        # Establish connection to the PostgreSQL database
        conn = psycopg2.connect(DB_CONFIG)
        cur = conn.cursor()
        print("✅ Connected to PostgreSQL on port 5432.")
        
        while True:
            # Poll for new messages from Kafka (1-second timeout)
            msg = consumer.poll(1.0)
            
            if msg is None: 
                continue
            if msg.error():
                print(f"⚠️ Consumer error: {msg.error()}")
                continue
            
            try:
                # Parse the incoming JSON payload
                data = json.loads(msg.value().decode('utf-8'))
                
                # Robust data extraction using .get() to prevent KeyErrors
                # This ensures the consumer stays alive even if a message is malformed
                eq_id      = data.get('id')
                status     = data.get('status')
                activity   = data.get('activity', 'WORKING') # Default to WORKING if not provided
                active_sec = data.get('analytics', {}).get('active', 0)
                idle_sec   = data.get('analytics', {}).get('idle', 0)

                # Database insertion logic
                if eq_id:
                    query = """
                        INSERT INTO utilization_stats (equipment_id, state, activity, active_seconds, idle_seconds)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    cur.execute(query, (eq_id, status, activity, active_sec, idle_sec))
                    
                    # Commit the transaction to disk
                    conn.commit()
                    print(f"💾 Persisted record: {eq_id} | State: {status} | Act: {activity}")

            except json.JSONDecodeError as e:
                print(f"❌ Failed to decode message JSON: {e}")
            except Exception as db_err:
                print(f"❌ Database Insertion Error: {db_err}")
                conn.rollback() # Rollback on DB error to maintain transaction integrity

    except Exception as e:
        print(f"❌ Critical System Error: {e}")
    finally:
        # Graceful shutdown
        if 'consumer' in locals():
            consumer.close()
        if 'conn' in locals():
            cur.close()
            conn.close()

if __name__ == "__main__":
    run_consumer()