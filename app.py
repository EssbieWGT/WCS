import os
from flask import Flask, request, redirect, url_for, send_from_directory, render_template
import pandas as pd
import chardet
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Persistent storage for user uploads
PERSISTENT_UPLOAD_FOLDER = "/var/uploads"
os.makedirs(PERSISTENT_UPLOAD_FOLDER, exist_ok=True)  # Ensure it exists

# Temporary processing folder (cleared on restart)
TEMP_UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)  # Ensure it exists

app.config['PERSISTENT_UPLOAD_FOLDER'] = PERSISTENT_UPLOAD_FOLDER
app.config['TEMP_UPLOAD_FOLDER'] = TEMP_UPLOAD_FOLDER

# Hardcoded login credentials (environment variables recommended)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
USERNAME = os.getenv('LOGIN_USERNAME')
PASSWORD = os.getenv('LOGIN_PASSWORD')

# Simple in-memory tracking
usage_tracking = {"live_view": 0, "view": 0}

def get_csv_files():
    """Fetch CSV files from PERSISTENT_UPLOAD_FOLDER and sort alphabetically."""
    if not os.path.exists(PERSISTENT_UPLOAD_FOLDER):
        print(f"Warning: PERSISTENT_UPLOAD_FOLDER '{PERSISTENT_UPLOAD_FOLDER}' does not exist.")
        return []
    files = [f for f in os.listdir(PERSISTENT_UPLOAD_FOLDER) if f.endswith(".csv")]
    files.sort(key=lambda f: f.lower())  # Sort case-insensitively
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
    file_path = os.path.join(app.config['PERSISTENT_UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return f"Error: {filename} not found.", 404
    return send_from_directory(app.config['PERSISTENT_UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/upload/<filename>', methods=['POST'])
def upload_file(filename):
    """Handles file uploads and saves them in persistent storage."""
    if 'file' not in request.files:
        return "No file uploaded", 400

    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    original_filename = secure_filename(filename)
    new_filename = f"{os.path.splitext(original_filename)[0]}view.csv"
    file_path = os.path.join(app.config['PERSISTENT_UPLOAD_FOLDER'], new_filename)

    temp_path = os.path.join(app.config['TEMP_UPLOAD_FOLDER'], 'temp_upload')
    file.save(temp_path)

    try:
        if file.filename.lower().endswith('.xlsx'):
            # Convert .xlsx to .csv with utf-8 encoding
            excel_data = pd.read_excel(temp_path, engine='openpyxl')
            excel_data.to_csv(file_path, index=False, encoding='utf-8-sig')
        else:
            # Detect the file encoding using chardet
            with open(temp_path, 'rb') as f:
                raw_data = f.read()
                detected_encoding = chardet.detect(raw_data)['encoding']
            
            # Load CSV with detected encoding
            csv_data = pd.read_csv(temp_path, encoding=detected_encoding, dtype=str, keep_default_na=False)
            
            # Define a function to normalize problematic characters
            def normalize_text(text):
                if isinstance(text, str):
                    text = text.replace('', "'").replace('“', '"').replace('”', '"')
                    text = text.replace('‘', "'").replace('’', "'").replace('–', '-')
                    text = re.sub(r'[^\x00-\x7F]+', '', text)  # Remove any remaining non-ASCII characters
                return text

            # Apply normalization to all text fields in the dataframe
            csv_data = csv_data.applymap(normalize_text)
            
            # Save the cleaned data back to a new CSV file with UTF-8 encoding
            csv_data.to_csv(file_path, index=False, encoding='utf-8-sig')

        os.remove(temp_path)
    except Exception as e:
        return f"Error processing file: {e}"

    return redirect(url_for('main_page'))

@app.route('/uploads/<filename>')
def uploads(filename):
    """Fetches files from the persistent storage folder."""
    file_path = os.path.join(app.config['PERSISTENT_UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return f"Error: {filename} not found.", 404
    return send_from_directory(app.config['PERSISTENT_UPLOAD_FOLDER'], filename)

@app.route('/live_view/<filename>')
def live_view(filename):
    """Loads files from the persistent storage for viewing."""
    usage_tracking["live_view"] += 1
    return render_template('live_view.html', filename=filename, navigation=True)

@app.route('/view/<filename>/<option>')
def view_file(filename, option):
    """Loads files from the persistent storage for rendering."""
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

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
