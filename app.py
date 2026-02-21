from flask import Flask, render_template, request, jsonify
import cv2
import numpy as np
import base64
import datetime

app = Flask(__name__)

drowsy_count = 0

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    global drowsy_count
    
    data = request.json["image"]
    
    # Decode base64 image
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
        drowsy_count += 1

    return jsonify({
        "status": status,
        "alerts": drowsy_count,
        "time": str(datetime.datetime.now())
    })

if __name__ == "__main__":
    app.run(debug=True)