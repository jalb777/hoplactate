mport streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import hashlib
from datetime import datetime, time
from stravalib.client import Client
from streamlit_gsheets import GSheetsConnection

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Training Log Analyzer", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1GPlvl8n0uybnWqrIDVqMBLFZ-FM5lMQUeyG1mC22JuI/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

RUN_LOG, LACTATE_LOG, USERS_LOG = "Run_Log", "Lactate_Log", "Users"

# --- HELPERS ---
def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

@st.cache_data(ttl=600)
def load_data(worksheet_name):
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet=worksheet_name)
        df.columns = df.columns.str.strip()
        if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        if 'Athlete_ID' in df.columns and 'username' in st.session_state and st.session_state.username:
            df = df[df['Athlete_ID'] == st.session_state.username]
        return df.dropna(subset=['Date'])
    except: return pd.DataFrame()

def save_data(df, worksheet_name):
    conn.update(spreadsheet=SHEET_URL, worksheet=worksheet_name, data=df)
    st.cache_data.clear()

def calculate_metabolic_fitness(df):
    df_c = df.copy()
    for col in ['Recovery_Min', 'LT1_Min', 'LT2_Min', 'VO2_Min']:
        if col not in df_c.columns: df_c[col] = 0.0
    df_c['Training_Load'] = df_c['Recovery_Min']*1 + df_c['LT1_Min']*2 + df_c['LT2_Min']*4 + df_c['VO2_Min']*6
    daily = df_c.groupby('Date')['Training_Load'].sum().resample('D').sum().fillna(0).reset_index()
    daily['Fitness'] = daily['Training_Load'].ewm(span=42, adjust=False).mean()
    daily['Fatigue'] = daily['Training_Load'].ewm(span=7, adjust=False).mean()
    daily['Form'] = daily['Fitness'] - daily['Fatigue']
    return daily

# --- AUTH ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.title("🏃‍♂️ Training Log Analyzer")
    auth_mode = st.radio("Option:", ["Log In", "Create Account"], horizontal=True)
    users_df = load_data(USERS_LOG)
    with st.form("auth"):
        user, password = st.text_input("Username").lower(), st.text_input("Password", type="password")
        if st.form_submit_button("Submit"):
            if auth_mode == "Log In":
                if not users_df.empty and user in users_df['Username'].values and hash_password(password) == users_df[users_df['Username'] == user]['Password'].iloc[0]:
                    st.session_state.logged_in, st.session_state.username = True, user
                    st.rerun()
                else: st.error("Invalid credentials.")
            else:
                save_data(pd.concat([users_df, pd.DataFrame([{'Username': user, 'Password': hash_password(password)}])]), USERS_LOG)
                st.success("Account created!")
