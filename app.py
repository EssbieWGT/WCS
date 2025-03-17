import os
import re
import pandas as pd
import chardet
from flask import Flask, request, redirect, url_for, send_from_directory, render_template, session
from flask import flash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Persistent storage for user uploads (Available to `view.html`)
PERSISTENT_UPLOAD_FOLDER = "/var/uploads"
os.makedirs(PERSISTENT_UPLOAD_FOLDER, exist_ok=True)

# Temporary storage for main page & downloads (Cleared after restart)
TEMP_UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")  # Use GitHub folder directly
os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)

app.config['PERSISTENT_UPLOAD_FOLDER'] = PERSISTENT_UPLOAD_FOLDER
app.config['TEMP_UPLOAD_FOLDER'] = TEMP_UPLOAD_FOLDER

# Hardcoded login credentials (environment variables recommended)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'defaultsecretkey')  # Set default for local testing
USERNAME = os.getenv('LOGIN_USERNAME', 'admin')
PASSWORD = os.getenv('LOGIN_PASSWORD', 'password')

# Basic usage tracking
usage_tracking = {"live_view": 0, "view": 0}

# Helper function to normalize text
def normalize_text(text):
    """Fixes curly quotes, dashes, and removes non-ASCII characters."""
    if isinstance(text, str):
        text = text.replace('', "'").replace('“', '"').replace('”', '"')
        text = text.replace('‘', "'").replace('’', "'").replace('–', '-')
        text = re.sub(r'[^\x00-\x7F]+', '', text)  # Remove remaining non-ASCII characters
    return text

# Helper function to list files from temporary storage (for main page)
def get_temp_files():
    """Fetches CSV files from temporary storage for main page."""
    if not os.path.exists(TEMP_UPLOAD_FOLDER):
        return []
    files = [f for f in os.listdir(TEMP_UPLOAD_FOLDER) if f.endswith(".csv")]
    files.sort(key=lambda f: f.lower())  # Sort case-insensitively
    return files

# Helper function to list files from persistent storage (for view.html)
def get_persistent_files():
    """Fetches user-uploaded CSV files from persistent storage."""
    if not os.path.exists(PERSISTENT_UPLOAD_FOLDER):
        return []
    files = [f for f in os.listdir(PERSISTENT_UPLOAD_FOLDER) if f.endswith(".csv")]
    files.sort(key=lambda f: f.lower())  # Sort case-insensitively
    return files

# Login Page
@app.route('/', methods=['GET', 'POST'])
def login():
    """Handles user authentication."""
    if request.method == 'POST':
        if request.form['username'] == USERNAME and request.form['password'] == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('main_page'))
        return "Invalid credentials, try again."
    return render_template('login.html')

# Main Page (shows temporary storage files)
@app.route('/main')
def main_page():
    """Displays the main page with CSV files from temporary storage."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    files = get_temp_files()
    return render_template('main.html', files=files, navigation=True)

@app.route('/upload/<filename>', methods=['POST'])
def upload_file(filename):
    """Handles file uploads and flashes a success message on `main.html`."""
    if 'file' not in request.files:
        flash("No file uploaded", "error")
        return redirect(url_for('main_page'))

    file = request.files['file']
    if file.filename == '':
        flash("No selected file", "error")
        return redirect(url_for('main_page'))

    original_filename = secure_filename(filename)

    # Save file in persistent storage (for `view.html`)
    persistent_file_path = os.path.join(app.config['PERSISTENT_UPLOAD_FOLDER'], original_filename)

    # Also save a copy in temporary storage (for `/main` and `/download`)
    temp_file_path = os.path.join(app.config['TEMP_UPLOAD_FOLDER'], original_filename)

    file.save(persistent_file_path)
    file.save(temp_file_path)

    flash(f"File '{original_filename}' uploaded successfully!", "success")
    return redirect(url_for('main_page'))

# View Page (Loads user-uploaded files from persistent storage for `view.html`)
@app.route('/view/<filename>')
def view_file(filename):
    """Displays user-uploaded files from persistent storage in `view.html`."""
    usage_tracking["view"] += 1
    file_path = os.path.join(app.config['PERSISTENT_UPLOAD_FOLDER'], filename)

    if not os.path.exists(file_path):
        return f"Error: {filename} not found.", 404

    return render_template('view.html', filename=filename, navigation=True)

# Download File (Allows users to download from temporary storage)
@app.route('/download/<filename>')
def download_file(filename):
    """Allows users to download only files from temporary storage (`/tmp/uploads`)."""
    file_path = os.path.join(app.config['TEMP_UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return f"Error: {filename} not found.", 404
    return send_from_directory(app.config['TEMP_UPLOAD_FOLDER'], filename, as_attachment=True)

# Live View Page (Loads files from temporary storage)
@app.route('/live_view/<filename>')
def live_view(filename):
    """Loads files from temporary storage for live viewing (should not persist)."""
    usage_tracking["live_view"] += 1
    temp_file_path = os.path.join(app.config['TEMP_UPLOAD_FOLDER'], filename)

    if not os.path.exists(temp_file_path):
        return f"Error: {filename} not found in temporary storage.", 404

    return render_template('live_view.html', filename=filename, navigation=True)

# Logout
@app.route('/logout')
def logout():
    """Logs out the user and clears session."""
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# Debug Route (Check storage locations)
@app.route('/debug')
def debug_storage():
    """Debugging page to check files in both storage locations."""
    temp_files = get_temp_files()
    persistent_files = get_persistent_files()
    return f"""
    <h3>Temporary Storage Files:</h3> {temp_files}
    <h3>Persistent Storage Files:</h3> {persistent_files}
    """

if __name__ == '__main__':
    app.run(debug=True)
