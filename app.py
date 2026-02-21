from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Driver Safety System Running 🚗"

if __name__ == "__main__":
    app.run(debug=True)
    