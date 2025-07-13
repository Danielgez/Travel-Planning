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

@app.route('/show_route', methods=['POST'])
def show_route():
    selected_school = request.form.get('selected_school')
    selected_sheet = request.form.get('sheet_name')
    filename = request.form.get('filename')
    start_address = request.form.get('start_address')

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        df = pd.read_excel(filepath, sheet_name=selected_sheet)
        address_col = None
        school_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if 'כתובת' in col_lower or 'address' in col_lower:
                address_col = col
            if 'בית ספר' in col_lower or 'מוסד חינוך' in col_lower or 'school' in col_lower:
                school_col = col
        if not address_col or not school_col:
            raise ValueError("לא נמצאה עמודת כתובת או בית ספר בגליון.")

        # הוספת עיר ברירת מחדל לכתובות חסרות עיר מתוך כתובת בית הספר שנבחר
        df = add_default_city_to_addresses(df, address_col, school_col, selected_school)

        # קבלת רשימת כתובות וקואורדינטות
        route_addresses, route_coords = build_route_tsp(
            df, address_col, school_col, selected_school, start_address
        )

        return render_template(
            'route.html',
            route_addresses=route_addresses,
            coordinates=route_coords
        )
    except Exception as e:
        return f"שגיאה בעת עיבוד הנתונים: {e}"



def add_default_city_to_addresses(df, address_col, school_col, selected_school):
    """
    מוסיף עיר ברירת מחדל לכתובות חסרות עיר מתוך כתובת בית הספר שנבחר.
    """
    # מקבל את הכתובת המלאה של בית הספר שנבחר
    school_row = df[df[school_col] == selected_school].iloc[0]
    school_address = str(school_row[address_col])
    # מפצל לפי פסיקים ומוציא את העיר (נניח שהעיר היא הרכיב האחרון בכתובת)
    default_city = school_address.split(',')[-1].strip()

    def ensure_city_in_address(address):
        if pd.isna(address):
            return address
        # אם אין פסיק, נניח שאין עיר ונוסיף
        if ',' not in address:
            return f"{address}, {default_city}"
        # אם החלק האחרון ריק או מספר בלבד, נוסיף עיר
        last_part = address.split(',')[-1].strip()
        if last_part == '' or last_part.isdigit():
            return f"{address}, {default_city}"
        return address

    df[address_col] = df[address_col].apply(ensure_city_in_address)
    return df


def build_route_tsp(df, address_col, school_col, selected_school, start_address):
    school_rows = df[df[school_col] == selected_school]
    addresses = school_rows[address_col].dropna().tolist()

    # מוסיפים את כתובת ההתחלה בראש הרשימה
    route_addresses = [start_address] + addresses

    # ממירים כל כתובת לקואורדינטות
    route_coords = []
    for addr in route_addresses:
        lat, lon = geocode_address(addr)
        if lat is None or lon is None:
            raise ValueError(f"לא ניתן למצוא את הכתובת: {addr}")
        route_coords.append([lat, lon])

    # בונים טקסט פשוט להצגה (לדוגמה)
    route_text = " -> ".join(route_addresses)

    return route_addresses, route_coords


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

    # מציאת עמודות שמכילות את מוסדות הלימוד
    school_col = None
    for col in df.columns:
        col_lower = str(col).lower()
        if 'בית ספר' in col_lower or 'מוסד חינוך' in col_lower or 'school' in col_lower:
            school_col = col
            break
    if not school_col:
        return "לא נמצאה עמודת בית ספר בגליון."

    schools = df[school_col].dropna().unique().tolist()
return render_template('route.html', route_addresses=route_addresses, coordinates=route_coords)


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
