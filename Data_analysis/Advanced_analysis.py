import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from github import Github
import io

st.subheader("🚀 Advanced Quantitative Analysis")
st.markdown("Interactive visualizations, VWAP analysis, and Whale anomaly detection.")

# --- 1. FETCH FILES FROM GITHUB ---
@st.cache_data(ttl=60) # Cache to prevent spamming GitHub API
def fetch_github_files():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo"])
        contents = repo.get_contents("Data_analysis")
        # Only return CSV files
        return [f.name for f in contents if f.name.endswith(".csv")], repo
    except Exception as e:
        return None, str(e)

saved_files, repo_or_error = fetch_github_files()

if not saved_files:
    if isinstance(repo_or_error, str):
        st.error(f"GitHub Connection Error: {repo_or_error}")
    else:
        st.info("No data files found on GitHub. Please upload and save data in the first tab.")
else:
    # --- 2. SELECT & LOAD DATA ---
    col_sel, col_emp = st.columns([1, 2])
    with col_sel:
        selected_file = st.selectbox("Select Broker Data to Analyze:", saved_files)

    if selected_file:
        try:
            repo = repo_or_error
            file_data = repo.get_contents(f"Data_analysis/{selected_file}")
            csv_string = file_data.decoded_content.decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_string))
            
            # Ensure Date is datetime and sorted
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date").reset_index(drop=True)
            
            # Recalculate deep metrics just in case they are missing from CSV
            df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
            df["Cum_Net_Qty"] = df["Net_Qty"].cumsum()
            df["Net_Amount"] = df["Buy_Amount"] - df["Sell_Amount"]
            df["Cum_Net_Amount"] = df["Net_Amount"].cumsum()
            df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
            df["Avg_30D_Vol"] = df["Total_Vol"].rolling(window=30, min_periods=1).mean()
            
            # VWAP (Volume Weighted Average Price) Calculations
            df["Buy_VWAP"] = np.where(df["Buy_Qty"] > 0, df["Buy_Amount"] / df["Buy_Qty"], 0)
            df["Sell_VWAP"] = np.where(df["Sell_Qty"] > 0, df["Sell_Amount"] / df["Sell_Qty"], 0)

            # --- 3. TOP KPI METRICS (WACC & INVENTORY) ---
            st.write("---")
            st.markdown("### 🎯 Broker Profile & Cost Basis")
            
            total_buy_qty = df["Buy_Qty"].sum()
            total_buy_amt = df["Buy_Amount"].sum()
            total_sell_qty = df["Sell_Qty"].sum()
            total_sell_amt = df["Sell_Amount"].sum()
            
            current_inventory = df["Cum_Net_Qty"].iloc[-1]
            
            # Est. WACC (Overall Average Buy Price)
            est_wacc = (total_buy_amt / total_buy_qty) if total_buy_qty > 0 else 0
            est_sell_price = (total_sell_amt / total_sell_qty) if total_sell_qty > 0 else 0
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Current Est. Inventory", f"{current_inventory:,.0f} units")
            m2.metric("Overall Est. WACC (Buy)", f"Rs {est_wacc:,.2f}")
            m3.metric("Overall Avg Sell Price", f"Rs {est_sell_price:,.2f}")
            
            # Profitability Indicator
            diff = est_sell_price - est_wacc
            m4.metric("Avg Price Spread", f"Rs {diff:,.2f}", delta=f"{(diff/est_wacc)*100:.1f}%" if est_wacc > 0 else "0%")

            # --- 4. INTERACTIVE CHART: VOLUME & ACCUMULATION ---
            st.write("---")
            st.markdown("### 📊 Inventory & Volume Dynamics")
            
            # Create a Plotly Figure with 2 Y-Axes
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Add Buy Volume Bars (Green)
            fig.add_trace(go.Bar(
                x=df["Date"], y=df["Buy_Qty"], name="Buy Qty", 
                marker_color="rgba(39, 174, 96, 0.7)"
            ), secondary_y=False)
            
            # Add Sell Volume Bars (Red - Negative for overlap effect)
            fig.add_trace(go.Bar(
                x=df["Date"], y=-df["Sell_Qty"], name="Sell Qty", 
                marker_color="rgba(231, 76, 60, 0.7)"
            ), secondary_y=False)
            
            # Add Cumulative Inventory Line (Blue)
            fig.add_trace(go.Scatter(
                x=df["Date"], y=df["Cum_Net_Qty"], name="Cumulative Inventory",
                mode="lines", line=dict(color="#2980b9", width=3)
            ), secondary_y=True)
            
            fig.update_layout(
                title="Accumulation Line vs Daily Volume",
                barmode='relative',
                height=500,
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig.update_yaxes(title_text="Daily Volume", secondary_y=False)
            fig.update_yaxes(title_text="Cumulative Inventory", secondary_y=True)
            
            st.plotly_chart(fig, use_container_width=True)

            # --- 5. TWO-COLUMN LAYOUT FOR HEATMAP & WHALES ---
            col_heat, col_whale = st.columns(2)
            
            with col_heat:
                st.markdown("### 🗓️ Activity Heatmap")
                st.caption("Net Buying/Selling by Day of the Week")
                
                # Prepare Heatmap Data
                df_heat = df.copy()
                df_heat['Day_of_Week'] = df_heat['Date'].dt.day_name()
                df_heat['Month'] = df_heat['Date'].dt.to_period('M').astype(str)
                
                # Group data
                heat_pivot = df_heat.groupby(['Month', 'Day_of_Week'])['Net_Qty'].sum().unstack()
                
                # Ensure correct day order
                days_order = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
                heat_pivot = heat_pivot.reindex(columns=[d for d in days_order if d in heat_pivot.columns]).fillna(0)
                
                # Plotly Heatmap
                fig_heat = px.imshow(
                    heat_pivot, 
                    color_continuous_scale="RdYlGn", 
                    color_continuous_midpoint=0,
                    aspect="auto",
                    labels=dict(x="Day of Week", y="Month", color="Net Qty")
                )
                fig_heat.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_heat, use_container_width=True)

            with col_whale:
                st.markdown("### 🚨 Whale Radar (Anomalies)")
                st.caption("Days where activity exceeded 2x the 30-Day Average Volume")
                
                # Find days where net quantity was huge compared to normal trading
                anomalies = df[abs(df["Net_Qty"]) > (df["Avg_30D_Vol"] * 2.0)].copy()
                
                if anomalies.empty:
                    st.success("No extreme abnormal behavior detected in this dataset.")
                else:
                    # Format for display
                    anomalies["Action"] = anomalies["Net_Qty"].apply(lambda x: "🟢 Massive Buy" if x > 0 else "🔴 Massive Dump")
                    anomalies["Date"] = anomalies["Date"].dt.strftime('%Y-%m-%d')
                    
                    display_anomalies = anomalies[["Date", "Action", "Net_Qty", "Avg_30D_Vol"]].sort_values(by="Date", ascending=False)
                    
                    st.dataframe(
                        display_anomalies.style.format({"Net_Qty": "{:,.0f}", "Avg_30D_Vol": "{:,.0f}"}),
                        use_container_width=True,
                        height=400
                    )

        except Exception as e:
            st.error(f"❌ Error rendering advanced analysis: {e}")
