# 🏗️ Equipment Utilization Monitoring System

## 1. Project Overview
A real-time AI monitoring system for construction sites. It tracks equipment, calculates Dwell Time (idle duration), and classifies activities like Digging and Loading using a distributed microservices architecture.

### 🎥 Demo Video
Watch the system in action here: 
https://www.loom.com/share/d5d02e437d8e42ca8fbc6937e9a17a0d

---

## 2. Technical Solutions
* **Articulated Motion:** Solved via Region-Based Pixel Variance. Detects arm movement even if the machine base is stationary.
* **Persistent Re-ID:** Solved with Spatial-Temporal logic. Stitches IDs together if a machine is occluded, ensuring Dwell Time accuracy.
* **Smart Interaction:** Detects "BEING LOADED" by monitoring proximity between Trucks and active Excavators.

---

## 3. Quick Setup & Run

1. **Start Infrastructure:**
docker-compose up -d

2. **Initialize Database:**
docker exec -it postgres psql -U user -d equipment_db -c "CREATE TABLE IF NOT EXISTS utilization_stats (id SERIAL PRIMARY KEY, equipment_id TEXT, state TEXT, activity TEXT, active_seconds FLOAT, idle_seconds FLOAT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"

3. **Run Services (Separate Terminals):**
- Analytics: `cd analytics_service && python consumer.py`
- CV Engine: `cd cv_service && python main.py`
- Dashboard: `cd dashboard && streamlit run app.py`

---

## 4. Architecture
* **CV Service:** YOLOv8n + Tracking (Kafka Producer).
* **Analytics Service:** Data Persistence (Kafka Consumer).
* **Dashboard:** Real-time UI (Streamlit).
* **Storage:** PostgreSQL & Apache Kafka.

**Developed by Karim Atef.**