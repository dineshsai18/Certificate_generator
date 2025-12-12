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

def load_certificate_bytes_by_key(key: str) -> bytes | None:
    s3_conf = st.secrets["s3"]
    s3 = get_s3_client()
    try:
        obj = s3.get_object(Bucket=s3_conf["bucket"], Key=key)
        return obj["Body"].read()
    except s3.exceptions.ClientError:
        return None

st.title("Employee Certificates – Grid View")

employees = list_generated_certificates()
if not employees:
    st.info("No certificates found in S3 under `Gen_certificates/`.")
    st.stop()

GRID_COLS = 4
cols = st.columns(GRID_COLS)

for idx, emp in enumerate(employees):
    col = cols[idx % GRID_COLS]
    with col:
        with st.expander(emp["name"], expanded=False):
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
