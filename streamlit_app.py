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
    # Use db.DB_SCHEMA
    c_count = session.table(f"{db.DB_SCHEMA}.CUSTOMER").where(~F.col("IS_DELETED")).count()
    r_count = session.table(f"{db.DB_SCHEMA}.CUSTOMER_REPORT").where(~F.col("IS_DELETED")).count()
    return user, c_count, r_count

current_user, total_customers, total_reports = get_dashboard_stats()

@st.dialog("⚠️ Confirm Deletion")
def delete_customer_dialog(cust_id, cust_name):
    st.write(f"Are you sure you want to delete **{cust_name}**?")
    if st.button("Confirm Deletion", type="primary", use_container_width=True):
        db.delete_customer(cust_id, current_user)
        st.rerun()
    if st.button("Cancel", use_container_width=True): 
        st.rerun()

@st.dialog("⚠️ Confirm Deletion")
def delete_biomarker_dialog(b_id, b_name):
    st.write(f"Are you sure you want to delete **{b_name}**?")
    st.error("This action will remove the biomarker from active lists.")
    if st.button("Confirm Deletion", type="primary", use_container_width=True):
        db.delete_biomarker(b_id, current_user)
        st.session_state.success_toast = "🗑️ Biomarker deleted."
        st.rerun()
    if st.button("Cancel", use_container_width=True): 
        st.rerun()

@st.dialog("📊 All Biomarker Records", width="large")
def view_all_biomarkers_dialog():
    # Fetch all records by passing an empty search string
    all_b = db.get_biomarkers("") 
    if all_b.empty:
        st.info("No biomarkers found.")
    else:
        # Sort and select specific columns for a clean display
        all_b = all_b.sort_values(by="BIOMARKER", ascending=True)
        disp_df = all_b[['BIOMARKER', 'PANEL', 'UNIT', 'SUPPLEMENT_RESPONSIVE', 'HIGHER_IS_BETTER']]
        st.dataframe(disp_df, use_container_width=True, hide_index=True)
    
with st.sidebar:
    st.title("🏥 Vitalis")
    st.caption(f"👤 {current_user}")
    st.divider()
    st.metric("Total Customers", int(total_customers))
    st.metric("Total Reports", int(total_reports))

# FIXED: Navigation state management
if "switch_nav" in st.session_state:
    st.session_state.main_nav = st.session_state.switch_nav
    del st.session_state.switch_nav

# 1. Initialize the Master Switch
if "in_config_mode" not in st.session_state:
    st.session_state.in_config_mode = False

def toggle_config():
    st.session_state.in_config_mode = not st.session_state.in_config_mode

def on_radio_change():
    # If the user clicks a radio button, force the app out of Config mode
    st.session_state.in_config_mode = False

# 2. Render the Top Bar
nav_c1, nav_c2 = st.columns([6, 1])
with nav_c1:
    options = ["📋 Customer List", "➕ Add Customer"]
    current_nav = st.session_state.get("main_nav", "📋 Customer List")
    
    # Visually clear the radio selection if in Config mode
    radio_idx = None if st.session_state.in_config_mode else (options.index(current_nav) if current_nav in options else 0)
    
    st.radio("Navigation", options, index=radio_idx, key="main_nav", horizontal=True, label_visibility="collapsed", on_change=on_radio_change)

with nav_c2:
    btn_label = "🔙 Exit Config" if st.session_state.in_config_mode else "⚙️ Config"
    st.button(btn_label, use_container_width=True, on_click=toggle_config)

st.divider()


# ==========================================
# APP ROUTING (STRICT ISOLATION)
# ==========================================

