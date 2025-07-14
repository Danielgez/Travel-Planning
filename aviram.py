from flask import Flask, render_template, request, redirect, url_for
import os
import pandas as pd
import requests
import time
import math
import numpy as np

# ... כל הפונקציות שהגדרת למעלה נשארות כפי שהן ...

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
def geocode_address(address):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': address,
        'format': 'json',
        'limit': 1
    }
    headers = {
        'User-Agent': 'MyAppName/1.0 (your_email@example.com)'  # חשוב להכניס מידע אמיתי ליצירת קשר
    }
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    else:
        print(f"Error: {response.status_code} - {response.text}")
    return None, None


def haversine_distance(coord1, coord2):
    # מחשב מרחק בין שתי נקודות גאוגרפיות בקילומטרים
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371  # רדיוס כדור הארץ בק"מ
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def solve_tsp_nearest_neighbor(coords):
    n = len(coords)
    if n == 0:
        return []

    visited = [False] * n
    order = [0]  # מתחילים בנקודה הראשונה (כתובת ההתחלה)
    visited[0] = True

    for _ in range(n - 1):
        last = order[-1]
        next_idx = None
        min_dist = float('inf')
        for i in range(n):
            if not visited[i]:
                dist = haversine_distance(coords[last], coords[i])
                if dist < min_dist:
                    min_dist = dist
                    next_idx = i
        order.append(next_idx)
        visited[next_idx] = True

    return order


@app.route('/show_route', methods=['POST'])
def show_route():
    selected_school = request.form.get('selected_school')
    selected_sheet = request.form.get('sheet_name')
    filename = request.form.get('filename')
    start_address = request.form.get('start_address')
    destination_address = request.form.get('destination_address')

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        df = pd.read_excel(filepath, sheet_name=selected_sheet)
        address_col = None
        school_col = None
        for col in df.columns:
            col_lower = str(col).strip().lower()
            if 'כתובת' in col_lower or 'address' in col_lower:
                address_col = col
            if any(keyword in col_lower for keyword in ['בית ספר', 'מוסד חינוך', 'מוסד', 'school']):
                school_col = col
        if not address_col or not school_col:
            raise ValueError("לא נמצאה עמודת כתובת או בית ספר בגליון.")

        df = add_default_city_to_addresses(df, address_col, school_col, selected_school)

        route_addresses, route_coords = build_route_tsp(
            df, address_col, school_col, selected_school, start_address, destination_address
        )

        return render_template(
            'route.html',
            route_addresses=route_addresses,
            coordinates=route_coords
        )
    except Exception as e:
        return f"שגיאה בעת עיבוד הנתונים: {e}"


@app.route('/input_destination', methods=['POST'])
def input_destination():
    filename = request.form.get('filename')
    sheet_name = request.form.get('sheet_name')
    selected_school = request.form.get('selected_school')
    start_address = request.form.get('start_address')

    return render_template('input_destination.html',
                           filename=filename,
                           sheet_name=sheet_name,
                           selected_school=selected_school,
                           start_address=start_address)



def add_default_city_to_addresses(df, address_col, school_col, selected_school):
    """
    מוסיף עיר ברירת מחדל לכתובות חסרות עיר מתוך כתובת בית הספר שנבחר.
    """
    school_row = df[df[school_col] == selected_school].iloc[0]
    school_address = str(school_row[address_col])
    default_city = school_address.split(',')[-1].strip()

    def ensure_city_in_address(address):
        if pd.isna(address):
            return address
        if ',' not in address:
            return f"{address}, {default_city}"
        last_part = address.split(',')[-1].strip()
        if last_part == '' or last_part.isdigit():
            return f"{address}, {default_city}"
        return address

    df[address_col] = df[address_col].apply(ensure_city_in_address)
    return df



def build_route_tsp(df, address_col, school_col, selected_school, start_address, destination_address=None):
    school_rows = df[df[school_col].astype(str).str.contains(selected_school, case=False, na=False)]
    
    # כל הכתובות במסלול, למעט המוצא והיעד
    all_addresses = [addr for addr in school_rows[address_col].dropna().tolist()
                     if addr != start_address and addr != destination_address]

    start_latlon = geocode_address(start_address)
    if start_latlon == (None, None):
        raise ValueError(f"לא ניתן למצוא את כתובת ההתחלה: {start_address}")

    coords = [start_latlon]
    valid_addresses = [start_address]  # נתחיל עם הכתובת הראשונה

    for addr in all_addresses:
        lat, lon = geocode_address(addr)
        if lat is None or lon is None:
            raise ValueError(f"לא ניתן למצוא את הכתובת: {addr}")
        coords.append((lat, lon))
        valid_addresses.append(addr)

    # פתור את TSP רק על התחנות בדרך
    order = solve_tsp_nearest_neighbor(coords)

    sorted_addresses = [valid_addresses[i] for i in order]
    sorted_coords = [coords[i] for i in order]

    # אם יש יעד סופי - הוסף אותו לאחר המיון
    if destination_address:
        dest_latlon = geocode_address(destination_address)
        if dest_latlon == (None, None):
            raise ValueError(f"לא ניתן למצוא את כתובת היעד: {destination_address}")
        sorted_addresses.append(destination_address)
        sorted_coords.append(dest_latlon)

    return sorted_addresses, sorted_coords

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return "לא נבחר קובץ"
        file = request.files['file']
        if file.filename == '':
            return "לא נבחר קובץ"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        # קבלת שמות הגליונות
        xls = pd.ExcelFile(filepath)
        sheet_names = xls.sheet_names
        return render_template('select_sheet.html', filename=file.filename, sheet_names=sheet_names)

    return render_template('upload.html')


@app.route('/select_school', methods=['POST'])
def select_school():
    selected_sheet = request.form.get('sheet_name')
    filename = request.form.get('filename')

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    df = pd.read_excel(filepath, sheet_name=selected_sheet)

    school_col = None
    for col in df.columns:
        col_lower = str(col).strip().lower()
        if any(keyword in col_lower for keyword in ['בית ספר', 'מוסד חינוך', 'מוסד', 'school']):
            school_col = col
            break
    if not school_col:
        return "לא נמצאה עמודת בית ספר בגליון."

    schools = df[school_col].dropna().unique().tolist()

    return render_template('select_school.html',
                           filename=filename,
                           sheet_name=selected_sheet,
                           schools=schools)


@app.route('/input_start', methods=['POST'])
def input_start():
    selected_school = request.form.get('school_name')
    selected_sheet = request.form.get('sheet_name')
    filename = request.form.get('filename')

    return render_template('input_start.html',
                           filename=filename,
                           sheet_name=selected_sheet,
                           selected_school=selected_school)



if __name__ == '__main__':
    app.run(debug=True)
