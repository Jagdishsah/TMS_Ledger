import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from github import Github
import io
import datetime

st.markdown("### 🌊 Institutional Elliott Wave Engine")
st.caption("Advanced EW analysis with Strict Rules, HTF Bias, Invalidation Levels, and Replay Backtesting.")

# --- 1. GITHUB FETCHING ---
@st.cache_data(ttl=300)
def fetch_saved_stocks():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"])
        contents = repo.get_contents("Stock_Data")
        return [f.name.replace(".csv", "") for f in contents if f.name.endswith(".csv")], repo
    except Exception: return [], None

saved_stocks, repo = fetch_saved_stocks()

# --- CORE ENGINE (Reusable for Live & Replay) ---
def run_ew_analysis(df_full, replay_date, sensitivity, wave_type):
    # Slice for Replay Mode
    df = df_full[df_full['Date'].dt.date <= replay_date].copy().reset_index(drop=True)
    future_df = df_full[df_full['Date'].dt.date > replay_date].copy() 
    
    if len(df) < 50:
        st.error("Not enough data to analyze. Need at least 50 days.")
        return

    # HTF Bias & OHLC Validation
    df['SMA_200'] = df['Close'].rolling(200, min_periods=50).mean()
    htf_bullish = df['Close'].iloc[-1] > df['SMA_200'].iloc[-1]

    # --- SWING DETECTION ---
    def find_swings(data, order):
        highs, lows = [], []
        for i in range(order, len(data) - order):
            if data['High'].iloc[i] == max(data['High'].iloc[i-order:i+order+1]):
                highs.append((i, data['High'].iloc[i], 'High', data['Date'].iloc[i]))
            if data['Low'].iloc[i] == min(data['Low'].iloc[i-order:i+order+1]):
                lows.append((i, data['Low'].iloc[i], 'Low', data['Date'].iloc[i]))
        
        last_idx = len(data) - 1
        if data['High'].iloc[last_idx] >= max(data['High'].iloc[-order:]):
            highs.append((last_idx, data['High'].iloc[last_idx], 'High_Unconfirmed', data['Date'].iloc[last_idx]))
        if data['Low'].iloc[last_idx] <= min(data['Low'].iloc[-order:]):
            lows.append((last_idx, data['Low'].iloc[last_idx], 'Low_Unconfirmed', data['Date'].iloc[last_idx]))

        swings = sorted(highs + lows, key=lambda x: x[0])
        alt_swings = []
        for s in swings:
            base_type = s[2].split('_')[0]
            if not alt_swings:
                alt_swings.append(s)
            elif base_type != alt_swings[-1][2].split('_')[0]:
                alt_swings.append(s)
            else:
                if base_type == 'High' and s[1] > alt_swings[-1][1]: alt_swings[-1] = s
                elif base_type == 'Low' and s[1] < alt_swings[-1][1]: alt_swings[-1] = s
        return alt_swings

    all_swings = find_swings(df, sensitivity)

    # --- WAVE RULES ---
    def find_motive_waves(swings):
        waves = []
        for i in range(len(swings) - 5):
            if 'Low' in swings[i][2]:
                p = swings[i:i+6]
                pr = [x[1] for x in p]
                if pr[2] <= pr[0] or pr[4] <= pr[1] or pr[3] <= pr[1] or pr[5] <= pr[3]: continue
                if (pr[3]-pr[2]) < (pr[1]-pr[0]) and (pr[3]-pr[2]) < (pr[5]-pr[4]): continue
                waves.append(p)
        return waves

    def find_abc_corrections(swings):
        waves = []
        for i in range(len(swings) - 3):
            if 'High' in swings[i][2]: 
                p = swings[i:i+4]
                pr = [x[1] for x in p]
                if pr[1] >= pr[0] or pr[2] <= pr[1] or pr[2] >= pr[0] or pr[3] >= pr[1]: continue
                waves.append(p)
        return waves

    motives = find_motive_waves(all_swings)
    corrections = find_abc_corrections(all_swings)
    
    # Mode Selection
    if wave_type == "Auto-Predict (Last 6 Months)":
        l_mot = motives[-1][-1][3] if motives else pd.Timestamp.min
        l_cor = corrections[-1][-1][3] if corrections else pd.Timestamp.min
        active_mode = "Motive" if l_mot > l_cor else "Correction" if l_cor > l_mot else "None"
        detected_patterns = motives if active_mode == "Motive" else corrections if active_mode == "Correction" else []
    else:
        active_mode = "Motive" if "Motive" in wave_type else "Correction"
        detected_patterns = motives if active_mode == "Motive" else corrections

    # --- PLOTTING ---
    fig = go.Figure()
    
    # Base Candlestick
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price', opacity=0.8))
    
    if not future_df.empty:
        fig.add_trace(go.Candlestick(x=future_df['Date'], open=future_df['Open'], high=future_df['High'], low=future_df['Low'], close=future_df['Close'], increasing_line_color='rgba(128,128,128,0.3)', decreasing_line_color='rgba(128,128,128,0.3)', name='Future (Replay)'))
        
        # 🚀 THE FINAL FIX: Convert date to Milliseconds (Float). Plotly handles float math perfectly without crashing!
        replay_ms = pd.Timestamp(replay_date).timestamp() * 1000
        fig.add_vline(x=replay_ms, line_dash="dash", line_color="white", annotation_text="Replay Present")

    if not detected_patterns:
        st.warning("No patterns found at this sensitivity/date.")
        st.plotly_chart(fig, use_container_width=True)
        return

    last_pattern = detected_patterns[-1]
    labels = ['0', '1', '2', '3', '4', '5'] if active_mode == "Motive" else ['0', 'A', 'B', 'C']
    color = '#2ecc71' if active_mode == "Motive" else '#e74c3c'
    
    w_dates = [p[3] for p in last_pattern]
    w_prices = [p[1] for p in last_pattern]
    
    fig.add_trace(go.Scatter(x=w_dates, y=w_prices, mode='lines+markers', line=dict(color=color, width=4), name='Wave Structure'))
    for i, p in enumerate(last_pattern):
        is_unconfirmed = "Unconfirmed" in p[2]
        border_col = "yellow" if is_unconfirmed else color
        # Also fix the wave labels by using milliseconds just to be 100% safe
        ann_x = pd.Timestamp(p[3]).timestamp() * 1000
        fig.add_annotation(x=ann_x, y=p[1], text=f"<b>{labels[i]}</b>", showarrow=True, ax=0, ay=-25 if 'High' in p[2] else 25, font=dict(color='black' if is_unconfirmed else 'white'), bgcolor=border_col)

    # --- INSTITUTIONAL ANALYSIS & INVALIDATION ---
    st.markdown(f"### 📈 AI Market Bias: {'BULLISH 🟢' if htf_bullish else 'BEARISH 🔴'} (HTF 200-SMA)")
    c1, c2 = st.columns(2)
    
    if active_mode == "Motive":
        invalidation_level = w_prices[1]
        c1.error(f"🚨 **DUMP EXPECTED (TAKE PROFIT)**")
        c2.warning(f"❌ **Invalidation Level:** Rs {invalidation_level:.2f} (Overlap Rule)")
        
        pred_A = w_prices[5] - ((w_prices[5] - w_prices[0]) * 0.382)
        fig.add_hline(y=pred_A, line_dash="dash", line_color="#e74c3c", annotation_text="Target A (38.2% Fib)")
        
    elif active_mode == "Correction":
        invalidation_level = w_prices[0]
        c1.success(f"🟢 **PUMP EXPECTED (BUY SIGNAL)**")
        c2.warning(f"❌ **Invalidation Level:** Rs {invalidation_level:.2f} (Origin Rule)")
        
        diff = w_prices[0] - w_prices[3]
        fib_618 = w_prices[3] + (diff * 0.618)
        fig.add_hline(y=fib_618, line_dash="dash", line_color="#f1c40f", annotation_text="Golden Breakout (0.618)")

    dt_breaks = pd.date_range(start=df_full['Date'].min(), end=df_full['Date'].max()).difference(df_full['Date'])
    fig.update_xaxes(rangebreaks=[dict(values=dt_breaks.strftime('%Y-%m-%d').tolist())], rangeslider_visible=False)
    fig.update_layout(height=650, template="plotly_dark", hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)

