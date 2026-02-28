import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from github import Github
import io

st.markdown("### 🌊 AI Elliott Wave Auto-Predictor")
st.caption("Scans the market structure, finds the most recent completed wave, and generates Buy/Sell signals based on Fibonacci projections.")

# --- 1. GITHUB FETCHING ---
def fetch_saved_stocks():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"])
        contents = repo.get_contents("Stock_Data")
        return [f.name.replace(".csv", "") for f in contents if f.name.endswith(".csv")], repo
    except Exception:
        return [], None

saved_stocks, repo = fetch_saved_stocks()

if not saved_stocks:
    st.warning("No stock data found in Cloud. Please go to the 'Stock Graph' tab and save data first!")
else:
    c1, c2, c3 = st.columns([2, 1, 1])
    selected_stock = c1.selectbox("Select Stock to Analyze:", saved_stocks)
    swing_sensitivity = c2.number_input("Swing Sensitivity (Days)", min_value=3, max_value=20, value=5)
    wave_type = c3.selectbox("Scan Mode:", ["Auto-Predict (Last 6 Months)", "Motive (1-2-3-4-5)", "Correction (A-B-C)"])

    if selected_stock:
        file_data = repo.get_contents(f"Stock_Data/{selected_stock}.csv")
        df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)

        # 🚀 DATA LIMITER (For Performance & Recent Relevance)
        if wave_type == "Auto-Predict (Last 6 Months)":
            six_months_ago = df['Date'].max() - pd.DateOffset(months=6)
            df = df[df['Date'] >= six_months_ago].reset_index(drop=True)
            st.info("⚡ Auto-Predict active: Fast scanning the last 6 months to determine the current market cycle.")
        elif len(df) > 500:
            df = df.tail(500).reset_index(drop=True)

        # --- 2. SWING DETECTION ALGORITHM ---
        def find_swings(data, order):
            highs, lows = [], []
            for i in range(order, len(data) - order):
                if data['High'].iloc[i] == max(data['High'].iloc[i-order:i+order+1]):
                    highs.append((i, data['High'].iloc[i], 'High', data['Date'].iloc[i]))
                if data['Low'].iloc[i] == min(data['Low'].iloc[i-order:i+order+1]):
                    lows.append((i, data['Low'].iloc[i], 'Low', data['Date'].iloc[i]))
            
            swings = sorted(highs + lows, key=lambda x: x[0])
            alternating_swings = []
            for swing in swings:
                if not alternating_swings:
                    alternating_swings.append(swing)
                else:
                    if swing[2] != alternating_swings[-1][2]:
                        alternating_swings.append(swing)
                    else:
                        if swing[2] == 'High' and swing[1] > alternating_swings[-1][1]:
                            alternating_swings[-1] = swing
                        elif swing[2] == 'Low' and swing[1] < alternating_swings[-1][1]:
                            alternating_swings[-1] = swing
            return alternating_swings

        # --- 3. WAVE ALGORITHMS ---
        def find_motive_waves(swings):
            valid_waves = []
            for i in range(len(swings) - 5):
                if swings[i][2] == 'Low':
                    p = swings[i:i+6]
                    pr = [x[1] for x in p]
                    if pr[2] <= pr[0]: continue
                    if pr[4] <= pr[1]: continue
                    if pr[3] <= pr[1] or pr[5] <= pr[3]: continue
                    w1, w3, w5 = pr[1]-pr[0], pr[3]-pr[2], pr[5]-pr[4]
                    if w3 < w1 and w3 < w5: continue
                    valid_waves.append(p)
            return valid_waves

        def find_abc_corrections(swings):
            valid_waves = []
            for i in range(len(swings) - 3):
                if swings[i][2] == 'High': 
                    p = swings[i:i+4]
                    pr = [x[1] for x in p]
                    if pr[1] >= pr[0]: continue
                    if pr[2] <= pr[1] or pr[2] >= pr[0]: continue
                    if pr[3] >= pr[1]: continue
                    valid_waves.append(p)
            return valid_waves

        all_swings = find_swings(df, swing_sensitivity)
        
        motives = find_motive_waves(all_swings)
        corrections = find_abc_corrections(all_swings)

        # DETERMINE ACTIVE MODE
        if wave_type == "Auto-Predict (Last 6 Months)":
            last_motive_date = motives[-1][-1][3] if motives else pd.Timestamp.min
            last_corr_date = corrections[-1][-1][3] if corrections else pd.Timestamp.min
            
            if last_motive_date > last_corr_date:
                active_mode = "Motive"
                detected_patterns = motives
            elif last_corr_date > last_motive_date:
                active_mode = "Correction"
                detected_patterns = corrections
            else:
                detected_patterns = []
                active_mode = "None"
        elif wave_type == "Motive (1-2-3-4-5)":
            active_mode = "Motive"
            detected_patterns = motives
        else:
            active_mode = "Correction"
            detected_patterns = corrections

        # --- 4. VISUALIZATION & PREDICTION ---
        st.write("---")
        if not detected_patterns:
            st.warning("No valid structures found in this timeframe. Market is likely consolidating or sensitivity needs adjustment.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name='Price', increasing_line_color='#26a69a', decreasing_line_color='#ef5350', opacity=0.4
            ))

            last_pattern = detected_patterns[-1]
            
            if active_mode == "Motive":
                labels = ['0', '1', '2', '3', '4', '5']
                line_color = '#2ecc71'
            else:
                labels = ['0', 'A', 'B', 'C']
                line_color = '#e74c3c'

            # Plot Pattern
            w_dates, w_prices = [p[3] for p in last_pattern], [p[1] for p in last_pattern]
            fig.add_trace(go.Scatter(x=w_dates, y=w_prices, mode='lines+markers', line=dict(color=line_color, width=4), name='Recent Pattern'))
            
            for i, p in enumerate(last_pattern):
                fig.add_annotation(
                    x=p[3], y=p[1], text=f"<b>{labels[i]}</b>",
                    showarrow=True, arrowhead=2, ax=0, ay=-25 if p[2]=='High' else 25,
                    font=dict(size=14, color='white'), bgcolor=line_color
                )

            current_price = df['Close'].iloc[-1]
            
            # --- AI TRADING DESK (THE PREDICTOR) ---
            st.markdown("### 🤖 Trading Desk AI Recommendation")
            
            if active_mode == "Motive":
                st.error("🚨 **SIGNAL: EXIT / TAKE PROFIT**")
                st.markdown(f"**Analysis:** The AI detected a completed 5-Wave Bullish Impulse ending at Rs {last_pattern[-1][1]}. According to Elliott Wave theory, an A-B-C bearish correction is mathematically imminent.")
                
                # Predict A-B-C Dump
                p0, p5 = last_pattern[0][1], last_pattern[-1][1]
                pred_A = p5 - ((p5 - p0) * 0.382)
                
                fig.add_shape(type="rect", x0=w_dates[-1], y0=pred_A*0.98, x1=df['Date'].iloc[-1] + pd.Timedelta(days=15), y1=pred_A*1.02, fillcolor="rgba(231, 76, 60, 0.2)", line=dict(width=0))
                fig.add_annotation(x=df['Date'].iloc[-1] + pd.Timedelta(days=7), y=pred_A, text="<b>Expected Dump Target (Wave A)</b>", font=dict(color="#e74c3c"))
                st.metric("Expected Drawdown (Wave A Target)", f"Rs {pred_A:.2f}")

            elif active_mode == "Correction":
                st.success("🟢 **SIGNAL: ENTER / BUY**")
                st.markdown(f"**Analysis:** The AI detected a completed A-B-C Bearish Correction bottoming out at Rs {last_pattern[-1][1]}. The weak hands have been shaken out. A new 1-2-3-4-5 Bullish Impulse is mathematically primed to begin.")
                
                # Predict New Wave 1 and Wave 3 Targets
                p0, pC = last_pattern[0][1], last_pattern[-1][1]
                correction_drop = p0 - pC
                pred_W1 = pC + (correction_drop * 0.618)  # Standard Wave 1 retracement of ABC
                pred_W3 = pC + (correction_drop * 1.618)  # Standard Wave 3 extension
                
                fig.add_shape(type="rect", x0=w_dates[-1], y0=pred_W1*0.98, x1=df['Date'].iloc[-1] + pd.Timedelta(days=15), y1=pred_W1*1.02, fillcolor="rgba(46, 204, 113, 0.2)", line=dict(width=0))
                fig.add_annotation(x=df['Date'].iloc[-1] + pd.Timedelta(days=7), y=pred_W1, text="<b>Expected Initial Pump (Wave 1)</b>", font=dict(color="#2ecc71"))
                
                c_buy1, c_buy2 = st.columns(2)
                c_buy1.metric("Short-Term Target (Wave 1)", f"Rs {pred_W1:.2f}")
                c_buy2.metric("Macro Bull Target (Wave 3)", f"Rs {pred_W3:.2f}")

            # Formatting
            dt_breaks = pd.date_range(start=df['Date'].min(), end=df['Date'].max()).difference(df['Date'])
            fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], rangeslider_visible=False)
            fig.update_layout(height=650, template="plotly_dark", hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
