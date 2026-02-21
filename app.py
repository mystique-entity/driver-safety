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
            occupation TEXT,
            route TEXT,
            predictive_risk TEXT,
            total_checks INTEGER DEFAULT 0,
            drowsy_events INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS manual_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_name TEXT,
            vehicle_no TEXT,
            occupation TEXT,
            route TEXT,
            shift_start TEXT,
            shift_end TEXT,
            incident_time TEXT,
            total_checks INTEGER,
            drowsy_events INTEGER,
            safety_score REAL,
            risk_level TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS drowsy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            event_time TEXT,
            occupation TEXT,
            route TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- MEDIAPIPE ----------------
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True)

LEFT_EYE = [33,160,158,133,153,144]
RIGHT_EYE = [362,385,387,263,373,380]

closed_start_time = None

def eye_aspect_ratio(landmarks, eye):
    p1,p2,p3,p4,p5,p6 = [landmarks[i] for i in eye]
    v1 = np.linalg.norm(np.array(p2)-np.array(p6))
    v2 = np.linalg.norm(np.array(p3)-np.array(p5))
    h  = np.linalg.norm(np.array(p1)-np.array(p4))
    return (v1+v2)/(2*h)

# ---------------- AUTH ----------------
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
        c.execute("INSERT INTO users (username,password) VALUES (?,?)",(username,password))
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
    c.execute("SELECT id FROM users WHERE username=? AND password=?",(username,password))
    user = c.fetchone()
    conn.close()

    if user:
        session["user_id"]=user[0]
        return redirect(url_for("dashboard"))
    return "Invalid Credentials"

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("home"))
    return render_template("dashboard.html")

# ---------------- START SESSION ----------------
@app.route("/start-session", methods=["POST"])
def start_session():

    occupation = request.json.get("occupation")
    route = request.json.get("route")

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("""
        SELECT occupation FROM manual_sessions
        GROUP BY occupation
        ORDER BY SUM(drowsy_events) DESC LIMIT 1
    """)
    worst_occ = c.fetchone()

    c.execute("""
        SELECT route FROM manual_sessions
        GROUP BY route
        ORDER BY SUM(drowsy_events) DESC LIMIT 1
    """)
    worst_route = c.fetchone()

    c.execute("""
        SELECT incident_time FROM manual_sessions
        GROUP BY incident_time
        ORDER BY COUNT(*) DESC LIMIT 1
    """)
    worst_time = c.fetchone()

    current_hour = datetime.now().strftime("%H")
    risk_level = "LOW"

    if worst_occ and occupation == worst_occ[0]:
        risk_level = "HIGH"

    if worst_route and route == worst_route[0]:
        risk_level = "HIGH"

    if worst_time and worst_time[0].startswith(current_hour):
        risk_level = "HIGH"

    c.execute("""
        INSERT INTO sessions (user_id,start_time,occupation,route,predictive_risk)
        VALUES (?,?,?,?,?)
    """,(session["user_id"],
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         occupation,
         route,
         risk_level))

    conn.commit()
    session["session_id"]=c.lastrowid
    conn.close()

    return jsonify({"predictive_risk":risk_level})

# ---------------- LIVE ANALYSIS ----------------
@app.route("/analyze", methods=["POST"])
def analyze():
    global closed_start_time

    data=request.json["image"]
    encoded=data.split(",")[1]
    frame=cv2.imdecode(np.frombuffer(base64.b64decode(encoded),np.uint8),1)
    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
    results=face_mesh.process(rgb)

    status="SAFE"
    drowsy=0

    if results.multi_face_landmarks:
        face=results.multi_face_landmarks[0]
        h,w,_=frame.shape
        landmarks=[(int(l.x*w),int(l.y*h)) for l in face.landmark]
        ear=(eye_aspect_ratio(landmarks,LEFT_EYE)+eye_aspect_ratio(landmarks,RIGHT_EYE))/2

        if ear<0.25:
            if closed_start_time is None:
                closed_start_time=time.time()
            elif time.time()-closed_start_time>1:
                status="DROWSY"
                drowsy=1
        else:
            closed_start_time=None

    conn=sqlite3.connect(DATABASE)
    c=conn.cursor()
    c.execute("""
        UPDATE sessions
        SET total_checks=total_checks+1,
            drowsy_events=drowsy_events+?
        WHERE id=?
    """,(drowsy,session["session_id"]))
    conn.commit()
    conn.close()

    return jsonify({"status":status})

