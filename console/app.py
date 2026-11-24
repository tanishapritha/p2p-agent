import os
import requests
import streamlit as st

st.set_page_config(page_title="P2P Agent Workbench", layout="wide")
st.title("P2P Invoice Agent — Developer Workbench")
base = st.sidebar.text_input("Backend URL", os.getenv("P2P_API_URL", "http://127.0.0.1:8000")).rstrip("/")
if st.sidebar.button("Check backend"):
    try:
        st.sidebar.json(requests.get(base + "/health", timeout=5).json())
    except requests.RequestException as exc:
        st.sidebar.error(str(exc))
tab1, tab2, tab3 = st.tabs(["PDF extraction", "Deterministic match", "Cases"])
with tab1:
    upload = st.file_uploader("Invoice PDF", type=["pdf"])
    if upload and st.button("Extract with configured real LLM"):
        response = requests.post(base + "/invoices/upload",
            files={"file": (upload.name, upload.getvalue(), "application/pdf")}, timeout=120)
        st.code(response.text, language="json")
with tab2:
    st.caption("Submit a MatchInput JSON payload to the deterministic matching endpoint.")
    payload = st.text_area("Match JSON", value='{"invoice_number":"INV-1042","vendor_match":true,"currency":"INR","invoice_subtotal":"550000","invoice_tax":"99000","invoice_total":"649000","invoice_lines":[{"description":"laptop","quantity":"10","unit_price":"55000"}],"po_found":true,"po_currency":"INR","po_lines":[{"description":"laptop","quantity":"10","unit_price":"50000"}],"grn_found":true,"grn_lines":[{"description":"laptop","quantity":"10","unit_price":"0"}]}', height=300)
    if st.button("Run deterministic match"):
        response = requests.post(base + "/matching/evaluate", data=payload,
                                 headers={"Content-Type":"application/json"}, timeout=20)
        st.code(response.text, language="json")
with tab3:
    if st.button("Refresh cases"):
        try:
            st.json(requests.get(base + "/cases", timeout=10).json())
        except requests.RequestException as exc:
            st.error(str(exc))
st.warning("Developer console only. Recommendations are not approvals. Payment execution is not supported.")
