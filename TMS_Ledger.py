import streamlit as st
import pandas as pd
from github import Github, Auth
from io import StringIO
import plotly.express as px
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="TMS Ledger Pro", page_icon="📒", layout="wide")

# --- GITHUB ENGINE (Reused) ---
def get_repo():
    try:
        # Uses the same secrets as your main app
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        auth = Auth.Token(token)
        g = Github(auth=auth)
        return g.get_repo(repo_name)
    except:
        return None

def get_data():
    repo = get_repo()
    if not repo: return pd.DataFrame()
    try:
        file = repo.get_contents("tms_ledger.csv")
        return pd.read_csv(StringIO(file.decoded_content.decode()))
    except:
        return pd.DataFrame(columns=["Date", "Type", "Direction", "Amount", "Balance", "Description", "Ref_ID"])

def save_data(df):
    repo = get_repo()
    if not repo: return
    csv_content = df.to_csv(index=False)
    try:
        file = repo.get_contents("tms_ledger.csv")
        repo.update_file(file.path, "Update Ledger", csv_content, file.sha)
    except:
        repo.create_file("tms_ledger.csv", "Create Ledger", csv_content)

# --- APP LOGIC ---
st.title("📒 TMS Money Manager")
st.caption("Track Cash Flow, Collateral, and Settlements")

# 1. SIDEBAR: ADD TRANSACTION
with st.sidebar:
    st.header("💸 New Transaction")
    
    with st.form("entry_form"):
        date = st.date_input("Date")
        txn_type = st.selectbox("Transaction Type", 
            ["Load Collateral (Deposit)", "Request Refund (Withdraw)", "Buy Settlement (Payment)", "Sell Settlement (Receipt)"])
        
        amount = st.number_input("Amount (Rs)", min_value=1.0, step=100.0)
        desc = st.text_input("Description (e.g., ConnectIPS Ref, Script Name)")
        
        if st.form_submit_button("Record Transaction"):
            df = get_data()
            
            # Logic for Direction (Credit/Debit relative to BROKER BALANCE)
            direction = ""
            if txn_type == "Load Collateral (Deposit)": direction = "CREDIT" # Balance Goes UP
            elif txn_type == "Request Refund (Withdraw)": direction = "DEBIT" # Balance Goes DOWN
            elif txn_type == "Buy Settlement (Payment)": direction = "DEBIT" # Balance Goes DOWN
            elif txn_type == "Sell Settlement (Receipt)": direction = "CREDIT" # Balance Goes UP
            
            # Logic for Running Balance
            prev_bal = df.iloc[-1]["Balance"] if not df.empty else 0.0
            new_bal = prev_bal + amount if direction == "CREDIT" else prev_bal - amount
            
            new_row = pd.DataFrame([{
                "Date": date,
                "Type": txn_type,
                "Direction": direction,
                "Amount": amount,
                "Balance": new_bal,
                "Description": desc,
                "Ref_ID": datetime.now().strftime("%H%M%S") # Simple ID
            }])
            
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.success("Transaction Recorded!")

# 2. DASHBOARD METRICS
df = get_data()

if not df.empty:
    # Calculations
    total_loaded = df[df["Type"] == "Load Collateral (Deposit)"]["Amount"].sum()
    total_withdrawn = df[df["Type"] == "Request Refund (Withdraw)"]["Amount"].sum()
    
    buy_settlements = df[df["Type"] == "Buy Settlement (Payment)"]["Amount"].sum()
    sell_settlements = df[df["Type"] == "Sell Settlement (Receipt)"]["Amount"].sum()
    
    current_balance = df.iloc[-1]["Balance"]
    net_investment = total_loaded - total_withdrawn # Actual Cash from Bank
    
    # Visuals
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏦 Current Broker Balance", f"Rs {current_balance:,.2f}", help="Money currently sitting in TMS")
    col2.metric("💳 Net Cash Invested", f"Rs {net_investment:,.2f}", help="Total Loaded - Total Withdrawn")
    col3.metric("📉 Total Buys Paid", f"Rs {buy_settlements:,.2f}")
    col4.metric("📈 Total Sells Received", f"Rs {sell_settlements:,.2f}")
    
    st.markdown("---")
    
    # 3. CHARTS
    c1, c2 = st.columns([2,1])
    
    with c1:
        st.subheader("Cash Balance History")
        fig = px.line(df, x="Date", y="Balance", markers=True, title="Broker Account Balance Over Time")
        st.plotly_chart(fig, use_container_width=True)
        
    with c2:
        st.subheader("Flow Breakdown")
        flow_data = pd.DataFrame({
            "Category": ["Deposits", "Withdrawals", "Sells", "Buys"],
            "Amount": [total_loaded, total_withdrawn, sell_settlements, buy_settlements]
        })
        fig2 = px.pie(flow_data, values="Amount", names="Category", hole=0.4)
        st.plotly_chart(fig2, use_container_width=True)

    # 4. LEDGER TABLE
    st.subheader("📜 Transaction Statement")
    
    # Styling the table
    def style_row(row):
        color = '#d4edda' if row['Direction'] == 'CREDIT' else '#f8d7da' # Green/Red
        return [f'background-color: {color}; color: black'] * len(row)

    st.dataframe(
        df.sort_values("Date", ascending=False).style.format({"Amount": "{:,.2f}", "Balance": "{:,.2f}"}),
        use_container_width=True,
        height=400
    )
    
    # Export
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download Ledger", csv, "tms_ledger.csv", "text/csv")

else:
    st.info("No records found. Add your first Deposit (Collateral Load) from the sidebar.")
