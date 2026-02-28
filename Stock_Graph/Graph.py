import streamlit as st
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from github import Github
import io

st.markdown("### 📈 Pro Interactive Stock Chart")

# --- 1. GITHUB HELPER FUNCTIONS ---
def get_repo():
    try:
        g = Github(st.secrets["github"]["token"]) 
        return g.get_repo(st.secrets["github"]["repo_name"])
    except Exception as e:
        st.error(f"GitHub Auth Error: {e}")
        return None

def fetch_saved_stocks():
    repo = get_repo()
    if repo:
        try:
            # We will save stock graphs in a dedicated "Stock_Data" folder
            contents = repo.get_contents("Stock_Data")
            return [f.name.replace(".csv", "") for f in contents if f.name.endswith(".csv")]
        except Exception:
            return [] # Folder might not exist yet
    return []

# --- 2. DATA MANAGEMENT (UPLOAD & SAVE) ---
with st.expander("📁 Data Management (Upload & Save)", expanded=False):
    uploaded_file = st.file_uploader("Upload OHLCV Data (TXT/JSON)", type=["txt", "json"])
    
    if uploaded_file is not None:
        try:
            raw_data = json.load(uploaded_file)
            if raw_data.get("s") == "ok" and "t" in raw_data:
                up_df = pd.DataFrame({
                    "Date": pd.to_datetime(raw_data["t"], unit='s'),
                    "Open": raw_data["o"], "High": raw_data["h"],
                    "Low": raw_data["l"], "Close": raw_data["c"],
                    "Volume": raw_data["v"]
                })
                st.success(f"✅ Loaded {len(up_df)} rows from file.")
                
                # Save & Merge UI
                c1, c2 = st.columns([3, 1])
                stock_symbol = c1.text_input("Stock Symbol to Save/Merge (e.g., NABIL):").upper()
                if c2.button("💾 Save to Cloud", use_container_width=True):
                    if stock_symbol:
                        repo = get_repo()
                        file_path = f"Stock_Data/{stock_symbol}.csv"
                        try:
                            # Try to merge with existing data
                            file_contents = repo.get_contents(file_path)
                            existing_df = pd.read_csv(io.StringIO(file_contents.decoded_content.decode('utf-8')))
                            existing_df["Date"] = pd.to_datetime(existing_df["Date"])
                            
                            combined_df = pd.concat([existing_df, up_df]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
                            updated_csv = combined_df.to_csv(index=False)
                            repo.update_file(file_contents.path, f"Updated {stock_symbol}", updated_csv, file_contents.sha)
                            st.success(f"🎉 Merged with existing `{stock_symbol}` data in Cloud!")
                        except Exception:
                            # File doesn't exist, create it
                            new_csv = up_df.to_csv(index=False)
                            repo.create_file(file_path, f"Created {stock_symbol}", new_csv)
                            st.success(f"🎉 Created new `{stock_symbol}` record in Cloud!")
                    else:
                        st.error("Please enter a stock symbol.")
            else:
                st.error("Invalid TradingView JSON format.")
        except Exception as e:
            st.error(f"Error parsing file: {e}")

# --- 3. LOAD CLOUD DATA & CALCULATE INDICATORS ---
st.write("---")
saved_stocks = fetch_saved_stocks()

c_load, c_ind1, c_ind2 = st.columns([2, 1, 1])
selected_stock = c_load.selectbox("Select Stock to Chart:", ["-- Select --"] + saved_stocks)

# Indicator Toggles
show_sma = c_ind1.checkbox("Show Moving Averages", value=True)
show_rsi = c_ind2.checkbox("Show RSI (14)", value=True)

if selected_stock != "-- Select --":
    repo = get_repo()
    file_data = repo.get_contents(f"Stock_Data/{selected_stock}.csv")
    df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    # --- CALCULATE INDICATORS ---
    # 1. Moving Averages
    df["SMA_20"] = df["Close"].rolling(window=20).mean()
    df["SMA_50"] = df["Close"].rolling(window=50).mean()
    
    # 2. Volume Moving Average
    df["Vol_SMA_30"] = df["Volume"].rolling(window=30).mean()
    
    # 3. RSI (Relative Strength Index - 14 Day)
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # --- 4. BUILD TRADINGVIEW-STYLE CHART ---
    # Determine rows based on RSI toggle
    rows = 3 if show_rsi else 2
    row_heights = [0.6, 0.2, 0.2] if show_rsi else [0.7, 0.3]
    
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, 
        vertical_spacing=0.03, 
        row_heights=row_heights
    )

    # TRACE 1: Candlestick
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name='Price', increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ), row=1, col=1)

    # TRACE 2: SMAs
    if show_sma:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA_20'], line=dict(color='orange', width=1.5), name='SMA 20'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA_50'], line=dict(color='blue', width=1.5), name='SMA 50'), row=1, col=1)

    # TRACE 3: Volume & Volume SMA
    colors = ['#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for i, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df['Date'], y=df['Volume'], marker_color=colors, name='Volume', opacity=0.8), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['Vol_SMA_30'], line=dict(color='purple', width=2), name='Vol SMA 30'), row=2, col=1)

    # TRACE 4: RSI (Optional)
    if show_rsi:
        fig.add_trace(go.Scatter(x=df['Date'], y=df["RSI_14"], line=dict(color='purple', width=1.5), name='RSI 14'), row=3, col=1)
        # Add Overbought/Oversold lines
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
        fig.update_yaxes(range=[0, 100], row=3, col=1)

    # --- 5. SMOOTHNESS FIX (Remove Weekend Gaps) ---
    # Plotly leaves gaps for dates that don't exist in the dataframe. 
    # We fix this by converting the X-axis to a category based on the exact dates we have!
    dt_breaks = pd.date_range(start=df['Date'].min(), end=df['Date'].max()).difference(df['Date'])
    
    fig.update_xaxes(
        rangebreaks=[dict(values=dt_breaks)], # Removes all days where market was closed!
        rangeslider_visible=False, 
        showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)'
    )
    
    fig.update_yaxes(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)')

    # Overall Layout Tuning
    fig.update_layout(
        height=800 if show_rsi else 650,
        title=f"Chart: {selected_stock}",
        template="plotly_dark", # TradingView dark mode feel
        hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)
