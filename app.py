from flask import Flask, redirect, render_template, session, url_for

from config import Config
from routes import admin, auth, customer

app = Flask(__name__)
app.config.from_object(Config)


# ===== Blueprints =====
app.register_blueprint(auth.bp)
app.register_blueprint(admin.bp, url_prefix="/admin")
app.register_blueprint(customer.bp, url_prefix="/customer")


@app.route("/")
def index():
    if "user" in session:
        if session.get("role") == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("customer.dashboard"))
    return redirect(url_for("auth.login"))


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    # For local development
    app.run(debug=True)

