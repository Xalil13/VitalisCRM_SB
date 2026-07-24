import streamlit as st
from snowflake.snowpark.context import get_active_session
import snowflake.snowpark.functions as F
import pandas as pd
from datetime import date
from utils import generate_id, calculate_age
from schema import init_tables
import database as db

st.set_page_config(page_title="Vitalis CRM", layout="wide", page_icon="🏥")
session = get_active_session()
init_tables() 

if "success_toast" in st.session_state:
    st.toast(st.session_state.success_toast)
    del st.session_state.success_toast

@st.cache_data(ttl=600)
def get_dashboard_stats():
    user = session.sql("SELECT CURRENT_USER()").collect()[0][0]
    c_count = session.table("VITALIS_DEV.APP.CUSTOMER").where(~F.col("IS_DELETED")).count()
    r_count = session.table("VITALIS_DEV.APP.CUSTOMER_REPORT").where(~F.col("IS_DELETED")).count()
    return user, c_count, r_count

current_user, total_customers, total_reports = get_dashboard_stats()

@st.dialog("⚠️ Confirm Deletion")
def delete_customer_dialog(cust_id, cust_name):
    st.write(f"Are you sure you want to delete **{cust_name}**?")
    if st.button("Confirm Deletion", type="primary", use_container_width=True):
        db.delete_customer(cust_id, current_user)
        st.rerun()
    if st.button("Cancel", use_container_width=True): st.rerun()

with st.sidebar:
    st.title("🏥 Vitalis"); st.caption(f"👤 {current_user}"); st.divider()
    st.metric("Total Customers", int(total_customers)); st.metric("Total Reports", int(total_reports))

# FIXED: Navigation state management
if "switch_nav" in st.session_state:
    st.session_state.main_nav = st.session_state.switch_nav
    del st.session_state.switch_nav

st.radio("Navigation", ["📋 Customer List", "➕ Add Customer"], key="main_nav", horizontal=True, label_visibility="collapsed")
st.divider()

