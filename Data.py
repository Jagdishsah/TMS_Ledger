import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import numpy as np
from github import Github
import io

# Ensure the Data_analysis directory exists locally for temporary caching
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
            
            # --- 2. CALCULATE METRICS, 30-DAY AVG & CUMULATIVE TOTALS ---
            if "Buy_Qty" in df.columns and "Sell_Qty" in df.columns:
                df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
                df["Cum_Net_Qty"] = df["Net_Qty"].cumsum()  # Running total of Qty
                
                df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
                # 30-Day Moving Average of Volume
                df["Avg_30D_Vol"] = df["Total_Vol"].rolling(window=30, min_periods=1).mean()
                
            if "Buy_Amount" in df.columns and "Sell_Amount" in df.columns:
                df["Net_Amount"] = df["Buy_Amount"] - df["Sell_Amount"]  
                df["Cum_Net_Amount"] = df["Net_Amount"].cumsum()  # Running total of Amount

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
                # Grab the final cumulative values for the period
                final_cum_qty = filtered_df["Cum_Net_Qty"].iloc[-1] if not filtered_df.empty else 0
                final_cum_amt = filtered_df["Cum_Net_Amount"].iloc[-1] if not filtered_df.empty else 0
                
                qty_color = "#198754" if final_cum_qty > 0 else "#dc3545"
                amt_color = "#198754" if final_cum_amt > 0 else "#dc3545"
                
                st.write("#### 📊 Cumulative Position (End of Selected Period)")
                c1, c2 = st.columns(2)
                c1.markdown(f"""
                <div style="background-color: {qty_color}; padding: 20px; border-radius: 10px; color: white; text-align: center;">
                    <h3 style="color: white; margin:0;">Holding Inventory (Cum. Qty)</h3>
                    <h2 style="color: white; margin:0;">{final_cum_qty:,.0f}</h2>
                    <p style="margin:0;">{'🟢 Net Accumulator' if final_cum_qty > 0 else '🔴 Net Distributor'}</p>
                </div>
                """, unsafe_allow_html=True)
                
                c2.markdown(f"""
                <div style="background-color: {amt_color}; padding: 20px; border-radius: 10px; color: white; text-align: center;">
                    <h3 style="color: white; margin:0;">Net Capital Flow (Cum. Amount)</h3>
                    <h2 style="color: white; margin:0;">Rs {final_cum_amt:,.2f}</h2>
                    <p style="margin:0;">{'🟢 Capital Trapped/Invested' if final_cum_amt > 0 else '🔴 Capital Booked/Exited'}</p>
                </div>
                """, unsafe_allow_html=True)
                
                st.write("<br>", unsafe_allow_html=True)

                # --- 5. COLOR STRENGTH STYLING FUNCTION ---
                def apply_color_strength(row):
                    net = row["Net_Qty"]
                    avg_vol = row["Avg_30D_Vol"]
                    
                    if avg_vol == 0 or pd.isna(avg_vol): return [''] * len(row)
                    
                    aggression_ratio = abs(net) / avg_vol 
                    alpha = min(max(aggression_ratio * 0.5, 0.15), 0.85)
                    
                    if net > 0:
                        color = f"rgba(0, 200, 0, {alpha})"
                    elif net < 0:
                        color = f"rgba(255, 0, 0, {alpha})"
                    else:
                        color = "rgba(128, 128, 128, 0.2)"
                        
                    return [f"background-color: {color}; color: white;"] * len(row)

                # Prepare final display dataframe
                display_df = filtered_df.copy()
                display_df["Date"] = display_df["Date"].dt.strftime('%Y-%m-%d')
                
                fmt_df = display_df[["Date", "Buy_Qty", "Sell_Qty", "Net_Qty", "Cum_Net_Qty", "Buy_Amount", "Sell_Amount", "Net_Amount", "Cum_Net_Amount", "Avg_30D_Vol"]].copy()
                
                st.write("### 🧮 Detailed Breakdown (Color-coded by Aggression)")
                styled_df = fmt_df.style.apply(apply_color_strength, axis=1)\
                                        .format({
                                            "Buy_Qty": "{:,.0f}", "Sell_Qty": "{:,.0f}", 
                                            "Net_Qty": "{:,.0f}", "Cum_Net_Qty": "{:,.0f}",
                                            "Buy_Amount": "{:,.0f}", "Sell_Amount": "{:,.0f}", 
                                            "Net_Amount": "{:,.0f}", "Cum_Net_Amount": "{:,.0f}",
                                            "Avg_30D_Vol": "{:,.0f}"
                                        })
                st.dataframe(styled_df, use_container_width=True, height=400)
                
               

                # --- 6. SMART MERGE & SAVE TO GITHUB ---
                st.write("---")
                st.subheader("💾 Save to GitHub (Permanent)")
                st.info("This will permanently merge and save the data directly to your GitHub repository.")
                
                c_input, c_btn = st.columns([3, 1])
                with c_input:
                    save_name = st.text_input("Filename (e.g., Broker_58)", value="Master_Broker_Data")
                with c_btn:
                    st.write("")
                    st.write("")
                    if st.button("Commit to GitHub", use_container_width=True):
                        if save_name:
                            file_path = f"Data_analysis/{save_name}.csv"
                            save_df = display_df.drop(columns=["Total_Vol", "Avg_30D_Vol"], errors='ignore')
                            
                            try:
                                # Authenticate with GitHub
                                g = Github(st.secrets["github"]["token"]) 
                                repo = g.get_repo(st.secrets["github"]["repo_name"]) 
                                
                                try:
                                    # Fetch existing file from GitHub to merge
                                    file_contents = repo.get_contents(file_path)
                                    existing_csv = file_contents.decoded_content.decode('utf-8')
                                    existing_df = pd.read_csv(io.StringIO(existing_csv))
                                    
                                    # Merge logic
                                    combined_df = pd.concat([existing_df, save_df])
                                    combined_df = combined_df.drop_duplicates(subset=["Date"], keep="last")
                                    combined_df = combined_df.sort_values(by="Date").reset_index(drop=True)
                                    
                                    # Update file on GitHub
                                    updated_csv = combined_df.to_csv(index=False)
                                    repo.update_file(file_contents.path, f"App: Updated {save_name}", updated_csv, file_contents.sha)
                                    st.success(f"🎉 Successfully merged and saved `{save_name}.csv` to GitHub!")
                                    
                                except Exception: 
                                    # File doesn't exist yet, create it!
                                    new_csv = save_df.to_csv(index=False)
                                    repo.create_file(file_path, f"App: Created {save_name}", new_csv)
                                    st.success(f"🎉 Successfully created `{save_name}.csv` on GitHub!")
                                    
                            except KeyError:
                                st.error("❌ GitHub secrets not found. Make sure st.secrets['github']['token'] and ['repo'] exist.")
                            except Exception as e:
                                st.error(f"❌ Failed to connect to GitHub. Error: {e}")
                        else:
                            st.error("Please provide a filename.")
                            
        # THIS WAS THE MISSING BLOCK!
        except json.JSONDecodeError:
            st.error("❌ The file uploaded is not a valid JSON structure.")
        except Exception as e:
            st.error(f"❌ An error occurred while processing the file: {e}")
            
    else:
        st.info("👆 Please upload a `.txt` or `.json` file containing your broker data to begin.")

