Equipment Utilization & Activity Classification Prototype
1. Project Overview
This project is a high-performance, real-time monitoring system designed for construction sites. It utilizes Computer Vision (AI) and a distributed microservices architecture to track equipment utilization, calculate Dwell Time (idle duration), and classify complex work activities.
Key Features:
Articulated Motion Detection: Distinguishes between a stationary machine and a machine working with its arm (e.g., an excavator digging while parked).
Intelligent Re-ID: Persistent tracking of equipment IDs even after temporary occlusion or drastic pose changes.
Smart Activity Classification: Real-time detection of activities: Digging, Swinging, Loading, Moving, and Waiting.
Distributed Pipeline: Uses Apache Kafka to decouple AI processing from analytics and visualization.
2. System Architecture
The system is built using a Microservices Design Pattern to ensure scalability and reliability:
CV Microservice (Producer): Runs YOLOv8n and a custom Spatial-Temporal tracker. It streams status payloads to Kafka.
Message Broker (Apache Kafka): Handles high-throughput data streaming between services.
Analytics Service (Consumer): Listens to Kafka and persists historical logs into a PostgreSQL database.
Live Dashboard (Streamlit): Consumes real-time data for instant site visualization and reporting.
3. Technical Write-up: Design Decisions
A. Solving the "Articulated Motion" Challenge
Traditional AI trackers often mark a machine as "Inactive" if its global coordinates (Bounding Box) don't change. This is inaccurate for excavators.
The Technique: I implemented Internal Pixel Variance Analysis.
How it works: The system crops the machine's bounding box and performs Frame-Differencing on a normalized 32x32 pixel buffer. By calculating the Mean Intensity Change within the crop, the system detects articulated parts moving (like the arm or bucket) even if the base is stationary. This ensures the machine remains in an ACTIVE state.
B. Advanced Re-ID via "Spatial Anchors"
Occlusions and pose changes (like a bucket extending) often cause trackers to assign new IDs, which resets the "Dwell Time."
The Solution: I developed a custom SmartManager class that enforces Spatial-Temporal Continuity.
Logic: When the tracker assigns a new raw ID, the system checks for any recently "lost" objects within a specific Euclidean distance radius and a temporal window (10 seconds). If a match is found, the system "stitches" the tracks, maintaining a Stable Global ID. This keeps the Dwell Time (Idle Session) and Total Active Time accurate throughout the operation.
C. Interaction-Aware Activity Classification
The system uses a heuristic state machine to classify activities:
BEING LOADED: A specialized logic for Trucks. If a truck is stationary while an active excavator is nearby, the truck is automatically marked as BEING LOADED and set to ACTIVE, preventing false idle logging.
DIGGING/SWINGING: Differentiated based on the intensity of the internal motion score.
4. Setup & Installation
Prerequisites:
Docker & Docker Compose
Python 3.9+
Step 1: Spin up Infrastructure
code
Bash
docker-compose up -d
Step 2: Configure Database
code
Bash
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
Step 3: Run Microservices
Run each in a separate terminal:
Analytics Consumer: cd analytics_service && pip install -r requirements.txt && python consumer.py
CV Engine: cd cv_service && pip install -r requirements.txt && python main.py
UI Dashboard: cd dashboard && pip install -r requirements.txt && streamlit run app.py
5. Model Selection Trade-offs
I utilized YOLOv8n (Nano) for this prototype.
Trade-off: While larger models (Medium/Large) offer slightly higher accuracy, they are computationally expensive on CPU-only environments.
Optimization: To bridge this gap, I implemented a low-confidence threshold (0.1) and a Spatial Re-ID layer. This configuration provides near-real-time performance (FPS) on standard CPUs while maintaining production-grade ID stability.