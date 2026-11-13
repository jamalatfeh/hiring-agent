"""Hiring Agent demo: blind-ranked nurse screening.

Standalone prototype. Two rule-based readers extract years of experience and
skills. Where they disagree, the user decides. Nothing is ever sent: the
approval button only records the decision in the audit log.
"""
import io
import re
import unicodedata
from datetime import datetime

import pandas as pd
import streamlit as st

LICENCE_LABEL = "Claimed, not verified"
OUTREACH_TEXT = "Draft ready for review. Click Approve to record your decision."

# ---------------------------------------------------------------------------
# Skills vocabulary: canonical name -> patterns that mean the same thing
# ---------------------------------------------------------------------------
SKILLS = {
    "ICU": [r"\bicu\b", r"intensive care", r"critical care"],
    "ER": [r"\ber\b", r"emergency (room|department|care|nursing)", r"\bed nursing\b"],
    "Pediatrics": [r"pediatric", r"paediatric"],
    "NICU": [r"\bnicu\b", r"neonatal"],
    "Ventilator": [r"ventilator", r"mechanical ventilation"],
    "Dialysis": [r"dialysis"],
    "Oncology": [r"oncology"],
    "Triage": [r"triage"],
    "Telemetry": [r"telemetry"],
    "Wound care": [r"wound care"],
    "IV therapy": [r"\biv therapy\b", r"intravenous"],
    "Medication administration": [r"medication administration", r"medication management"],
    "BLS": [r"\bbls\b", r"basic life support"],
    "ACLS": [r"\bacls\b", r"advanced cardiac life support"],
    "PALS": [r"\bpals\b", r"pediatric advanced life support"],
    "Infection control": [r"infection control", r"infection prevention"],
    "EHR": [r"\behr\b", r"electronic health record", r"electronic medical record"],
}


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[ \t]+", " ", text)


def canon_skills(text: str) -> set:
    t = normalise(text)
    return {name for name, pats in SKILLS.items() if any(re.search(p, t) for p in pats)}


# ---------------------------------------------------------------------------
# Injection check: phrases, not single words. A basic check, not a full defence.
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