# --- ADD CUSTOMER ---
if st.session_state.main_nav == "➕ Add Customer":
    st.subheader("Create New Customer")
    sources = db.get_sources(); source_opts = {row['SOURCE_NAME']: row['SOURCE_ID'] for _, row in sources.iterrows()}

    with st.form("new_customer_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            n_name = st.text_input("Name *")
            n_email = st.text_input("Email")
            n_phone = st.text_input("Phone")
            n_dob = st.date_input("Date of Birth", value=None, min_value=date(1900,1,1), max_value=date.today())
        with col2:
            n_gender = st.selectbox("Gender", ["", "Male", "Female", "Other"])
            n_source = st.selectbox("Source", options=list(source_opts.keys()))
            n_notes = st.text_area("Notes", height=100)
        
        if st.form_submit_button("Create Customer", use_container_width=True, type="primary"):
            if n_name:
                db.add_customer(generate_id(), n_name, n_email, n_phone, source_opts.get(n_source), n_dob, n_gender, n_notes, current_user)
                # Tell Streamlit to switch tabs on the next run
                st.session_state.switch_nav = "📋 Customer List"
                st.rerun()
            else: st.error("Name is required")

# --- CUSTOMER LIST & DETAIL VIEW ---
else:
    search_term = st.text_input("🔍 Search", placeholder="Name, ID, Email, or Phone...")
    customers = db.get_customers(search_term)
    
    if customers.empty: st.info("No customers found.")
    else:
        customer_map = {f"{r.CUSTOMER_NAME} ({r.CUSTOMER_ID})": r.CUSTOMER_ID for r in customers.itertuples()}
        sel_id = customer_map[st.selectbox("Select Customer", options=list(customer_map.keys()))]
        sel_cust = customers[customers['CUSTOMER_ID'] == sel_id].iloc[0]
        
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            age = calculate_age(sel_cust['DATE_OF_BIRTH'])
            def p_item(icon, label, value): return f"<div style='font-size: 0.9rem; padding: 2px 0;'><span style='color: gray;'>{icon} {label}:</span> {value}</div>"

            with c1: st.markdown(p_item("📧", "Email", sel_cust['EMAIL'] or "N/A"), unsafe_allow_html=True); st.markdown(p_item("📞", "Phone", sel_cust['PHONE'] or "N/A"), unsafe_allow_html=True)
            with c2: st.markdown(p_item("🎂", "Age", age if age else "N/A"), unsafe_allow_html=True); st.markdown(p_item("⚧", "Gender", sel_cust['GENDER'] or "N/A"), unsafe_allow_html=True)
            with c3: st.markdown(p_item("🌐", "Source", sel_cust['SOURCE_NAME'] or "N/A"), unsafe_allow_html=True); st.markdown(p_item("📄", "Reports", len(db.get_customer_reports(sel_id))), unsafe_allow_html=True)

        # FIXED: Details tab state management
        tab = st.radio("Details", ["Reports", "Markers", "Edit", "Notes", "Activity"], key="detail_tabs", horizontal=True, label_visibility="collapsed")
        st.divider()

        if tab == "Reports":
            if "up_key" not in st.session_state: st.session_state.up_key = 0
            with st.container(border=True):
                uploaded_files = st.file_uploader("Upload New PDF(s)", type=['pdf'], accept_multiple_files=True, key=f"up_{st.session_state.up_key}", label_visibility="collapsed")
                if st.button("📤 Upload Files", disabled=not uploaded_files):
                    with st.spinner("Uploading..."):
                        for f in uploaded_files:
                            rid = generate_id()
                            spath = f"@VITALIS_DEV.APP.LAB_REPORT_LANDING/{sel_id}/{rid}_{f.name}"
                            session.file.put_stream(f, spath, auto_compress=False, overwrite=True)
                            db.add_report(rid, sel_id, f.name, spath, current_user)
                    st.session_state.up_key += 1; st.rerun()

            reports = db.get_customer_reports(sel_id)
            if not reports.empty:
                h_cols = st.columns([2, 2.5, 1.5, 1.5, 1, 0.6, 0.6, 0.6])
                h_cols[0].markdown("**Name**"); h_cols[1].markdown("**Stage Path**"); h_cols[2].markdown("**Uploaded**"); h_cols[3].markdown("**Extracted**"); h_cols[4].markdown("**Status**"); h_cols[5].markdown("**Actions**")
                st.divider()
                
                for _, r in reports.iterrows():
                    r_cols = st.columns([2, 2.5, 1.5, 1.5, 1, 0.6, 0.6, 0.6])
                    r_cols[0].write(r['ORIGINAL_FILENAME']); r_cols[1].caption(r['STAGE_PATH'])
                    r_cols[2].write(r['UPLOADED_AT'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['UPLOADED_AT']) else "N/A")
                    r_cols[3].write(r['EXTRACTED_AT'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['EXTRACTED_AT']) else "N/A")
                    r_cols[4].write("✅ Yes" if r['IS_EXTRACTED'] else "⏳ No")
                    
                    with r_cols[5].popover("▶️ Ext" if not r['IS_EXTRACTED'] else "🔄 Re-Ext"):
                        st.markdown("**Manual Extraction**")
                        batch_val = st.text_input("Assign Batch #", key=f"bnum_{r['REPORT_ID']}")
                        
                        # The button is disabled until the user types something in the Batch field
                        if st.button("Start Extraction", key=f"ex_{r['REPORT_ID']}", type="primary", disabled=not batch_val, use_container_width=True):
                            with st.spinner(f"Extracting as Batch {batch_val}..."): 
                                success, msg = db.extract_report(r['REPORT_ID'], sel_id, r['STAGE_PATH'], batch_val, current_user)
                                if success:
                                    st.session_state.success_toast = f"✅ Extracted successfully into Batch {batch_val}!"
                                    st.rerun()
                                else:
                                    st.error(f"Extraction failed: {msg}")
                    
                    content = db.get_file_content(r['STAGE_PATH'])
                    if content: r_cols[6].download_button("⬇️", content, r['ORIGINAL_FILENAME'], "application/pdf", key=f"dl_{r['REPORT_ID']}")
                    else: r_cols[6].write("") 
                        
                    with r_cols[7].popover("🗑️"):
                        if st.button("Confirm", key=f"del_{r['REPORT_ID']}", type="primary"):
                            db.delete_report(r['REPORT_ID'], sel_id, current_user)
                            st.rerun()
                    st.divider()
            else: st.info("No reports have been uploaded yet.")

        elif tab == "Markers":
            reports = db.get_customer_reports(sel_id); rep_opts = {"All Reports": None}
            for _, r in reports.iterrows():
                if r['IS_EXTRACTED']: rep_opts[f"{r['ORIGINAL_FILENAME']} ({r['UPLOADED_AT'].strftime('%Y-%m-%d')})"] = r['REPORT_ID']
            
            sel_rep = rep_opts[st.selectbox("Filter by Report", options=list(rep_opts.keys()))]
            markers = db.get_customer_markers(sel_id, sel_rep)
            if not markers.empty:
                csv_df = markers.drop(columns=['IS_DELETED'], errors='ignore')
                st.download_button("📥 Download Full CSV", csv_df.to_csv(index=False).encode('utf-8'), f"markers_{sel_id}.csv", "text/csv")
                
                cols_order = ['ORIGINAL_FILENAME', 'REPORT_SECTION', 'BATCH_NUMBER', 'MARKER_NAME', 'RESULT', 'UNIT', 'REFERENCE_VALUES','REFERENCE_START','REFERENCE_END', 'WITHIN_RANGE', 'STAGE_PATH']
                disp = markers[cols_order].copy(); disp.columns = ['Report Name', 'Section','Batch Number', 'Marker', 'Result', 'Unit', 'Reference','Reference Start', 'Reference End', 'Within Range', 'Storage Path']
                st.dataframe(disp, use_container_width=True, hide_index=True)
            else: st.info("No markers found.")

        elif tab == "Edit":
            sources = db.get_sources(); source_opts = {row['SOURCE_NAME']: row['SOURCE_ID'] for _, row in sources.iterrows()}
            with st.form("edit_customer_form"):
                col1, col2 = st.columns(2)
                with col1:
                    e_name = st.text_input("Name", value=sel_cust['CUSTOMER_NAME'] or "")
                    e_email = st.text_input("Email", value=sel_cust['EMAIL'] or "")
                    e_phone = st.text_input("Phone", value=sel_cust['PHONE'] or "")
                with col2:
                    e_dob = st.date_input("Date of Birth", value=sel_cust['DATE_OF_BIRTH'] if pd.notna(sel_cust['DATE_OF_BIRTH']) else None)
                    e_gender = st.selectbox("Gender", ["", "Male", "Female", "Other"], index=["", "Male", "Female", "Other"].index(sel_cust['GENDER'] or ""))
                    s_list = list(source_opts.keys()); curr_s = sel_cust['SOURCE_NAME'] if pd.notna(sel_cust['SOURCE_NAME']) else s_list[0]
                    e_source = st.selectbox("Source", s_list, index=s_list.index(curr_s) if curr_s in s_list else 0)
                
                if st.form_submit_button("💾 Save Changes", use_container_width=True, type="primary"):
                    db.update_customer(sel_id, e_name, e_email, e_phone, source_opts[e_source], e_dob, e_gender, current_user)
                    st.success("Saved!"); st.rerun()
            if st.button("🗑️ Delete Customer", use_container_width=True): delete_customer_dialog(sel_id, sel_cust['CUSTOMER_NAME'])

        elif tab == "Notes":
            notes = st.text_area("Notes", value=sel_cust['NOTES'] or "", height=200)
            if st.button("Save Notes", use_container_width=True):
                db.update_notes(sel_id, notes, current_user)
                st.success("Notes saved"); st.rerun()
        
        elif tab == "Activity": st.dataframe(db.get_activity_log(sel_id), use_container_width=True)