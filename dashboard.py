import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
from datetime import datetime, time
from stravalib.client import Client

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Metabolic Training Hub", layout="wide")
st.title("🏃‍♂️ Metabolic Training Hub")

# --- STRAVA CREDENTIALS ---
CLIENT_ID = 256747  # Replace with yours
CLIENT_SECRET = '812d2a7b01d0e2efb084139152f1997db1a092cd'  # Replace with yours
REFRESH_TOKEN = '714aecfc2257a54974220ec2bbe6e40a98f32e5b'  # Replace with yours

# --- FILE PATHS ---
RUN_LOG = 'seasonal_log.csv'
LACTATE_LOG = 'lactate_log.csv'

# --- HELPER FUNCTIONS ---
def load_data(filepath):
    if os.path.exists(filepath):
        try:
            return pd.read_csv(filepath)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def save_data(df, filepath):
    df.to_csv(filepath, index=False)

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
    if fitness_df.empty:
        return None
    latest = fitness_df.iloc[-1]
    form = latest['Form']
    insights = {}
    if form < -30:
        insights['status'] = "🚨 High Fatigue / Overreaching Risk"
        insights['advice'] = f"Your Form is critically low at {form:.1f}. You are deep in a high-fatigue state. Prioritize strict active recovery or a rest day."
        insights['target_workout'] = "🧘 Easy 30-40 min Recovery Spin/Jog"
    elif -30 <= form <= -10:
        insights['status'] = "🟢 Optimal Training Zone (Productive Overload)"
        insights['advice'] = f"Your Form is {form:.1f}. This is the 'sweet spot' for collegiate volume progression."
        insights['target_workout'] = "⏱️ Split Threshold Block: e.g., 3x2 Mile at LT1/LT2 pace"
    elif -10 < form <= 5:
        insights['status'] = "🟡 Neutral / Transition State"
        insights['advice'] = f"Your Form is resting at {form:.1f}. You have absorbed recent microcycles."
        insights['target_workout'] = "🏃‍♂️ Aerobic Base Building: 60-70 mins steady state at upper Zone 1"
    else:
        insights['status'] = "⚡ Fresh / Peaking State"
        insights['advice'] = f"Your Form is positive at +{form:.1f}. Systematic fatigue has cleared."
        insights['target_workout'] = "🚀 High-End Quality: Short VO2 Max repetitions or an official time-trial/race"
    return insights

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

            # --- AUTOMATED COACHING INSIGHTS ---
            st.divider()
            st.subheader("💡 Automated Coaching Insights")
            insights = generate_training_suggestions(fitness_df)
            if insights:
                st.markdown(f"### Current State: {insights['status']}")
                st.info(insights['advice'])
                st.markdown(f"**Recommended Target for Next Session:** {insights['target_workout']}")

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

    # --- CHART 4: LACTATE CURVE PROFILE ---
    st.divider()
    st.subheader("🩸 Lactate Curve Profile")
    lac_df = load_data(LACTATE_LOG)
    
    if not lac_df.empty and 'Heart_Rate' in lac_df.columns and 'Pace' in lac_df.columns:
        def parse_pace(pace_str):
            try:
                parts = str(pace_str).split(':')
                return int(parts[0]) + int(parts[1]) / 60.0
            except:
                return 0.0

        def format_pace(decimal_pace):
            mins = int(decimal_pace)
            secs = int((decimal_pace - mins) * 60)
            return f"{mins}:{secs:02d}"

        lac_df['Pace_Dec'] = lac_df['Pace'].apply(parse_pace)
        lac_df = lac_df.sort_values('Heart_Rate') 
        
        fig2, (ax_hr, ax_pace) = plt.subplots(1, 2, figsize=(14, 5))
        
        # 1. Lactate vs. Heart Rate
        ax_hr.plot(lac_df['Heart_Rate'], lac_df['Lactate_mmol'], marker='o', color='red', linewidth=2)
        
        # Interpolate exact HR for 1.8 and 3.3 mmol
        if lac_df['Lactate_mmol'].max() >= 1.8 and lac_df['Lactate_mmol'].min() <= 1.8:
            lt1_hr = np.interp(1.8, lac_df['Lactate_mmol'], lac_df['Heart_Rate'])
            ax_hr.axvline(x=lt1_hr, color='green', linestyle=':', alpha=0.8, label=f'LT1 HR: {int(lt1_hr)} BPM')
            
        if lac_df['Lactate_mmol'].max() >= 3.3 and lac_df['Lactate_mmol'].min() <= 3.3:
            lt2_hr = np.interp(3.3, lac_df['Lactate_mmol'], lac_df['Heart_Rate'])
            ax_hr.axvline(x=lt2_hr, color='orange', linestyle=':', alpha=0.8, label=f'LT2 HR: {int(lt2_hr)} BPM')

        ax_hr.axhline(y=1.8, color='green', linestyle='--', alpha=0.5, label='1.8 mmol Baseline')
        ax_hr.axhline(y=3.3, color='orange', linestyle='--', alpha=0.5, label='3.3 mmol Baseline')
        ax_hr.set_xlabel("Heart Rate (BPM)")
        ax_hr.set_ylabel("Blood Lactate (mmol/L)")
        ax_hr.set_title("Internal Cost (HR)")
        ax_hr.legend()
        ax_hr.grid(True, linestyle=':', alpha=0.6)

        # 2. Lactate vs. Pace
        lac_df = lac_df.sort_values('Pace_Dec', ascending=False)
        ax_pace.plot(lac_df['Pace_Dec'], lac_df['Lactate_mmol'], marker='o', color='blue', linewidth=2)
        
        sorted_indices = np.argsort(lac_df['Lactate_mmol'].values)
        sorted_lac = lac_df['Lactate_mmol'].values[sorted_indices]
        sorted_pace = lac_df['Pace_Dec'].values[sorted_indices]
        
        # Interpolate exact Pace for 1.8 and 3.3 mmol
        if sorted_lac.max() >= 1.8 and sorted_lac.min() <= 1.8:
            lt1_pace_dec = np.interp(1.8, sorted_lac, sorted_pace)
            ax_pace.axvline(x=lt1_pace_dec, color='green', linestyle=':', alpha=0.8, label=f'LT1 Pace: {format_pace(lt1_pace_dec)}')
            
        if sorted_lac.max() >= 3.3 and sorted_lac.min() <= 3.3:
            lt2_pace_dec = np.interp(3.3, sorted_lac, sorted_pace)
            ax_pace.axvline(x=lt2_pace_dec, color='orange', linestyle=':', alpha=0.8, label=f'LT2 Pace: {format_pace(lt2_pace_dec)}')

        ax_pace.axhline(y=1.8, color='green', linestyle='--', alpha=0.5)
        ax_pace.axhline(y=3.3, color='orange', linestyle='--', alpha=0.5)
        ax_pace.set_xlabel("Pace (Min/Mile)")
        ax_pace.set_title("External Output (Pace)")
        ax_pace.invert_xaxis() 
        
        ticks = ax_pace.get_xticks()
        ax_pace.set_xticklabels([format_pace(t) for t in ticks])
        ax_pace.legend()
        ax_pace.grid(True, linestyle=':', alpha=0.6)

        st.pyplot(fig2)
        
    else:
        st.info("🩸 Your lactate log is empty or missing data columns.")

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
                            
                            # Zone Categorization
                            bins = [0, 140, 160, 175, 200]
                            labels = ['Recovery', 'LT1 (Aerobic)', 'LT2 (Threshold)', 'VO2 Max']
                            df_stream['Zone'] = pd.cut(df_stream['heartrate'], bins=bins, labels=labels)
                            time_in_zones = df_stream['Zone'].value_counts(sort=False) / 60
                            
                            # Calculate EF (Filtering out 0 velocity/standing still)
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
                                'Aerobic_EF': run_ef.mean().round(2)
                            })
                        progress_bar.progress((i + 1) / len(activities))
                        
                    if new_entries:
                        updated_runs = pd.concat([existing_runs, pd.DataFrame(new_entries)], ignore_index=True)
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
                'Recovery_Min': rec_min, 'LT1_Min': lt1_min, 'LT2_Min': lt2_min, 'VO2_Min': vo2_min, 'Aerobic_EF': 0.0
            }])
            existing_runs = load_data(RUN_LOG)
            updated_runs = pd.concat([existing_runs, new_run], ignore_index=True)
            save_data(updated_runs, RUN_LOG)
            st.success("Manual run added to the database!")

# ==========================================
# 🩸 LOG LACTATE TEST
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


