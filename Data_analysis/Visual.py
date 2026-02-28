import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from github import Github
import io

st.subheader("🎨 Dynamic Visualization Studio")

@st.cache_data(ttl=60)
def fetch_github_files():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"])
        return [f.name for f in repo.get_contents("Data_analysis") if f.name.endswith(".csv")], repo
    except: return None, None

saved_files, repo = fetch_github_files()

if saved_files:
    selected_file = st.selectbox("Select Data Source:", saved_files)
    if selected_file:
        file_data = repo.get_contents(f"Data_analysis/{selected_file}")
        df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        df["Date"] = pd.to_datetime(df["Date"])
        
        # Date Filter
        min_date, max_date = df["Date"].min().date(), df["Date"].max().date()
        date_range = st.date_input("Filter Dates:", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        
        if len(date_range) == 2:
            mask = (df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])
            df = df.loc[mask].copy().reset_index(drop=True)
            
            # Re-calc basics
            df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
            df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
            df["Daily_VWAP"] = np.where(df["Total_Vol"] > 0, (df["Buy_Amount"] + df["Sell_Amount"]) / df["Total_Vol"], 0)

            st.write("---")
            chart_type = st.selectbox("Select Visualization Type:", [
                "1. Custom Scatter / Bubble Chart",
                "2. Buy vs Sell Donut Chart",
                "3. Net Quantity Speedometer (Gauge)"
            ])

            if chart_type == "1. Custom Scatter / Bubble Chart":
                st.markdown("Swap values to find hidden correlations.")
                num_cols = ["Date", "Buy_Qty", "Sell_Qty", "Net_Qty", "Total_Vol", "Daily_VWAP", "Buy_Amount", "Sell_Amount"]
                
                c1, c2, c3, c4 = st.columns(4)
                x_axis = c1.selectbox("X-Axis", num_cols, index=0)
                y_axis = c2.selectbox("Y-Axis", num_cols, index=5)
                size_col = c3.selectbox("Bubble Size", ["None"] + num_cols, index=4)
                color_col = c4.selectbox("Color By", ["None"] + num_cols, index=3)
                
                kwargs = {"x": x_axis, "y": y_axis}
                if size_col != "None": kwargs["size"] = df[size_col].abs() # Abs to prevent negative sizes
                if color_col != "None": kwargs["color"] = color_col
                
                fig = px.scatter(df, **kwargs, color_continuous_scale="RdYlGn", color_continuous_midpoint=0 if color_col=="Net_Qty" else None)
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

            elif chart_type == "2. Buy vs Sell Donut Chart":
                buy_sum, sell_sum = df["Buy_Qty"].sum(), df["Sell_Qty"].sum()
                fig = px.pie(values=[buy_sum, sell_sum], names=["Total Buy", "Total Sell"], hole=0.5, color_discrete_sequence=["#27ae60", "#e74c3c"])
                st.plotly_chart(fig, use_container_width=True)

            elif chart_type == "3. Net Quantity Speedometer (Gauge)":
                total_net = df["Net_Qty"].sum()
                max_vol = df["Total_Vol"].sum()
                fig = go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = total_net,
                    title = {'text': "Net Accumulation/Distribution Gauge"},
                    gauge = {
                        'axis': {'range': [-max_vol, max_vol]},
                        'bar': {'color': "black"},
                        'steps' : [
                            {'range': [-max_vol, 0], 'color': "#ff9999"},
                            {'range': [0, max_vol], 'color': "#99ff99"}],
                    }
                ))
                st.plotly_chart(fig, use_container_width=True)
