import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import numpy as np

# Ensure the Data_analysis directory exists
SAVE_DIR = "Data_analysis"
os.makedirs(SAVE_DIR, exist_ok=True)

st.title("📈 Advanced Data Analysis Studio")
st.markdown("Analyze Accumulation/Distribution, visualize aggression, and manage your broker data.")

# --- TABS FOR NAVIGATION ---
tab1, tab2 = st.tabs(["📤 Upload & Analyze", "📂 Browse Saved Data"])

with tab1:
    # --- 1. FILE UPLOAD & PROCESSING ---
    uploaded_file = st.file_uploader("Upload raw data file (JSON or TXT)", type=["txt", "json"])

    if uploaded_file is not None:
        try:
            # Load the JSON data
            raw_data = json.load(uploaded_file)
            
            if "data" in raw_data:
                df = pd.DataFrame(raw_data["data"])
            else:
                df = pd.DataFrame(raw_data)
                
            # Clean numeric columns
            num_cols = ["b_qty", "s_qty", "b_amt", "s_amt"]
            for col in num_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    
            df["Date"] = pd.to_datetime(df["date"], errors='coerce')
            df = df.sort_values(by="Date").reset_index(drop=True)
            
            # Rename for professionalism
            df.rename(columns={
                "b_qty": "Buy_Qty", "s_qty": "Sell_Qty",
                "b_amt": "Buy_Amount", "s_amt": "Sell_Amount"
            }, inplace=True, errors='ignore')
            
            # --- 2. CALCULATE METRICS & 30-DAY AVERAGE ---
            if "Buy_Qty" in df.columns and "Sell_Qty" in df.columns:
                df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
                df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
                # 30-Day Moving Average of Volume (min_periods=1 so it works even if <30 days)
                df["Avg_30D_Vol"] = df["Total_Vol"].rolling(window=30, min_periods=1).mean()
                
            if "Buy_Amount" in df.columns and "Sell_Amount" in df.columns:
                df["Net_Amount"] = df["Buy_Amount"] - df["Sell_Amount"]  # Positive means money went IN (Accumulation)

            # --- 3. CUSTOM DATE FILTER ---
            st.write("---")
            st.subheader("📅 Filter & Analyze Data")
            
            min_date, max_date = df["Date"].min().date(), df["Date"].max().date()
            date_range = st.date_input("Select Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                mask = (df["Date"].dt.date >= start_date) & (df["Date"].dt.date <= end_date)
                filtered_df = df.loc[mask].copy()
                
                # --- 4. TOTAL NET BOXES WITH COLOR ---
                total_net_qty = filtered_df["Net_Qty"].sum()
                total_net_amt = filtered_df["Net_Amount"].sum()
                
                # Determine colors for summary boxes
                qty_color = "#198754" if total_net_qty > 0 else "#dc3545" # Bootstrap Green / Red
                amt_color = "#198754" if total_net_amt > 0 else "#dc3545"
                
                st.write("#### 📊 Total Net Summary")
                c1, c2 = st.columns(2)
                c1.markdown(f"""
                <div style="background-color: {qty_color}; padding: 20px; border-radius: 10px; color: white; text-align: center;">
                    <h3 style="color: white; margin:0;">Total Net Qty</h3>
                    <h2 style="color: white; margin:0;">{total_net_qty:,.0f}</h2>
                    <p style="margin:0;">{'🟢 Accumulating' if total_net_qty > 0 else '🔴 Distributing'}</p>
                </div>
                """, unsafe_allow_html=True)
                
                c2.markdown(f"""
                <div style="background-color: {amt_color}; padding: 20px; border-radius: 10px; color: white; text-align: center;">
                    <h3 style="color: white; margin:0;">Total Net Amount</h3>
                    <h2 style="color: white; margin:0;">Rs {total_net_amt:,.2f}</h2>
                    <p style="margin:0;">{'🟢 Capital Inflow' if total_net_amt > 0 else '🔴 Capital Outflow'}</p>
                </div>
                """, unsafe_allow_html=True)
                
                st.write("<br>", unsafe_allow_html=True)

                # --- 5. COLOR STRENGTH STYLING FUNCTION ---
                def apply_color_strength(row):
                    """Returns background color based on Accumulation/Distribution and Volume Aggression"""
                    net = row["Net_Qty"]
                    avg_vol = row["Avg_30D_Vol"]
                    
                    if avg_vol == 0 or pd.isna(avg_vol): return [''] * len(row)
                    
                    # Calculate how aggressive this day was compared to the 30-day average
                    # Ratio > 1 means higher than average volume. Cap at 2.5 for max darkness.
                    aggression_ratio = abs(net) / avg_vol 
                    
                    # Convert ratio to an opacity (alpha) between 0.15 (light) and 0.85 (dark)
                    alpha = min(max(aggression_ratio * 0.5, 0.15), 0.85)
                    
                    if net > 0:
                        color = f"rgba(0, 200, 0, {alpha})"  # Green
                    elif net < 0:
                        color = f"rgba(255, 0, 0, {alpha})"  # Red
                    else:
                        color = "rgba(128, 128, 128, 0.2)"   # Neutral Gray
                        
                    return [f"background-color: {color}; color: white;"] * len(row)

                # Prepare final display dataframe
                display_df = filtered_df.copy()
                display_df["Date"] = display_df["Date"].dt.strftime('%Y-%m-%d')
                
                # Format numbers for readability before display
                fmt_df = display_df[["Date", "Buy_Qty", "Sell_Qty", "Net_Qty", "Buy_Amount", "Sell_Amount", "Net_Amount", "Avg_30D_Vol"]].copy()
                
                st.write("### 🧮 Detailed Breakdown (Color-coded by Aggression)")
                # Apply styling
                styled_df = fmt_df.style.apply(apply_color_strength, axis=1)\
                                        .format({
                                            "Buy_Qty": "{:,.0f}", "Sell_Qty": "{:,.0f}", "Net_Qty": "{:,.0f}",
                                            "Buy_Amount": "{:,.0f}", "Sell_Amount": "{:,.0f}", "Net_Amount": "{:,.0f}",
                                            "Avg_30D_Vol": "{:,.0f}"
                                        })
                st.dataframe(styled_df, use_container_width=True, height=400)

                # --- 6. SMART MERGE & SAVE ---
                st.write("---")
                st.subheader("💾 Smart Save (Merge Data)")
                st.info("If the file already exists, new dates will be added and duplicates will be removed.")
                
                c_input, c_btn = st.columns([3, 1])
                with c_input:
                    save_name = st.text_input("Filename (e.g., Broker_58)", value="Master_Broker_Data")
                with c_btn:
                    st.write("")
                    st.write("")
                    if st.button("Merge & Save CSV", use_container_width=True):
                        if save_name:
                            final_path = os.path.join(SAVE_DIR, f"{save_name}.csv")
                            
                            # Clean up the dataset to save
                            save_df = display_df.drop(columns=["Total_Vol", "Avg_30D_Vol"], errors='ignore')
                            
                            if os.path.exists(final_path):
                                # Load existing data and merge
                                existing_df = pd.read_csv(final_path)
                                combined_df = pd.concat([existing_df, save_df])
                                # Drop duplicates based on Date (keep the newly uploaded data if dates overlap)
                                combined_df = combined_df.drop_duplicates(subset=["Date"], keep="last")
                                # Sort by date
                                combined_df = combined_df.sort_values(by="Date").reset_index(drop=True)
                                combined_df.to_csv(final_path, index=False)
                                st.success(f"🎉 Merged with existing file and saved as `{final_path}`! (Total Days: {len(combined_df)})")
                            else:
                                # Save as new
                                save_df.to_csv(final_path, index=False)
                                st.success(f"🎉 Created new file `{final_path}`!")
                        else:
                            st.error("Please provide a filename.")

        except Exception as e:
            st.error(f"❌ Error processing file: {e}")

# --- 7. BROWSE SAVED DATA TAB ---
with tab2:
    st.subheader("📂 Your Saved Analyses")
    saved_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".csv")]
    
    if saved_files:
        selected_file = st.selectbox("Select a file to view:", saved_files)
        
        if selected_file:
            file_path = os.path.join(SAVE_DIR, selected_file)
            hist_df = pd.read_csv(file_path)
            
            st.write(f"**Showing Data for:** `{selected_file}` ({len(hist_df)} rows)")
            
            # Simple Total calculation for the saved file
            if "Net_Qty" in hist_df.columns:
                t_qty = hist_df["Net_Qty"].sum()
                st.metric("Historical Net Qty Accumulation", f"{t_qty:,.0f}", delta="Accumulating" if t_qty > 0 else "Distributing")
            
            st.dataframe(hist_df, use_container_width=True)
            
            # Allow user to delete file
            if st.button(f"🗑️ Delete {selected_file}"):
                os.remove(file_path)
                st.success(f"Deleted {selected_file}")
                st.rerun()
    else:
        st.info("No saved data found in the `Data_analysis` folder yet.")