# --- MAIN UI ROUTING ---
if not saved_stocks:
    pass
else:
    c_stock, c_sens, c_mode = st.columns([2, 1, 1])
    selected_stock = c_stock.selectbox("Select Stock:", saved_stocks)
    sensitivity = c_sens.number_input("Degree (Sensitivity)", 2, 20, 4)
    wave_type = c_mode.selectbox("Scan Mode:", ["Auto-Predict (Last 6 Months)", "Motive (1-2-3-4-5)", "Correction (A-B-C)"])

    if selected_stock:
        file_data = repo.get_contents(f"Stock_Data/{selected_stock}.csv")
        df_master = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        df_master["Date"] = pd.to_datetime(df_master["Date"])
        df_master = df_master[(df_master['High'] >= df_master['Low']) & (df_master['High'] >= df_master['Close'])].sort_values("Date").reset_index(drop=True)

        if wave_type == "Auto-Predict (Last 6 Months)":
            df_master = df_master[df_master['Date'] >= df_master['Date'].max() - pd.DateOffset(months=6)].reset_index(drop=True)

        tab_live, tab_replay = st.tabs(["🔴 Live Market Scanner", "⏪ Replay & Backtester Mode"])
        
        with tab_live:
            st.info("Analyzing live, real-time data up to the most recent trading day.")
            run_ew_analysis(df_master, df_master['Date'].max().date(), sensitivity, wave_type)
            
        with tab_replay:
            st.markdown("### ⏪ The Time Machine")
            st.caption("Rewind the market to a past date. The AI will make its prediction based ONLY on data up to that date, and actual future candles will appear in grey so you can backtest the prediction!")
            
            min_d = df_master['Date'].min().date()
            max_d = df_master['Date'].max().date()
            
            if min_d >= max_d:
                st.warning("Not enough date range to use the Replay Slider.")
            else:
                default_date = max_d - datetime.timedelta(days=30)
                if default_date < min_d:
                    default_date = min_d
                
                replay_date = st.slider(
                    "Select Replay Date:", 
                    min_value=min_d, 
                    max_value=max_d, 
                    value=default_date,
                    step=datetime.timedelta(days=1),
                    format="YYYY-MM-DD"
                )
                
                run_ew_analysis(df_master, replay_date, sensitivity, wave_type)
