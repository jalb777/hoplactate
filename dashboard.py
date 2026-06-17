import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
import hashlib
from datetime import datetime, time
from stravalib.client import Client
from streamlit_gsheets import GSheetsConnection

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Training Log Analyzer", layout="wide")

# --- CREDENTIALS & DATABASE ---
CLIENT_ID = 256747 
CLIENT_SECRET = '812d2a7b01d0e2efb084139152f1997db1a092cd' 
REFRESH_TOKEN = '714aecfc2257a54974220ec2bbe6e40a98f32e5b'

# Replace with your actual Google Sheet URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1GPlvl8n0uybnWqrIDVqMBLFZ-FM5lMQUeyG1mC22JuI/edit"

# Connect to Streamlit Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

# Set the tab names
RUN_LOG = "Run_Log"
LACTATE_LOG = "Lactate_Log"
USERS_LOG = "Users"

# --- HELPER FUNCTIONS ---
def hash_password(password):
    """Encrypts passwords so they are not plain-text in Google Sheets"""
    return hashlib.sha256(password.encode()).hexdigest()

@st.cache_data(ttl=600)
def load_data(worksheet_name):
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet=worksheet_name)
        # Strip whitespace from headers to prevent hidden key errors
        df.columns = df.columns.str.strip()
        
        # Define required columns for your app logic
        required_cols = ['Date', 'Aerobic_EF', 'Pace_Dec', 'Athlete_ID']
        
        if df.empty:
            return pd.DataFrame(columns=required_cols)
            
        # Ensure Date column exists and is datetime
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        # Filter by user if applicable
        if 'Athlete_ID' in df.columns and 'username' in st.session_state:
            df = df[df['Athlete_ID'] == st.session_state.username]
            
        return df
    except Exception:
        return pd.DataFrame(columns=['Date', 'Aerobic_EF', 'Pace_Dec', 'Athlete_ID'])

def save_data(df, worksheet_name):
    """Overwrites the specific tab with the updated DataFrame"""
    conn.update(spreadsheet=SHEET_URL, worksheet=worksheet_name, data=df)
    st.cache_data.clear()

def calculate_metabolic_fitness(df):
    if df.empty or 'Recovery_Min' not in df.columns:
        return pd.DataFrame()
    df_copy = df.copy()
    df_copy['Training_Load'] = (
        df_copy.get('Recovery_Min', 0) * 1.0 +
        df_copy.get('LT1_Min', 0) * 2.0 +
        df_copy.get('LT2_Min', 0) * 4.0 +
        df_copy.get('VO2_Min', 0) * 6.0
    )
    daily_log = df_copy.groupby('Date')['Training_Load'].sum().reset_index()
    daily_log['Date'] = pd.to_datetime(daily_log['Date'])
    daily_log.set_index('Date', inplace=True)
    if not daily_log.empty:
        idx = pd.date_range(daily_log.index.min(), daily_log.index.max())
        daily_log = daily_log.reindex(idx, fill_value=0)
    daily_log['Fitness'] = daily_log['Training_Load'].ewm(span=42, adjust=False).mean()
    daily_log['Fatigue'] = daily_log['Training_Load'].ewm(span=7, adjust=False).mean()
    daily_log['Form'] = daily_log['Fitness'] - daily_log['Fatigue']
    return daily_log.reset_index().rename(columns={'index': 'Date'})

def generate_training_suggestions(fitness_df):
    if fitness_df.empty: return None
    form = fitness_df.iloc[-1]['Form']
    insights = {}
    if form < -30:
        insights['status'], insights['advice'], insights['target_workout'] = "🚨 High Fatigue", "Form is critically low. Deep fatigue state.", "🧘 Easy 30-40 min Recovery"
    elif -30 <= form <= -10:
        insights['status'], insights['advice'], insights['target_workout'] = "🟢 Optimal Zone", "The 'sweet spot' for volume progression.", "⏱️ Split Threshold Block"
    elif -10 < form <= 5:
        insights['status'], insights['advice'], insights['target_workout'] = "🟡 Neutral State", "You have absorbed recent microcycles.", "🏃‍♂️ Aerobic Base Building"
    else:
        insights['status'], insights['advice'], insights['target_workout'] = "⚡ Peaking State", "Systematic fatigue has cleared.", "🚀 High-End Quality / Time-Trial"
    return insights

# ==========================================
# 🔐 AUTHENTICATION ENGINE
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None

