import os
import streamlit as st
import boto3

st.set_page_config(page_title="Certificate Viewer", layout="wide")

def get_s3_client():
    s3_conf = st.secrets["s3"]
    return boto3.client(
        "s3",
        aws_access_key_id=s3_conf["aws_access_key_id"],
        aws_secret_access_key=s3_conf["aws_secret_access_key"],
        region_name=s3_conf["region"],
    )

@st.cache_data(ttl=300)
def list_generated_certificates():
    s3_conf = st.secrets["s3"]
    s3 = get_s3_client()
    prefix = "Gen_certificates/"
    resp = s3.list_objects_v2(Bucket=s3_conf["bucket"], Prefix=prefix)
    contents = resp.get("Contents", [])
    employees = []
    for obj in contents:
        key = obj.get("Key")
        if not key or key.endswith("/"):
            continue
        filename = key.split("/")[-1]
        name_part = os.path.splitext(filename)[0]
        emp_name = name_part.replace("certificate_", "", 1) if name_part.startswith("certificate_") else name_part
        employees.append({"name": emp_name, "key": key})
    employees.sort(key=lambda x: x["name"].lower())
    return employees

@st.cache_data(ttl=300, show_spinner=False)
def load_certificate_bytes_by_key(key: str) -> bytes | None:
    s3_conf = st.secrets["s3"]
    s3 = get_s3_client()
    try:
        obj = s3.get_object(Bucket=s3_conf["bucket"], Key=key)
        return obj["Body"].read()
    except s3.exceptions.ClientError:
        return None

employees = list_generated_certificates()
if not employees:
    st.info("No certificates found in S3 under `Gen_certificates/`.")
    st.stop()

st.title("Thank you Team - We sailed through 2025")

# ---------- LEFT (names) / RIGHT (preview) ----------

left, right = st.columns([1, 2])  # adjust ratio as you like [web:83][web:108]

# track selected employee index
if "selected_idx" not in st.session_state:
    st.session_state["selected_idx"] = None

with left:
    st.subheader("Team members")
    GRID_COLS = 2  # grid only in the left column
    cols = st.columns(GRID_COLS)

    for idx, emp in enumerate(employees):
        col = cols[idx % GRID_COLS]
        with col:
            is_selected = st.session_state["selected_idx"] == idx
            # simple visual cue for selection
            label = f"▶ {emp['name']}" if is_selected else emp["name"]
            if st.button(label, key=f"btn_{idx}", use_container_width=True):
                st.session_state["selected_idx"] = idx if not is_selected else None

with right:
    st.subheader("Certificate preview")
    sel_idx = st.session_state.get("selected_idx")

    if sel_idx is None:
        st.info("Click a name on the left to view their certificate.")
    else:
        emp = employees[sel_idx]
        cert_bytes = load_certificate_bytes_by_key(emp["key"])
        if cert_bytes:
            st.image(cert_bytes, caption=emp["name"], use_column_width=True)
            st.download_button(
                "Download certificate",
                data=cert_bytes,
                file_name=emp["key"].split("/")[-1],
                mime="image/png",
                key=f"dl_{sel_idx}",
            )
        else:
            st.error("Could not load certificate. Please try again.")