def is_injection(text: str) -> bool:
    t = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).lower())
    return any(re.search(p, t) for p in INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------
def read_text(name: str, data: bytes) -> str:
    """Return the text of a TXT or PDF file. Empty string if nothing readable."""
    if name.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        except Exception:
            return ""
    return data.decode("utf-8", errors="ignore").strip()


# ---------------------------------------------------------------------------
# Blind step: remove personal details before any ranking happens
# ---------------------------------------------------------------------------
PII_LINE = re.compile(
    r"^\s*(name|full name|nationality|gender|sex|date of birth|dob|birth ?date|age|"
    r"marital status|religion|visa status|passport( no| number)?|emirates id|photo|address)\b.*$",
    re.I | re.M,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"(\+\d[\d\s().-]{7,}\d|\b0\d[\d\s().-]{7,}\d)")
URL = re.compile(r"https?://\S+|www\.\S+")
PRONOUNS = re.compile(r"\b(he|she|him|her|his|hers|mr|mrs|ms|miss)\b\.?", re.I)


def blind(text: str) -> str:
    out = PII_LINE.sub("", text)
    out = EMAIL.sub("[removed]", out)
    out = URL.sub("[removed]", out)
    out = PHONE.sub("[removed]", out)
    out = PRONOUNS.sub("[removed]", out)
    lines = [l for l in out.splitlines()]
    # Drop a leading line that looks like a person's name (2 to 4 capitalised words).
    for i, l in enumerate(lines):
        if l.strip():
            if re.fullmatch(r"[A-Z][a-zA-Z'.-]+(\s+[A-Z][a-zA-Z'.-]+){1,3}", l.strip()):
                lines[i] = ""
            break
    return "\n".join(l for l in lines if l.strip())


# ---------------------------------------------------------------------------
# Two readers (different methods)
# ---------------------------------------------------------------------------
THIS_YEAR = datetime.now().year


def reader_a(text: str) -> dict:
    """Reader A: stated years and skills found anywhere in the text (regex)."""
    t = normalise(text)
    nums = [int(n) for n in re.findall(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+\w+){0,3}?\s+experience", t)]
    nums += [int(n) for n in re.findall(r"experience\s*[:\-]?\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", t)]
    return {"years": max(nums) if nums else None, "skills": canon_skills(text)}


def reader_b(text: str) -> dict:
    """Reader B: years from date ranges, skills from the Skills section only."""
    t = normalise(text)
    spans = []
    for m in re.finditer(r"\b((?:19|20)\d{2})\s*(?:-|–|—|to)\s*((?:19|20)\d{2}|present|current|now)\b", t):
        start = int(m.group(1))
        end = THIS_YEAR if m.group(2) in ("present", "current", "now") else int(m.group(2))
        if end >= start:
            spans.append((start, end))
    years = None
    if spans:
        spans.sort()
        merged = [list(spans[0])]
        for s, e in spans[1:]:
            if s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        years = sum(e - s for s, e in merged)
    skills = set()
    m = re.search(r"^\s*skills?\b[^\n]*\n?((?:.*\n?){0,12})", text, re.I | re.M)
    if m:
        first_line = re.sub(r"^\s*skills?\s*:?", "", m.group(0).split("\n")[0], flags=re.I)
        block = first_line + "\n" + "\n".join(m.group(1).split("\n")[:12])
        # stop at the next heading (a short line ending with a colon, or an all-caps word)
        block = re.split(r"\n\s*(?:[A-Z][A-Za-z ]{2,25}:|[A-Z ]{4,})\s*\n", block)[0]
        skills = canon_skills(block)
    return {"years": years, "skills": skills}


def compare(a: dict, b: dict) -> list:
    """Return a list of disagreement messages. Empty list means the readers agree."""
    issues = []
    if a["years"] is not None and b["years"] is not None and abs(a["years"] - b["years"]) > 1:
        issues.append(f"Years differ: Reader A {a['years']}, Reader B {b['years']}")
    if a["skills"] != b["skills"]:
        diff = sorted(a["skills"] ^ b["skills"])
        issues.append("Skills differ: " + ", ".join(diff))
    return issues


def licence_status(text: str) -> str:
    return f"DHA ({LICENCE_LABEL})" if re.search(r"\bdha\b", text, re.I) else "Not stated"


# ---------------------------------------------------------------------------
# Ranking against the job description
# ---------------------------------------------------------------------------
def parse_jd(jd: str) -> dict:
    m = re.search(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", jd, re.I)
    return {"skills": canon_skills(jd), "min_years": int(m.group(1)) if m else None}


def score(skills: set, years, jd: dict) -> int:
    overlap = (len(skills & jd["skills"]) / len(jd["skills"])) if jd["skills"] else 0.0
    if jd["min_years"]:
        yrs_ok = min((years or 0) / jd["min_years"], 1.0)
    else:
        yrs_ok = 1.0
    return round(100 * (0.8 * overlap + 0.2 * yrs_ok))


def process(name: str, data: bytes, idx: int, jd: dict) -> dict:
    cid = f"Candidate_{idx}"
    raw = read_text(name, data)
    rec = {"cid": cid, "file": name, "status": None, "issues": [], "blind": ""}
    if not raw:
        rec["status"] = "Unreadable"
        return rec
    if is_injection(raw):
        rec["status"] = "Quarantined"
        return rec
    text = blind(raw)
    a, b = reader_a(text), reader_b(text)
    rec.update(blind=text, a=a, b=b, issues=compare(a, b), licence=licence_status(raw))
    rec["status"] = "Needs confirmation" if rec["issues"] else "Ranked"
    if rec["status"] == "Ranked":
        years = a["years"] if a["years"] is not None else b["years"]
        rec.update(skills=a["skills"], years=years, score=score(a["skills"], years, jd))
    return rec


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
DEFAULT_JD = ("Registered nurse, ICU. Minimum 3 years experience. "
              "Skills: ICU, ventilator, BLS, ACLS. DHA licence required.")


def log(event: str, cid: str = "", file: str = ""):
    st.session_state.audit.append({
        "Time": datetime.utcnow().strftime("%H:%M:%S") + " UTC", "Event": event,
        "Candidate": cid, "File": file})


def log_once(key, event, cid, file):
    if key not in st.session_state.logged:
        st.session_state.logged.add(key)
        log(event, cid, file)


def main():
    st.set_page_config(page_title="Hiring Agent", layout="wide")
    for k, v in (("audit", []), ("logged", set()), ("approved", set()), ("choice", {})):
        if k not in st.session_state:
            st.session_state[k] = v

    st.title("🏥 Hiring Agent")
    st.markdown("**Demo: Blind-ranked nurse screening for UAE hospitals.**")
    st.sidebar.header("Agent Rules")
    st.sidebar.info("1. Injection quarantine before reading.\n"
                    "2. Blind ranking: no names, photos or nationality.\n"
                    "3. Two readers. If they disagree, a person decides.\n"
                    "4. Human approval before outreach.\n"
                    f"5. Licences are always '{LICENCE_LABEL}'.")

    st.write("### 1. Job description and resumes")
    jd_text = st.text_area("Job description", DEFAULT_JD, height=100)
    files = st.file_uploader("Upload nurse resumes (PDF or TXT)", type=["pdf", "txt"],
                             accept_multiple_files=True)
    if not files:
        st.info("Upload resumes to start. Nothing is stored. Files are read in memory.")
        show_audit()
        return

    jd = parse_jd(jd_text)
    st.caption(f"Job description read as: skills {sorted(jd['skills']) or 'none found'}, "
               f"minimum years {jd['min_years'] or 'not set'}.")
    recs = []
    for i, f in enumerate(files, 1):
        data = f.getvalue()
        rec = process(f.name, data, i, jd)
        recs.append(rec)
        key = (f.name, len(data))
        if rec["status"] == "Quarantined":
            log_once(key + ("q",), "Quarantined (injection pattern)", rec["cid"], f.name)
        elif rec["status"] == "Unreadable":
            log_once(key + ("u",), "Unreadable (no text found; needs OCR)", rec["cid"], f.name)
        elif rec["status"] == "Needs confirmation":
            log_once(key + ("d",), "Readers disagree", rec["cid"], f.name)

    # Apply the user's choice for candidates whose readers disagree
    for r in recs:
        if r["status"] == "Needs confirmation" and r["cid"] in st.session_state.choice:
            pick = r["a"] if st.session_state.choice[r["cid"]] == "A" else r["b"]
            years = pick["years"]
            r.update(status="Ranked", skills=pick["skills"], years=years,
                     score=score(pick["skills"], years, jd))

    st.write("### 2. Blind-ranked shortlist")
    ranked = sorted([r for r in recs if r["status"] == "Ranked"],
                    key=lambda r: (-r["score"], int(r["cid"].split("_")[1])))
    if ranked:
        st.dataframe(pd.DataFrame([{
            "Rank": n, "Candidate": r["cid"], "Score": r["score"],
            "Years (read)": r["years"] if r["years"] is not None else "not found",
            "Matched skills": ", ".join(sorted(r["skills"] & jd["skills"])) or "none",
            "Licence": r["licence"]} for n, r in enumerate(ranked, 1)]),
            use_container_width=True, hide_index=True)
        st.caption("Ties are broken by upload order only. Names, filenames and personal details are never used.")
    else:
        st.warning("No candidates ranked yet.")

    quarantined = [r for r in recs if r["status"] == "Quarantined"]
    if quarantined:
        st.error(f"🚨 Quarantine Alert: Injection detected. {len(quarantined)} file(s) were not read and are not ranked.")
    for r in recs:
        if r["status"] == "Unreadable":
            st.warning(f"{r['cid']}: no readable text (a scanned PDF needs OCR). Handed back to the user.")

    for r in recs:
        if r["status"] == "Needs confirmation":
            st.warning(f"⚠️ {r['cid']}: the two readers disagree. {'; '.join(r['issues'])}")
            sel = st.radio(f"Which reading should {r['cid']} use?",
                           ["Reader A (regex)", "Reader B (rule-based)"], key=f"rd_{r['cid']}", horizontal=True)
            if st.button(f"Confirm for {r['cid']}", key=f"cf_{r['cid']}"):
                st.session_state.choice[r["cid"]] = "A" if sel.startswith("Reader A") else "B"
                log("Reader choice confirmed by user: " + sel, r["cid"], r["file"])
                st.rerun()

    with st.expander("What the ranker sees (blinded text)"):
        pick = st.selectbox("Candidate", [r["cid"] for r in recs if r["blind"]] or ["none"])
        for r in recs:
            if r["cid"] == pick and r["blind"]:
                st.code(r["blind"])

    st.write("### 3. Human approval queue")
    st.info("The AI prepares the outreach. The HR manager approves. Nothing is actually sent in this demo.")
    for r in ranked[:3]:
        with st.expander(f"Review {r['cid']} (score {r['score']})"):
            st.write(f"**Licence:** {r['licence']}")
            st.text_area("Drafted outreach", OUTREACH_TEXT, key=f"out_{r['cid']}", disabled=True)
            if r["cid"] in st.session_state.approved:
                st.success("Approved by HR manager.")
            elif st.button(f"Approve {r['cid']}", key=f"ap_{r['cid']}"):
                st.session_state.approved.add(r["cid"])
                log("Approved by HR manager", r["cid"], r["file"])
                st.rerun()
    show_audit()


def show_audit():
    st.write("---")
    st.write("### 4. Audit log")
    st.caption("Filenames appear here for the HR manager and platform admin only, not in the ranking.")
    if st.session_state.audit:
        st.dataframe(pd.DataFrame(st.session_state.audit), use_container_width=True, hide_index=True)
    else:
        st.info("No events yet.")


if __name__ == "__main__":
    main()
