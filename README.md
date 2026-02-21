Driver Safety Monitoring System

A real-time driver safety monitoring web application that detects driver drowsiness using computer vision. The system analyzes live camera input and generates alerts when unsafe conditions are detected.



 Project Description

This project uses OpenCV and facial landmark detection to monitor driver alertness.  
If drowsiness is detected, the system triggers alerts and updates safety analytics in real time.



 Tech Stack

- Python
- Flask
- OpenCV
- MediaPipe
- SQLite
- HTML,  JavaScript



 Features

- Real-time drowsiness detection
- Safety score calculation
- Alert system with sound
- Dashboard with analytics
- Driver history tracking
- Report generation

---

 Project Structure

```
driver-safety/
│
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── templates/
├── static/
```

---
 Installation

1. Clone the repository

```
git clone <your-repo-link>
cd driver-safety
```

2. Create virtual environment

```
python -m venv venv
```

3. Activate virtual environment

Windows:
```
venv\Scripts\activate
```

4. Install dependencies

```
pip install -r requirements.txt

---

 Run the Project

```
python app.py


Live Deployment

This project currently runs locally using Flask.
Deployment can be done using Render or Railway.

 API Endpoints

- `/analyze` → Process camera frame
- `/summary` → Get safety summary
- `/analytics` → Analytics data

Demo vdo
https://drive.google.com/file/d/1WWFitFfOBZeJCMcOf7ovxJyGEdJuWiUX/view?usp=sharing
 
👥 Team Members

Nimisha

---

 License

This project is licensed under the MIT License.
