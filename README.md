# 🏗️ Construction Equipment Utilization & Activity Classification

## 1. Project Overview
This project is a high-performance, real-time monitoring system designed for construction sites. It leverages Computer Vision (AI) and a distributed microservices architecture to track equipment utilization, calculate **Dwell Time** (idle duration), and classify complex work activities.

### 🎥 Demo Video
[![Watch the Demo](https://cdn.loom.com/sessions/thumbnails/d5d02e437d8e42ca8fbc6937e9a17a0d-with-play.gif)](https://www.loom.com/share/d5d02e437d8e42ca8fbc6937e9a17a0d)

*Click the image above to watch the live system analytics and tracking performance.*

---

## 2. Technical Write-up: Core Challenges & Solutions

### A. Solving the "Articulated Motion" Challenge
A major issue in monitoring excavators is that the machine base often remains stationary while the arm is working (Digging/Swinging). Traditional centroid-based tracking would incorrectly mark this as "Inactive".
*   **The Solution:** I implemented **Region-Based Pixel Variance Analysis**. 
*   **How it works:** The system crops the bounding box of each machine, resizes it to a normalized 32x32 buffer, and calculates the **Mean Intensity Change** between frames. High internal pixel variance confirms that articulated parts are moving, maintaining an **ACTIVE** state even if global coordinates remain unchanged.

### B. Advanced Re-ID via "Spatial-Temporal Anchors"
In construction environments, equipment often goes out of frame or is occluded, causing trackers to assign new IDs and reset the "Dwell Time" (Idle Session Time).
*   **The Solution:** I developed a custom `SmartManager` class to enforce **Spatial-Temporal Continuity**.
*   **Logic:** When the YOLO tracker assigns a new raw ID, the system calculates the **Euclidean distance** between the new detection and the last known positions of "lost" objects within a **10-second window**. If a match is found within a 120px radius, the system "stitches" the tracks together, maintaining a stable **Global ID**. This ensures that Dwell Time and Utilization metrics remain cumulative and accurate.

### C. Interaction-Aware Activity Classification
The system utilizes a heuristic state machine to classify activities:
*   **BEING LOADED:** A specialized logic for Trucks. If a truck is stationary while an active excavator is detected in close proximity, the truck is marked as **BEING LOADED** and its state is set to **ACTIVE**, preventing false idle logs.
*   **DIGGING/SWINGING:** Differentiated by the intensity of the "Inner-Box Motion" score.

---

## 3. System Architecture
The system follows a **Microservices Design Pattern** to ensure scalability:

1.  **CV Microservice (Producer):** Uses **YOLOv8n** (optimized for CPU) to stream telemetry data to Kafka.
2.  **Apache Kafka:** Acts as the central data backbone, decoupling AI processing from storage.
3.  **Analytics Service (Consumer):** Persists real-time logs into a **PostgreSQL** database.
4.  **Live Dashboard (Streamlit):** Visualizes live equipment status, Dwell Time, and Utilization percentage.

---

## 4. Setup & Installation

### Step 1: Spin up Infrastructure (Docker)
```bash
docker-compose up -d
### Step 2: Initialize Database Table
```bash
docker exec -it postgres psql -U user -d equipment_db -c "
CREATE TABLE IF NOT EXISTS utilization_stats (
    id SERIAL PRIMARY KEY,
    equipment_id TEXT,
    state TEXT,
    activity TEXT,
    active_seconds FLOAT,
    idle_seconds FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);"
### Step 3: Run Microservices
*(Run each in a separate terminal tab)*
1. **Analytics Consumer:** `cd analytics_service && python consumer.py`
2. **CV Engine:** `cd cv_service && python main.py`
3. **UI Dashboard:** `cd dashboard && streamlit run app.py`

---

## 5. Project Structure
```text
├── cv_service/             # Detection, Tracking & Kafka Producer
├── analytics_service/      # PostgreSQL Storage Consumer
├── dashboard/              # Streamlit UI Visualization
├── docker-compose.yml      # Kafka, Zookeeper, Postgres
└── README.md               # Documentation