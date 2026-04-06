"""
EagleVision - Computer Vision Microservice
This script handles real-time detection, tracking, and activity classification
for construction equipment using YOLOv8 and a custom Spatial-Temporal Re-ID engine.
"""

import cv2
import json
import time
import numpy as np
from ultralytics import YOLO
from confluent_kafka import Producer

# --- 1. Configuration & Constants ---
KAFKA_BROKER = 'localhost:9092'
MODEL_PATH   = 'yolov8n.pt' # Nano variant chosen for optimal CPU performance
VIDEO_PATH   = "/workspaces/equipment-utilization-prototype/videoplayback.mp4"
FRAME_SKIP   = 5            # Process 1 frame every 5 to reduce CPU load

# --- 2. Re-ID Engine ---
class SmartManager:
    """
    Manages equipment identity across frames. 
    Implements Spatial-Temporal anchors to solve ID switching during occlusions.
    """
    def __init__(self):
        self.registry = {}       # Stores metadata for each stable Global ID
        self.yolo_to_global = {} # Maps transient YOLO IDs to stable Global IDs
        self.next_id = 1

    def update(self, raw_id, box, detected_class, current_time):
        """
        Calculates the spatial proximity between new detections and lost tracks.
        """
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        
        # Scenario A: If ID already mapped, update its position and return
        if raw_id in self.yolo_to_global:
            g_id = self.yolo_to_global[raw_id]
            self.registry[g_id]['last_pos'] = (cx, cy)
            self.registry[g_id]['last_seen'] = current_time
            return g_id

        # Scenario B: New ID detected. Search registry for a 'lost' unit nearby
        for g_id, data in self.registry.items():
            dist = np.sqrt((cx - data['last_pos'][0])**2 + (cy - data['last_pos'][1])**2)
            # Re-identification criteria: Within 120px and lost for less than 10 seconds
            if dist < 120 and (current_time - data['last_seen']) < 10:
                self.yolo_to_global[raw_id] = g_id
                data['last_pos'] = (cx, cy)
                data['last_seen'] = current_time
                return g_id
        
        # Scenario C: Brand new equipment unit entering the scene
        new_id = self.next_id
        self.next_id += 1
        self.registry[new_id] = {
            'class': detected_class, 
            'last_pos': (cx, cy), 
            'last_seen': current_time,
            'motion_history': [], 
            'active_time': 0, 
            'idle_time': 0,
            'state': 'INACTIVE', 
            'state_start_time': current_time, 
            'last_tick': current_time
        }
        self.yolo_to_global[raw_id] = new_id
        return new_id

# --- 3. Initializing Components ---
print("🚀 Initializing EagleVision CV Pipeline...")
producer = Producer({'bootstrap.servers': KAFKA_BROKER})
model = YOLO(MODEL_PATH)
manager = SmartManager()

prev_crops = {}
frame_count = 0
cap = cv2.VideoCapture(VIDEO_PATH)

# --- 4. Main Processing Loop ---
while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    
    frame_count += 1
    if frame_count % FRAME_SKIP != 0: continue 

    # Inference pre-processing: Resize to 360p for speed
    frame_small = cv2.resize(frame, (640, 360))
    # Run YOLO tracking with a low confidence threshold to capture distant units
    results = model.track(frame_small, persist=True, conf=0.1, verbose=False)
    current_time = time.time()
    
    frame_objs = {} 

    if results[0].boxes.id is not None:
        ids   = results[0].boxes.id.cpu().numpy().astype(int)
        boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
        clss  = results[0].boxes.cls.cpu().numpy().astype(int)
        
        # Stage 1: Data Gathering & Internal Motion Analysis
        for r_id, box, c_idx in zip(ids, boxes, clss):
            if (box[2]-box[0])*(box[3]-box[1]) < 1000: continue # Filter artifacts
            
            g_id = manager.update(r_id, box, model.names[c_idx], current_time)
            
            # Articulated Motion Detection: Frame differencing inside the bounding box
            crop = frame_small[max(0,box[1]):min(360,box[3]), max(0,box[0]):min(640,box[2])]
            motion_score = 0
            if g_id in prev_crops and crop.size > 0:
                p_c = cv2.resize(prev_crops[g_id], (32, 32))
                c_c = cv2.resize(crop, (32, 32))
                diff = cv2.absdiff(cv2.cvtColor(p_c, cv2.COLOR_BGR2GRAY), cv2.cvtColor(c_c, cv2.COLOR_BGR2GRAY))
                motion_score = np.mean(diff)
            prev_crops[g_id] = crop
            
            # Record motion for current frame classification
            frame_objs[g_id] = {'class': manager.registry[g_id]['class'], 'motion': motion_score}

        # Stage 2: Interaction-Aware Activity Classification
        for g_id, info in frame_objs.items():
            # Check if any nearby equipment (e.g. excavator) is working
            loader_active = any(v['motion'] > 8 for k, v in frame_objs.items() if k != g_id)
            
            # Classification Heuristics
            if info['class'] == 'truck':
                if info['motion'] > 15: activity = "DUMPING/MOVING"
                elif loader_active and info['motion'] < 6: activity = "BEING LOADED"
                else: activity = "WAITING"
            else: # Excavator / Loader Logic
                if info['motion'] > 18: activity = "DIGGING"
                elif info['motion'] > 6: activity = "SWINGING"
                else: activity = "WAITING"

            info['activity'] = activity # Save to dict for logging
            new_state = "ACTIVE" if activity != "WAITING" else "INACTIVE"
            
            # Stage 3: Analytics & State Management (Dwell Time)
            reg = manager.registry[g_id]
            dt = current_time - reg['last_tick']
            if new_state == "ACTIVE": reg['active_time'] += dt
            else: reg['idle_time'] += dt
            reg['last_tick'] = current_time
            
            # Reset session timer if equipment state changes
            if reg['state'] != new_state:
                reg['state'] = new_state
                reg['state_start_time'] = current_time
            
            # Stage 4: Data Streaming to Kafka
            payload = {
                "id": f"UNIT-{g_id}", 
                "status": new_state, 
                "activity": activity,
                "dwell_time": round(current_time - reg['state_start_time'], 1),
                "analytics": {
                    "active": round(reg['active_time'], 1), 
                    "idle": round(reg['idle_time'], 1)
                }
            }
            try:
                producer.produce('equipment_stats', value=json.dumps(payload))
            except BufferError:
                producer.flush(1) # Clear buffer if full
        
        # Display live telemetry in terminal
        print(f"📊 F:{frame_count} | IDs:{list(frame_objs.keys())} | Acts:{[v['activity'] for v in frame_objs.values()]}")

    producer.flush(0)
cap.release()
print("✅ Processing Completed Successfully.")