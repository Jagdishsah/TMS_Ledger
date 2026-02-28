import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.markdown("### Upload your Trading Data")
st.caption("Upload files containing OHLCV JSON data (like your `temp_data.txt`).")

# 1. File Uploader
uploaded_file = st.file_uploader("Upload Stock Data (TXT/JSON)", type=["txt", "json"], key="stock_graph_uploader")

if uploaded_file is not None:
    try:
        # 2. Parse the JSON data
        raw_data = json.load(uploaded_file)
        
        # Verify it's the right format
        if raw_data.get("s") == "ok" and "t" in raw_data:
            # 3. Build the Pandas DataFrame
            # 't' is Unix timestamp in seconds
            df = pd.DataFrame({
                "Date": pd.to_datetime(raw_data["t"], unit='s'),
                "Open": raw_data["o"],
                "High": raw_data["h"],
                "Low": raw_data["l"],
                "Close": raw_data["c"],
                "Volume": raw_data["v"]
            })
            
            st.success(f"✅ Data loaded successfully! ({len(df)} data points found)")
            
            # Show a small preview
            with st.expander("View Raw Data"):
                st.dataframe(df.tail(), use_container_width=True)

            # 4. Create an Advanced Plotly Chart
            # We use subplots to put the Candlestick on top and Volume on the bottom
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, subplot_titles=('Price Chart', 'Volume'), 
                                row_width=[0.2, 0.7])

            # Candlestick Trace
            fig.add_trace(go.Candlestick(
                x=df['Date'],
                open=df['Open'], high=df['High'],
                low=df['Low'], close=df['Close'],
                name='Price',
                increasing_line_color='green', decreasing_line_color='red'
            ), row=1, col=1)

            # Volume Bar Trace
            # Color volume bars based on whether it was a green or red day
            colors = ['green' if row['Close'] >= row['Open'] else 'red' for index, row in df.iterrows()]
            fig.add_trace(go.Bar(
                x=df['Date'], y=df['Volume'], 
                name='Volume', marker_color=colors
            ), row=2, col=1)

            # Format the layout
            fig.update_layout(
                height=700,
                xaxis_rangeslider_visible=False, # Hide the default rangeslider for a cleaner look
                template="plotly_white", # Change to "plotly_dark" if you prefer dark mode!
                hovermode="x unified",
                margin=dict(l=20, r=20, t=40, b=20)
            )

            # Render in Streamlit
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.error("Invalid data format. File must contain standard TradingView JSON keys: 's', 't', 'o', 'h', 'l', 'c', 'v'.")
            
    except Exception as e:
        st.error(f"❌ Error processing the file: {e}")
