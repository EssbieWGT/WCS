from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask import flash
import os
import csv
from werkzeug.utils import secure_filename
from datetime import datetime
import pandas as pd
import re
import chardet
from dotenv import load_dotenv  # Load environment variables from .env file


app = Flask(__name__)
TEMP_UPLOAD_FOLDER = 'uploads'
os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)
app.config['TEMP_UPLOAD_FOLDER'] = TEMP_UPLOAD_FOLDER

PERSISTENT_UPLOAD_FOLDER = "/var/uploads"
os.makedirs(PERSISTENT_UPLOAD_FOLDER, exist_ok=True)
app.config['PERSISTENT_UPLOAD_FOLDER'] = PERSISTENT_UPLOAD_FOLDER

# Hardcoded login credentials
app.secret_key = os.getenv('FLASK_SECRET_KEY')
USERNAME = os.getenv('LOGIN_USERNAME')
PASSWORD = os.getenv('LOGIN_PASSWORD')

# Simple in-memory tracking
usage_tracking = {"live_view": 0, "view": 0}

# Helper function to list files from temporary storage (for main page)
def get_temp_files():
    """Fetches CSV files from temporary storage for main page."""
    if not os.path.exists(TEMP_UPLOAD_FOLDER):
        return []
    files = [f for f in os.listdir(TEMP_UPLOAD_FOLDER) if f.endswith(".csv") and not f.endswith("view.csv")]
    files.sort(key=lambda f: f.lower())  # Sorts case-insensitively
    return files

# Helper function to list files from persistent storage (for view.html)
def get_persistent_files():
    """Fetches user-uploaded CSV files from persistent storage."""
    if not os.path.exists(PERSISTENT_UPLOAD_FOLDER):
        return []
    files = [f for f in os.listdir(PERSISTENT_UPLOAD_FOLDER) if f.endswith(".csv")]
    files.sort(key=lambda f: f.lower())  # Sort case-insensitively
    return files

# Helper function to get CSV files
def get_csv_files():
    # Fetch only CSV files and exclude 'view' files, then sort alphabetically
    files = [f for f in os.listdir(TEMP_UPLOAD_FOLDER) if f.endswith(".csv") and not f.endswith("view.csv")]
    files.sort(key=lambda f: f.lower())  # Sorts case-insensitively
    return files

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == USERNAME and request.form['password'] == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('main_page'))
        return "Invalid credentials, try again."
    return render_template('login.html')

@app.route('/main')
def main_page():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    files = get_csv_files()
    return render_template('main.html', files=files, navigation=True)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['TEMP_UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/upload/<filename>', methods=['POST'])
def upload_file(filename):
    if 'file' not in request.files:
        flash("No file uploaded", "error")
        return redirect(url_for('main_page'))

    file = request.files['file']
    if file.filename == '':
        flash("No selected file", "error")
        return redirect(url_for('main_page'))

    original_filename = secure_filename(filename)
    new_filename = f"{os.path.splitext(original_filename)[0]}view.csv"

    persistent_file_path = os.path.join(app.config['PERSISTENT_UPLOAD_FOLDER'], new_filename)
    temp_file_path = os.path.join(app.config['TEMP_UPLOAD_FOLDER'], new_filename)

    try:
        # Save file to persistent storage
        file.save(persistent_file_path)
        file.stream.seek(0)  # Reset stream position
        # Save file to temporary storage
        file.save(temp_file_path)

        if file.filename.lower().endswith('.xlsx'):
            excel_data = pd.read_excel(persistent_file_path, engine='openpyxl')
            excel_data.to_csv(persistent_file_path, index=False, encoding='utf-8-sig')
            excel_data.to_csv(temp_file_path, index=False, encoding='utf-8-sig')
        else:
            # Detect encoding of the uploaded CSV
            with open(persistent_file_path, 'rb') as f:
                detected_encoding = chardet.detect(f.read())['encoding']

            # Read CSV data
            csv_data = pd.read_csv(persistent_file_path, encoding=detected_encoding, dtype=str, keep_default_na=False)

            # Define text normalization
            def normalize_text(text):
                if isinstance(text, str):
                    text = text.replace('', "'").replace('“', '"').replace('”', '"')
                    text = text.replace('‘', "'").replace('’', "'").replace('–', '-')
                    text = re.sub(r'[^\x00-\x7F]+', '', text)
                return text

            # Normalize CSV data
            csv_data = csv_data.applymap(normalize_text)

            # Save normalized CSV data
            csv_data.to_csv(persistent_file_path, index=False, encoding='utf-8-sig')
            csv_data.to_csv(temp_file_path, index=False, encoding='utf-8-sig')

        # Record upload timestamp
        timestamp_path = os.path.join(app.config['TEMP_UPLOAD_FOLDER'], 'upload_timestamp.txt')
        with open(timestamp_path, 'w', encoding='utf-8') as f:
            f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        flash(f"File '{original_filename}' uploaded and processed successfully!", "success")

    except Exception as e:
        flash(f"Error processing file: {e}", "error")

    return redirect(url_for('main_page'))

@app.route('/uploads/<filename>')
def uploads(filename):
    return send_from_directory(app.config['TEMP_UPLOAD_FOLDER'], filename)

@app.route('/live_view/<filename>')
def live_view(filename):
    usage_tracking["live_view"] += 1
    return render_template('live_view.html', filename=filename, navigation=True)

@app.route('/view/<filename>/<option>')
def view_file(filename, option):
    usage_tracking["view"] += 1
    lower_filename = filename.lower()
    if lower_filename == 'joly.csv':
        return render_template('jolyview.html', filename=filename, navigation=True)
    lower_option = option.lower()
    if lower_option == 'links':
        return render_template('links.html', filename=filename, navigation=True)
    elif lower_option == 'cards':
        return render_template('cards.html', filename=filename, navigation=True)
    return render_template('view.html', filename=filename)
def view_file(filename):
    usage_tracking["view"] += 1
    return render_template('view.html', filename=filename, navigation=True)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# Debug Route (Check storage locations)
@app.route('/debug')
def debug_storage():
    """Debugging page to check files in both storage locations."""
    temp_files = get_temp_files()
    persistent_files = get_persistent_files()
    appMap = app.url_map
    return f"""
    <h3>Temporary Storage Files:</h3> {temp_files}
    <h3>Persistent Storage Files:</h3> {persistent_files}
    <h3>App Director: </h3> {appMap}
    """
if __name__ == '__main__':
    app.run(debug=True)