if not st.session_state.logged_in:
    st.title("🏃‍♂️ Training Log Analyzer ")
    st.markdown("### Lets Go Hop")
    
    # Toggle between Login and Sign Up
    auth_mode = st.radio("Select an option:", ["Log In", "Create Account"], horizontal=True)
    
    users_df = load_data(USERS_LOG)
    
    if auth_mode == "Log In":
        with st.form("login_form"):
            user_input = st.text_input("Username").lower()
            pass_input = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Enter Dashboard")
            
            if submitted:
                if not users_df.empty and user_input in users_df['Username'].values:
                    stored_hash = users_df[users_df['Username'] == user_input]['Password'].iloc[0]
                    if hash_password(pass_input) == stored_hash:
                        st.session_state.logged_in = True
                        st.session_state.username = user_input
                        st.rerun()
                    else:
                        st.error("Incorrect password.")
                else:
                    st.error("Username not found.")
                    
    elif auth_mode == "Create Account":
        with st.form("signup_form"):
            new_user = st.text_input("Choose a Username").lower()
            new_pass = st.text_input("Choose a Password", type="password")
            confirm_pass = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Create Account")
            
            if submitted:
                if not new_user or not new_pass:
                    st.error("Please fill out all fields.")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match.")
                elif not users_df.empty and new_user in users_df['Username'].values:
                    st.error("Username already exists! Choose another.")
                else:
                    new_user_data = pd.DataFrame([{'Username': new_user, 'Password': hash_password(new_pass)}])
                    updated_users = pd.concat([users_df, new_user_data], ignore_index=True) if not users_df.empty else new_user_data
                    save_data(updated_users, USERS_LOG)
                    st.success("Account created! Please switch to 'Log In' to enter.")

