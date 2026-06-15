import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime, time
from stravalib.client import Client

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Metabolic Training Hub", layout="wide")
st.title("🏃‍♂️ Metabolic Training Hub")

# --- STRAVA CREDENTIALS ---
CLIENT_ID = 256747  # Replace with yours
CLIENT_SECRET = '812d2a7b01d0e2efb084139152f1997db1a092cd'  # Replace with yours
REFRESH_TOKEN = '18eeeefcc8cdfab3f254cb0e2c05708cbe8a7510'  # Replace with yours

from streamlit_gsheets import GSheetsConnection

# Your Google Sheet URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit"

# Establish the connection
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet_name):
    """Pulls live data from the Google Sheet"""
    try:
        # ttl=0 forces it to pull fresh data every time (no caching)
        df = conn.read(spreadsheet=SHEET_URL, worksheet=worksheet_name, ttl=0)
        return df.dropna(how="all") # Cleans up blank rows Google Sheets sometimes returns
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return pd.DataFrame()

def save_data(df, worksheet_name):
    """Overwrites the specific tab with the updated DataFrame"""
    conn.update(worksheet=worksheet_name, data=df)
    # Clear the cache so the next load gets the new data
    st.cache_data.clear()
# --- SIDEBAR NAVIGATION ---
st.sidebar.header("Navigation")
menu = st.sidebar.radio("Go to:", [
    "📊 Dashboard", 
    "🔄 Sync Strava", 
    "📋 Activity Catalog", 
    "➕ Add Manual Run", 
    "🩸 Log Lactate Test"
])

# ==========================================
# 📊 DASHBOARD VIEW
# ==========================================
if menu == "📊 Dashboard":
    runs_df = load_data(RUN_LOG)
    
    if not runs_df.empty and 'Date' in runs_df.columns:
        runs_df['Date'] = pd.to_datetime(runs_df['Date'])
        runs_df = runs_df.sort_values('Date')
        
        # --- CHART 1: SEASONAL VOLUME ---
        st.subheader("Seasonal Volume Trends")
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(runs_df['Date'].dt.strftime('%m-%d'), runs_df['Recovery_Min'], label='Recovery', color='gray', alpha=0.6)
        bottom_val = runs_df['Recovery_Min'].copy()
        if 'LT1_Min' in runs_df.columns:
            ax.bar(runs_df['Date'].dt.strftime('%m-%d'), runs_df['LT1_Min'], bottom=bottom_val, label='LT1', color='green', alpha=0.6)
            bottom_val += runs_df['LT1_Min']
        if 'LT2_Min' in runs_df.columns:
            ax.bar(runs_df['Date'].dt.strftime('%m-%d'), runs_df['LT2_Min'], bottom=bottom_val, label='LT2', color='orange', alpha=0.8)
        ax.set_ylabel("Minutes")
        ax.legend(loc='upper left')
        plt.xticks(rotation=45)
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

            # ------------------------------------------
            # AUTOMATED COACHING INSIGHTS
            # ------------------------------------------
            st.divider()
            st.subheader("💡 Automated Coaching Insights")
            
            # This now safely runs because we know fitness_df exists!
            try:
                insights = generate_training_suggestions(fitness_df)
                if insights:
                    st.markdown(f"### Current State: {insights['status']}")
                    st.info(insights['advice'])
                    st.markdown(f"**Recommended Target for Next Session:** {insights['target_workout']}")
            except NameError:
                st.error("Hold up! You are missing the 'generate_training_suggestions' function in your helper section.")
            # ------------------------------------------

        # --- CHART 3: AEROBIC EFFICIENCY FACTOR (EF) ---
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
        st.info("📊 Your training log is currently empty.")

    # --- CHART 4: LACTATE CURVE ---
    st.divider()
    st.subheader("Lactate Curve Profile")
    lac_df = load_data(LACTATE_LOG)
    
    if not lac_df.empty and 'Heart_Rate' in lac_df.columns:
        fig2, ax2 = plt.subplots(figsize=(8, 4))
        ax2.plot(lac_df['Heart_Rate'], lac_df['Lactate_mmol'], marker='o', color='red', linewidth=2)
        ax2.axhline(y=2.0, color='green', linestyle='--', alpha=0.5, label='LT1 Baseline (2.0 mmol)')
        ax2.axhline(y=4.0, color='orange', linestyle='--', alpha=0.5, label='LT2 Baseline (4.0 mmol)')
        ax2.set_xlabel("Heart Rate (BPM)")
        ax2.set_ylabel("Blood Lactate (mmol/L)")
        ax2.legend()
        ax2.grid(True, linestyle=':', alpha=0.6)
        st.pyplot(fig2)
        