if st.session_state.in_config_mode:
    # --- CONFIGURATION MODE ---
    st.header("⚙️ Configuration")
    
    tab_bio, tab_supp, tab_map = st.tabs(["🧬 Biomarkers", "💊 Supplements", "🔗 Marker Mapping"])
    
    with tab_bio:
        st.subheader("Biomarkers Management")
        with st.expander("➕ Add New Biomarker", expanded=False):
            with st.form("new_biomarker_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    n_bio = st.text_input("Biomarker Name *")
                    n_panel = st.text_input("Panel *")
                    n_unit = st.text_input("Unit *")
                with col2:
                    n_supp = st.selectbox("Supplement-responsive?", ["Yes", "No", "Indirect", "Safety flag", "N/A"])
                    n_higher = st.selectbox("Higher is better?", ["Yes", "No (low is good)", "N/A", "N/A (directional)"])
                
                if st.form_submit_button("Add Biomarker", type="primary", use_container_width=True):
                    if n_bio and n_panel and n_unit:
                        db.add_biomarker(n_bio, n_panel, n_unit, n_supp, n_higher, current_user)
                        st.session_state.success_toast = f"✅ Biomarker '{n_bio}' added!"
                        st.rerun()
                    else:
                        st.error("Please fill in all required fields (*).")
                        
        st.divider()
        st.write("") # Small spacing
        search_col, btn_col = st.columns([4, 1], vertical_alignment="bottom")
    
        with search_col:
            b_search = st.text_input("🔍 Search Biomarkers", placeholder="Type biomarker name, panel, unit, or letter to filter...", label_visibility="collapsed")
        with btn_col:
            if st.button("📊 View All Records"):
                view_all_biomarkers_dialog()
        biomarkers = db.get_biomarkers(b_search)
        if biomarkers.empty:
            st.info("No active biomarkers found matching your search.")
        else:
            biomarkers = biomarkers.sort_values(by="BIOMARKER", ascending=True)
            b_map = {f"{r.BIOMARKER} - {r.UNIT} ({r.PANEL})": r.ID for r in biomarkers.itertuples()}
            sel_b_name = st.selectbox("Select Biomarker to view details", options=list(b_map.keys()))
            sel_b_id = b_map[sel_b_name]
            sel_b_data = biomarkers[biomarkers['ID'] == sel_b_id].iloc[0]
            
            with st.container(border=True):
                h_col1, h_col2, h_col3 = st.columns([6, 2, 2])
                with h_col1:
                    st.markdown(f"### {sel_b_data['BIOMARKER']}")
                    st.caption(f"Panel: {sel_b_data['PANEL']} | Unit: {sel_b_data['UNIT']}")
                with h_col2:
                    if st.button("✏️ Edit", use_container_width=True, key=f"edit_btn_{sel_b_id}"):
                        st.session_state.edit_biomarker_id = sel_b_id
                        st.rerun()
                with h_col3:
                    if st.button("🗑️ Delete", type="primary", use_container_width=True, key=f"del_btn_{sel_b_id}"):
                        delete_biomarker_dialog(sel_b_id, sel_b_data['BIOMARKER'])
                st.divider()
                
                if st.session_state.get("edit_biomarker_id") == sel_b_id:
                    with st.form(f"edit_form_{sel_b_id}"):
                        st.markdown("**Edit Details**")
                        c1, c2 = st.columns(2)
                        with c1:
                            e_bio = st.text_input("Biomarker Name", value=sel_b_data['BIOMARKER'])
                            e_panel = st.text_input("Panel", value=sel_b_data['PANEL'])
                            e_unit = st.text_input("Unit", value=sel_b_data['UNIT'])
                        with c2:
                            supp_options = ["Yes", "No", "Indirect", "Safety flag", "N/A", "Monitor", "Safety gate", "Safety check", "Modifier"]
                            curr_supp = sel_b_data['SUPPLEMENT_RESPONSIVE']
                            e_supp = st.selectbox("Supplement-responsive?", supp_options, index=supp_options.index(curr_supp) if curr_supp in supp_options else 0)
                            
                            high_options = ["Yes", "No (low is good)", "N/A", "N/A (directional)", "N/A (optimal range)"]
                            curr_high = sel_b_data['HIGHER_IS_BETTER']
                            e_higher = st.selectbox("Higher is better?", high_options, index=high_options.index(curr_high) if curr_high in high_options else 0)
                        
                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1:
                            if st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True):
                                db.update_biomarker(sel_b_id, e_bio, e_panel, e_unit, e_supp, e_higher, current_user)
                                st.session_state.success_toast = "✅ Changes saved!"
                                st.session_state.edit_biomarker_id = None
                                st.rerun()
                        with btn_c2:
                            if st.form_submit_button("Cancel", use_container_width=True):
                                st.session_state.edit_biomarker_id = None
                                st.rerun()
                else:
                    # Detail View (Read-Only) using standard Markdown
                    c1, c2 = st.columns(2)
                    c1.markdown(f"**Supplement-Responsive:**  \n{sel_b_data['SUPPLEMENT_RESPONSIVE']}")
                    c2.markdown(f"**Higher is Better:**  \n{sel_b_data['HIGHER_IS_BETTER']}")

    with tab_supp:
        st.subheader("Supplement Master")
        st.info("Add, edit, or delete supplements directly in the table below. Click 'Save Changes' when done.")
        supp_df = db.get_supplements()
        
        edited_supp = st.data_editor(
            supp_df, 
            num_rows="dynamic", 
            use_container_width=True, 
            key="supp_editor",
            column_config={"ID": None, "UPDATED_AT": None} # Hide system columns
        )
        
        if st.button("💾 Save Supplement Changes", type="primary"):
            edits = st.session_state["supp_editor"]
            # Handle Edits
            for idx, changes in edits["edited_rows"].items():
                row = supp_df.iloc[idx].to_dict()
                row.update(changes)
                db.upsert_supplement(row['ID'], row.get('INGREDIENT_NAME'), row.get('MIN_DOSE'), row.get('STANDARD_DOSE'), row.get('MAX_DOSE'), row.get('UNIT'), row.get('FOOD_REQUIRED'), row.get('SPECIAL_POPULATIONS'), row.get('HARD_STOP'), row.get('DOSE_CAP'), row.get('MONITORING_REQUIRED'), row.get('MALE_MODIFIER'), row.get('FEMALE_MODIFIER'), row.get('AGE_MODIFIER_18_34'), row.get('AGE_MODIFIER_35_49'), row.get('AGE_MODIFIER_50_64'), row.get('AGE_MODIFIER_65_PLUS'))
            # Handle Adds
            for row in edits["added_rows"]:
                db.upsert_supplement(None, row.get('INGREDIENT_NAME'), row.get('MIN_DOSE'), row.get('STANDARD_DOSE'), row.get('MAX_DOSE'), row.get('UNIT'), row.get('FOOD_REQUIRED', False), row.get('SPECIAL_POPULATIONS'), row.get('HARD_STOP', False), row.get('DOSE_CAP', False), row.get('MONITORING_REQUIRED', False), row.get('MALE_MODIFIER'), row.get('FEMALE_MODIFIER'), row.get('AGE_MODIFIER_18_34'), row.get('AGE_MODIFIER_35_49'), row.get('AGE_MODIFIER_50_64'), row.get('AGE_MODIFIER_65_PLUS'))
            
            st.session_state.success_toast = "✅ Supplements updated!"
            st.rerun()

    with tab_map:
        st.subheader("Supplement Marker Mapping")
        map_df = db.get_mappings()
        
        # 1. Create lookup dictionaries (Name -> ID) for saving later
        bio_df = db.get_biomarkers("")
        bio_map = {row['BIOMARKER']: row['ID'] for _, row in bio_df.iterrows()} if not bio_df.empty else {}
        
        supp_df = db.get_supplements()
        supp_map = {row['INGREDIENT_NAME']: row['ID'] for _, row in supp_df.iterrows()} if not supp_df.empty else {}
        
        # 2. Display the Data Editor using Names instead of IDs
        edited_map = st.data_editor(
            map_df, 
            num_rows="dynamic", 
            use_container_width=True, 
            key="map_editor",
            column_config={
                "ID": None, # Hide the mapping row ID
                "BIOMARKER_NAME": st.column_config.SelectboxColumn("Biomarker", options=list(bio_map.keys()), required=True),
                "INGREDIENT_NAME": st.column_config.SelectboxColumn("Ingredient", options=list(supp_map.keys()), required=True)
            }
        )
        
        if st.button("💾 Save Mapping Changes", type="primary"):
            edits = st.session_state["map_editor"]
            
            # Handle Edits
            for idx, changes in edits["edited_rows"].items():
                row = map_df.iloc[idx].to_dict()
                row.update(changes)
                
                # Translate the selected Name back to the database ID
                b_id = bio_map.get(row.get('BIOMARKER_NAME'))
                i_id = supp_map.get(row.get('INGREDIENT_NAME'))
                
                db.upsert_mapping(
                    row['ID'], b_id, row.get('RESULT_TIER'), i_id, row.get('DOSE_TIER'), 
                    row.get('PRIORITY_RANK'), row.get('DOSE_DECIDER'), row.get('MUST_BE_CO_DOSE_WITH'), 
                    row.get('FORMULAS'), row.get('EXPECTED_DELTA_W4'), row.get('EXPECTED_DELTA_W12')
                )
                
            # Handle Adds
            for row in edits["added_rows"]:
                # Translate the selected Name back to the database ID
                b_id = bio_map.get(row.get('BIOMARKER_NAME'))
                i_id = supp_map.get(row.get('INGREDIENT_NAME'))
                
                db.upsert_mapping(
                    None, b_id, row.get('RESULT_TIER'), i_id, row.get('DOSE_TIER'), 
                    row.get('PRIORITY_RANK'), row.get('DOSE_DECIDER', ""), row.get('MUST_BE_CO_DOSE_WITH'), 
                    row.get('FORMULAS'), row.get('EXPECTED_DELTA_W4'), row.get('EXPECTED_DELTA_W12')
                )
            
            st.session_state.success_toast = "✅ Mappings updated!"
            st.rerun()