# ==========================================
# 🚀 MAIN APP (ONLY RUNS IF LOGGED IN)
# ==========================================
if st.session_state.logged_in:
    
    st.sidebar.success(f"Logged in as: **{st.session_state.username}**")
    if st.sidebar.button("Log Out"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()
        
    st.sidebar.header("Navigation")
    menu = st.sidebar.radio("Go to:", [
        "📊 Dashboard", 
        "🔄 Sync Strava", 
        "📋 Activity Catalog", 
        "➕ Add Manual Run", 
        "🩸 Log Lactate Test"
    ])

    if menu == "📊 Dashboard":
        st.title(f"{st.session_state.username.capitalize()}'s Training Log Analyzer")
        runs_df = load_data(RUN_LOG)

        if not runs_df.empty and 'Date' in runs_df.columns:
            runs_df['Date'] = pd.to_datetime(runs_df['Date'], errors='coerce')
            runs_df = runs_df.dropna(subset=['Date']).sort_values('Date')
            
# --- CHART 1: SEASONAL VOLUME ---
            st.write("--- DEBUGGING DATA ---")
            st.write(f"Total rows in runs_df: {len(runs_df)}")
            st.write("Unique dates in runs_df:", runs_df['Date_Only'].unique())
            st.write("Sample of the data being grouped:")
            st.write(runs_df.head(10))

            st.subheader("Seasonal Volume Trends")
            
            # 1. Clean and Group
            runs_df['Date_Only'] = pd.to_datetime(runs_df['Date']).dt.date
            plot_df = runs_df.groupby('Date_Only')[['Recovery_Min', 'LT1_Min', 'LT2_Min']].sum().reset_index().sort_values('Date_Only')
            
            # 2. Get numeric indices instead of just strings
            x_idx = np.arange(len(plot_df))
            x_labels = [d.strftime('%m-%d') for d in plot_df['Date_Only']]
            rec = plot_df['Recovery_Min'].fillna(0).tolist()
            lt1 = plot_df['LT1_Min'].fillna(0).tolist()
            lt2 = plot_df['LT2_Min'].fillna(0).tolist()
            
            # 3. Plotting
            fig, ax = plt.subplots(figsize=(10, 4))
            
            # USE x_idx (the numbers 0, 1, 2...) instead of x_labels
            ax.bar(x_idx, rec, label='Recovery', color='gray', alpha=0.6)
            ax.bar(x_idx, lt1, bottom=rec, label='LT1', color='green', alpha=0.6)
            bottom_lt2 = [r + l1 for r, l1 in zip(rec, lt1)]
            ax.bar(x_idx, lt2, bottom=bottom_lt2, label='LT2', color='orange', alpha=0.8)
            
            # 4. Force the X-axis labels to match the positions
            ax.set_xticks(x_idx)
            ax.set_xticklabels(x_labels, rotation=45)
            
            ax.set_ylabel("Minutes")
            ax.legend(loc='upper left')
            plt.tight_layout()
            
            st.pyplot(fig)
            st.divider()
            
            # --- CHART 2: FITNESS & FORM MODEL ---
            st.subheader("Impulse-Response Model (Fitness & Form)")
            fitness_df = calculate_metabolic_fitness(runs_df)
            if not fitness_df.empty:
                fig_fit, ax_fit = plt.subplots(figsize=(10, 5))
                ax_fit.plot(fitness_df['Date'], fitness_df['Fitness'], label='Fitness (42-Day)', color='blue', linewidth=2)
                ax_fit.plot(fitness_df['Date'], fitness_df['Fatigue'], label='Fatigue (7-Day)', color='red', linewidth=1.5, linestyle='--')
                ax_fit.fill_between(fitness_df['Date'], 0, fitness_df['Form'], where=(fitness_df['Form'] >= 0), color='green', alpha=0.3, label='Fresh')
                ax_fit.fill_between(fitness_df['Date'], 0, fitness_df['Form'], where=(fitness_df['Form'] < 0), color='orange', alpha=0.3, label='Tired')
                ax_fit.axhline(0, color='black', linewidth=1)
                ax_fit.set_ylabel("Training Load Score")
                ax_fit.legend(loc='upper left')
                plt.xticks(rotation=45)
                st.pyplot(fig_fit)

                # --- COACHING INSIGHTS ---
                st.divider()
                st.subheader("💡 Automated Coaching Insights")
                insights = generate_training_suggestions(fitness_df)
                if insights:
                    st.markdown(f"### Current State: {insights['status']}")
                    st.info(insights['advice'])
                    st.markdown(f"**Recommended Target for Next Session:** {insights['target_workout']}")

            # --- CHART 3: AEROBIC EF ---
            if 'Aerobic_EF' in runs_df.columns:
                st.divider()
                st.subheader("🫀 Aerobic Efficiency Factor (Base Progression)")
                ef_df = runs_df[runs_df['Aerobic_EF'] > 0]
                if not ef_df.empty:
                    fig_ef, ax_ef = plt.subplots(figsize=(10, 3))
                    ax_ef.plot(ef_df['Date'], ef_df['Aerobic_EF'], marker='o', color='purple', linewidth=2, label='Aerobic EF')
                    z = np.polyfit(range(len(ef_df)), ef_df['Aerobic_EF'], 1)
                    p = np.poly1d(z)
                    ax_ef.plot(ef_df['Date'], p(range(len(ef_df))), linestyle='--', color='black', alpha=0.5, label='Macro Trend')
                    ax_ef.set_ylabel("EF (Meters/Beat)")
                    ax_ef.legend(loc='upper left')
                    plt.xticks(rotation=45)
                    st.pyplot(fig_ef)

        else:
            st.info("📊 Your training log is currently empty. Sync or add a run to get started.")

     # --- CHART 4: LACTATE TRACKER ---
        st.divider()
        st.subheader("🩸 Lactate Tracker")
        lac_df = load_data(LACTATE_LOG)
        
        if not lac_df.empty and 'Heart_Rate' in lac_df.columns and 'Pace' in lac_df.columns and 'Date' in lac_df.columns:
            # Formatting Helpers
            def parse_pace(pace_str):
                try:
                    parts = str(pace_str).split(':')
                    return int(parts[0]) + int(parts[1]) / 60.0
                except: return 0.0

            def format_pace(decimal_pace):
                mins = int(decimal_pace)
                secs = int((decimal_pace - mins) * 60)
                return f"{mins}:{secs:02d}"

            lac_df['Pace_Dec'] = lac_df['Pace'].apply(parse_pace)
            lac_df['Date'] = pd.to_datetime(lac_df['Date'])
            test_dates = sorted(lac_df['Date'].dt.date.unique())
            
            if len(test_dates) > 0:
                cutoff = test_dates[-1] - pd.Timedelta(days=120)
                suggested_idx = next((i for i, d in enumerate(test_dates) if d >= cutoff), 0)
                
                st.markdown("### 1. Chronological Scrubber")
                col1, col2 = st.columns(2)
                with col1:
                    baseline_date = st.selectbox("🔵 Baseline Test", options=test_dates, index=suggested_idx, format_func=lambda x: x.strftime('%b %d, %Y'))
                with col2:
                    comp_date = st.selectbox("🔴 Current Status", options=test_dates, index=len(test_dates)-1, format_func=lambda x: x.strftime('%b %d, %Y'))
                
                st.markdown("### 2. Predictive Simulator")
                show_ghost = st.checkbox("Enable Ghost Curve Projection")
                
                shift_decimal = 0.0
                
                if show_ghost:
                    p_col1, p_col2 = st.columns(2)
                    with p_col1:
                        time_mode = st.radio("Timeline", ["Set Weeks", "Race Date"], horizontal=True)
                        weeks_out = st.slider("Additional Weeks of Training", 1, 24, 6)
                        curr_mileage = st.number_input("Current Weekly Mileage", 20, 120, 50)
                        planned_avg_mileage = curr_mileage + (st.number_input("Avg. Weekly Mileage Change", -10, 30, 5) / 2)
                    with p_col2:
                        lt2_min = st.number_input("Avg LT2 Minutes/Week", 0, 120, 50)
                        vol_qual = st.slider("Consistency (1-5)", 1.0, 5.0, 4.0, step=0.5, help="1=Burnout, 5=Robotic.")

                    # --- CALIBRATION ENGINE ---
                    latest_df = lac_df[lac_df['Date'].dt.date == comp_date].copy()
                    current_lt1_dec = 6.0
                    if not latest_df.empty:
                        s_lac = latest_df['Lactate_mmol'].values[np.argsort(latest_df['Lactate_mmol'].values)]
                        s_pace = latest_df['Pace_Dec'].values[np.argsort(latest_df['Lactate_mmol'].values)]
                        if s_lac.max() >= 1.8 and s_lac.min() <= 1.8:
                            current_lt1_dec = np.interp(1.8, s_lac, s_pace)
                    
                    dim_coeff = (6.0 / current_lt1_dec) ** 1.5 
                    runs_df = load_data(RUN_LOG)
                    ef_trend_coeff = 1.0
                    if len(runs_df) >= 4:
                        last_4 = runs_df.tail(4)
                        z = np.polyfit(range(len(last_4)), last_4['Aerobic_EF'], 1)
                        ef_trend_coeff = 1.0 + (z[0] * 5)
                    
                    total_time = (planned_avg_mileage * 10)
                    pol_penalty = 1.0 if (lt2_min / total_time) < 0.20 else 0.85
                    
                    shift_decimal = (weeks_out * 1.2 * dim_coeff * ((planned_avg_mileage/curr_mileage)**0.5) * (vol_qual/3.0) * ef_trend_coeff * pol_penalty) / 60.0

                # --- PLOTTING ---
                fig2, (ax_hr, ax_pace) = plt.subplots(1, 2, figsize=(14, 5))
                summary_data = []
                for t_date in [baseline_date, comp_date]:
                    day_df = lac_df[lac_df['Date'].dt.date == t_date].copy()
                    is_latest = (t_date == comp_date)
                    line_style, plot_color = ('-', 'red') if is_latest else ('--', 'blue')
                    
                    ax_hr.plot(day_df.sort_values('Heart_Rate')['Heart_Rate'], day_df.sort_values('Heart_Rate')['Lactate_mmol'], marker='o', linestyle=line_style, color=plot_color, label=f"{'Current' if is_latest else 'Baseline'}: {t_date}")
                    ax_pace.plot(day_df.sort_values('Pace_Dec', ascending=False)['Pace_Dec'], day_df.sort_values('Pace_Dec', ascending=False)['Lactate_mmol'], marker='o', linestyle=line_style, color=plot_color)

                if show_ghost:
                    latest_df = lac_df[lac_df['Date'].dt.date == comp_date].sort_values('Pace_Dec', ascending=False)
                    ax_pace.plot(latest_df['Pace_Dec'] - shift_decimal, latest_df['Lactate_mmol'], marker='x', linestyle=':', color='purple', label="Projected Goal", linewidth=2.5)

                ax_hr.set_xlabel("HR (BPM)"); ax_hr.set_ylabel("Lactate (mmol/L)"); ax_hr.grid(True, linestyle=':')
                ax_pace.set_xlabel("Pace (Min/Mile)"); ax_pace.invert_xaxis(); ax_pace.grid(True, linestyle=':')
                ax_pace.set_xticklabels([format_pace(t) for t in ax_pace.get_xticks()])
                ax_hr.legend(); ax_pace.legend()
                
                st.pyplot(fig2)
                
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

'''

Notes
-Need to update chart 4 to show pace vs lactate curve and heart rate on 2 y axes
-fix the single column of chart 1
-move lactate curve up as chart 2

'''
