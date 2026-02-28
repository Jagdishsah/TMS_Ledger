import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# Ensure the Data_analysis directory exists
SAVE_DIR = "Data_analysis"
os.makedirs(SAVE_DIR, exist_ok=True)

st.title("📈 Data Analysis Studio")
st.markdown("Upload raw broker data, filter it, and save the refined versions.")

# --- 1. FILE UPLOAD & PROCESSING ---
uploaded_file = st.file_uploader("Upload your raw data file (JSON or TXT)", type=["txt", "json"])

if uploaded_file is not None:
    try:
        # Load the JSON data
        raw_data = json.load(uploaded_file)
        
        # Check if it uses the {"data": [...]} structure like your uploaded file
        if "data" in raw_data:
            df = pd.DataFrame(raw_data["data"])
        else:
            df = pd.DataFrame(raw_data) # Fallback just in case
            
        # Convert strings to actual numbers and dates for accurate calculations
        num_cols = ["b_qty", "s_qty", "b_amt", "s_amt"]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        df["date"] = pd.to_datetime(df["date"], errors='coerce')
        
        # Rename columns to be cleaner and more professional
        df.rename(columns={
            "date": "Date",
            "b_qty": "Buy_Qty",
            "s_qty": "Sell_Qty",
            "b_amt": "Buy_Amount",
            "s_amt": "Sell_Amount"
        }, inplace=True)
        
        # Add useful calculated metrics
        if "Buy_Qty" in df.columns and "Sell_Qty" in df.columns:
            df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
        if "Buy_Amount" in df.columns and "Sell_Amount" in df.columns:
            df["Net_Amount"] = df["Sell_Amount"] - df["Buy_Amount"]
            
        # Automatically save to Temp.csv
        temp_path = os.path.join(SAVE_DIR, "Temp.csv")
        df.to_csv(temp_path, index=False)
        
        st.success(f"✅ Data successfully loaded and cached as `{temp_path}`")
        
        with st.expander("👀 View Full Raw Data", expanded=False):
            st.dataframe(df, use_container_width=True)

        # --- 2. CUSTOM DATE FILTER ---
        st.write("---")
        st.subheader("📅 Filter Data")
        
        # Get min and max dates from the dataset
        min_date = df["Date"].min().date()
        max_date = df["Date"].max().date()
        
        # Date range picker
        date_range = st.date_input(
            "Select Date Range", 
            value=(min_date, max_date), 
            min_value=min_date, 
            max_value=max_date
        )
        
        # Ensure the user has selected both a start and end date
        if len(date_range) == 2:
            start_date, end_date = date_range
            
            # Apply the filter
            mask = (df["Date"].dt.date >= start_date) & (df["Date"].dt.date <= end_date)
            filtered_df = df.loc[mask].copy()
            
            # Format the date nicely for the UI
            display_df = filtered_df.copy()
            display_df["Date"] = display_df["Date"].dt.strftime('%Y-%m-%d')
            
            st.write(f"### Filtered Results ({len(filtered_df)} Days)")
            st.dataframe(display_df, use_container_width=True)
            
            # Show summary metrics for the filtered range
            st.write("#### 📊 Selected Range Summary")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Buy Qty", f"{filtered_df['Buy_Qty'].sum():,.0f}")
            col2.metric("Total Sell Qty", f"{filtered_df['Sell_Qty'].sum():,.0f}")
            col3.metric("Total Buy Amount", f"Rs {filtered_df['Buy_Amount'].sum():,.2f}")
            col4.metric("Total Sell Amount", f"Rs {filtered_df['Sell_Amount'].sum():,.2f}")
            
            # --- 3. SAVE FINAL RESULT ---
            st.write("---")
            st.subheader("💾 Save Final Result")
            st.info("Your data will be saved in the `Data_analysis` folder.")
            
            c_input, c_btn = st.columns([3, 1])
            with c_input:
                save_name = st.text_input("Filename (no extension needed)", value="Filtered_Broker_Data")
            with c_btn:
                st.write("") # Spacer to align button
                st.write("")
                if st.button("Save as CSV", use_container_width=True):
                    if save_name:
                        final_path = os.path.join(SAVE_DIR, f"{save_name}.csv")
                        filtered_df.to_csv(final_path, index=False)
                        st.success(f"🎉 Final result saved successfully as `{final_path}`!")
                    else:
                        st.error("Please provide a valid filename.")

    except json.JSONDecodeError:
        st.error("❌ The file uploaded is not a valid JSON structure.")
    except Exception as e:
        st.error(f"❌ An error occurred: {e}")
else:
    st.info("👆 Please upload a `.txt` or `.json` file containing your broker data to begin.")
