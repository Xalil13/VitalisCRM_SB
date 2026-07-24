import streamlit as st
import pandas as pd
import json
from snowflake.snowpark.context import get_active_session
import snowflake.snowpark.functions as F
from get_schema import get_db_schema

DB_SCHEMA = get_db_schema()

# --- DATA RETRIEVAL ---
@st.cache_data(ttl=3600)
def get_sources():
    session = get_active_session()
    df = session.table(f"{DB_SCHEMA}.CUSTOMER_SOURCE")
    return df.filter(F.col("IS_ACTIVE") == True).select("SOURCE_ID", "SOURCE_NAME").sort(F.col("SOURCE_NAME")).to_pandas()

def get_activity_log(customer_id):
    session = get_active_session()
    df = session.table(f"{DB_SCHEMA}.ACTIVITY_LOG")
    return df.filter(F.col("CUSTOMER_ID") == customer_id).sort(F.col("CREATED_AT").desc()).limit(20).to_pandas()

def get_customers(search_term=""):
    session = get_active_session()
    c = session.table(f"{DB_SCHEMA}.CUSTOMER")
    s = session.table(f"{DB_SCHEMA}.CUSTOMER_SOURCE")
    
    df = c.join(s, c["SOURCE_ID"] == s["SOURCE_ID"], "left").select(c["*"], s["SOURCE_NAME"])
    df = df.filter(c["IS_DELETED"] == False)
    
    if search_term:
        search_col = F.lower(F.lit(f"%{search_term}%"))
        df = df.filter((F.lower(c["CUSTOMER_NAME"]).like(search_col)) | (F.lower(c["CUSTOMER_ID"]).like(search_col)))
        
    return df.sort(c["CREATED_AT"].desc()).to_pandas()

def get_customer_reports(customer_id):
    session = get_active_session()
    df = session.table(f"{DB_SCHEMA}.CUSTOMER_REPORT")
    return df.filter((F.col("CUSTOMER_ID") == customer_id) & (F.col("IS_DELETED") == False)).sort(F.col("UPLOADED_AT").desc()).to_pandas()

def get_customer_markers(customer_id, report_id=None):
    session = get_active_session()
    m = session.table(f"{DB_SCHEMA}.REPORT_MARKER")
    r = session.table(f"{DB_SCHEMA}.CUSTOMER_REPORT")
    
    df = m.join(r, m["REPORT_ID"] == r["REPORT_ID"]).select(m["*"], r["ORIGINAL_FILENAME"], r["STAGE_PATH"])
    df = df.filter((m["CUSTOMER_ID"] == customer_id) & (m["IS_DELETED"] == False) & (r["IS_DELETED"] == False))
    
    if report_id:
        df = df.filter(m["REPORT_ID"] == report_id)
        
    return df.to_pandas()

@st.cache_data(ttl=300)
def get_file_content(stage_path):
    try: return get_active_session().file.get_stream(stage_path).read()
    except: return None

# --- API METHODS (CALLING STORED PROCEDURES) ---
def add_customer(customer_id, name, email, phone, source_id, dob, gender, notes, user_name):
    dob_str = str(dob) if dob else ""
    get_active_session().call(f'{DB_SCHEMA}.SP_ADD_CUSTOMER', customer_id, name or "", email or "", phone or "", source_id or "", dob_str, gender or "", notes or "", user_name)

def update_customer(customer_id, name, email, phone, source_id, dob, gender, user_name):
    dob_str = str(dob) if dob else ""
    get_active_session().call(f'{DB_SCHEMA}.SP_UPDATE_CUSTOMER', customer_id, name or "", email or "", phone or "", source_id or "", dob_str, gender or "", user_name)

def update_notes(customer_id, notes, user_name):
    get_active_session().call(f'{DB_SCHEMA}.SP_UPDATE_NOTES', customer_id, notes or "", user_name)

def delete_customer(customer_id, user_name):
    get_active_session().call(f'{DB_SCHEMA}.SP_DELETE_CUSTOMER', customer_id, user_name)

def add_report(report_id, customer_id, filename, stage_path, user_name):
    get_active_session().call(f'{DB_SCHEMA}.SP_ADD_REPORT', report_id, customer_id, filename, stage_path, user_name)

def delete_report(report_id, customer_id, user_name):
    get_active_session().call(f'{DB_SCHEMA}.SP_DELETE_REPORT', report_id, customer_id, user_name)

# --- AI EXTRACTION (Stored Procedure) ---
def extract_report(report_id, customer_id, stage_path, batch_number, user_name): 
    try:
        df = get_active_session().sql(
            f"CALL {DB_SCHEMA}.SP_EXTRACT_REPORT(?::VARCHAR, ?::VARCHAR, ?::VARCHAR, ?::VARCHAR, ?::VARCHAR)", 
            params=[str(report_id), str(customer_id), str(stage_path), str(batch_number), str(user_name)]
        ).collect()
        
        res = df[0][0]
        
        if res == 'SUCCESS':
            return True, "Success"
        return False, res
    except Exception as e: 
        return False, str(e)