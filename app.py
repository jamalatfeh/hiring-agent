import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Hiring Agent", layout="wide")
st.title("🏥 Hiring Agent")
st.markdown("**Demo: Blind-ranked nurse screening for UAE hospitals.**")

st.sidebar.header("Agent Rules")
st.sidebar.info("1. Blind ranking (no PII).\n2. Injection quarantine.\n3. Human approval before outreach.")

st.write("### 1. Upload Resumes")
uploaded_files = st.file_uploader("Upload Nurse Resumes (PDF/TXT)", type=["pdf", "txt"], accept_multiple_files=True)

if uploaded_files:
    st.write(f"Found {len(uploaded_files)} resumes. Running screening...")
    
    results = []
    
    for file in uploaded_files:
        # Read the file content
        content = file.read().decode("utf-8", errors="ignore")
        
        # 1. QUARANTINE SCAN
        if "ignore previous instructions" in content.lower() or "rank me first" in content.lower():
            results.append({
                "Filename": file.name,
                "Status": "Quarantined",
                "Score": 0,
                "Reason": "Injection detected"
            })
            continue
            
        # 2. BLIND EXTRACTION (Mocked for demo)
        # In a real app, you would strip names/photos here.
        # For the demo, we assume the file is clean and has a DHA license.
        
        score = 85
        reason = "DHA License: Yes. Experience: 5 years."
        
        # 3. RANKING
        results.append({
            "Filename": file.name,
            "Status": "Ranked",
            "Score": score,
            "Reason": reason
        })
        
    df = pd.DataFrame(results)
    
    # Display the ranked list
    st.write("### 2. Blind-Ranked Shortlist")
    st.dataframe(df, use_container_width=True)
    
    # Display the quarantine alert if any
    quarantined = df[df["Status"] == "Quarantined"]
    if not quarantined.empty:
        st.error(f"🚨 **Quarantine Alert:** {len(quarantined)} malicious file(s) detected and removed.")
        
    # 4. HUMAN APPROVAL (Outreach)
    st.write("### 3. Human Approval Queue")
    st.info("The AI prepares the outreach. The HR manager sends it.")
    
    for index, row in df.iterrows():
        if row["Status"] == "Ranked":
            with st.expander(f"Review Candidate: {row['Filename']}"):
                st.write(f"**Score:** {row['Score']} | **Reason:** {row['Reason']}")
                st.text_area("Drafted Outreach:", value="Dear Candidate, we are impressed with your DHA license and experience. We would like to invite you for an interview.", key=f"outreach_{index}")
                if st.button(f"Approve and Send to {row['Filename']}", key=f"btn_{index}"):
                    st.success("Outreach approved and sent.")