import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from github import Github
import io

st.subheader("🚀 Advanced Quantitative Analysis")
st.markdown("Dynamic visualizations and anomaly detection based on your selected date range.")

# --- 1. FETCH FILES FROM GITHUB ---
@st.cache_data(ttl=60)
def fetch_github_files():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"])
        contents = repo.get_contents("Data_analysis")
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
    col_sel, col_emp = st.columns([1, 2])
    with col_sel:
        selected_file = st.selectbox("Select Broker Data to Analyze:", saved_files)

    if selected_file:
        try:
            repo = repo_or_error
            file_data = repo.get_contents(f"Data_analysis/{selected_file}")
            csv_string = file_data.decoded_content.decode('utf-8')
            raw_df = pd.read_csv(io.StringIO(csv_string))
            
            raw_df["Date"] = pd.to_datetime(raw_df["Date"])
            raw_df = raw_df.sort_values("Date").reset_index(drop=True)

            # --- 2. DYNAMIC DATE RANGE FILTER ---
            st.write("---")
            min_date, max_date = raw_df["Date"].min().date(), raw_df["Date"].max().date()
            date_range = st.date_input("🗓️ Select Date Range for Analysis", value=(min_date, max_date), min_value=min_date, max_value=max_date)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                mask = (raw_df["Date"].dt.date >= start_date) & (raw_df["Date"].dt.date <= end_date)
                df = raw_df.loc[mask].copy().reset_index(drop=True)
                
                if df.empty:
                    st.warning("No data available for this date range.")
                else:
                    # --- 3. DYNAMIC RECALCULATION (Starts at 0 for the selected range) ---
                    df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
                    df["Cum_Net_Qty"] = df["Net_Qty"].cumsum() # Cumsum starts from the filtered start date!
                    
                    df["Net_Amount"] = df["Buy_Amount"] - df["Sell_Amount"]
                    df["Cum_Net_Amount"] = df["Net_Amount"].cumsum()
                    
                    df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
                    df["Avg_30D_Vol"] = df["Total_Vol"].rolling(window=30, min_periods=1).mean()
                    
                    # VWAP Calculations
                    df["Buy_VWAP"] = np.where(df["Buy_Qty"] > 0, df["Buy_Amount"] / df["Buy_Qty"], 0)
                    df["Sell_VWAP"] = np.where(df["Sell_Qty"] > 0, df["Sell_Amount"] / df["Sell_Qty"], 0)
                    df["Daily_VWAP"] = np.where(df["Total_Vol"] > 0, (df["Buy_Amount"] + df["Sell_Amount"]) / df["Total_Vol"], 0)

                    # --- 4. TOP KPI METRICS ---
                    st.write("---")
                    st.markdown(f"### 🎯 Broker Profile ({start_date} to {end_date})")
                    
                    total_buy_qty = df["Buy_Qty"].sum()
                    total_buy_amt = df["Buy_Amount"].sum()
                    total_sell_qty = df["Sell_Qty"].sum()
                    total_sell_amt = df["Sell_Amount"].sum()
                    
                    current_inventory = df["Cum_Net_Qty"].iloc[-1]
                    est_wacc = (total_buy_amt / total_buy_qty) if total_buy_qty > 0 else 0
                    est_sell_price = (total_sell_amt / total_sell_qty) if total_sell_qty > 0 else 0
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Range Inventory Shift", f"{current_inventory:,.0f} units")
                    m2.metric("Range Est. WACC (Buy)", f"Rs {est_wacc:,.2f}")
                    m3.metric("Range Avg Sell Price", f"Rs {est_sell_price:,.2f}")
                    diff = est_sell_price - est_wacc
                    m4.metric("Avg Price Spread", f"Rs {diff:,.2f}", delta=f"{(diff/est_wacc)*100:.1f}%" if est_wacc > 0 else "0%")

                    # --- 5. INTERACTIVE CHART: DYNAMIC ACCUMULATION ---
                    st.write("---")
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    fig.add_trace(go.Bar(x=df["Date"], y=df["Buy_Qty"], name="Buy Qty", marker_color="rgba(39, 174, 96, 0.7)"), secondary_y=False)
                    fig.add_trace(go.Bar(x=df["Date"], y=-df["Sell_Qty"], name="Sell Qty", marker_color="rgba(231, 76, 60, 0.7)"), secondary_y=False)
                    fig.add_trace(go.Scatter(x=df["Date"], y=df["Cum_Net_Qty"], name="Cum. Inventory", mode="lines", line=dict(color="#2980b9", width=3)), secondary_y=True)
                    
                    fig.update_layout(title="Volume & Inventory Trend (Range Adjusted)", barmode='relative', height=500, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig, use_container_width=True)

                    # --- 6. VOLUME PROFILE & WHALES ---
                    col_vp, col_whale = st.columns(2)
                    
                    with col_vp:
                        st.markdown("### 🧱 Volume by Price (Support/Resistance)")
                        vp_df = df[df["Daily_VWAP"] > 0].copy()
                        if not vp_df.empty:
                            bins = np.linspace(vp_df["Daily_VWAP"].min(), vp_df["Daily_VWAP"].max(), 12)
                            vp_df['Price_Zone'] = pd.cut(vp_df['Daily_VWAP'], bins=bins)
                            profile = vp_df.groupby('Price_Zone', observed=False).agg({'Buy_Qty': 'sum', 'Sell_Qty': 'sum'}).reset_index()
                            profile['Price_Level'] = profile['Price_Zone'].apply(lambda x: f"Rs {int(x.mid)}" if pd.notnull(x) else "Unknown")
                            
                            fig_vp = go.Figure()
                            fig_vp.add_trace(go.Bar(y=profile['Price_Level'], x=profile['Buy_Qty'], name='Buy Vol', orientation='h', marker_color='rgba(39, 174, 96, 0.8)'))
                            fig_vp.add_trace(go.Bar(y=profile['Price_Level'], x=-profile['Sell_Qty'], name='Sell Vol', orientation='h', marker_color='rgba(231, 76, 60, 0.8)'))
                            fig_vp.update_layout(barmode='relative', yaxis=dict(autorange="reversed"), height=400, hovermode="y unified", margin=dict(t=30))
                            st.plotly_chart(fig_vp, use_container_width=True)

                    with col_whale:
                        st.markdown("### 🚨 Whale Radar (Range Anomalies)")
                        anomalies = df[abs(df["Net_Qty"]) > (df["Avg_30D_Vol"] * 2.0)].copy()
                        if anomalies.empty:
                            st.success("No abnormal volume spikes in this date range.")
                        else:
                            anomalies["Action"] = anomalies["Net_Qty"].apply(lambda x: "🟢 Heavy Buy" if x > 0 else "🔴 Heavy Sell")
                            anomalies["Date"] = anomalies["Date"].dt.strftime('%Y-%m-%d')
                            disp = anomalies[["Date", "Action", "Net_Qty", "Daily_VWAP"]].sort_values(by="Date", ascending=False)
                            st.dataframe(disp.style.format({"Net_Qty": "{:,.0f}", "Daily_VWAP": "Rs {:,.1f}"}), use_container_width=True, height=350)

        except Exception as e:
            st.error(f"❌ Error rendering advanced analysis: {e}")