# ==========================================
# 🔄 SYNC STRAVA
# ==========================================
elif menu == "🔄 Sync Strava":
    st.subheader("Pull Activities by Date Range")
    
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
                
                # Format dates for API
                dt_start = datetime.combine(start_date, time.min)
                dt_end = datetime.combine(end_date, time.max)
                
                activities = client.get_activities(after=dt_start, before=dt_end)
                activities_list = list(activities)
                
                if not activities_list:
                    st.warning("No activities found in this date range.")
                else:
                    existing_runs = load_data(RUN_LOG)
                    existing_ids = existing_runs['Activity_ID'].values if not existing_runs.empty else []
                    
                    new_entries = []
                    progress_bar = st.progress(0)
                    
                    for i, act in enumerate(activities_list):
                        if act.id in existing_ids or not getattr(act, 'has_heartrate', False):
                            progress_bar.progress((i + 1) / len(activities_list))
                            continue
                            
                        # NEW: Ask Strava for pace (velocity) alongside heart rate
                        types = ['time', 'heartrate', 'velocity_smooth']
                        streams = client.get_activity_streams(act.id, types=types)
                        
                        if streams and 'heartrate' in streams and 'velocity_smooth' in streams:
                            hr_data = streams['heartrate'].data
                            vel_data = streams['velocity_smooth'].data
                            
                            df_stream = pd.DataFrame({
                                'heartrate': hr_data,
                                'velocity': vel_data
                            }).dropna()
                            
                            # Zone Categorization
                            bins = [0, 140, 160, 175, 200]
                            labels = ['Recovery', 'LT1 (Aerobic)', 'LT2 (Threshold)', 'VO2 Max']
                            df_stream['Zone'] = pd.cut(df_stream['heartrate'], bins=bins, labels=labels)
                            time_in_zones = df_stream['Zone'].value_counts(sort=False) / 60
                            
                            # NEW: Calculate Aerobic Efficiency Factor (EF)
                            # We only look at data under LT1 to filter out interval noise
                            aerobic_df = df_stream[df_stream['heartrate'] < 160]
                            
                            if not aerobic_df.empty:
                                # EF = Speed (meters/minute) divided by Heart Rate (BPM)
                                aerobic_df['EF'] = (aerobic_df['velocity'] * 60) / aerobic_df['heartrate']
                                run_ef = aerobic_df['EF'].mean().round(2)
                            else:
                                run_ef = 0.0
                            
                            new_entries.append({
                                'Date': act.start_date_local.strftime('%Y-%m-%d'),
                                'Activity_ID': act.id,
                                'Name': act.name,
                                'Recovery_Min': time_in_zones.get('Recovery', 0).round(1),
                                'LT1_Min': time_in_zones.get('LT1 (Aerobic)', 0).round(1),
                                'LT2_Min': time_in_zones.get('LT2 (Threshold)', 0).round(1),
                                'VO2_Min': time_in_zones.get('VO2 Max', 0).round(1),
                                'Aerobic_EF': run_ef  # Saving to the new Google Sheets column
                            })
                        progress_bar.progress((i + 1) / len(activities_list))
                        
                    if new_entries:
                        updated_runs = pd.concat([existing_runs, pd.DataFrame(new_entries)], ignore_index=True)
                        save_data(updated_runs, RUN_LOG)
                        st.success(f"Successfully synced {len(new_entries)} new activities!")
                    else:
                        st.info("No new physiological data to sync. All valid runs are already logged.")
                        
            except Exception as e:
                st.error(f"Failed to sync: {e}")

# ==========================================
# 📋 ACTIVITY CATALOG
# ==========================================
elif menu == "📋 Activity Catalog":
    st.subheader("Manage Your Training Log")
    st.write("Double-click any cell to edit. Select the checkbox on the left of a row and press 'Delete' on your keyboard to remove an entry.")
    
    runs_df = load_data(RUN_LOG)
    
    if not runs_df.empty:
        # data_editor makes the dataframe interactive. num_rows="dynamic" allows deleting.
        edited_df = st.data_editor(runs_df, num_rows="dynamic", use_container_width=True)
        
        if st.button("Save Changes to Database", type="primary"):
            save_data(edited_df, RUN_LOG)
            st.success("Database updated successfully!")
    else:
        st.info("Your catalog is empty. Sync some data from Strava first!")

# ==========================================
# ➕ ADD MANUAL RUN (Unchanged)
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
                'Recovery_Min': rec_min, 'LT1_Min': lt1_min, 'LT2_Min': lt2_min, 'VO2_Min': vo2_min
            }])
            existing_runs = load_data(RUN_LOG)
            updated_runs = pd.concat([existing_runs, new_run], ignore_index=True)
            save_data(updated_runs, RUN_LOG)
            st.success("Manual run added to the database!")

# ==========================================
# 🩸 LOG LACTATE TEST (Unchanged)
# ==========================================
elif menu == "🩸 Log Lactate Test":
    st.subheader("Input Blood Step-Test Data")
    with st.form("lactate_form"):
        date = st.date_input("Test Date")
        phase = st.text_input("Phase (e.g., Step 1, Step 2)", "Step 1")
        pace = st.text_input("Pace (e.g., 6:30)", "6:00")
        hr = st.number_input("Heart Rate (BPM)", min_value=40, max_value=220, step=1)
        lactate = st.number_input("Lactate (mmol/L)", min_value=0.0, step=0.1)
        submitted = st.form_submit_button("Save Data Point")
        if submitted:
            new_lac = pd.DataFrame([{
                'Date': str(date), 'Test_Phase': phase, 'Pace': pace, 'Heart_Rate': hr, 'Lactate_mmol': lactate
            }])
            existing_lac = load_data(LACTATE_LOG)
            updated_lac = pd.concat([existing_lac, new_lac], ignore_index=True)
            save_data(updated_lac, LACTATE_LOG)
            st.success(f"Logged {lactate} mmol/L at {hr} BPM!")