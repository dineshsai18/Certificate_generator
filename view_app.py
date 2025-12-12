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

GRID_COLS = 4
cols = st.columns(GRID_COLS)

# Track which employee index is currently open
if "open_idx" not in st.session_state:
    st.session_state["open_idx"] = None

def select_emp(idx):
    # If clicking the same index, close it; else open new one
    if st.session_state["open_idx"] == idx:
        st.session_state["open_idx"] = None
    else:
        st.session_state["open_idx"] = idx

for idx, emp in enumerate(employees):
    col = cols[idx % GRID_COLS]
    with col:
        is_open = st.session_state["open_idx"] == idx
        
        with st.expander(emp["name"], expanded=is_open):

            # Button that sets which card is open
            if st.button(emp["name"], key=f"btn_{idx}", use_container_width=True):
                select_emp(idx)
                st.rerun()  # ensure layout refresh so only one stays open

            # “Flipped” view: show certificate only for active card
            if is_open:
                cert_bytes = load_certificate_bytes_by_key(emp["key"])
                if cert_bytes:
                    st.image(cert_bytes, use_column_width=True)
                    st.download_button(
                        "Download",
                        data=cert_bytes,
                        file_name=emp["key"].split("/")[-1],
                        mime="image/png",
                        key=f"dl_{idx}",
                    )
                else:
                    st.error("Could not load certificate.")