else:
    if st.sidebar.button("Log Out"): st.session_state.logged_in = False; st.rerun()
    menu = st.sidebar.radio("Go to:", ["📊 Dashboard", "🔄 Sync Strava", "📋 Activity Catalog", "➕ Add Manual Run", "🩸 Log Lactate Test"])

    # --- MAIN DASHBOARD ---
    if menu == "📊 Dashboard":
        st.title(f"{st.session_state.username.capitalize()}'s Dashboard")
        runs_df = load_data(RUN_LOG)
        if not runs_df.empty:
            # 1. Seasonal Volume
            st.subheader("Seasonal Volume Trends")
            runs_df['Date_Only'] = runs_df['Date'].dt.date
            plot_df = runs_df.groupby('Date_Only')[['Recovery_Min', 'LT1_Min', 'LT2_Min']].sum().reset_index().sort_values('Date_Only')
            
            fig, ax = plt.subplots(figsize=(10, 4))
            x = np.arange(len(plot_df))
            r, l1, l2 = plot_df['Recovery_Min'].fillna(0), plot_df['LT1_Min'].fillna(0), plot_df['LT2_Min'].fillna(0)
            ax.bar(x, r, label='Recovery', color='gray'); ax.bar(x, l1, bottom=r, label='LT1', color='green')
            ax.bar(x, l2, bottom=r+l1, label='LT2', color='orange')
            ax.set_xticks(x); ax.set_xticklabels(plot_df['Date_Only'], rotation=45)
            st.pyplot(fig)
            
            # 2. Fitness/Form
            st.subheader("Fitness & Form")
            fit_df = calculate_metabolic_fitness(runs_df)
            fig_f, ax_f = plt.subplots(); ax_f.plot(fit_df['Date'], fit_df['Form']); st.pyplot(fig_f)
        else: st.info("No data found.")

    # --- LOGGING SECTIONS ---
    elif menu == "🩸 Log Lactate Test":
        with st.form("lac_form"):
            date, phase, pace, hr, lac = st.date_input("Date"), st.selectbox("Type", ["LT1", "LT2", "VO2"]), st.text_input("Pace", "6:00"), st.number_input("HR", 40, 220, 150), st.number_input("Lactate", 0.0, 15.0, 2.0)
            if st.form_submit_button("Save"):
                save_data(pd.concat([load_data(LACTATE_LOG), pd.DataFrame([{'Athlete_ID': st.session_state.username, 'Date': str(date), 'Test_Phase': phase, 'Pace': pace, 'Heart_Rate': hr, 'Lactate_mmol': lac}])]), LACTATE_LOG)
                st.success("Logged!")
    # ==========================================
    # 🔄 SYNC STRAVA
    # ==========================================
    elif menu == "🔄 Sync Strava":
        st.subheader("Pull Activities by Date Range")
        st.info(
            "**💡 Syncing Best Practices: The 120-Day Rule**\n\n"
            "Please **do not** sync your entire all-time Strava history. "
            "Because this platform uses an exponential impulse-response model to track your physiology, "
            "any workout older than 4 to 5 months mathematically decays to 0% impact on your current fitness and fatigue scores. \n\n"
            "**Recommendation:** Set your start date to roughly **90 to 120 days ago** (including any down weeks or injury blocks). "
            "This gives the algorithm a perfect 'run-in' period to calibrate your baseline engine without slowing down the database.")
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Start Date")
        end_date = col2.date_input("End Date")
        
        if st.button("Sync Data", type="primary"):
            with st.spinner("Connecting to Strava API..."):
                try:
                    client = Client()
                    refresh_response = client.refresh_access_token(
                        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, refresh_token=REFRESH_TOKEN
                    )
                    client.access_token = refresh_response['access_token']
                    dt_start = datetime.combine(start_date, time.min)
                    dt_end = datetime.combine(end_date, time.max)
                    activities = list(client.get_activities(after=dt_start, before=dt_end))
                    
                    if not activities:
                        st.warning("No activities found in this date range.")
                    else:
                        existing_runs = load_data(RUN_LOG)
                        existing_ids = existing_runs['Activity_ID'].values if not existing_runs.empty else []
                        new_entries = []
                        progress_bar = st.progress(0)
                        
                        for i, act in enumerate(activities):
                            if act.id in existing_ids or not getattr(act, 'has_heartrate', False):
                                progress_bar.progress((i + 1) / len(activities))
                                continue
                                
                            types = ['time', 'heartrate', 'velocity_smooth']
                            streams = client.get_activity_streams(act.id, types=types)
                            
                            if streams and 'heartrate' in streams and 'velocity_smooth' in streams:
                                df_stream = pd.DataFrame({
                                    'heartrate': streams['heartrate'].data,
                                    'velocity': streams['velocity_smooth'].data
                                }).dropna()
                                
                                bins = [0, 140, 160, 175, 200]
                                labels = ['Recovery', 'LT1 (Aerobic)', 'LT2 (Threshold)', 'VO2 Max']
                                df_stream['Zone'] = pd.cut(df_stream['heartrate'], bins=bins, labels=labels)
                                time_in_zones = df_stream['Zone'].value_counts(sort=False) / 60
                                
                                aerobic_df = df_stream[(df_stream['heartrate'] < 160) & (df_stream['velocity'] > 0.5)]
                                run_ef = (aerobic_df['velocity'] * 60) / aerobic_df['heartrate'] if not aerobic_df.empty else pd.Series([0.0])
                                
                                new_entries.append({
                                    'Date': act.start_date_local.strftime('%Y-%m-%d'),
                                    'Activity_ID': act.id,
                                    'Name': act.name,
                                    'Recovery_Min': time_in_zones.get('Recovery', 0).round(1),
                                    'LT1_Min': time_in_zones.get('LT1 (Aerobic)', 0).round(1),
                                    'LT2_Min': time_in_zones.get('LT2 (Threshold)', 0).round(1),
                                    'VO2_Min': time_in_zones.get('VO2 Max', 0).round(1),
                                    'Aerobic_EF': run_ef.mean().round(2),
                                    'Athlete_ID': st.session_state.username  # Tags run to the user
                                })
                            progress_bar.progress((i + 1) / len(activities))
                            
                        if new_entries:
                            updated_runs = pd.concat([existing_runs, pd.DataFrame(new_entries)], ignore_index=True) if not existing_runs.empty else pd.DataFrame(new_entries)
                            save_data(updated_runs, RUN_LOG)
                            st.success(f"Successfully synced {len(new_entries)} new activities!")
                        else:
                            st.info("No new physiological data to sync.")
                except Exception as e:
                    st.error(f"Failed to sync: {e}")

    # ==========================================
    # 📋 ACTIVITY CATALOG
    # ==========================================
    elif menu == "📋 Activity Catalog":
        st.subheader("Manage Your Training Log")
        runs_df = load_data(RUN_LOG)
        if not runs_df.empty:
            edited_df = st.data_editor(runs_df, num_rows="dynamic", use_container_width=True)
            if st.button("Save Changes to Database", type="primary"):
                save_data(edited_df, RUN_LOG)
                st.success("Database updated successfully!")
        else:
            st.info("Your catalog is empty. Sync some data from Strava first!")

    # ==========================================
    # ➕ ADD MANUAL RUN
    # ==========================================
    elif menu == "➕ Add Manual Run":
        st.subheader("Log a Treadmill or Untracked Workout")
        with st.form("manual_run_form"):
            date = st.date_input("Date")
            name = st.text_input("Workout Name", "Treadmill Recovery")
            rec_min = st.number_input("Recovery Minutes", min_value=0.0, step=1.0)
            lt1_min = st.number_input("LT1 Minutes", min_value=0.0, step=1.0)
            lt2_min = st.number_input("LT2 Minutes", min_value=0.0, step=1.0)
            vo2_min = st.number_input("VO2 Minutes", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Save Workout")
            if submitted:
                new_run = pd.DataFrame([{
                    'Date': str(date), 'Activity_ID': 'Manual', 'Name': name,
                    'Recovery_Min': rec_min, 'LT1_Min': lt1_min, 'LT2_Min': lt2_min, 'VO2_Min': vo2_min, 'Aerobic_EF': 0.0,
                    'Athlete_ID': st.session_state.username
                }])
                existing_runs = load_data(RUN_LOG)
                updated_runs = pd.concat([existing_runs, new_run], ignore_index=True) if not existing_runs.empty else new_run
                save_data(updated_runs, RUN_LOG)
                st.success("Manual run added to the database!")

    # ==========================================
    # 🩸 LOG LACTATE TEST
    # ==========================================
    elif menu == "🩸 Log Lactate Test":
        st.subheader("Input Blood Step-Test Data")
        with st.form("lactate_form"):
            date = st.date_input("Test Date")
            phase = st.selectbox("Workout Type",["LT1", "LT2", "VO2"])
            pace = st.text_input("Mile Pace (e.g., 6:30)", "6:00")
            hr = st.number_input("Average Rep Heart Rate (BPM)", min_value=40, max_value=220, step=1)
            lactate = st.number_input("Lactate (mmol/L)", min_value=0.0, step=0.1, format="%.1f")
            submitted = st.form_submit_button("Save Data Point")
            if submitted:
                new_lac = pd.DataFrame([{
                   'Athlete_ID': st.session_state.username, 'Date': str(date), 'Test_Phase': phase, 'Pace': pace, 'Heart_Rate': hr, 'Lactate_mmol': lactate
                    
                }])
                existing_lac = load_data(LACTATE_LOG)
                updated_lac = pd.concat([existing_lac, new_lac], ignore_index=True) if not existing_lac.empty else new_lac
                save_data(updated_lac, LACTATE_LOG)
                st.success(f"Logged {lactate} mmol/L at {hr} BPM!")

