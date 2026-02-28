import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from github import Github
import io

st.markdown("### 🔍 Institutional Elliott Wave Scanner")
st.caption("This algorithmic scanner calculates local extrema (Swings) and filters them through R.N. Elliott's 3 absolute mathematical rules to find valid Motive (Impulse) 5-Wave structures.")

# --- 1. GITHUB FETCHING ---
@st.cache_data(ttl=60)
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
    c1, c2 = st.columns([2, 1])
    selected_stock = c1.selectbox("Select Stock to Analyze:", saved_stocks)
    
    # Sensitivity controls how big a "swing" has to be to be considered a wave point.
    swing_sensitivity = c2.number_input("Swing Sensitivity (Days)", min_value=3, max_value=20, value=5, help="Higher numbers find macro trends. Lower numbers find micro day-trading waves.")

    if selected_stock:
        # Load Data
        file_data = repo.get_contents(f"Stock_Data/{selected_stock}.csv")
        df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)

        # --- 2. THE SWING DETECTION ALGORITHM ---
        def find_swings(data, order):
            """Finds local tops and bottoms to act as potential wave points."""
            highs, lows = [], []
            for i in range(order, len(data) - order):
                if data['High'].iloc[i] == max(data['High'].iloc[i-order:i+order+1]):
                    highs.append((i, data['High'].iloc[i], 'High', data['Date'].iloc[i]))
                if data['Low'].iloc[i] == min(data['Low'].iloc[i-order:i+order+1]):
                    lows.append((i, data['Low'].iloc[i], 'Low', data['Date'].iloc[i]))
            
            # Combine and sort by date index
            swings = sorted(highs + lows, key=lambda x: x[0])
            
            # Force alternating highs and lows (remove consecutive highs/lows)
            alternating_swings = []
            for swing in swings:
                if not alternating_swings:
                    alternating_swings.append(swing)
                else:
                    if swing[2] != alternating_swings[-1][2]:
                        alternating_swings.append(swing)
                    else:
                        # Keep the more extreme point if two of the same type appear sequentially
                        if swing[2] == 'High' and swing[1] > alternating_swings[-1][1]:
                            alternating_swings[-1] = swing
                        elif swing[2] == 'Low' and swing[1] < alternating_swings[-1][1]:
                            alternating_swings[-1] = swing
            return alternating_swings

        # --- 3. THE ELLIOTT WAVE RULES ALGORITHM ---
        def find_elliott_motive_waves(swings):
            """Scans sequence of 6 points (0,1,2,3,4,5) against absolute EW Rules."""
            valid_waves = []
            
            # We need at least 6 points for a full 5-wave impulse (Start + 5 ends)
            for i in range(len(swings) - 5):
                # We are looking for a Bullish Impulse (Starts with a Low)
                if swings[i][2] == 'Low':
                    p0 = swings[i]   # Start
                    p1 = swings[i+1] # Wave 1 Peak
                    p2 = swings[i+2] # Wave 2 Trough
                    p3 = swings[i+3] # Wave 3 Peak
                    p4 = swings[i+4] # Wave 4 Trough
                    p5 = swings[i+5] # Wave 5 Peak
                    
                    pr0, pr1, pr2, pr3, pr4, pr5 = p0[1], p1[1], p2[1], p3[1], p4[1], p5[1]
                    
                    # RULE 1: Wave 2 cannot retrace > 100% of Wave 1
                    if pr2 <= pr0: continue
                        
                    # RULE 2: Wave 4 cannot overlap the territory of Wave 1
                    if pr4 <= pr1: continue
                        
                    # Structure Check: Wave 3 must pass Wave 1, Wave 5 must pass Wave 3
                    if pr3 <= pr1 or pr5 <= pr3: continue
                        
                    # RULE 3: Wave 3 cannot be the shortest motive wave
                    w1_len = pr1 - pr0
                    w3_len = pr3 - pr2
                    w5_len = pr5 - pr4
                    if w3_len < w1_len and w3_len < w5_len: continue
                        
                    # If it passes all strict rules, save it!
                    valid_waves.append((p0, p1, p2, p3, p4, p5))
                    
            return valid_waves

        # Execute Algorithms
        all_swings = find_swings(df, swing_sensitivity)
        ew_patterns = find_elliott_motive_waves(all_swings)

        # --- 4. VISUALIZATION ---
        st.write("---")
        if not ew_patterns:
            st.error("No valid Elliott Wave patterns detected at this sensitivity. Try adjusting the 'Swing Sensitivity' parameter.")
        else:
            st.success(f"🎯 Discovered {len(ew_patterns)} mathematically perfect Elliott Wave formations!")
            
            fig = go.Figure()

            # Base Candlestick Chart
            fig.add_trace(go.Candlestick(
                x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name='Price', increasing_line_color='#26a69a', decreasing_line_color='#ef5350', opacity=0.5
            ))

            # Plot the Swings (Background ZigZag)
            swing_dates = [s[3] for s in all_swings]
            swing_prices = [s[1] for s in all_swings]
            fig.add_trace(go.Scatter(
                x=swing_dates, y=swing_prices, mode='lines', 
                line=dict(color='rgba(255, 255, 255, 0.2)', width=1, dash='dot'), 
                name='Detected Swings', hoverinfo='skip'
            ))

            # Highlight Valid Elliott Waves
            colors = ['#f1c40f', '#e67e22', '#3498db', '#9b59b6', '#2ecc71'] # Cycle colors for multiple waves
            
            for index, wave in enumerate(ew_patterns):
                color = colors[index % len(colors)]
                w_dates = [p[3] for p in wave]
                w_prices = [p[1] for p in wave]
                
                # Draw the thick Wave Line
                fig.add_trace(go.Scatter(
                    x=w_dates, y=w_prices, mode='lines+markers',
                    line=dict(color=color, width=3),
                    marker=dict(size=8, color=color, symbol='circle'),
                    name=f'EW Impulse {index+1}'
                ))
                
                # Add Labels (0, 1, 2, 3, 4, 5)
                labels = ['0', '1', '2', '3', '4', '5']
                for i, p in enumerate(wave):
                    fig.add_annotation(
                        x=p[3], y=p[1],
                        text=f"<b>{labels[i]}</b>",
                        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
                        arrowcolor=color, ax=0, ay=-30 if p[2]=='High' else 30,
                        font=dict(size=14, color='white'),
                        bgcolor=color, bordercolor="white", borderwidth=1, borderpad=2
                    )

            # Format Layout without Weekend Gaps
            dt_breaks = pd.date_range(start=df['Date'].min(), end=df['Date'].max()).difference(df['Date'])
            fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], rangeslider_visible=False)
            fig.update_layout(
                height=700, template="plotly_dark", title=f"Elliott Wave Analysis: {selected_stock}",
                hovermode="x unified", margin=dict(l=10, r=10, t=40, b=10)
            )

            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("📖 Read AI Rule Verification Report"):
                st.write("The algorithm confirmed the following rules for the most recent wave:")
                last_wave = ew_patterns[-1]
                st.markdown(f"- **Rule 1 Passed:** Wave 2 low (Rs {last_wave[2][1]}) never broke below Wave 0 start (Rs {last_wave[0][1]}).")
                st.markdown(f"- **Rule 2 Passed:** Wave 4 low (Rs {last_wave[4][1]}) never overlapped Wave 1 peak (Rs {last_wave[1][1]}).")
                
                w1_len = last_wave[1][1] - last_wave[0][1]
                w3_len = last_wave[3][1] - last_wave[2][1]
                st.markdown(f"- **Rule 3 Passed:** Wave 3 traveled Rs {w3_len:.2f}, validating it is not the shortest wave (Wave 1 traveled Rs {w1_len:.2f}).")
