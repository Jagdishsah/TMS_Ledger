import streamlit as st
import pandas as pd
from github import Github, Auth
from io import StringIO
import plotly.express as px
from datetime import datetime, timedelta

## --- 1. APP CONFIGURATION ---
st.set_page_config(
    page_title="NEPSE TMS Pro Ledger", 
    page_icon="💹", 
    layout="wide",
    initial_sidebar_state="expanded"
)

## --- 2. CUSTOM CSS FOR UI POLISH ---
st.markdown("""
<style>
    /* Metric Cards Styling */
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 10px;
        border-radius: 8px;
    }
    /* Alert Box Styling */
    .risk-alert {background-color: #ffcccb; padding: 15px; border-radius: 8px; color: #8b0000; font-weight: bold; border-left: 5px solid red;}
    .safe-zone {background-color: #d4edda; padding: 15px; border-radius: 8px; color: #155724; border-left: 5px solid green;}
    /* Table Styling */
    .stDataFrame {border: 1px solid #f0f0f0; border-radius: 5px;}
</style>
""", unsafe_allow_html=True)

## --- 3. GITHUB BACKEND (DATABASE) ---
def get_repo():
    ## Tries to connect to GitHub using secrets
    try:
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        auth = Auth.Token(token)
        g = Github(auth=auth)
        return g.get_repo(repo_name)
    except:
        return None

def get_data():
    ## Fetches the CSV file from GitHub. If missing, creates an empty DataFrame.
    repo = get_repo()
    if not repo: return pd.DataFrame()
    try:
        file = repo.get_contents("tms_ledger_master.csv")
        df = pd.read_csv(StringIO(file.decoded_content.decode()))
        ## Convert Strings back to Date objects for math
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df["Due_Date"] = pd.to_datetime(df["Due_Date"]).dt.date
        return df
    except:
        ## Initialize Master Schema if file doesn't exist
        return pd.DataFrame(columns=[
            "Date", "Type", "Category", "Amount", "Status", 
            "Due_Date", "Ref_ID", "Description", "Is_Non_Cash", 
            "Dispute_Note", "Fiscal_Year"
        ])

def save_data(df):
    ## Saves the DataFrame back to GitHub CSV
    repo = get_repo()
    if not repo: return
    
    ## Create a copy to format dates as strings
    save_df = df.copy()
    save_df["Date"] = pd.to_datetime(save_df["Date"]).dt.strftime("%Y-%m-%d")
    save_df["Due_Date"] = pd.to_datetime(save_df["Due_Date"]).dt.strftime("%Y-%m-%d")
    
    csv_content = save_df.to_csv(index=False)
    try:
        file = repo.get_contents("tms_ledger_master.csv")
        repo.update_file(file.path, "Update Ledger Master", csv_content, file.sha)
    except:
        repo.create_file("tms_ledger_master.csv", "Create Ledger Master", csv_content)

## --- 4. HELPER FUNCTIONS ---
def get_fiscal_year(date_obj):
    ## Calculates Nepal Fiscal Year (starts approx mid-July / Shrawan)
    year = date_obj.year
    month = date_obj.month
    if month >= 7: return f"{year}/{year+1}"
    return f"{year-1}/{year}"

## --- 5. DATA LOGIC & CALCULATIONS ---
df = get_data()

if not df.empty:
    ## A. Bank Perspective (Real Cash Flow)
    ## Cash OUT: Deposits (Real), Direct Payments (EOD), IPOs, Expenses
    money_out = df[
        (df["Category"].isin(["DEPOSIT", "DIRECT_PAY", "PRIMARY_INVEST", "EXPENSE"])) & 
        (df["Is_Non_Cash"] == False)
    ]["Amount"].sum()
    
    ## Cash IN: Withdrawals
    money_in = df[df["Category"] == "WITHDRAW"]["Amount"].sum()
    
    ## Net Cash Invested: The "Truth" of your wallet
    net_cash_invested = money_out - money_in
    
    ## B. TMS Perspective (Collateral & Buying Power)
    ## Credits (Increases Limit): Deposits (Real+NonCash), Sells (Receivables), Direct Payments
    tms_credits = df[df["Category"].isin(["DEPOSIT", "RECEIVABLE", "DIRECT_PAY"])]["Amount"].sum()
    
    ## Debits (Decreases Limit): Withdrawals, Buys (Payables), Expenses
    tms_debits = df[df["Category"].isin(["WITHDRAW", "PAYABLE", "EXPENSE"])]["Amount"].sum()
    
    ## Current TMS Balance (What Broker sees)
    tms_balance = tms_credits - tms_debits

    ## C. Settlement Status
    pending_df = df[df["Status"] == "Pending"]
    payable_due = pending_df[pending_df["Category"] == "PAYABLE"]["Amount"].sum()
    receivable_due = pending_df[pending_df["Category"] == "RECEIVABLE"]["Amount"].sum()
    net_due = payable_due - receivable_due # Positive means you owe money

