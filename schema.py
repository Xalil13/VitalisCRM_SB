import streamlit as st
from snowflake.snowpark.context import get_active_session

@st.cache_resource
def init_tables():
    session = get_active_session()

    # --- 1. TABLES ---
    session.sql("CREATE TABLE IF NOT EXISTS VITALIS_SB.APP.CUSTOMER_SOURCE (SOURCE_ID VARCHAR PRIMARY KEY, SOURCE_NAME VARCHAR, IS_ACTIVE BOOLEAN DEFAULT TRUE)").collect()

    session.sql("""
        CREATE TABLE IF NOT EXISTS VITALIS_SB.APP.CUSTOMER (
            CUSTOMER_ID VARCHAR PRIMARY KEY, CUSTOMER_NAME VARCHAR, EMAIL VARCHAR, PHONE VARCHAR,
            SOURCE_ID VARCHAR, DATE_OF_BIRTH DATE, GENDER VARCHAR, NOTES VARCHAR,
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP(), UPDATED_AT TIMESTAMP, IS_DELETED BOOLEAN DEFAULT FALSE, DELETED_AT TIMESTAMP
        )
    """).collect()

    session.sql("""
        CREATE TABLE IF NOT EXISTS VITALIS_SB.APP.CUSTOMER_REPORT (
            REPORT_ID VARCHAR PRIMARY KEY, CUSTOMER_ID VARCHAR, ORIGINAL_FILENAME VARCHAR, STAGE_PATH VARCHAR,
            EXTRACTION_DATA VARIANT, IS_EXTRACTED BOOLEAN DEFAULT FALSE, EXTRACTED_AT TIMESTAMP,
            UPLOADED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP(), IS_DELETED BOOLEAN DEFAULT FALSE, DELETED_AT TIMESTAMP
        )
    """).collect()

    session.sql("""
        CREATE TABLE IF NOT EXISTS VITALIS_SB.APP.REPORT_MARKER (
            MARKER_ID VARCHAR PRIMARY KEY, REPORT_ID VARCHAR, CUSTOMER_ID VARCHAR, LAB_NAME VARCHAR,
            PATIENT_NAME VARCHAR, REPORT_SECTION VARCHAR, MARKER_NAME VARCHAR, RESULT VARCHAR, UNIT VARCHAR,
            REFERENCE_VALUES VARCHAR, WITHIN_RANGE VARCHAR, IS_DELETED BOOLEAN DEFAULT FALSE
        )
    """).collect()

    session.sql("""
        CREATE TABLE IF NOT EXISTS VITALIS_SB.APP.ACTIVITY_LOG (
            LOG_ID VARCHAR PRIMARY KEY, CUSTOMER_ID VARCHAR, ACTION VARCHAR, DETAILS VARCHAR, USER_NAME VARCHAR,
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        )
    """).collect()

    # --- 2. STORED PROCEDURES (YOUR API) ---

    # SP: Add Customer
    session.sql("""
        CREATE PROCEDURE IF NOT EXISTS VITALIS_SB.APP.SP_ADD_CUSTOMER(
            p_id VARCHAR, p_name VARCHAR, p_email VARCHAR, p_phone VARCHAR,
            p_source_id VARCHAR, p_dob VARCHAR, p_gender VARCHAR, p_notes VARCHAR, p_user VARCHAR
        )
        RETURNS VARCHAR LANGUAGE SQL AS $$
        BEGIN
            INSERT INTO VITALIS_SB.APP.CUSTOMER (CUSTOMER_ID, CUSTOMER_NAME, EMAIL, PHONE, SOURCE_ID, DATE_OF_BIRTH, GENDER, NOTES, UPDATED_AT)
            SELECT :p_id, :p_name, :p_email, :p_phone, :p_source_id, TRY_TO_DATE(:p_dob), :p_gender, :p_notes, CURRENT_TIMESTAMP();

            INSERT INTO VITALIS_SB.APP.ACTIVITY_LOG (LOG_ID, CUSTOMER_ID, ACTION, DETAILS, USER_NAME)
            SELECT UUID_STRING(), :p_id, 'CREATED', 'Customer added', :p_user;

            RETURN 'SUCCESS';
        END;
        $$;
    """).collect()

    # SP: Update Customer Info
    session.sql("""
        CREATE PROCEDURE IF NOT EXISTS VITALIS_SB.APP.SP_UPDATE_CUSTOMER(
            p_id VARCHAR, p_name VARCHAR, p_email VARCHAR, p_phone VARCHAR,
            p_source_id VARCHAR, p_dob VARCHAR, p_gender VARCHAR, p_user VARCHAR
        )
        RETURNS VARCHAR LANGUAGE SQL AS $$
        BEGIN
            UPDATE VITALIS_SB.APP.CUSTOMER
            SET CUSTOMER_NAME = :p_name, EMAIL = :p_email, PHONE = :p_phone,
                SOURCE_ID = :p_source_id, DATE_OF_BIRTH = TRY_TO_DATE(:p_dob), GENDER = :p_gender, UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE CUSTOMER_ID = :p_id;

            INSERT INTO VITALIS_SB.APP.ACTIVITY_LOG (LOG_ID, CUSTOMER_ID, ACTION, DETAILS, USER_NAME)
            SELECT UUID_STRING(), :p_id, 'UPDATED', 'Customer info updated', :p_user;

            RETURN 'SUCCESS';
        END;
        $$;
    """).collect()

    # SP: Update Notes
    session.sql("""
        CREATE PROCEDURE IF NOT EXISTS VITALIS_SB.APP.SP_UPDATE_NOTES(p_id VARCHAR, p_notes VARCHAR, p_user VARCHAR)
        RETURNS VARCHAR LANGUAGE SQL AS $$
        BEGIN
            UPDATE VITALIS_SB.APP.CUSTOMER SET NOTES = :p_notes, UPDATED_AT = CURRENT_TIMESTAMP() WHERE CUSTOMER_ID = :p_id;
            
            INSERT INTO VITALIS_SB.APP.ACTIVITY_LOG (LOG_ID, CUSTOMER_ID, ACTION, DETAILS, USER_NAME) 
            SELECT UUID_STRING(), :p_id, 'NOTES_UPDATED', 'Notes updated', :p_user;
            
            RETURN 'SUCCESS';
        END;
        $$;
    """).collect()

    # SP: Delete Customer (Soft delete everything linked to them)
    session.sql("""
        CREATE PROCEDURE IF NOT EXISTS VITALIS_SB.APP.SP_DELETE_CUSTOMER(p_id VARCHAR, p_user VARCHAR)
        RETURNS VARCHAR LANGUAGE SQL AS $$
        BEGIN
            UPDATE VITALIS_SB.APP.CUSTOMER SET IS_DELETED = TRUE, DELETED_AT = CURRENT_TIMESTAMP() WHERE CUSTOMER_ID = :p_id;
            UPDATE VITALIS_SB.APP.CUSTOMER_REPORT SET IS_DELETED = TRUE, DELETED_AT = CURRENT_TIMESTAMP() WHERE CUSTOMER_ID = :p_id;
            UPDATE VITALIS_SB.APP.REPORT_MARKER SET IS_DELETED = TRUE WHERE CUSTOMER_ID = :p_id;

            INSERT INTO VITALIS_SB.APP.ACTIVITY_LOG (LOG_ID, CUSTOMER_ID, ACTION, DETAILS, USER_NAME) 
            SELECT UUID_STRING(), :p_id, 'DELETED', 'Customer deleted', :p_user;
            
            RETURN 'SUCCESS';
        END;
        $$;
    """).collect()

    # SP: Add Report
    session.sql("""
        CREATE PROCEDURE IF NOT EXISTS VITALIS_SB.APP.SP_ADD_REPORT(p_report_id VARCHAR, p_customer_id VARCHAR, p_filename VARCHAR, p_stage_path VARCHAR, p_user VARCHAR)
        RETURNS VARCHAR LANGUAGE SQL AS $$
        BEGIN
            INSERT INTO VITALIS_SB.APP.CUSTOMER_REPORT (REPORT_ID, CUSTOMER_ID, ORIGINAL_FILENAME, STAGE_PATH) 
            SELECT :p_report_id, :p_customer_id, :p_filename, :p_stage_path;
            
            INSERT INTO VITALIS_SB.APP.ACTIVITY_LOG (LOG_ID, CUSTOMER_ID, ACTION, DETAILS, USER_NAME) 
            SELECT UUID_STRING(), :p_customer_id, 'REPORT_UPLOADED', :p_filename, :p_user;
            
            RETURN 'SUCCESS';
        END;
        $$;
    """).collect()

    # SP: Delete Report
    session.sql("""
        CREATE PROCEDURE IF NOT EXISTS VITALIS_SB.APP.SP_DELETE_REPORT(p_report_id VARCHAR, p_customer_id VARCHAR, p_user VARCHAR)
        RETURNS VARCHAR LANGUAGE SQL AS $$
        BEGIN
            UPDATE VITALIS_SB.APP.CUSTOMER_REPORT SET IS_DELETED = TRUE, DELETED_AT = CURRENT_TIMESTAMP() WHERE REPORT_ID = :p_report_id;
            UPDATE VITALIS_SB.APP.REPORT_MARKER SET IS_DELETED = TRUE WHERE REPORT_ID = :p_report_id;
            
            INSERT INTO VITALIS_SB.APP.ACTIVITY_LOG (LOG_ID, CUSTOMER_ID, ACTION, DETAILS, USER_NAME) 
            SELECT UUID_STRING(), :p_customer_id, 'REPORT_DELETED', 'Report deleted', :p_user;
            
            RETURN 'SUCCESS';
        END;
        $$;
    """).collect()

    # SP: Extract Report
    session.sql("""
         CREATE PROCEDURE IF NOT EXISTS VITALIS_SB.APP.SP_EXTRACT_REPORT(
             P_REPORT_ID VARCHAR, 
             P_CUSTOMER_ID VARCHAR, 
             P_STAGE_PATH VARCHAR, 
             P_BATCH_NUMBER VARCHAR,
             P_USER VARCHAR
         )
         RETURNS VARCHAR
         LANGUAGE SQL
         EXECUTE AS OWNER
         AS $$
         DECLARE
             v_data VARIANT;
             v_parsed VARIANT;
             v_instr_range VARCHAR := 'Given this reference range text, extract the numeric lower bound (start) and upper bound (end). Return ONLY two numbers separated by a pipe character like: start|end. If there is no lower bound write NULL for start. If there is no upper bound write NULL for end. For ranges like "Up to 20" return NULL|20. For "More Than 60" return 60|NULL. For "82.0 - 99.0" return 82.0|99.0. For complex ranges like Hb A1c with Non Diabetic/Pre Diabetic/Diabetic, use the Non Diabetic upper limit as end and NULL as start (e.g. NULL|5.7). Return only the two values separated by pipe, nothing else.';
             v_instr_within VARCHAR := 'Try to parse the result as a numeric value then understand the reference range. If the result falls within the reference range then write Yes. If the result falls out of the reference range write No. If the reference is null then put null. If you are not 100% sure keep it null. If the result means non-diabetic write Yes. Dont write your thinking steps just answer with with one word Yes, No, or Null';
         BEGIN
             -- 1. Extract the JSON from Document AI
             SELECT VITALIS_SB.APP.EXTRACT_LAB_REPORT(:P_STAGE_PATH) INTO :v_data;
 
             IF (:v_data IS NULL OR :v_data = '') THEN
                 RETURN 'Extraction failed: No data returned.';
             END IF;
 
             -- Ensure we cast the returned string into true JSON variant
             v_parsed := PARSE_JSON(:v_data);
 
             -- 2. Update Report metadata
             UPDATE VITALIS_SB.APP.CUSTOMER_REPORT
             SET EXTRACTION_DATA = :v_parsed, IS_EXTRACTED = TRUE, EXTRACTED_AT = CURRENT_TIMESTAMP()
             WHERE REPORT_ID = :P_REPORT_ID;
 
             -- Clear old markers
             DELETE FROM VITALIS_SB.APP.REPORT_MARKER WHERE REPORT_ID = :P_REPORT_ID;
 
             -- 3. Insert markers with AI-parsed reference bounds, AI within-range check, and the BATCH NUMBER
             INSERT INTO VITALIS_SB.APP.REPORT_MARKER (
                 MARKER_ID, REPORT_ID, CUSTOMER_ID, LAB_NAME, PATIENT_NAME,
                 PATIENT_NUMBER, PATIENT_AGE, PATIENT_SEX, PATIENT_DOB,
                 ACCESSION, RECEIVED_DATE, REPORTED_DATE,
                 REPORT_SECTION, MARKER_NAME, RESULT, UNIT, REFERENCE_VALUES,
                 REFERENCE_START, REFERENCE_END, WITHIN_RANGE, BATCH_NUMBER
             )
             SELECT
                 MARKER_ID, REPORT_ID, CUSTOMER_ID, LAB_NAME, PATIENT_NAME,
                 PATIENT_NUMBER, PATIENT_AGE, PATIENT_SEX, PATIENT_DOB,
                 ACCESSION, RECEIVED_DATE, REPORTED_DATE,
                 REPORT_SECTION, MARKER_NAME, RESULT, UNIT, REFERENCE_VALUES,
                 CASE
                     WHEN TRIM(REPLACE(SPLIT_PART(REPLACE(ai_range, '"', ''), '|', 1), ' ', '')) IN ('NULL', 'null', '', 'None', 'none', 'N/A') THEN NULL
                     ELSE TRIM(REPLACE(SPLIT_PART(REPLACE(ai_range, '"', ''), '|', 1), ' ', ''))
                 END,
                 CASE
                     WHEN TRIM(REPLACE(SPLIT_PART(REPLACE(ai_range, '"', ''), '|', 2), ' ', '')) IN ('NULL', 'null', '', 'None', 'none', 'N/A') THEN NULL
                     ELSE TRIM(REPLACE(SPLIT_PART(REPLACE(ai_range, '"', ''), '|', 2), ' ', ''))
                 END,
                 CASE
                     WHEN UPPER(ai_within) LIKE '%YES%' THEN 'Yes'
                     WHEN UPPER(ai_within) LIKE '%NO%' THEN 'No'
                     ELSE NULL
                 END,
                 :P_BATCH_NUMBER
             FROM (
                 SELECT
                     :P_REPORT_ID || '_' || m.index AS MARKER_ID,
                     :P_REPORT_ID AS REPORT_ID,
                     :P_CUSTOMER_ID AS CUSTOMER_ID,
                     CAST(:v_parsed:response:lab_name AS STRING) AS LAB_NAME,
                     CAST(:v_parsed:response:patient_name AS STRING) AS PATIENT_NAME,
                     CAST(:v_parsed:response:patient_number AS STRING) AS PATIENT_NUMBER,
                     CAST(:v_parsed:response:patient_age AS STRING) AS PATIENT_AGE,
                     CAST(:v_parsed:response:patient_sex AS STRING) AS PATIENT_SEX,
                     TRY_TO_DATE(CAST(:v_parsed:response:patient_dob AS STRING)) AS PATIENT_DOB,
                     CAST(:v_parsed:response:accession AS STRING) AS ACCESSION,
                     CAST(:v_parsed:response:received_date AS STRING) AS RECEIVED_DATE,
                     CAST(:v_parsed:response:reported_date AS STRING) AS REPORTED_DATE,
                     COALESCE(CAST(:v_parsed:response:lab_markers:report_section[m.index] AS STRING), CAST(:v_parsed:response:report_section AS STRING), 'Unknown') AS REPORT_SECTION,
                     CAST(:v_parsed:response:lab_markers:marker_name[m.index] AS STRING) AS MARKER_NAME,
                     CAST(:v_parsed:response:lab_markers:result[m.index] AS STRING) AS RESULT,
                     CAST(:v_parsed:response:lab_markers:unit[m.index] AS STRING) AS UNIT,
                     CAST(:v_parsed:response:lab_markers:reference_values[m.index] AS STRING) AS REFERENCE_VALUES,
                     CASE
                         WHEN COALESCE(CAST(:v_parsed:response:lab_markers:reference_values[m.index] AS STRING), 'None') IN ('None', 'none', 'N/A', '')
                         THEN 'NULL|NULL'
                         ELSE AI_COMPLETE('openai-gpt-5-mini', :v_instr_range || ' Reference: ' || CAST(:v_parsed:response:lab_markers:reference_values[m.index] AS STRING))
                     END AS ai_range,
                     AI_COMPLETE('openai-gpt-5-mini', :v_instr_within || ' Result: ' || COALESCE(CAST(:v_parsed:response:lab_markers:result[m.index] AS STRING), 'N/A') || ' Ref: ' || COALESCE(CAST(:v_parsed:response:lab_markers:reference_values[m.index] AS STRING), 'N/A')) AS ai_within
                 FROM LATERAL FLATTEN(input => :v_parsed:response:lab_markers:marker_name) m
             );
 
             -- 4. Log Action
             INSERT INTO VITALIS_SB.APP.ACTIVITY_LOG (LOG_ID, CUSTOMER_ID, ACTION, DETAILS, USER_NAME)
             SELECT UUID_STRING(), :P_CUSTOMER_ID, 'REPORT_EXTRACTED', 'Batch ' || :P_BATCH_NUMBER || ' extracted', :P_USER;
 
             RETURN 'SUCCESS';
         END;
         $$;
     """).collect()