# ---------------- SUMMARY ----------------
@app.route("/summary")
def summary():
    conn=sqlite3.connect(DATABASE)
    c=conn.cursor()
    c.execute("""
        SELECT total_checks,drowsy_events,predictive_risk
        FROM sessions WHERE id=?
    """,(session["session_id"],))
    row=c.fetchone()
    conn.close()

    total,drowsy,risk=row
    safety=round((1-drowsy/total)*100,2) if total>0 else 100

    return jsonify({
        "total_checks":total,
        "drowsy_events":drowsy,
        "safety_score":safety,
        "predictive_risk":risk
    })

# ---------------- HISTORY ----------------
@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("home"))

    conn=sqlite3.connect(DATABASE)
    c=conn.cursor()
    c.execute("""
        SELECT start_time,occupation,route,total_checks,drowsy_events,predictive_risk
        FROM sessions
        WHERE user_id=?
        ORDER BY id DESC
    """,(session["user_id"],))
    data=c.fetchall()
    conn.close()

    return render_template("history.html", sessions=data)

# ---------------- ANALYTICS ----------------
@app.route("/analytics")
def analytics():

    if "user_id" not in session:
        return redirect(url_for("home"))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Driver drowsy events
    c.execute("""
        SELECT event_time, occupation, route
        FROM drowsy_logs
        WHERE session_id IN (
            SELECT id FROM sessions WHERE user_id=?
        )
        ORDER BY event_time DESC
    """, (session["user_id"],))

    events = c.fetchall()

    conn.close()

    return render_template("analytics.html", events=events)

# ---------------- DEMO DATA ----------------
@app.route("/generate-full-demo-data")
def generate_full_demo_data():

    conn=sqlite3.connect(DATABASE)
    c=conn.cursor()

    demo_data=[
        ("Arun Kumar","KL-07-1234","Truck Driver","Kochi-Trivandrum Highway","22:00","06:00","02:30",120,18),
        ("Rahul Nair","KL-01-5678","Bus Driver","Calicut-Kannur Route","05:00","14:00","06:45",95,8),
        ("Meera Das","KL-10-2222","Delivery Driver","Ernakulam City Loop","09:00","18:00","14:15",150,3),
        ("Suresh Pillai","KL-08-8888","Taxi Driver","Kottayam-Alappuzha Road","18:00","02:00","00:40",80,22),
        ("Nikhil Raj","KL-12-9999","Truck Driver","Palakkad-Thrissur Highway","23:00","07:00","03:10",200,25),
        ("Anjali Menon","KL-15-4444","Bus Driver","Thrissur-Guruvayur Route","04:30","12:30","05:20",110,12)
    ]

    for name,vehicle,occupation,route,start,end,incident,total,drowsy in demo_data:
        safety=round((1-drowsy/total)*100,2)
        risk="LOW" if safety>=90 else "MODERATE" if safety>=75 else "HIGH"

        c.execute("""
            INSERT INTO manual_sessions
            (driver_name,vehicle_no,occupation,route,
             shift_start,shift_end,incident_time,
             total_checks,drowsy_events,safety_score,risk_level)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,(name,vehicle,occupation,route,start,end,incident,total,drowsy,safety,risk))

    conn.commit()
    conn.close()

    return "Demo data added successfully!"

if __name__=="__main__":
    app.run(debug=True)