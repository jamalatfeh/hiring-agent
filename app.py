import re
import unicodedata
from datetime import datetime

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Mock data (demo only). Names and emails stay hidden until consent is given.
# ---------------------------------------------------------------------------
CANDIDATES = [
    {"id": 1, "name": "Maria Santos", "role": "Nurse", "skills": "ICU", "licence": "DHA", "email": "maria@example.com", "consent": False},
    {"id": 2, "name": "John Doe", "role": "Nurse", "skills": "ER", "licence": "DHA", "email": "john@example.com", "consent": True},
    {"id": 3, "name": "Aisha Khan", "role": "Nurse", "skills": "Pediatrics", "licence": "DHA", "email": "aisha@example.com", "consent": False},
]
LICENCE_LABEL = "Claimed, not verified"

# ---------------------------------------------------------------------------
# Injection check. A basic phrase check, not a complete defence.
# Patterns are phrases, not single words: "ignore" or "system" alone would
# flag normal messages ("I will not ignore your call", "EHR system").
# ---------------------------------------------------------------------------
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+|the\s+)*(previous|prior|above|earlier)\s+(instructions|rules|prompts?)",
    r"disregard\s+(all\s+|any\s+|the\s+)*(previous|prior|above|earlier)",
    r"(reveal|show|print)\s+(the\s+|your\s+)?system\s+prompt",
    r"\bsystem\s+prompt\b",
    r"rank\s+me\s+(first|number\s+one|#1|at\s+the\s+top)",
    r"you\s+are\s+now\s+(a|an|the)\b",
    r"override\s+(the\s+)?(rules|instructions|safety)",
]


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", text)


def is_injection(text: str) -> bool:
    t = normalise(text)
    return any(re.search(p, t) for p in INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# Consent state and audit log (the Platform Admin's view)
# ---------------------------------------------------------------------------
def init_state():
    if "consent" not in st.session_state:
        st.session_state.consent = {c["id"]: c["consent"] for c in CANDIDATES}
        st.session_state.requested = set()
        st.session_state.audit = []


def log(actor: str, action: str):
    st.session_state.audit.append(
        {"Time": datetime.now().strftime("%H:%M:%S"), "Actor": actor, "Action": action}
    )


def status_of(cid: int) -> str:
    if st.session_state.consent[cid]:
        return "Consent Granted"
    if cid in st.session_state.requested:
        return "Requested (awaiting candidate)"
    return "Hidden (Awaiting Consent)"


def main():
    st.set_page_config(page_title="Headhunter Agent", layout="wide")
    init_state()

    st.title("🔍 Headhunter Agent")
    st.markdown("**Demo: Consented candidate search for verified recruiters.**")

    st.sidebar.header("Agent Rules")
    st.sidebar.info(
        "1. Blind search: candidate IDs only, no names or emails.\n"
        "2. Three-way consent: the candidate consents, the recruiter requests, "
        "the platform admin audits.\n"
        "3. Injection check on candidate messages."
    )

    # ---------------- 1. Recruiter search ----------------
    st.write("### 1. Recruiter: blind search")
    query = st.text_input("Search by skill or licence (e.g., ICU, ER, DHA)", "")
    if query:
        rows = []
        for c in CANDIDATES:
            haystack = f"{c['skills']} {c['licence']}".lower()
            if query.lower() in haystack:
                rows.append({
                    "Candidate ID": f"#{c['id']}",
                    "Role": c["role"],
                    "Skills": c["skills"],
                    "Licence": f"{c['licence']} ({LICENCE_LABEL})",
                    "Status": status_of(c["id"]),
                })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.warning("No candidates found.")

    # ---------------- 2. Recruiter requests contact ----------------
    st.write("### 2. Recruiter: request contact")
    ids = [c["id"] for c in CANDIDATES]
    req_id = st.selectbox("Candidate ID", ids, format_func=lambda i: f"#{i}", key="req")
    if st.button("Request contact"):
        if st.session_state.consent[req_id]:
            st.info(f"#{req_id} has already given consent.")
        else:
            st.session_state.requested.add(req_id)
            log("Recruiter", f"Requested contact with #{req_id}")
            st.success(f"Request sent to candidate #{req_id}.")

    # ---------------- 3. Candidate dashboard (simulation) ----------------
    st.write("---")
    st.write("### 3. Candidate dashboard (simulation)")
    st.caption("In the live product the candidate signs in to their own account. "
               "Here one person plays both roles so you can see the flow.")
    pending = sorted(st.session_state.requested - {i for i, v in st.session_state.consent.items() if v})
    if pending:
        who = st.selectbox("Pending requests", pending, format_func=lambda i: f"Request for candidate #{i}", key="cand")
        col1, col2 = st.columns(2)
        if col1.button("I approve contact"):
            st.session_state.consent[who] = True
            st.session_state.requested.discard(who)
            log(f"Candidate #{who}", "Granted consent")
            st.rerun()
        if col2.button("I decline"):
            st.session_state.requested.discard(who)
            log(f"Candidate #{who}", "Declined request")
            st.rerun()
    else:
        st.info("No pending requests.")

    # ---------------- 4. Recruiter: consented contacts ----------------
    st.write("### 4. Recruiter: consented contacts")
    shown = False
    for c in CANDIDATES:
        if st.session_state.consent[c["id"]]:
            st.write(f"**#{c['id']}: {c['name']}**, {c['email']}")
            shown = True
    if not shown:
        st.info("No contact details are visible until a candidate consents.")

    # ---------------- 5. Injection check ----------------
    st.write("---")
    st.write("### 5. Injection check")
    up = st.file_uploader("Upload a candidate message (.txt)", type=["txt"])
    if up:
        content = up.read().decode("utf-8", errors="ignore")
        if is_injection(content):
            st.error("🚨 Quarantine Alert: Injection detected.")
            st.caption("The message was not read further and is not shown.")
            log("System", "Quarantined an uploaded message")
        else:
            st.success("No injection pattern detected. This is a basic phrase check.")
            log("System", "Uploaded message passed the basic check")

    # ---------------- 6. Platform admin audit log ----------------
    st.write("---")
    st.write("### 6. Platform admin: consent and audit log")
    if st.session_state.audit:
        st.dataframe(pd.DataFrame(st.session_state.audit), use_container_width=True)
    else:
        st.info("No events yet.")


if __name__ == "__main__":
    main()
