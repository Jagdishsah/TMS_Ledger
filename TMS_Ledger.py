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

# Initialize if empty
if df.empty:
    st.info("Welcome to TMS Ultimate. Start by adding your Opening Balance (Load Collateral) in the sidebar.")
else:
    # --- 1. GLOBAL CALCULATIONS (The Brain) ---
    # A. Bank Perspective (Net Cash Flow)
    # Money leaving bank = Deposits + Direct Pays + IPOs + Expenses
    money_out = df[df["Category"].isin(["DEPOSIT", "DIRECT_PAY", "PRIMARY_INVEST", "EXPENSE"]) & (df["Is_Non_Cash"]==False)]["Amount"].sum()
    # Money entering bank = Withdrawals
    money_in = df[df["Category"] == "WITHDRAW"]["Amount"].sum()
    net_cash_invested = money_out - money_in
    
    # B. TMS Perspective (Trading Limit/Collateral)
    # Credits (Limit Up): Deposits (All) + Sells + Direct Pays
    tms_credits = df[df["Category"].isin(["DEPOSIT", "RECEIVABLE", "DIRECT_PAY"])]["Amount"].sum()
    # Debits (Limit Down): Withdrawals + Buys + Expenses
    tms_debits = df[df["Category"].isin(["WITHDRAW", "PAYABLE", "EXPENSE"])]["Amount"].sum()
    
    # Current "Broker Balance"
    tms_balance = tms_credits - tms_debits

    # C. Status Checks
    pending_settlements = df[df["Status"] == "Pending"]
    total_due_payable = pending_settlements[pending_settlements["Category"] == "PAYABLE"]["Amount"].sum()
    total_due_receivable = pending_settlements[pending_settlements["Category"] == "RECEIVABLE"]["Amount"].sum()
    
    # --- 2. TABS STRUCTURE ---
    st.title("🏦 TMS Command Center")
    
    # The 4 requested tabs
    tab_dash, tab_hist, tab_graph, tab_manage = st.tabs([
        "🏠 Dashboard & Alerts", 
        "📜 History Log", 
        "📊 Summary Graphs", 
        "🛠️ Manage Data"
    ])

    # --- TAB 1: DASHBOARD (Summary & Alerts) ---
    with tab_dash:
        # A. High Level Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💵 Net Cash Invested", f"Rs {net_cash_invested:,.0f}", help="Total Real Cash In - Total Real Cash Out")
        
        # Logic for "House Money"
        if net_cash_invested < 0:
            m2.metric("🏆 House Money", f"Rs {abs(net_cash_invested):,.0f}", delta="Risk Free Profit!")
        else:
            m2.metric("🛡️ Capital at Risk", f"Rs {net_cash_invested:,.0f}")

        # Logic for Collateral / Due
        if tms_balance < 0:
            m3.metric("⚠️ IMMEDIATE DUE", f"Rs {abs(tms_balance):,.0f}", delta="Pay Now!", delta_color="inverse")
        else:
            m3.metric("🏦 Available Collateral", f"Rs {tms_balance:,.0f}", delta="Buying Power")

        net_settlement = total_due_payable - total_due_receivable
        m4.metric("⚖️ Net Settlement (T+2)", f"Rs {net_settlement:,.0f}", help="Payable - Receivable pending")

        st.markdown("---")

        # B. Critical Alerts Section
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("🚨 Critical Alerts")
            alert_count = 0
            
            # Alert 1: Negative Balance
            if tms_balance < -100: # Tolerance of 100
                st.error(f"⚠️ **NEGATIVE COLLATERAL:** You owe the broker **Rs {abs(tms_balance):,.2f}**. Pay via ConnectIPS immediately to avoid penalties.")
                alert_count += 1
            
            # Alert 2: Overdue Settlements
            overdue = pending_settlements[pd.to_datetime(pending_settlements["Due_Date"]) < pd.to_datetime(datetime.now().date())]
            if not overdue.empty:
                st.warning(f"🕒 **OVERDUE SETTLEMENTS:** {len(overdue)} transactions are past their due date. Check status.")
                st.dataframe(overdue[["Date", "Type", "Amount", "Due_Date"]])
                alert_count += 1
                
            # Alert 3: Disputes
            disputes = df[df["Dispute_Note"].notna() & (df["Dispute_Note"] != "")]
            if not disputes.empty:
                st.info(f"🗣️ **ACTIVE DISPUTES:** You have {len(disputes)} flagged transactions.")
                alert_count += 1
                
            if alert_count == 0:
                st.success("✅ All Systems Normal. No critical actions needed.")

        with c2:
            st.subheader("⚡ Quick Actions")
            # Mark Pending as Cleared
            if not pending_settlements.empty:
                st.write(f"**{len(pending_settlements)} Pending Items**")
                
                # Create a selection list
                opts = pending_settlements.apply(lambda x: f"{x['Due_Date']} | {x['Type']} | Rs {x['Amount']}", axis=1).tolist()
                sel_to_clear = st.multiselect("Select to Settle/Clear:", opts)
                
                if st.button("Mark Selected as CLEARED"):
                    for item in sel_to_clear:
                        parts = item.split(" | ")
                        # Logic to find row
                        mask = (df["Due_Date"].astype(str) == parts[0]) & (df["Amount"] == float(parts[2].replace("Rs ", ""))) & (df["Status"] == "Pending")
                        idx = df[mask].first_valid_index()
                        if idx is not None:
                            df.at[idx, "Status"] = "Cleared"
                    save_data(df)
                    st.rerun()
            else:
                st.write("Nothing pending.")

    # --- TAB 2: HISTORY (Detailed Ledger) ---
    with tab_hist:
        st.subheader("📜 Complete Transaction Log")
        
        # Filters
        c_filter1, c_filter2 = st.columns(2)
        search_txt = c_filter1.text_input("🔍 Search Description (e.g., NICA, IPS ID)")
        type_filter = c_filter2.multiselect("Filter by Category", df["Category"].unique(), default=df["Category"].unique())
        
        # Apply Filters
        view_df = df.copy()
        if search_txt:
            view_df = view_df[view_df["Description"].str.contains(search_txt, case=False, na=False)]
        if type_filter:
            view_df = view_df[view_df["Category"].isin(type_filter)]
            
        # Styling
        def style_status(val):
            color = 'red' if val == 'Pending' else 'green'
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            view_df.sort_values("Date", ascending=False).style.map(style_status, subset=["Status"])
            .format({"Amount": "Rs {:,.2f}"}),
            use_container_width=True,
            height=500
        )
        
        # Export
        csv = view_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download History CSV", csv, "tms_history.csv", "text/csv")

    # --- TAB 3: SUMMARY GRAPHS (Visuals) ---
    with tab_graph:
        st.subheader("📊 Financial Visualization")
        
        g1, g2 = st.columns(2)
        
        with g1:
            # 1. Cash Flow Trend (Net Investment over time)
            st.markdown("**Net Cash Position Over Time**")
            # Create a running total of cash in/out
            flow_df = df.copy()
            # Invert Withdrawals to be negative for graphing
            flow_df["Cash_Flow"] = flow_df.apply(
                lambda x: -x["Amount"] if x["Category"] == "WITHDRAW" else (x["Amount"] if x["Category"] in ["DEPOSIT", "PRIMARY_INVEST"] else 0), axis=1
            )
            flow_df = flow_df.sort_values("Date")
            flow_df["Cumulative_Invested"] = flow_df["Cash_Flow"].cumsum()
            
            fig_line = px.line(flow_df, x="Date", y="Cumulative_Invested", markers=True)
            st.plotly_chart(fig_line, use_container_width=True)
            
        with g2:
            # 2. Expense & Penalty Breakdown
            st.markdown("**Where is money leaking? (Expenses/Fines)**")
            exp_df = df[df["Category"] == "EXPENSE"]
            if not exp_df.empty:
                fig_pie = px.pie(exp_df, values="Amount", names="Type", hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No expenses recorded yet! Good job.")

        st.markdown("---")
        
        # 3. Monthly Activity Bar Chart
        st.markdown("**Monthly Activity Volume**")
        df["Month"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m")
        monthly_stats = df.groupby(["Month", "Category"])["Amount"].sum().reset_index()
        fig_bar = px.bar(monthly_stats, x="Month", y="Amount", color="Category", barmode="group")
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- TAB 4: MANAGE DATA (CRUD) ---
    with tab_manage:
        st.subheader("🛠️ Data Management")
        st.info("Use this tab to delete incorrect entries or update dispute notes.")
        
        # Select an entry to manage
        # Create a readable label for the dropdown
        df["Label"] = df.apply(lambda x: f"{x['Date']} | {x['Type']} | Rs {x['Amount']} | {x['Description']}", axis=1)
        
        selected_label = st.selectbox("Select Transaction to Edit/Delete", df["Label"].tolist())
        
        if selected_label:
            # Find the index
            idx = df[df["Label"] == selected_label].index[0]
            row = df.loc[idx]
            
            st.write("---")
            st.write(f"**Selected:** {row['Type']} on {row['Date']}")
            
            c_edit, c_del = st.columns(2)
            
            with c_edit:
                st.markdown("#### 📝 Edit Note / Dispute")
                new_note = st.text_input("Dispute/Notes", value=row["Dispute_Note"] if pd.notna(row["Dispute_Note"]) else "")
                if st.button("Update Note"):
                    df.at[idx, "Dispute_Note"] = new_note
                    save_data(df)
                    st.success("Note Updated!")
                    st.rerun()

            with c_del:
                st.markdown("#### 🗑️ Delete Entry")
                st.warning("This action cannot be undone.")
                if st.button("Delete Transaction Permanently"):
                    df = df.drop(index=idx)
                    save_data(df)
                    st.error("Transaction Deleted.")
                    st.rerun()