else:
    # --- CRM MODE (ISOLATED) ---
    
    if st.session_state.main_nav == "➕ Add Customer":
        st.subheader("Create New Customer")
        sources = db.get_sources()
        source_opts = {row['SOURCE_NAME']: row['SOURCE_ID'] for _, row in sources.iterrows()}

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
                    st.session_state.switch_nav = "📋 Customer List"
                    st.rerun()
                else: 
                    st.error("Name is required")    

    # --- CUSTOMER LIST & DETAIL VIEW ---
    elif st.session_state.main_nav == "📋 Customer List":
        search_term = st.text_input("🔍 Search", placeholder="Name, ID, Email, or Phone...")
        customers = db.get_customers(search_term)
        
        if customers.empty: 
            st.info("No customers found.")
        else:
            customer_map = {f"{r.CUSTOMER_NAME} ({r.CUSTOMER_ID})": r.CUSTOMER_ID for r in customers.itertuples()}
            sel_id = customer_map[st.selectbox("Select Customer", options=list(customer_map.keys()))]
            sel_cust = customers[customers['CUSTOMER_ID'] == sel_id].iloc[0]
            
            with st.container(border=True):
                c1, c2, c3 = st.columns(3)
                age = calculate_age(sel_cust['DATE_OF_BIRTH'])
                def p_item(icon, label, value): return f"<div style='font-size: 0.9rem; padding: 2px 0;'><span style='color: gray;'>{icon} {label}:</span> {value}</div>"

                with c1: 
                    st.markdown(p_item("📧", "Email", sel_cust['EMAIL'] or "N/A"), unsafe_allow_html=True)
                    st.markdown(p_item("📞", "Phone", sel_cust['PHONE'] or "N/A"), unsafe_allow_html=True)
                with c2: 
                    st.markdown(p_item("🎂", "Age", age if age else "N/A"), unsafe_allow_html=True)
                    st.markdown(p_item("⚧", "Gender", sel_cust['GENDER'] or "N/A"), unsafe_allow_html=True)
                with c3: 
                    st.markdown(p_item("🌐", "Source", sel_cust['SOURCE_NAME'] or "N/A"), unsafe_allow_html=True)
                    st.markdown(p_item("📄", "Reports", len(db.get_customer_reports(sel_id))), unsafe_allow_html=True)

            # Details tab state management
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
                                # Use db.DB_SCHEMA for the stage path
                                spath = f"@{db.DB_SCHEMA}.LAB_REPORT_LANDING/{sel_id}/{rid}_{f.name}"
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
                    
                    # Include MARKER_ID so we can update it, but hide it in the UI
                    cols_order = ['MARKER_ID', 'ORIGINAL_FILENAME', 'REPORT_SECTION', 'BATCH_NUMBER', 'MARKER_NAME', 'RESULT', 'UNIT', 'REFERENCE_VALUES','REFERENCE_START','REFERENCE_END', 'WITHIN_RANGE', 'STAGE_PATH']
                    disp = markers[cols_order].copy()
                    disp.columns = ['MARKER_ID', 'Report Name', 'Section','Batch Number', 'Marker', 'Result', 'Unit', 'Reference','Reference Start', 'Reference End', 'Within Range', 'Storage Path']
                    
                    st.info("✏️ You can edit Section, Batch Number, Marker, Result, Unit, Reference, Reference Start, Reference End, and Within Range directly in the table below.")
                    
                    edited_markers = st.data_editor(
                        disp, 
                        use_container_width=True, 
                        hide_index=True,
                        key="marker_editor",
                        column_config={
                            "MARKER_ID": None, # Hidden
                            "Report Name": st.column_config.Column(disabled=True),
                            "Storage Path": st.column_config.Column(disabled=True)
                        }
                    )
                    
                    if st.button("💾 Save Marker Edits", type="primary"):
                        edits = st.session_state["marker_editor"]["edited_rows"]
                        if edits:
                            for idx, changes in edits.items():
                                row = disp.iloc[idx].to_dict()
                                row.update(changes) # Apply changes to the row
                                db.update_marker(
                                    row['MARKER_ID'], row['Section'], row['Batch Number'], 
                                    row['Marker'], row['Result'], row['Unit'], 
                                    row['Reference'], row['Reference Start'], row['Reference End'], 
                                    row['Within Range'], current_user
                                )
                            st.session_state.success_toast = "✅ Marker edits saved successfully!"
                            st.rerun()
                        else:
                            st.warning("No edits were made.")
                else: 
                    st.info("No markers found.")

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
            
            elif tab == "Activity": 
                st.dataframe(db.get_activity_log(sel_id), use_container_width=True)