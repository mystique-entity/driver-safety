from flask import Flask, render_template, request, jsonify
import cv2
import numpy as np
import base64
import sqlite3
import datetime

app = Flask(__name__)

# ---------- DATABASE SETUP ----------

def init_db():
    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- ROUTES ----------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json["image"]
    
    # Decode image
    image_data = base64.b64decode(data.split(",")[1])
    np_arr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    status = "SAFE"

    if len(faces) == 0:
        status = "DROWSY"

    # Save to database
    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()
    c.execute("INSERT INTO events (status, timestamp) VALUES (?, ?)",
              (status, str(datetime.datetime.now())))
    conn.commit()
    conn.close()

    return jsonify({"status": status})

@app.route("/summary")
def summary():
    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM events")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM events WHERE status='DROWSY'")
    drowsy = c.fetchone()[0]

    conn.close()

    return jsonify({
        "total_checks": total,
        "drowsy_events": drowsy,
        "safety_score": round((1 - (drowsy/total)) * 100, 2) if total > 0 else 100
    })

if __name__ == "__main__":
    app.run(debug=True, threaded=True)