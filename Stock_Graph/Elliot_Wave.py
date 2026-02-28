import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from github import Github
import io

st.markdown("### 🌊 AI Elliott Wave Auto-Predictor (Live Tracking)")
st.caption("Scans for completed market cycles AND tracks developing, unconfirmed waves in real-time.")

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
    swing_sensitivity = c2.number_input("Swing Sensitivity (Days)", min_value=2, max_value=20, value=4, help="Lower to 3 or 4 to catch early developing waves!")
    wave_type = c3.selectbox("Scan Mode:", ["Auto-Predict (Last 6 Months)", "Motive (1-2-3-4-5)", "Correction (A-B-C)"])

    if selected_stock:
        file_data = repo.get_contents(f"Stock_Data/{selected_stock}.csv")
        df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)

        # 🚀 DATA LIMITER
        if wave_type == "Auto-Predict (Last 6 Months)":
            six_months_ago = df['Date'].max() - pd.DateOffset(months=6)
            df = df[df['Date'] >= six_months_ago].reset_index(drop=True)
        elif len(df) > 500:
            df = df.tail(500).reset_index(drop=True)

        # --- 2. LIVE SWING DETECTION ALGORITHM ---
        def find_swings(data, order):
            highs, lows = [], []
            # Standard swing detection
            for i in range(order, len(data) - order):
                if data['High'].iloc[i] == max(data['High'].iloc[i-order:i+order+1]):
                    highs.append((i, data['High'].iloc[i], 'High', data['Date'].iloc[i]))
                if data['Low'].iloc[i] == min(data['Low'].iloc[i-order:i+order+1]):
                    lows.append((i, data['Low'].iloc[i], 'Low', data['Date'].iloc[i]))
            
            # 🔥 LIVE EDGE DETECTION: Catch the absolute current price if it's breaking out!
            last_idx = len(data) - 1
            if data['High'].iloc[last_idx] >= max(data['High'].iloc[-order:]):
                highs.append((last_idx, data['High'].iloc[last_idx], 'High', data['Date'].iloc[last_idx]))
            if data['Low'].iloc[last_idx] <= min(data['Low'].iloc[-order:]):
                lows.append((last_idx, data['Low'].iloc[last_idx], 'Low', data['Date'].iloc[last_idx]))

            swings = sorted(highs + lows, key=lambda x: x[0])
            
            # Filter alternating swings
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
                    if pr[2] <= pr[0] or pr[4] <= pr[1]: continue
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
                    if pr[1] >= pr[0] or pr[2] <= pr[1] or pr[2] >= pr[0] or pr[3] >= pr[1]: continue
                    valid_waves.append(p)
            return valid_waves

        all_swings = find_swings(df, swing_sensitivity)
        motives = find_motive_waves(all_swings)
        corrections = find_abc_corrections(all_swings)

        # Determine Active Mode
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
                detected_patterns, active_mode = [], "None"
        elif wave_type == "Motive (1-2-3-4-5)":
            active_mode, detected_patterns = "Motive", motives
        else:
            active_mode, detected_patterns = "Correction", corrections

        # --- 4. VISUALIZATION & LIVE TRACKING ---
        st.write("---")
        if not detected_patterns:
            st.warning("No completed structures found. Try lowering Swing Sensitivity to 3 or 4 to catch micro-waves.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name='Price', increasing_line_color='#26a69a', decreasing_line_color='#ef5350', opacity=0.4
            ))

            last_pattern = detected_patterns[-1]
            labels = ['0', '1', '2', '3', '4', '5'] if active_mode == "Motive" else ['0', 'A', 'B', 'C']
            line_color = '#2ecc71' if active_mode == "Motive" else '#e74c3c'

            # Plot Completed Pattern
            w_dates, w_prices = [p[3] for p in last_pattern], [p[1] for p in last_pattern]
            fig.add_trace(go.Scatter(x=w_dates, y=w_prices, mode='lines+markers', line=dict(color=line_color, width=4), name='Completed Pattern'))
            
            for i, p in enumerate(last_pattern):
                fig.add_annotation(
                    x=p[3], y=p[1], text=f"<b>{labels[i]}</b>", showarrow=True, arrowhead=2, ax=0, ay=-25 if p[2]=='High' else 25,
                    font=dict(size=14, color='white'), bgcolor=line_color
                )

            current_price = df['Close'].iloc[-1]
            current_date = df['Date'].iloc[-1]
            pattern_end_date = w_dates[-1]
            pattern_end_price = w_prices[-1]

            # 🔥 LIVE DEVELOPING WAVE TRACKER 🔥
            st.markdown("### 🤖 Trading Desk AI Recommendation")
            
            if active_mode == "Correction":
                # Check if price has started breaking out AFTER the C wave
                if current_date > pattern_end_date and current_price > pattern_end_price:
                    st.success("🟢 **SIGNAL: NEW BULLISH WAVE DETECTED! (ENTER / BUY)**")
                    st.markdown(f"**Live Analysis:** The A-B-C dump finished at Rs {pattern_end_price}. The algorithm detects that a **NEW Developing Wave (Likely Wave 1 or 3)** has already begun, pushing price up to Rs {current_price:.2f}.")
                    
                    # Draw a dashed line tracking the live breakout
                    fig.add_trace(go.Scatter(
                        x=[pattern_end_date, current_date], y=[pattern_end_price, current_price],
                        mode='lines+markers', line=dict(color='#f1c40f', width=3, dash='dash'), name='Live Developing Wave'
                    ))
                    fig.add_annotation(x=current_date, y=current_price, text="<b>Live Wave</b>", showarrow=True, arrowhead=2, font=dict(color="black"), bgcolor="#f1c40f")

                    # Fibonacci Targets for the new wave
                    correction_drop = w_prices[0] - pattern_end_price
                    pred_W3 = pattern_end_price + (correction_drop * 1.618)
                    st.metric("Macro Bull Target (Wave 3 Projection)", f"Rs {pred_W3:.2f}")

                else:
                    st.info("⏳ **SIGNAL: ACCUMULATE (WAIT FOR BREAKOUT)**")
                    st.markdown("**Live Analysis:** The A-B-C dump is complete. We are currently consolidating at the bottom. Prepare for a new Wave 1 breakout.")
            
            elif active_mode == "Motive":
                if current_date > pattern_end_date and current_price < pattern_end_price:
                    st.error("🚨 **SIGNAL: DUMP IN PROGRESS (EXIT)**")
                    st.markdown(f"**Live Analysis:** The 5-Wave Pump finished at Rs {pattern_end_price}. The algorithm detects that the **A-B-C Dump has already started**, bringing price down to Rs {current_price:.2f}.")
                    
                    # Draw dashed line tracking the live dump
                    fig.add_trace(go.Scatter(
                        x=[pattern_end_date, current_date], y=[pattern_end_price, current_price],
                        mode='lines+markers', line=dict(color='#e67e22', width=3, dash='dash'), name='Live Developing Dump'
                    ))
                    fig.add_annotation(x=current_date, y=current_price, text="<b>Live Dump</b>", showarrow=True, arrowhead=2, font=dict(color="white"), bgcolor="#e67e22")

                else:
                    st.warning("⚠️ **SIGNAL: TOP REACHED (TAKE PROFIT)**")
                    st.markdown("**Live Analysis:** Wave 5 just completed. A major correction is imminent.")

            # Formatting
            dt_breaks = pd.date_range(start=df['Date'].min(), end=df['Date'].max()).difference(df['Date'])
            fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], rangeslider_visible=False)
            fig.update_layout(height=650, template="plotly_dark", hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
