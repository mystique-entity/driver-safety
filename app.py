from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import base64
import cv2
import numpy as np
import mediapipe as mp
from datetime import datetime
import time

app = Flask(__name__)
app.secret_key = "driver_safety_secret_key"

DATABASE = "driver_data.db"

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            start_time TEXT,
            total_checks INTEGER DEFAULT 0,
            drowsy_events INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- MEDIAPIPE SETUP ----------------
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True)

LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

closed_start_time = None

def eye_aspect_ratio(landmarks, eye_indices):
    p1 = landmarks[eye_indices[0]]
    p2 = landmarks[eye_indices[1]]
    p3 = landmarks[eye_indices[2]]
    p4 = landmarks[eye_indices[3]]
    p5 = landmarks[eye_indices[4]]
    p6 = landmarks[eye_indices[5]]

    vertical1 = np.linalg.norm(np.array(p2) - np.array(p6))
    vertical2 = np.linalg.norm(np.array(p3) - np.array(p5))
    horizontal = np.linalg.norm(np.array(p1) - np.array(p4))

    return (vertical1 + vertical2) / (2.0 * horizontal)

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    return render_template("login.html")


@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                  (username, password))
        conn.commit()
    except:
        conn.close()
        return "User already exists"

    conn.close()
    return redirect(url_for("home"))


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=? AND password=?",
              (username, password))
    user = c.fetchone()
    conn.close()

    if user:
        session["user_id"] = user[0]
        return redirect(url_for("dashboard"))
    return "Invalid Credentials"


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("home"))
    return render_template("dashboard.html")


@app.route("/start-session", methods=["POST"])
def start_session():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 403

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("""
        INSERT INTO sessions (user_id, start_time)
        VALUES (?, ?)
    """, (session["user_id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    session["session_id"] = c.lastrowid
    conn.close()

    return jsonify({"message": "Session started"})


@app.route("/analyze", methods=["POST"])
def analyze():
    global closed_start_time

    if "session_id" not in session:
        return jsonify({"error": "No active session"}), 400

    data = request.json["image"]
    encoded_data = data.split(",")[1]
    np_arr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_frame)

    status = "SAFE"
    drowsy = 0

    if results.multi_face_landmarks:
        face_landmarks = results.multi_face_landmarks[0]
        h, w, _ = frame.shape

        landmarks = []
        for lm in face_landmarks.landmark:
            landmarks.append((int(lm.x * w), int(lm.y * h)))

        left_ear = eye_aspect_ratio(landmarks, LEFT_EYE)
        right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE)
        ear = (left_ear + right_ear) / 2.0

        if ear < 0.22:
            if closed_start_time is None:
                closed_start_time = time.time()
            elif time.time() - closed_start_time > 1:
                status = "DROWSY"
                drowsy = 1
        else:
            closed_start_time = None
    else:
        closed_start_time = None

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("""
        UPDATE sessions
        SET total_checks = total_checks + 1,
            drowsy_events = drowsy_events + ?
        WHERE id = ?
    """, (drowsy, session["session_id"]))

    conn.commit()
    conn.close()

    return jsonify({"status": status})


@app.route("/summary")
def summary():
    if "session_id" not in session:
        return jsonify({"error": "No session"}), 400

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT total_checks, drowsy_events FROM sessions WHERE id=?",
              (session["session_id"],))
    row = c.fetchone()
    conn.close()

    total = row[0]
    drowsy = row[1]

    safety = 100
    if total > 0:
        safety = round((1 - drowsy/total) * 100, 2)

    return jsonify({
        "total_checks": total,
        "drowsy_events": drowsy,
        "safety_score": safety
    })


@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("home"))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("""
        SELECT start_time, total_checks, drowsy_events
        FROM sessions
        WHERE user_id=?
        ORDER BY id DESC
    """, (session["user_id"],))

    data = c.fetchall()
    conn.close()

    return render_template("history.html", sessions=data)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)