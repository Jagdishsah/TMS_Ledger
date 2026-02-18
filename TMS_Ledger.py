import streamlit as st
import pandas as pd
from github import Github, Auth
from io import StringIO
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="TMS Ledger Ultimate", page_icon="📒", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .big-font {font-size:24px !important; font-weight: bold;}
    .risk-alert {background-color: #ffcccb; padding: 10px; border-radius: 5px; color: #8b0000;}
    .safe-zone {background-color: #d4edda; padding: 10px; border-radius: 5px; color: #155724;}
    .stTabs [data-baseweb="tab-list"] {gap: 24px;}
    .stTabs [data-baseweb="tab"] {height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px 4px 0 0;}
    .stTabs [aria-selected="true"] {background-color: #fff; border-bottom: 2px solid #ff4b4b;}
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
        return None

def get_data():
    repo = get_repo()
    if not repo: return pd.DataFrame()
    try:
        file = repo.get_contents("tms_ledger_v3.csv")
        df = pd.read_csv(StringIO(file.decoded_content.decode()))
        # Convert date columns back to datetime objects for calculation
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df["Due_Date"] = pd.to_datetime(df["Due_Date"]).dt.date
        return df
    except:
        # V3 Schema: Includes IPO, Penalty, Disputes
        return pd.DataFrame(columns=[
            "Date", "Type", "Category", "Amount", "Status", 
            "Due_Date", "Ref_ID", "Description", "Is_Non_Cash", 
            "Dispute_Note", "Fiscal_Year"
        ])

def save_data(df):
    repo = get_repo()
    if not repo: return
    # Convert dates to string for CSV storage
    save_df = df.copy()
    save_df["Date"] = pd.to_datetime(save_df["Date"]).dt.strftime("%Y-%m-%d")
    save_df["Due_Date"] = pd.to_datetime(save_df["Due_Date"]).dt.strftime("%Y-%m-%d")
    
    csv_content = save_df.to_csv(index=False)
    try:
        file = repo.get_contents("tms_ledger_v3.csv")
        repo.update_file(file.path, "Update Ledger V3", csv_content, file.sha)
    except:
        repo.create_file("tms_ledger_v3.csv", "Create Ledger V3", csv_content)

def get_fiscal_year(date_obj):
    # Nepal Fiscal Year usually starts mid-July (Shrawan 1)
    # Approx logic: If month > 7, it's Year/Year+1. Else Year-1/Year.
    year = date_obj.year
    month = date_obj.month
    if month >= 7: return f"{year}/{year+1}"
    return f"{year-1}/{year}"

# --- SIDEBAR: ADVANCED ENTRY ---
with st.sidebar:
    st.header("✍️ Transaction Entry")
    
    # Categories for different workflows
    action_cat = st.selectbox("Category", [
        "🔄 Fund Transfer (Collateral)", 
        "📈 Secondary Trade (TMS)", 
        "🏦 Direct Payment (EOD/Due)", 
        "🆕 IPO / Right Share",
        "⚠️ Penalty / Adjustment"
    ])
    
    with st.form("entry_form"):
        date = st.date_input("Date", datetime.now().date())
        amount = st.number_input("Amount (Rs)", min_value=1.0, step=1000.0)
        desc = st.text_input("Description / Script")
        ref_id = st.text_input("Ref ID / Cheque No / IPS ID")
        
        # Default values
        txn_type = ""
        cat = ""
        is_non_cash = False
        due_days = 0
        
        # Logic per Category
        if action_cat == "🔄 Fund Transfer (Collateral)":
            txn_type = st.radio("Type", ["Load Collateral", "Request Refund"])
            is_non_cash = st.checkbox("Non-Cash (Bank Guarantee/Cheque)")
            cat = "DEPOSIT" if "Load" in txn_type else "WITHDRAW"
            
        elif action_cat == "📈 Secondary Trade (TMS)":
            txn_type = st.radio("Type", ["Buy Settlement (Payable)", "Sell Settlement (Receivable)"])
            cat = "PAYABLE" if "Buy" in txn_type else "RECEIVABLE"
            due_days = 2 if "Buy" in txn_type else 3
            
        elif action_cat == "🏦 Direct Payment (EOD/Due)":
            st.info("Use this when you pay for shares directly from Bank without loading collateral first.")
            txn_type = "Direct Payment (Bank -> Broker)"
            cat = "DIRECT_PAY" # Reduces Bank, Settles Payable
            
        elif action_cat == "🆕 IPO / Right Share":
            txn_type = st.radio("Type", ["IPO Application (ASBA)", "Right Share Payment"])
            cat = "PRIMARY_INVEST" # Reduces Bank, Does NOT touch TMS
            
        elif action_cat == "⚠️ Penalty / Adjustment":
            txn_type = st.radio("Type", ["Closeout Penalty (Fine)", "Tax Adjustment", "Interest/DP Charge"])
            cat = "EXPENSE"
        
        if st.form_submit_button("Record Transaction"):
            df = get_data()
            due_date = date + timedelta(days=due_days)
            fy = get_fiscal_year(date)
            
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
            
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.success("Entry Saved.")

# --- MAIN ENGINE ---
df = get_data()

if df.empty:
    st.info("Welcome to TMS Ultimate. Start by adding your Opening Balance (Load Collateral) in the sidebar.")
else:
    # --- LOGIC CALCULATIONS ---
    # 1. Bank Perspective (Real Cash Flow)
    # Deposits + Direct Payments + IPOs + Expenses = Money Out
    # Withdrawals = Money In
    money_out = df[df["Category"].isin(["DEPOSIT", "DIRECT_PAY", "PRIMARY_INVEST", "EXPENSE"]) & (df["Is_Non_Cash"]==False)]["Amount"].sum()
    money_in = df[df["Category"] == "WITHDRAW"]["Amount"].sum()
    net_cash_invested = money_out - money_in
    
    # 2. TMS Perspective (Broker Balance)
    # Credits: Deposits (Cash+NonCash) + Sold Shares + Direct Payments (they clear debt)
    # Debits: Withdrawals + Bought Shares + Expenses
    tms_credits = df[df["Category"].isin(["DEPOSIT", "RECEIVABLE", "DIRECT_PAY"])]["Amount"].sum()
    tms_credits_noncash = df[(df["Category"] == "DEPOSIT") & (df["Is_Non_Cash"]==True)]["Amount"].sum()
    
    tms_debits = df[df["Category"].isin(["WITHDRAW", "PAYABLE", "EXPENSE"])]["Amount"].sum()
    
    # Status Checks
    cleared_credits = df[
        (df["Category"].isin(["DEPOSIT", "RECEIVABLE", "DIRECT_PAY"])) & 
        (df["Status"] == "Cleared")
    ]["Amount"].sum()
    
    cleared_debits = df[
        (df["Category"].isin(["WITHDRAW", "PAYABLE", "EXPENSE"])) & 
        (df["Status"] == "Cleared")
    ]["Amount"].sum()
    
    # BALANCES
    # Theoretical Balance (If everything settles today)
    tms_balance_theoretical = tms_credits - tms_debits
    
    # Actual "Payable to Broker" (Instant Check)
    # If negative, you owe money. If positive, you have collateral.
    
    # 3. IPO / Primary
    primary_investment = df[df["Category"] == "PRIMARY_INVEST"]["Amount"].sum()

    # --- DASHBOARD LAYOUT ---
    st.title("🏦 TMS Ledger Ultimate")
    
    tab1, tab2, tab3 = st.tabs(["📊 Overview & Risk", "📅 Calendar & Workflow", "📜 Reports & Audit"])
    
    # TAB 1: OVERVIEW & RISK
    with tab1:
        # Top Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💵 Total Net Cash Invested", f"Rs {net_cash_invested:,.0f}", help="Real money taken out of bank (includes IPOs).")
        m2.metric("🆕 IPO/Right Share Only", f"Rs {primary_investment:,.0f}")
        
        # Risk Logic
        if tms_balance_theoretical < 0:
            m3.metric("⚠️ EOD PAYABLE (DUE)", f"Rs {abs(tms_balance_theoretical):,.0f}", delta="You Owe Broker", delta_color="inverse")
            st.markdown(f"<div class='risk-alert'>🚨 <b>URGENT:</b> You have a negative balance of Rs {abs(tms_balance_theoretical):,.0f}. Pay via 'Direct Payment' or 'Load Collateral' immediately to avoid penalties.</div>", unsafe_allow_html=True)
        else:
            m3.metric("🛡️ Available Collateral", f"Rs {tms_balance_theoretical:,.0f}", delta="Safe", delta_color="normal")
        
        # House Money
        if net_cash_invested < 0:
            m4.markdown(f"### 🏆 House Money\n**Rs {abs(net_cash_invested):,.0f}**")
        else:
            m4.metric("Risk Capital", f"Rs {net_cash_invested:,.0f}")

        st.markdown("---")
        
        # Breakdown Chart
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Investment Distribution")
            chart_data = pd.DataFrame({
                "Type": ["TMS (Secondary)", "IPO/Right (Primary)", "Expenses/Fines"],
                "Amount": [
                    max(0, net_cash_invested - primary_investment), 
                    primary_investment,
                    df[df["Category"] == "EXPENSE"]["Amount"].sum()
                ]
            })
            fig = px.pie(chart_data, names="Type", values="Amount", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig, use_container_width=True)
            
        with c2:
            st.subheader("💡 Workflow Status")
            pending_cnt = len(df[df["Status"] == "Pending"])
            dispute_cnt = len(df[df["Dispute_Note"] != ""])
            
            st.write(f"**Pending Items:** {pending_cnt}")
            if pending_cnt > 0: st.warning("You have uncleared settlements.")
            
            st.write(f"**Active Disputes:** {dispute_cnt}")
            if dispute_cnt > 0: st.error("Resolve disputes with broker!")

    # TAB 2: CALENDAR & WORKFLOW
    with tab2:
        c_left, c_right = st.columns([2, 1])
        
        with c_left:
            st.subheader("🗓️ Settlement Calendar")
            # Filter only pending items
            pending = df[df["Status"] == "Pending"].sort_values("Due_Date")
            
            if not pending.empty:
                # Add "Days Remaining" column
                pending["Days Left"] = (pd.to_datetime(pending["Due_Date"]) - pd.to_datetime(datetime.now().date())).dt.days
                
                def color_days(val):
                    if val < 0: return "color: red; font-weight: bold"
                    if val == 0: return "color: orange; font-weight: bold"
                    return "color: green"

                st.dataframe(
                    pending[["Date", "Due_Date", "Days Left", "Type", "Amount", "Description"]]
                    .style.map(lambda x: color_days(x), subset=["Days Left"])
                    .format({"Amount": "{:,.2f}"}),
                    use_container_width=True
                )
            else:
                st.success("🎉 Nothing pending! Relax.")
                
        with c_right:
            st.subheader("✅ Action Center")
            
            # Settlement Action
            if not pending.empty:
                opts = pending.apply(lambda x: f"{x['Due_Date']} | {x['Type']} | Rs {x['Amount']}", axis=1).tolist()
                sel = st.multiselect("Mark as SETTLED/CLEARED:", opts)
                if st.button("Confirm Settlement"):
                    for item in sel:
                        # Find unique row based on string match (simplistic but works for MVP)
                        parts = item.split(" | ")
                        mask = (df["Due_Date"].astype(str) == parts[0]) & (df["Amount"] == float(parts[2].replace("Rs ", ""))) & (df["Status"] == "Pending")
                        idx = df[mask].first_valid_index()
                        if idx is not None:
                            df.at[idx, "Status"] = "Cleared"
                    save_data(df)
                    st.rerun()
            
            st.markdown("---")
            
            # Dispute Action
            st.write("**Report Issue / Dispute**")
            dispute_sel = st.selectbox("Select Transaction", df["Description"] + " - " + df["Amount"].astype(str))
            note = st.text_input("Dispute Note (e.g., Broker says received less)")
            if st.button("Flag Dispute"):
                # Find and update
                amt = float(dispute_sel.split(" - ")[1])
                mask = (df["Amount"] == amt)
                idx = df[mask].first_valid_index()
                if idx is not None:
                    df.at[idx, "Dispute_Note"] = note
                save_data(df)
                st.warning("Transaction Flagged.")

    # TAB 3: REPORTS & AUDIT
    with tab3:
        st.subheader("📑 Fiscal Year Tax & Audit Report")
        
        # Filter by Fiscal Year
        fys = df["Fiscal_Year"].unique()
        sel_fy = st.selectbox("Select Fiscal Year", fys)
        
        fy_df = df[df["Fiscal_Year"] == sel_fy]
        
        # Calculate Stats
        total_buy = fy_df[fy_df["Category"] == "PAYABLE"]["Amount"].sum()
        total_sell = fy_df[fy_df["Category"] == "RECEIVABLE"]["Amount"].sum()
        total_penalty = fy_df[fy_df["Category"] == "EXPENSE"]["Amount"].sum()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Buys (Turnover)", f"Rs {total_buy:,.2f}")
        col2.metric("Total Sells (Turnover)", f"Rs {total_sell:,.2f}")
        col3.metric("Penalties & Fees", f"Rs {total_penalty:,.2f}", delta_color="inverse")
        
        st.markdown("### 📜 Full Ledger for FY")
        st.dataframe(fy_df, use_container_width=True)
        
        csv_dl = fy_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download FY Report", csv_dl, f"Audit_Report_{sel_fy.replace('/','-')}.csv", "text/csv")
