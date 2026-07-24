import pandas as pd
from datetime import datetime, date
import uuid

def generate_id():
    return datetime.now().strftime('%Y%m%d%H%M%S') + '_' + uuid.uuid4().hex[:4].upper()

def calculate_age(dob):
    if pd.isna(dob): return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))