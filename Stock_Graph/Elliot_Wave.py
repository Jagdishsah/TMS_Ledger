import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from github import Github
import io

st.markdown("### 🌊 Advanced Elliott Wave & Fibonacci Predictor")
st.caption("Detects Motive Waves (1-5), Corrective Waves (A-B-C), and uses Fibonacci ratios to predict future price targets.")

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
    wave_type = c3.selectbox("Scan For:", ["Motive (1-2-3-4-5)", "Correction (A-B-C)"])

    if selected_stock:
        file_data = repo.get_contents(f"Stock_Data/{selected_stock}.csv")
        df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)

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
            """Finds Bullish 5-Wave structures (0-1-2-3-4-5)"""
            valid_waves = []
            for i in range(len(swings) - 5):
                if swings[i][2] == 'Low':
                    p = swings[i:i+6]
                    pr = [x[1] for x in p]
                    
                    # Rule 1: Wave 2 cannot retrace > 100% of Wave 1
                    if pr[2] <= pr[0]: continue
                    # Rule 2: Wave 4 cannot overlap Wave 1
                    if pr[4] <= pr[1]: continue
                    # Structure Check
                    if pr[3] <= pr[1] or pr[5] <= pr[3]: continue
                    # Rule 3: Wave 3 is not shortest
                    w1, w3, w5 = pr[1]-pr[0], pr[3]-pr[2], pr[5]-pr[4]
                    if w3 < w1 and w3 < w5: continue
                        
                    valid_waves.append(p)
            return valid_waves

        def find_abc_corrections(swings):
            """Finds Bearish A-B-C ZigZag Corrections (0-A-B-C)"""
            valid_waves = []
            for i in range(len(swings) - 3):
                if swings[i][2] == 'High': # Starts after a peak
                    p = swings[i:i+4]
                    pr = [x[1] for x in p]
                    
                    # Wave A goes down
                    if pr[1] >= pr[0]: continue
                    # Wave B retraces part of A (but not > 100%)
                    if pr[2] <= pr[1] or pr[2] >= pr[0]: continue
                    # Wave C goes lower than A
                    if pr[3] >= pr[1]: continue
                        
                    valid_waves.append(p)
            return valid_waves

        all_swings = find_swings(df, swing_sensitivity)
        
        if wave_type == "Motive (1-2-3-4-5)":
            detected_patterns = find_motive_waves(all_swings)
            labels = ['0', '1', '2', '3', '4', '5']
            line_color = '#2ecc71'
        else:
            detected_patterns = find_abc_corrections(all_swings)
            labels = ['0', 'A', 'B', 'C']
            line_color = '#e74c3c'

        # --- 4. VISUALIZATION & PREDICTION ---
        st.write("---")
        if not detected_patterns:
            st.warning(f"No valid {wave_type} patterns detected at this sensitivity. Try adjusting the sensitivity.")
        else:
            st.success(f"🎯 Discovered {len(detected_patterns)} valid {wave_type} formations!")
            
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name='Price', increasing_line_color='#26a69a', decreasing_line_color='#ef5350', opacity=0.4
            ))

            last_pattern = detected_patterns[-1] # Focus prediction on the most recent pattern

            # Plot Patterns
            for index, wave in enumerate(detected_patterns):
                w_dates, w_prices = [p[3] for p in wave], [p[1] for p in wave]
                fig.add_trace(go.Scatter(x=w_dates, y=w_prices, mode='lines+markers', line=dict(color=line_color, width=3), name=f'Pattern {index+1}'))
                
                for i, p in enumerate(wave):
                    fig.add_annotation(
                        x=p[3], y=p[1], text=f"<b>{labels[i]}</b>",
                        showarrow=True, arrowhead=2, ax=0, ay=-25 if p[2]=='High' else 25,
                        font=dict(size=12, color='white'), bgcolor=line_color
                    )

            # --- FIBONACCI PREDICTION ENGINE ---
            if wave_type == "Motive (1-2-3-4-5)" and len(last_pattern) == 6:
                # Predict the incoming A-B-C correction based on the completed 5-wave
                st.markdown("### 🔮 AI Target Predictor (Pending A-B-C Correction)")
                p0, p1, p2, p3, p4, p5 = [x[1] for x in last_pattern]
                
                # Target A: Usually retraces 38.2% of the entire 0-5 impulse
                total_motive_length = p5 - p0
                pred_A = p5 - (total_motive_length * 0.382)
                
                # Target B: Usually retraces 50% to 61.8% of Wave A
                wave_A_length = p5 - pred_A
                pred_B_low = pred_A + (wave_A_length * 0.50)
                pred_B_high = pred_A + (wave_A_length * 0.618)
                
                # Target C: Usually 100% of Wave A, projected from Wave B
                pred_C = pred_B_high - wave_A_length

                # Draw Prediction Zones on Chart
                future_date_A = df['Date'].iloc[-1] + pd.Timedelta(days=10)
                future_date_C = df['Date'].iloc[-1] + pd.Timedelta(days=20)
                
                fig.add_shape(type="rect", x0=last_pattern[-1][3], y0=pred_A*0.99, x1=future_date_A, y1=pred_A*1.01, fillcolor="rgba(231, 76, 60, 0.3)", line=dict(width=0))
                fig.add_annotation(x=future_date_A, y=pred_A, text="<b>Predicted Target A (38.2% Fib)</b>", showarrow=False, font=dict(color="#e74c3c"))

                fig.add_shape(type="rect", x0=future_date_A, y0=pred_C*0.98, x1=future_date_C, y1=pred_C*1.02, fillcolor="rgba(155, 89, 182, 0.3)", line=dict(width=0))
                fig.add_annotation(x=future_date_C, y=pred_C, text="<b>Predicted Target C (100% Ext)</b>", showarrow=False, font=dict(color="#9b59b6"))
                
                c_pa, c_pb, c_pc = st.columns(3)
                c_pa.metric("Predicted Wave A Bottom", f"Rs {pred_A:.2f}")
                c_pb.metric("Predicted Wave B Bounce", f"Rs {pred_B_low:.2f} - {pred_B_high:.2f}")
                c_pc.metric("Predicted Wave C Bottom", f"Rs {pred_C:.2f}")

            # Formatting
            dt_breaks = pd.date_range(start=df['Date'].min(), end=df['Date'].max()).difference(df['Date'])
            fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], rangeslider_visible=False)
            fig.update_layout(height=750, template="plotly_dark", hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
