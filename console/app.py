import os

import requests
import streamlit as st

st.set_page_config(page_title="P2P Agent Workbench", layout="wide")
st.title("P2P Invoice Agent — Developer Workbench")
base = st.sidebar.text_input(
    "Backend URL", os.getenv("P2P_API_URL", "http://127.0.0.1:8000")
).rstrip("/")
if st.sidebar.button("Check backend"):
    try:
        st.sidebar.json(requests.get(base + "/health", timeout=5).json())
    except requests.RequestException as exc:
        st.sidebar.error(str(exc))
tab1, tab2, tab3, tab4 = st.tabs(["PDF extraction", "Deterministic match", "Cases", "Agent runs"])
with tab1:
    upload = st.file_uploader("Invoice PDF", type=["pdf"])
    if upload and st.button("Extract with configured real LLM"):
        response = requests.post(
            base + "/invoices/upload",
            files={"file": (upload.name, upload.getvalue(), "application/pdf")},
            timeout=120,
        )
        st.code(response.text, language="json")
with tab2:
    st.caption("Submit a MatchInput JSON payload to the deterministic matching endpoint.")
    payload = st.text_area(
        "Match JSON",
        value='{"invoice_number":"INV-1042","vendor_match":true,"currency":"INR","invoice_subtotal":"550000","invoice_tax":"99000","invoice_total":"649000","invoice_lines":[{"description":"laptop","quantity":"10","unit_price":"55000"}],"po_found":true,"po_currency":"INR","po_lines":[{"description":"laptop","quantity":"10","unit_price":"50000"}],"grn_found":true,"grn_lines":[{"description":"laptop","quantity":"10","unit_price":"0"}]}',
        height=300,
    )
    if st.button("Run deterministic match"):
        response = requests.post(
            base + "/matching/evaluate",
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        st.code(response.text, language="json")
with tab3:
    if st.button("Refresh cases"):
        try:
            st.json(requests.get(base + "/cases", timeout=10).json())
        except requests.RequestException as exc:
            st.error(str(exc))
st.warning(
    "Developer console only. Recommendations are not approvals. Payment execution is not supported."
)

with tab4:
    st.subheader("Run an invoice investigation")
    invoice_id = st.number_input("Persisted invoice ID", min_value=1, step=1)
    idem = st.text_input(
        "Optional idempotency key", help="Reuse this key to avoid starting a duplicate run."
    )
    if st.button("Run LangGraph workflow"):
        try:
            params = {"idempotency_key": idem} if idem.strip() else {}
            response = requests.post(
                f"{base}/agent/invoices/{int(invoice_id)}/run", params=params, timeout=60
            )
            st.json(response.json())
            if response.ok and response.json().get("run_id"):
                st.session_state["p2p_last_run_id"] = response.json()["run_id"]
        except requests.RequestException as exc:
            st.error(str(exc))
    run_id = st.number_input(
        "Inspect run ID", min_value=0, step=1, value=int(st.session_state.get("p2p_last_run_id", 0))
    )
    if st.button("Fetch audit events") and run_id:
        try:
            st.json(requests.get(f"{base}/agent/runs/{int(run_id)}", timeout=15).json())
        except requests.RequestException as exc:
            st.error(str(exc))
    st.markdown("#### Record reviewer acknowledgement or dispute")
    reviewer = st.text_input("Reviewer name/identifier")
    decision = st.selectbox("Review decision", ["ACKNOWLEDGE", "DISPUTE"])
    note = st.text_area("Review note")
    if st.button("Submit review record") and run_id:
        try:
            response = requests.post(
                f"{base}/agent/runs/{int(run_id)}/review",
                json={"reviewer": reviewer, "decision": decision, "note": note},
                timeout=15,
            )
            st.code(response.text)
        except requests.RequestException as exc:
            st.error(str(exc))