# --- 7. BROWSE SAVED DATA FROM GITHUB ---
with tab2:
    st.subheader("📂 Your Saved Analyses (GitHub)")
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"])
        
        try:
            # Fetch folder contents from GitHub
            contents = repo.get_contents("Data_analysis")
            saved_files = [file.name for file in contents if file.name.endswith(".csv")]
            
            if saved_files:
                selected_file = st.selectbox("Select a file to view:", saved_files)
                
                if selected_file:
                    file_data = repo.get_contents(f"Data_analysis/{selected_file}")
                    csv_string = file_data.decoded_content.decode('utf-8')
                    hist_df = pd.read_csv(io.StringIO(csv_string))
                    
                    st.write(f"**Showing Data for:** `{selected_file}` ({len(hist_df)} rows)")
                    
                    if "Net_Qty" in hist_df.columns:
                        t_qty = hist_df["Net_Qty"].sum()
                        st.metric("Historical Net Qty", f"{t_qty:,.0f}", delta="Accumulating" if t_qty > 0 else "Distributing")
                    
                    st.dataframe(hist_df, use_container_width=True)
                    
                    # Delete from GitHub button
                    if st.button(f"🗑️ Delete {selected_file} from GitHub"):
                        repo.delete_file(file_data.path, f"App: Deleted {selected_file}", file_data.sha)
                        st.success(f"Deleted {selected_file} from GitHub!")
                        st.rerun()
            else:
                st.info("No CSV files found in the `Data_analysis` folder on GitHub.")
        except Exception:
            st.info("The `Data_analysis` folder hasn't been created on GitHub yet. Save a file first!")
            
    except Exception as e:
        st.error("❌ Could not authenticate with GitHub to load files. Check your secrets.")
