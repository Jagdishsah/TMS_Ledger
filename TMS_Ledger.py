import streamlit as st
import pandas as pd
from github import Github, Auth
from io import StringIO
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="TMS Ledger Pro", page_icon="📒", layout="wide")

# Custom CSS for Status Tags
st.markdown("""
<style>
    .pending {background-color: #ffeeba; color: #856404; padding: 2px 6px; border-radius: 4px; font-weight: bold;}
    .cleared {background-color: #d4edda; color: #155724; padding: 2px 6px; border-radius: 4px; font-weight: bold;}
    .metric-box {border: 1px solid #444; padding: 10px; border-radius: 5px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

# --- GITHUB ENGINE ---
def get_repo():
    try:
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        auth = Auth.Token(token)
        g = Github(auth=auth)
        return g.get_repo(repo_name)
    except:
        st.error("GitHub Connection Failed. Check Secrets.")
        return None

def get_data():
    repo = get_repo()
    if not repo: return pd.DataFrame()
    try:
        file = repo.get_contents("tms_ledger_v2.csv")
        df = pd.read_csv(StringIO(file.decoded_content.decode()))
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df["Due_Date"] = pd.to_datetime(df["Due_Date"]).dt.date
        return df
    except:
        # Define Schema V2
        return pd.DataFrame(columns=[
            "Date", "Type", "Category", "Amount", "Status", 
            "Due_Date", "Ref_ID", "Description", "Is_Non_Cash"
        ])

def save_data(df):
    repo = get_repo()
    if not repo: return
    # Ensure dates are string for CSV
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df["Due_Date"] = pd.to_datetime(df["Due_Date"]).dt.strftime("%Y-%m-%d")
    
    csv_content = df.to_csv(index=False)
    try:
        file = repo.get_contents("tms_ledger_v2.csv")
        repo.update_file(file.path, "Update Ledger V2", csv_content, file.sha)
    except:
        repo.create_file("tms_ledger_v2.csv", "Create Ledger V2", csv_content)

# --- SIDEBAR: TRANSACTION ENTRY ---
with st.sidebar:
    st.header("💸 TMS Action Center")
    
    mode = st.radio("Action Type", ["Fund Transfer (Bank ↔ TMS)", "Trade Settlement (Buy/Sell)"])
    
    with st.form("entry_form"):
        date_today = datetime.now().date()
        date = st.date_input("Transaction Date", date_today)
        
        if mode == "Fund Transfer (Bank ↔ TMS)":
            txn_type = st.selectbox("Type", ["Load Collateral (Deposit)", "Request Refund (Withdraw)"])
            is_non_cash = st.checkbox("Non-Cash (Bank Guarantee/Cheque)", help="Check this if no actual money left your bank account yet.")
            amount = st.number_input("Amount (Rs)", min_value=1.0, step=1000.0)
            desc = st.text_input("Details (ConnectIPS ID / Bank Name)")
            days_to_settle = 0 # Instant usually
            
        else: # Trade Settlement
            txn_type = st.selectbox("Type", ["Buy Settlement (Payable)", "Sell Settlement (Receivable)"])
            is_non_cash = False
            amount = st.number_input("Net Settlement Amount (Rs)", min_value=1.0, step=100.0)
            desc = st.text_input("Script / Sheet No")
            
            # Auto-calculate Due Date (T+2 for Pay, T+3 for Receive)
            if "Buy" in txn_type:
                days_to_settle = 2
            else:
                days_to_settle = 3
        
        # Calculate Due Date
        due_date = date + timedelta(days=days_to_settle)
        
        if st.form_submit_button("Record Entry"):
            df = get_data()
            
            # Map to Internal Categories
            if "Load" in txn_type: cat = "DEPOSIT"
            elif "Refund" in txn_type: cat = "WITHDRAW"
            elif "Buy" in txn_type: cat = "PAYABLE"
            elif "Sell" in txn_type: cat = "RECEIVABLE"
            
            new_row = pd.DataFrame([{
                "Date": date,
                "Type": txn_type,
                "Category": cat,
                "Amount": amount,
                "Status": "Pending", # Always starts as Pending
                "Due_Date": due_date,
                "Ref_ID": datetime.now().strftime("%H%M%S"),
                "Description": desc,
                "Is_Non_Cash": is_non_cash
            }])
            
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.success("Entry Recorded! Check 'Settlement Queue'.")

# --- MAIN DASHBOARD ---
df = get_data()

if df.empty:
    st.info("Ledger is empty. Start by loading your initial Collateral in the Sidebar.")
else:
    # --- 1. CALCULATE FINANCIALS ---
    
    # A. Core Cash (Bank Perspective)
    # Exclude Non-Cash (Guarantees) from "Net Cash Invested"
    real_deposits = df[(df["Category"] == "DEPOSIT") & (df["Is_Non_Cash"] == False)]["Amount"].sum()
    withdrawals = df[df["Category"] == "WITHDRAW"]["Amount"].sum()
    net_invested = real_deposits - withdrawals
    
    # B. Collateral (TMS Perspective)
    non_cash_collat = df[df["Is_Non_Cash"] == True]["Amount"].sum()
    
    # C. Settlements (Pending)
    pending_payables = df[(df["Category"] == "PAYABLE") & (df["Status"] == "Pending")]["Amount"].sum()
    pending_receivables = df[(df["Category"] == "RECEIVABLE") & (df["Status"] == "Pending")]["Amount"].sum()
    
    # D. Realized Gains (Cleared Sells - Cleared Buys)
    cleared_buys = df[(df["Category"] == "PAYABLE") & (df["Status"] == "Cleared")]["Amount"].sum()
    cleared_sells = df[(df["Category"] == "RECEIVABLE") & (df["Status"] == "Cleared")]["Amount"].sum()
    realized_pnl_cash = cleared_sells - cleared_buys

    # E. TMS Balance Calculation
    # (Deposits + NonCash + RealizedSells) - (Withdrawals + RealizedBuys)
    tms_balance = (real_deposits + non_cash_collat + cleared_sells) - (withdrawals + cleared_buys)

    # --- 2. HEADER METRICS ---
    st.title("🏦 TMS Liquidity Manager")
    
    # Row 1: The "Truth"
    m1, m2, m3, m4 = st.columns(4)
    
    m1.metric("💵 Net Cash Invested", f"Rs {net_invested:,.0f}", 
              help="Actual money sent from Bank minus money returned to Bank.")
    
    house_money = net_invested < 0
    if house_money:
        m2.markdown(f"### 🏆 **HOUSE MONEY**\nRs {-net_invested:,.0f} Profit secured!")
    else:
        m2.metric("🛡️ Capital at Risk", f"Rs {net_invested:,.0f}")

    m3.metric("🏦 Total Collateral", f"Rs {tms_balance:,.0f}", 
              help="Current Buying Power (Cash + Non-Cash + Settled Profits)")
    
    net_due = pending_payables - pending_receivables
    m4.metric("⚖️ Net Settlement Due", f"Rs {net_due:,.0f}", 
              delta=f"Payable: {pending_payables:,.0f} | Receivable: {pending_receivables:,.0f}",
              delta_color="inverse")

    st.markdown("---")

    # --- 3. SETTLEMENT QUEUE (The "Clearing" Side) ---
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("⏳ Settlement Queue (Pending)")
        pending_df = df[df["Status"] == "Pending"].copy()
        
        if not pending_df.empty:
            pending_df["Due In"] = (pd.to_datetime(pending_df["Due_Date"]) - pd.to_datetime(datetime.now().date())).dt.days
            
            # Simple Table
            st.dataframe(
                pending_df[["Date", "Type", "Amount", "Due_Date", "Due In", "Description"]],
                use_container_width=True
            )
            
            # ACTION: Mark as Cleared
            with st.expander("✅ Mark Items as Cleared (Settled)", expanded=True):
                # Filter pending items
                opts = pending_df.apply(lambda x: f"{x['Type']} - Rs {x['Amount']} ({x['Description']})", axis=1).tolist()
                sel_to_clear = st.multiselect("Select transactions that have been settled:", opts)
                
                if st.button("Update Status to CLEARED"):
                    # Find indices of selected items
                    for item in sel_to_clear:
                        # Extract basic matching logic (Amount and Desc)
                        amt = float(item.split("- Rs ")[1].split(" (")[0])
                        # Update the main DF
                        mask = (df["Status"] == "Pending") & (df["Amount"] == amt)
                        # Mark the first match as Cleared
                        idx = df[mask].first_valid_index()
                        if idx is not None:
                            df.at[idx, "Status"] = "Cleared"
                    
                    save_data(df)
                    st.rerun()
        else:
            st.success("🎉 No pending settlements! All clear.")

    with c2:
        st.subheader("🛒 Buying Power Check")
        active_orders = st.number_input("Value of Open Buy Orders", min_value=0.0, step=1000.0, help="Total value of orders currently placed in TMS but not executed.")
        
        free_cash = tms_balance - active_orders - pending_payables
        
        st.metric("Free Cash Available", f"Rs {free_cash:,.0f}", 
                  delta=f"Blocked: {active_orders + pending_payables:,.0f}",
                  delta_color="normal")
        
        if free_cash < 0:
            st.error("⚠️ Insufficient Collateral! Load funds immediately.")
        else:
            st.success("✅ Good to trade.")

    st.markdown("---")

    # --- 4. DETAILED LEDGER & HISTORY ---
    st.subheader("📜 Full Transaction Ledger")
    
    # Visual Filters
    f1, f2 = st.columns(2)
    search = f1.text_input("Search Description")
    status_filter = f2.selectbox("Filter Status", ["All", "Pending", "Cleared"])
    
    view_df = df.copy()
    if search: view_df = view_df[view_df["Description"].str.contains(search, case=False)]
    if status_filter != "All": view_df = view_df[view_df["Status"] == status_filter]
    
    # Styling
    def highlight_row(row):
        if row['Status'] == 'Pending':
            return ['background-color: #fff3cd; color: #856404'] * len(row)
        elif row['Category'] == 'DEPOSIT' or row['Category'] == 'RECEIVABLE':
             return ['color: green'] * len(row)
        elif row['Category'] == 'WITHDRAW' or row['Category'] == 'PAYABLE':
             return ['color: red'] * len(row)
        return [''] * len(row)

    st.dataframe(
        view_df.sort_values("Date", ascending=False).style.apply(highlight_row, axis=1)
        .format({"Amount": "Rs {:,.2f}"}),
        use_container_width=True
    )
    
    # Download
    csv_dl = view_df.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download Ledger CSV", csv_dl, "tms_ledger_v2.csv", "text/csv")
