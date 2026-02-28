import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from github import Github
import io

st.markdown("### 🌊 AI Elliott Wave Auto-Predictor (Pro Edition)")
st.caption("Features: Live Tracking, Volume Confirmation, Rule of Alternation, & Dynamic Fib Zones.")

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
    swing_sensitivity = c2.number_input("Swing Sensitivity (Days)", min_value=2, max_value=20, value=4)
    wave_type = c3.selectbox("Scan Mode:", ["Auto-Predict (Last 6 Months)", "Motive (1-2-3-4-5)", "Correction (A-B-C)"])

    if selected_stock:
        file_data = repo.get_contents(f"Stock_Data/{selected_stock}.csv")
        df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        
        # Ensure Volume column exists for Whale Check
        if 'Volume' not in df.columns and 'volume' in df.columns:
            df['Volume'] = df['volume']
        elif 'Volume' not in df.columns:
            df['Volume'] = 1 # Fallback if missing

        if wave_type == "Auto-Predict (Last 6 Months)":
            six_months_ago = df['Date'].max() - pd.DateOffset(months=6)
            df = df[df['Date'] >= six_months_ago].reset_index(drop=True)
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
            
            last_idx = len(data) - 1
            if data['High'].iloc[last_idx] >= max(data['High'].iloc[-order:]):
                highs.append((last_idx, data['High'].iloc[last_idx], 'High', data['Date'].iloc[last_idx]))
            if data['Low'].iloc[last_idx] <= min(data['Low'].iloc[-order:]):
                lows.append((last_idx, data['Low'].iloc[last_idx], 'Low', data['Date'].iloc[last_idx]))

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

        if wave_type == "Auto-Predict (Last 6 Months)":
            last_motive_date = motives[-1][-1][3] if motives else pd.Timestamp.min
            last_corr_date = corrections[-1][-1][3] if corrections else pd.Timestamp.min
            active_mode = "Motive" if last_motive_date > last_corr_date else "Correction" if last_corr_date > last_motive_date else "None"
            detected_patterns = motives if active_mode == "Motive" else corrections if active_mode == "Correction" else []
        elif wave_type == "Motive (1-2-3-4-5)":
            active_mode, detected_patterns = "Motive", motives
        else:
            active_mode, detected_patterns = "Correction", corrections

        # --- 4. VISUALIZATION & AI ANALYSIS ---
        st.write("---")
        if not detected_patterns:
            st.warning("No completed structures found. Try lowering Swing Sensitivity.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price', opacity=0.4))

            last_pattern = detected_patterns[-1]
            labels = ['0', '1', '2', '3', '4', '5'] if active_mode == "Motive" else ['0', 'A', 'B', 'C']
            line_color = '#2ecc71' if active_mode == "Motive" else '#e74c3c'

            w_dates, w_prices = [p[3] for p in last_pattern], [p[1] for p in last_pattern]
            fig.add_trace(go.Scatter(x=w_dates, y=w_prices, mode='lines+markers', line=dict(color=line_color, width=4), name='Completed Pattern'))
            
            for i, p in enumerate(last_pattern):
                fig.add_annotation(x=p[3], y=p[1], text=f"<b>{labels[i]}</b>", showarrow=True, ax=0, ay=-25 if p[2]=='High' else 25, font=dict(color='white'), bgcolor=line_color)

            current_price, current_date = df['Close'].iloc[-1], df['Date'].iloc[-1]
            pattern_end_date, pattern_end_price = w_dates[-1], w_prices[-1]

            st.markdown("### 🤖 Advanced Trading Desk Analysis")
            confidence_score = 100
            analysis_notes = []

            # 🛠️ A. RULE OF ALTERNATION (For Motives)
            if active_mode == "Motive":
                w2_time = last_pattern[2][0] - last_pattern[1][0]
                w4_time = last_pattern[4][0] - last_pattern[3][0]
                w2_depth = (last_pattern[1][1] - last_pattern[2][1]) / (last_pattern[1][1] - last_pattern[0][1])
                w4_depth = (last_pattern[3][1] - last_pattern[4][1]) / (last_pattern[3][1] - last_pattern[2][1])
                
                if abs(w2_time - w4_time) <= 2 and abs(w2_depth - w4_depth) < 0.2:
                    confidence_score -= 20
                    analysis_notes.append("⚠️ **Rule of Alternation Failed:** Wave 2 and Wave 4 look too similar in time and depth. This lowers the probability of a true 5-wave impulse.")
                else:
                    analysis_notes.append("✅ **Rule of Alternation Passed:** Wave 2 and Wave 4 show distinct behaviors (sharp vs sideways).")

            # 🐋 B. VOLUME CONFIRMATION
            if active_mode == "Motive" and df['Volume'].sum() > len(df): # basic check if volume isn't just 1s
                vol_w1 = df['Volume'].iloc[last_pattern[0][0]:last_pattern[1][0]].mean()
                vol_w3 = df['Volume'].iloc[last_pattern[2][0]:last_pattern[3][0]].mean()
                
                if vol_w3 < vol_w1:
                    confidence_score -= 30
                    analysis_notes.append(f"🐋 **Whale Check Failed:** Wave 3 Volume ({vol_w3:,.0f}) is lower than Wave 1 ({vol_w1:,.0f}). Warning: Weak impulse, potential fakeout.")
                else:
                    analysis_notes.append("✅ **Whale Check Passed:** Wave 3 shows strong volume confirmation.")

            # 📏 C. FIBONACCI RETRACEMENT OVERLAYS & PREDICTIONS
            if active_mode == "Correction":
                if current_date > pattern_end_date and current_price > pattern_end_price:
                    # Draw Fib lines from top of 0 to bottom of C
                    fib_0 = w_prices[0]
                    fib_100 = pattern_end_price
                    diff = fib_0 - fib_100
                    
                    fib_618 = fib_100 + (diff * 0.618)
                    fib_382 = fib_100 + (diff * 0.382)
                    
                    fig.add_hline(y=fib_618, line_dash="dot", line_color="#f39c12", annotation_text="Fib 0.618 Golden Ratio")
                    fig.add_hline(y=fib_382, line_dash="dot", line_color="#3498db", annotation_text="Fib 0.382 Retracement")
                    
                    fig.add_trace(go.Scatter(x=[pattern_end_date, current_date], y=[pattern_end_price, current_price], mode='lines+markers', line=dict(color='#f1c40f', width=3, dash='dash'), name='Live Wave'))

                    if current_price >= fib_618:
                        confidence_score += 20
                        st.success(f"🟢 **STRONG BUY: Golden Pocket Bounced!** (Confidence: {min(confidence_score, 100)}%)")
                        analysis_notes.append("🎯 **Fib Confluence:** Price has decisively broken above the 0.618 Fibonacci retracement of the A-B-C drop. Massive bullish confirmation.")
                    else:
                        st.info(f"🟡 **EARLY ENTRY SIGNAL.** (Confidence: {confidence_score}%)")
                        analysis_notes.append("⏳ Price is moving up but hasn't broken the 0.618 Golden Ratio resistance yet.")
                else:
                    st.info("Accumulate: Market consolidating at bottom.")
            
            elif active_mode == "Motive":
                st.error(f"🚨 **SIGNAL: DUMP IN PROGRESS / TAKE PROFIT** (Confidence: {confidence_score}%)")
                if current_date > pattern_end_date:
                    fig.add_trace(go.Scatter(x=[pattern_end_date, current_date], y=[pattern_end_price, current_price], mode='lines+markers', line=dict(color='#e67e22', width=3, dash='dash'), name='Live Dump'))

            for note in analysis_notes:
                st.markdown(note)

            # Formatting
            dt_breaks = pd.date_range(start=df['Date'].min(), end=df['Date'].max()).difference(df['Date'])
            fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], rangeslider_visible=False)
            fig.update_layout(height=650, template="plotly_dark", hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
