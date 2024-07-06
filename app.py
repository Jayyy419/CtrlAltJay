from flask import Flask, render_template, request, redirect, url_for
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configure Flask-Mail using environment variables
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'default_server')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'default_username')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'default_password')
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'false').lower() in ['true', '1', 't']

mail = Mail(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_message', methods=['POST'])
def send_message():
    fullname = request.form['fullname']
    email = request.form['email']
    message_body = request.form['message']

    msg = Message(
        subject=f"New contact form submission from {fullname}",
        sender=app.config['MAIL_USERNAME'],
        recipients=['Rone_peh@hotmail.com'],
        body=f"Name: {fullname}\nEmail: {email}\nMessage: {message_body}"
    )
    mail.send(msg)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
