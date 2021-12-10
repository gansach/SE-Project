# %%
from __future__ import division, print_function
import os
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
from flask import Flask, render_template, request, session
from flask_pymongo import PyMongo
import bcrypt
from werkzeug.utils import secure_filename

import zipfile
import glob

import json
from urllib.parse import quote

import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# %%
app = Flask(__name__)

app.config["MONGO_DBNAME"] = "Malaria"
app.config["MONGO_URI"] = "mongodb://127.0.0.1:27017/Malaria"
mongo = PyMongo(app)

# %%
app = Flask(__name__)
MODEL_PATH = "cnn_model.h5"
model = load_model(MODEL_PATH)


def send_email(email, infected, uninfected):
    chart_config = {
        "type": "bar",
        "data": {
            "labels": ["Cell Status"],
            "datasets": [
                {"label": "Infected Cells", "data": [infected]},
                {"label": "Uninfected Cells", "data": [uninfected]},
            ],
        },
    }

    encoded_config = quote(json.dumps(chart_config))
    chart_url = f"https://quickchart.io/chart?c={encoded_config}"

    email_message = f"""Hello, Your test resutlts are in. You are {"NOT infected" if uninfected >= infected else "INFECTED"} with Malaria.
    <br><br>
    Please see the chart below for more details:
    <br><br>
    <img width="400px" src="{chart_url}" />
    """

    me = "sachdevagandharv@gmail.com"
    you = email

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Malaria Diagnosis"
    msg["From"] = me
    msg["To"] = you

    msg.attach(MIMEText(email_message, "html"))
    mail = smtplib.SMTP("smtp.gmail.com", 587)

    mail.ehlo()

    mail.starttls()

    f = open("auth.txt", "r")
    password = f.read()
    f.close()

    mail.login(me, password)
    mail.sendmail(me, you, msg.as_string())
    mail.quit()


def image_predict(file_path, model):
    img = image.load_img(file_path, target_size=(224, 224))
    x = image.img_to_array(img)
    x = x / 255
    x = np.expand_dims(x, axis=0)
    preds = model.predict(x)
    preds = np.argmax(preds, axis=1)
    return preds == 0


def model_predict(file_path, model):
    infected, uninfected = 0, 0

    if file_path.endswith(".png"):
        if image_predict(file_path, model):
            return ("INFECTED", infected, uninfected)
        else:
            return ("uninfected", infected, uninfected)

    files = glob.glob("tmp/*")
    for f in files:
        os.remove(f)

    with zipfile.ZipFile(file_path, "r") as zip_ref:
        zip_ref.extractall("tmp")

    for filename in os.listdir("tmp"):
        if image_predict(f"tmp/{filename}", model):
            infected += 1
        else:
            uninfected += 1

    if uninfected >= infected:
        return ("uninfected", infected, uninfected)
    else:
        return ("INFECTED", infected, uninfected)


# %%
@app.route("/", methods=["POST", "GET"])
def index():
    if "email" in session:
        return render_template("sw_features.html")
    return render_template("index_sw.html")


# %%
@app.route("/predict", methods=["GET", "POST"])
def predict():
    msg = ""
    if request.method == "POST":
        f = request.files["file"]
        basepath = os.path.dirname(f.filename)
        file_path = os.path.join(basepath, "uploads", secure_filename(f.filename))
        f.save(file_path)

        infected, uninfected = 0, 0
        msg, infected, uninfected = model_predict(file_path, model)
        session["status"] = msg

        if infected or uninfected:
            send_email(session["email"], infected, uninfected)

        return render_template(
            "sw_features.html",
            msg="Result: " + msg,
            infected=infected,
            uninfected=uninfected,
        )
    return None


# %%
@app.route("/login", methods=["POST", "GET"])
def login():
    msg = ""
    users = mongo.db.collection
    login_user = users.find_one({"email": request.form["email"]})

    if login_user:
        if (
            bcrypt.hashpw(
                request.form["password"].encode("utf-8"), login_user["password"]
            )
            == login_user["password"]
        ):
            session["email"] = request.form["email"]
            session["Name"] = login_user["Name"]
            session["status"] = "unknown"
            # return redirect(url_for('sw_features.html'))
            return render_template("sw_features.html")
    msg = "Invalid username/password combination"
    return render_template("index_sw.html", msg=msg)


# %%
@app.route("/register", methods=["POST", "GET"])
def register():
    msg = ""
    if request.method == "POST":
        users = mongo.db.collection
        existing_user = users.find_one({"email": request.form["email"]})

        if existing_user is None:
            hashpass = bcrypt.hashpw(
                request.form["password"].encode("utf-8"), bcrypt.gensalt()
            )
            users.insert_one(
                {
                    "Name": request.form["Name"],
                    "email": request.form["email"],
                    "password": hashpass,
                    "Address": request.form["Address"],
                    "status": "unknown",
                }
            )
            session["email"] = request.form["email"]
            session["status"] = "unknown"
            msg = "You have successfully registered !!"
            # return redirect(url_for('index'))  #sending to index function
            return render_template("index_sw.html", msg=msg)
        msg = "That email already exists!"
        return render_template("index_sw.html", msg=msg)

    return render_template("register_sw.html", msg=msg)


# %%
@app.route("/logout")
def logout():
    msg = ""
    session.pop("email", None)
    session.pop("Name", None)
    return render_template("index_sw.html", msg="Successfully logged out")


# %%
if __name__ == "__main__":
    app.secret_key = "mysecret"
    app.run()

# %%
