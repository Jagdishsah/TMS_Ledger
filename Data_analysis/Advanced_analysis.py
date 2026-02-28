import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from github import Github
import io

st.subheader("🚀 Advanced Quantitative Analysis")

@st.cache_data(ttl=60)
def fetch_github_files():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"]) # FIXED REPO_NAME
        return [f.name for f in repo.get_contents("Data_analysis") if f.name.endswith(".csv")], repo
    except Exception as e: return None, str(e)

saved_files, repo_or_error = fetch_github_files()

if saved_files:
    selected_file = st.selectbox("Select Broker Data to Analyze:", saved_files)
    if selected_file:
        file_data = repo_or_error.get_contents(f"Data_analysis/{selected_file}")
        raw_df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        raw_df["Date"] = pd.to_datetime(raw_df["Date"])

        # --- DYNAMIC DATE FILTER ---
        min_date, max_date = raw_df["Date"].min().date(), raw_df["Date"].max().date()
        date_range = st.date_input("🗓️ Select Range (Cumulatives start at 0 on Start Date)", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        
        if len(date_range) == 2:
            mask = (raw_df["Date"].dt.date >= date_range[0]) & (raw_df["Date"].dt.date <= date_range[1])
            df = raw_df.loc[mask].copy().reset_index(drop=True)
            
            if not df.empty:
                # --- STRICT RECALCULATION FROM 0 FOR THE RANGE ---
                df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
                df["Cum_Net_Qty"] = df["Net_Qty"].cumsum() # Starts at 0 for this slice!
                df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
                df["Avg_30D_Vol"] = df["Total_Vol"].rolling(window=30, min_periods=1).mean()
                df["Daily_VWAP"] = np.where(df["Total_Vol"] > 0, (df["Buy_Amount"] + df["Sell_Amount"]) / df["Total_Vol"], 0)

                # --- BROKER KPI ---
                st.write("---")
                m1, m2 = st.columns(2)
                m1.metric("Range Net Inventory Shift", f"{df['Cum_Net_Qty'].iloc[-1]:,.0f} units")
                m2.metric("Range Avg Price", f"Rs {df['Daily_VWAP'].mean():,.2f}")

                # --- RESTORED DUAL AXIS CHART ---
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(go.Bar(x=df["Date"], y=df["Buy_Qty"], name="Buy Qty", marker_color="rgba(39, 174, 96, 0.7)"), secondary_y=False)
                fig.add_trace(go.Bar(x=df["Date"], y=-df["Sell_Qty"], name="Sell Qty", marker_color="rgba(231, 76, 60, 0.7)"), secondary_y=False)
                fig.add_trace(go.Scatter(x=df["Date"], y=df["Cum_Net_Qty"], name="Range Cum. Inventory", line=dict(color="#2980b9", width=3)), secondary_y=True)
                fig.update_layout(title="Volume & Inventory Trend (Range Adjusted)", barmode='relative', height=400)
                st.plotly_chart(fig, use_container_width=True)

                # --- RESTORED HEATMAP & WHALES ---
                c_heat, c_whale = st.columns(2)
                with c_heat:
                    st.markdown("### 🗓️ Activity Heatmap")
                    df_heat = df.copy()
                    df_heat['Day'] = df_heat['Date'].dt.day_name()
                    df_heat['Month'] = df_heat['Date'].dt.to_period('M').astype(str)
                    heat_pivot = df_heat.groupby(['Month', 'Day'])['Net_Qty'].sum().unstack().fillna(0)
                    st.plotly_chart(px.imshow(heat_pivot, color_continuous_scale="RdYlGn", color_continuous_midpoint=0, aspect="auto"), use_container_width=True)
                
                with c_whale:
                    st.markdown("### 🚨 Whale Radar (Anomalies)")
                    anomalies = df[abs(df["Net_Qty"]) > (df["Avg_30D_Vol"] * 2.0)].copy()
                    if not anomalies.empty:
                        anomalies["Action"] = anomalies["Net_Qty"].apply(lambda x: "🟢 Buy" if x > 0 else "🔴 Sell")
                        st.dataframe(anomalies[["Date", "Action", "Net_Qty", "Daily_VWAP"]], height=300)
                    else: st.success("No extreme anomalies.")