else:
    ## Default values for first run
    net_cash_invested = 0
    tms_balance = 0
    payable_due = 0
    receivable_due = 0
    net_due = 0

## --- 6. SIDEBAR NAVIGATION & TOOLS ---
with st.sidebar:
    st.title("💹 TMS Pro")
    
    ## Main Menu Navigation
    menu = st.radio("Navigation", [
        "🏠 Dashboard", 
        "✍️ New Entry", 
        "📜 Ledger History", 
        "📊 Analytics", 
        "🛠️ Manage Data"
    ])
    
    st.markdown("---")
    
    ## Quick Calculator Tool
    with st.expander("🧮 Quick Calc: Load Amount"):
        st.caption("How much to load to clear dues?")
        calc_buy = st.number_input("Todays Buy", min_value=0.0, step=1000.0)
        calc_avail = st.number_input("Avail Collateral", value=float(tms_balance))
        needed = calc_buy - calc_avail
        if needed > 0:
            st.error(f"Load: Rs {needed:,.0f}")
        else:
            st.success("Covered by Collateral")

## --- 7. MAIN PAGES ---

## >>> PAGE: DASHBOARD <<<
if menu == "🏠 Dashboard":
    st.title("🏦 Financial Command Center")
    
    ## Row 1: The "Big Numbers"
    c1, c2, c3, c4 = st.columns(4)
    
    ## Metric 1: Real Money Involved
    c1.metric(
        "💵 Net Cash Invested", 
        f"Rs {net_cash_invested:,.0f}", 
        help="Total Cash moved from Bank to Market. (Deposits + IPOs - Withdrawals)"
    )
    
    ## Metric 2: House Money Logic
    if net_cash_invested < 0:
        c2.metric("🏆 House Money", f"Rs {abs(net_cash_invested):,.0f}", delta="Risk Free!", help="You have withdrawn more profit than you put in!")
    else:
        c2.metric("🛡️ Capital Risk", f"Rs {net_cash_invested:,.0f}", help="Amount of your salary currently stuck in the market.")

    ## Metric 3: Broker Balance
    if tms_balance < 0:
        c3.metric("⚠️ TMS Balance", f"- Rs {abs(tms_balance):,.0f}", delta="Overdue", delta_color="inverse", help="Negative means you MUST pay the broker.")
    else:
        c3.metric("🏦 TMS Balance", f"Rs {tms_balance:,.0f}", delta="Collateral", help="Your buying power.")

    ## Metric 4: Upcoming Settlements
    c4.metric(
        "⚖️ Net Settlement (T+2)", 
        f"Rs {net_due:,.0f}", 
        delta=f"Pay: {payable_due:,.0f} | Rec: {receivable_due:,.0f}", 
        delta_color="inverse",
        help="Net amount to settle in next 2 days."
    )

    st.markdown("---")

    ## Row 2: Alerts & Actions
    col_alert, col_action = st.columns([2, 1])
    
    with col_alert:
        st.subheader("🚨 Risk Monitor")
        alert_triggered = False
        
        ## Alert: Negative Balance
        if tms_balance < -50:
            st.markdown(f"<div class='risk-alert'>⚠️ URGENT: Negative Collateral of Rs {abs(tms_balance):,.2f}. Load funds or use 'Direct Payment' immediately.</div>", unsafe_allow_html=True)
            alert_triggered = True
            
        ## Alert: Overdue Settlements
        if not pending_df.empty:
            overdue = pending_df[pd.to_datetime(pending_df["Due_Date"]) < pd.to_datetime(datetime.now().date())]
            if not overdue.empty:
                st.warning(f"🕒 **{len(overdue)} Overdue Settlements!** These should have been cleared by now.")
                st.dataframe(overdue[["Date", "Type", "Amount", "Due_Date"]], height=150)
                alert_triggered = True
        
        if not alert_triggered:
            st.markdown("<div class='safe-zone'>✅ All Systems Green. No urgent risks detected.</div>", unsafe_allow_html=True)

    with col_action:
        st.subheader("⚡ Settlement Queue")
        ## Quick Action to Clear Pending Items
        if not pending_df.empty:
            opts = pending_df.apply(lambda x: f"{x['Due_Date']} | Rs {x['Amount']} ({x['Type']})", axis=1).tolist()
            sel_clear = st.multiselect("Select items settled/paid today:", opts, help="Select items where money actually left/entered your bank.")
            
            if st.button("Mark as CLEARED"):
                for item in sel_clear:
                    parts = item.split(" | ")
                    date_str = parts[0]
                    ## Extract amount carefully
                    amt_str = parts[1].split(" (")[0].replace("Rs ", "")
                    
                    ## Locate and update
                    mask = (df["Due_Date"].astype(str) == date_str) & (df["Amount"] == float(amt_str)) & (df["Status"] == "Pending")
                    idx = df[mask].first_valid_index()
                    if idx is not None:
                        df.at[idx, "Status"] = "Cleared"
                save_data(df)
                st.success("Updated!")
                st.rerun()
        else:
            st.info("Nothing pending.")

