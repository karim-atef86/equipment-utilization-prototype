import cv2
import json
import time
import numpy as np
from ultralytics import YOLO
from confluent_kafka import Producer

# --- Configuration ---
KAFKA_CONFIG = {'bootstrap.servers': 'localhost:9092'}
MODEL_VARIANT = 'yolov8n.pt' # Nano variant for CPU optimization
VIDEO_SOURCE = "/workspaces/equipment-utilization-prototype/videoplayback.mp4"

class SmartManager:
    """
    Handles Re-Identification (Re-ID) using Spatial-Temporal anchors.
    Ensures that equipment IDs remain stable even during occlusions or pose changes.
    """
    def __init__(self):
        self.registry = {} 
        self.yolo_to_global = {} 
        self.next_id = 1

    def update(self, raw_id, box, detected_class, current_time):
        """
        Maps a temporary YOLO ID to a persistent Global ID based on proximity.
        """
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        
        # Check spatial distance to lost objects to maintain ID consistency
        for g_id, data in self.registry.items():
            dist = np.sqrt((cx - data['last_pos'][0])**2 + (cy - data['last_pos'][1])**2)
            if dist < 120 and (current_time - data['last_seen']) < 10:
                self.yolo_to_global[raw_id] = g_id
                data['last_pos'] = (cx, cy)
                data['last_seen'] = current_time
                return g_id
        
        # Create a new registry entry if no match is found
        new_id = self.next_id
        self.next_id += 1
        self.registry[new_id] = {
            'class': detected_class, 'last_pos': (cx, cy), 'last_seen': current_time,
            'motion_history': [], 'active_time': 0, 'idle_time': 0,
            'state': 'INACTIVE', 'state_start': current_time, 'last_tick': current_time
        }
        self.yolo_to_global[raw_id] = new_id
        return new_id

# Initialize core components
producer = Producer(KAFKA_CONFIG)
model = YOLO(MODEL_VARIANT)
manager = SmartManager()
prev_crops = {}
frame_count = 0

print("🚀 EagleVision System LIVE...")

cap = cv2.VideoCapture(VIDEO_SOURCE)
while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    
    frame_count += 1
    if frame_count % 5 != 0: continue # Process every 5th frame to save CPU

    # Resize for inference speed optimization
    frame_small = cv2.resize(frame, (640, 360))
    results = model.track(frame_small, persist=True, conf=0.1, iou=0.5, verbose=False)
    current_time = time.time()
    
    frame_objs = {} 

    if results[0].boxes.id is not None:
        ids = results[0].boxes.id.cpu().numpy().astype(int)
        boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
        clss = results[0].boxes.cls.cpu().numpy().astype(int)
        
        for r_id, box, c_idx in zip(ids, boxes, clss):
            if (box[2]-box[0])*(box[3]-box[1]) < 1000: continue # Filter noise
            
            g_id = manager.update(r_id, box, model.names[c_idx], current_time)
            
            # --- Articulated Motion Detection ---
            # Calculate pixel-level variance within the bounding box crop
            crop = frame_small[max(0,box[1]):min(360,box[3]), max(0,box[0]):min(640,box[2])]
            motion = 0
            if g_id in prev_crops and crop.size > 0:
                p_c = cv2.resize(prev_crops[g_id], (32, 32))
                c_c = cv2.resize(crop, (32, 32))
                diff = cv2.absdiff(cv2.cvtColor(p_c, cv2.COLOR_BGR2GRAY), cv2.cvtColor(c_c, cv2.COLOR_BGR2GRAY))
                motion = np.mean(diff)
            prev_crops[g_id] = crop
            
            # Apply smoothing to motion score to filter out detection jitter
            reg = manager.registry[g_id]
            reg['motion_history'].append(motion)
            if len(reg['motion_history']) > 5: reg['motion_history'].pop(0)
            avg_motion = np.mean(reg['motion_history'])
            
            frame_objs[g_id] = {'class': reg['class'], 'motion': avg_motion}

        # --- Activity Classification Logic ---
        for g_id, info in frame_objs.items():
            loader_active = any(v['motion'] > 8 for k, v in frame_objs.items() if k != g_id)
            
            if info['class'] == 'truck':
                if info['motion'] > 15: activity = "DUMPING/MOVING"
                elif loader_active and info['motion'] < 6: activity = "BEING LOADED"
                else: activity = "WAITING"
            else:
                if info['motion'] > 18: activity = "DIGGING"
                elif info['motion'] > 6: activity = "SWINGING"
                else: activity = "WAITING"

            new_state = "ACTIVE" if activity != "WAITING" else "INACTIVE"
            reg = manager.registry[g_id]
            
            # --- Analytics Update ---
            dt = current_time - reg['last_tick']
            if new_state == "ACTIVE": reg['active_time'] += dt
            else: reg['idle_time'] += dt
            reg['last_tick'] = current_time
            
            if reg['state'] != new_state:
                reg['state'] = new_state
                reg['state_start'] = current_time
            
            # --- Data Streaming (Kafka) ---
            payload = {
                "id": f"UNIT-{g_id}", "status": new_state, "activity": activity,
                "dwell_time": round(current_time - reg['state_start'], 1),
                "analytics": {"active": round(reg['active_time'], 1), "idle": round(reg['idle_time'], 1)}
            }
            producer.produce('equipment_stats', value=json.dumps(payload))
        
        print(f"📊 F:{frame_count} | IDs:{list(frame_objs.keys())} | Acts:{[v.get('activity') for v in frame_objs.values()]}")

    producer.flush(0)
cap.release()