## >>> PAGE: NEW ENTRY <<<
elif menu == "✍️ New Entry":
    st.header("📝 Record New Transaction")
    
    ## Organize inputs in a clean form
    with st.form("entry_form"):
        ## Row 1: Basics
        c1, c2 = st.columns(2)
        date = c1.date_input("Transaction Date", datetime.now().date(), help="When did this happen?")
        
        ## Logic Selector
        action_cat = c2.selectbox("Transaction Category", [
            "📈 Buy/Sell Shares (TMS)",
            "🔄 Fund Transfer (Collateral)",
            "🏦 Direct Payment (EOD Settlement)",
            "🆕 IPO / Right Share",
            "⚠️ Fees / Fines / Taxes"
        ], help="Choose what you did.")
        
        ## Dynamic Inputs based on Category
        txn_type = ""
        cat = ""
        is_non_cash = False
        due_days = 0
        
        st.markdown("### Transaction Details")
        
        if action_cat == "📈 Buy/Sell Shares (TMS)":
            c_type = st.radio("Action", ["Buy Shares (Payable)", "Sell Shares (Receivable)"], horizontal=True)
            txn_type = c_type
            cat = "PAYABLE" if "Buy" in c_type else "RECEIVABLE"
            due_days = 2 if "Buy" in c_type else 3
            
        elif action_cat == "🔄 Fund Transfer (Collateral)":
            c_type = st.radio("Action", ["Load Collateral (Deposit)", "Refund Request (Withdraw)"], horizontal=True)
            is_non_cash = st.checkbox("Non-Cash (Bank Guarantee / Cheque)", help="Check if money hasn't left bank yet.")
            txn_type = c_type
            cat = "DEPOSIT" if "Load" in c_type else "WITHDRAW"
            
        elif action_cat == "🏦 Direct Payment (EOD Settlement)":
            st.info("ℹ️ Use this when you pay Broker directly via ConnectIPS for a purchase (Bypassing Collateral Load).")
            txn_type = "Direct Payment (Bank -> Broker)"
            cat = "DIRECT_PAY" 
            
        elif action_cat == "🆕 IPO / Right Share":
            c_type = st.radio("Type", ["IPO Application", "Right Share Payment"], horizontal=True)
            txn_type = c_type
            cat = "PRIMARY_INVEST" 
            
        elif action_cat == "⚠️ Fees / Fines / Taxes":
            c_type = st.radio("Type", ["Closeout Fine (20%)", "DP Charge", "Renewal Fee"], horizontal=True)
            txn_type = c_type
            cat = "EXPENSE"

        ## Row 2: Amounts
        c3, c4, c5 = st.columns(3)
        amount = c3.number_input("Amount (Rs)", min_value=1.0, step=100.0)
        desc = c4.text_input("Description", placeholder="e.g. NICA, ConnectIPS, Right Share")
        ref_id = c5.text_input("Ref ID", placeholder="Cheque No / Transaction ID")
        
        ## Submit
        if st.form_submit_button("💾 Save Transaction"):
            due_date = date + timedelta(days=due_days)
            fy = get_fiscal_year(date)
            
            ## Create Record
            new_row = pd.DataFrame([{
                "Date": date,
                "Type": txn_type,
                "Category": cat,
                "Amount": amount,
                "Status": "Pending",
                "Due_Date": due_date,
                "Ref_ID": ref_id,
                "Description": desc,
                "Is_Non_Cash": is_non_cash,
                "Dispute_Note": "",
                "Fiscal_Year": fy
            }])
            
            ## Append and Save
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.success("Entry Saved Successfully!")

## >>> PAGE: HISTORY <<<
elif menu == "📜 Ledger History":
    st.header("📜 Transaction Ledger")
    
    ## Filters Area
    with st.expander("🔍 Filter & Search", expanded=True):
        f1, f2, f3 = st.columns(3)
        search = f1.text_input("Search Text")
        cat_filter = f2.multiselect("Filter Category", df["Category"].unique())
        stat_filter = f3.selectbox("Status", ["All", "Pending", "Cleared"])
        
    ## Apply Filters
    view_df = df.copy()
    if search: view_df = view_df[view_df["Description"].str.contains(search, case=False, na=False)]
    if cat_filter: view_df = view_df[view_df["Category"].isin(cat_filter)]
    if stat_filter != "All": view_df = view_df[view_df["Status"] == stat_filter]
    
    ## Sort by Date Descending
    view_df = view_df.sort_values("Date", ascending=False)
    
    ## Visual Styling for Table
    def highlight_rows(row):
        ## Red text for Pending
        if row["Status"] == "Pending": return ["color: #d63384; font-weight: bold"] * len(row)
        return [""] * len(row)

    st.dataframe(
        view_df.style.apply(highlight_rows, axis=1).format({"Amount": "Rs {:,.2f}"}),
        use_container_width=True,
        height=600
    )
    
    ## Export
    csv = view_df.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download CSV", csv, "tms_ledger.csv", "text/csv")

## >>> PAGE: VISUALS <<<
elif menu == "📊 Analytics":
    st.header("📊 Financial Analytics")
    
    if df.empty:
        st.warning("No data available to visualize.")
    else:
        tab1, tab2 = st.tabs(["📈 Cash Flow", "🍰 Portfolio Breakdown"])
        
        with tab1:
            st.subheader("Net Cash Investment Growth")
            ## Prepare Data
            cf_df = df.copy().sort_values("Date")
            ## Logic: Withdraw is Negative flow, Deposit/IPO is Positive flow
            cf_df["Flow"] = cf_df.apply(lambda x: -x["Amount"] if x["Category"] == "WITHDRAW" else (x["Amount"] if x["Category"] in ["DEPOSIT", "PRIMARY_INVEST", "DIRECT_PAY"] else 0), axis=1)
            cf_df["Cumulative"] = cf_df["Flow"].cumsum()
            
            fig_line = px.line(cf_df, x="Date", y="Cumulative", title="Net Capital Deployed Over Time", markers=True)
            st.plotly_chart(fig_line, use_container_width=True)
            
        with tab2:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Turnover by Category")
                fig_pie = px.pie(df, values="Amount", names="Category", hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                st.subheader("Expenses & Fines")
                exp_df = df[df["Category"] == "EXPENSE"]
                if not exp_df.empty:
                    fig_exp = px.bar(exp_df, x="Type", y="Amount", color="Type")
                    st.plotly_chart(fig_exp, use_container_width=True)
                else:
                    st.info("No expenses recorded.")

## >>> PAGE: MANAGE DATA <<<
elif menu == "🛠️ Manage Data":
    st.header("🛠️ Data Management")
    st.info("Use this section to correct mistakes or add notes to disputes.")
    
    ## Select Box Logic
    ## Create a label that is easy to read
    if not df.empty:
        df["Label"] = df.apply(lambda x: f"{x['Date']} | {x['Category']} | Rs {x['Amount']} | {x['Description']}", axis=1)
        
        sel_label = st.selectbox("Select Transaction to Edit/Delete", df["Label"].tolist())
        
        if sel_label:
            ## Get Index
            idx = df[df["Label"] == sel_label].index[0]
            row = df.loc[idx]
            
            st.write("---")
            st.write(f"**Selected:** {row['Type']} on {row['Date']}")
            
            c_edit, c_del = st.columns(2)
            
            with c_edit:
                st.subheader("📝 Edit Dispute / Note")
                curr_note = row["Dispute_Note"] if pd.notna(row["Dispute_Note"]) else ""
                new_note = st.text_input("Add Note (e.g., 'Called Broker')", value=curr_note)
                
                if st.button("Update Note"):
                    df.at[idx, "Dispute_Note"] = new_note
                    save_data(df)
                    st.success("Note updated.")
                    st.rerun()
            
            with c_del:
                st.subheader("🗑️ Delete Transaction")
                st.warning("Action is permanent.")
                if st.button("DELETE PERMANENTLY"):
                    df = df.drop(index=idx)
                    save_data(df)
                    st.error("Deleted.")
                    st.rerun()
    else:
        st.write("No data to manage.")
