import os
import streamlit as st
import boto3

# ---------------- S3 HELPERS ---------------- #

def get_s3_client():
    """
    Uses the same secrets structure as your generator app:
    [s3]
    aws_access_key_id = "..."
    aws_secret_access_key = "..."
    region = "ap-south-1"
    bucket = "your-bucket-name"
    """
    s3_conf = st.secrets["s3"]
    return boto3.client(
        "s3",
        aws_access_key_id=s3_conf["aws_access_key_id"],
        aws_secret_access_key=s3_conf["aws_secret_access_key"],
        region_name=s3_conf["region"],
    )


@st.cache_data(ttl=300)
def list_generated_certificates():
    """
    List all certificates under Gen_certificates/ and extract employee names.

    Expected key pattern:
        Gen_certificates/certificate_EMPNAME.png
    """
    s3_conf = st.secrets["s3"]
    s3 = get_s3_client()

    prefix = "Gen_certificates/"
    resp = s3.list_objects_v2(Bucket=s3_conf["bucket"], Prefix=prefix)

    # Debug info visible in the app if needed
    # st.write("Raw S3 list_objects_v2 response:", resp)

    contents = resp.get("Contents", [])
    if not contents:
        return []

    employees = []
    for obj in contents:
        key = obj.get("Key")
        if not key or key.endswith("/"):
            continue

        filename = key.split("/")[-1]               # certificate_Ravi_Kumar.png
        name_part = os.path.splitext(filename)[0]   # certificate_Ravi_Kumar

        if name_part.startswith("certificate_"):
            emp_name = name_part.replace("certificate_", "", 1)
        else:
            emp_name = name_part

        employees.append({"name": emp_name, "key": key})

    employees.sort(key=lambda x: x["name"].lower())
    return employees


def load_certificate_bytes_by_key(key: str) -> bytes | None:
    """
    Load the raw PNG bytes for a given S3 key.
    """
    s3_conf = st.secrets["s3"]
    s3 = get_s3_client()
    try:
        obj = s3.get_object(Bucket=s3_conf["bucket"], Key=key)
        return obj["Body"].read()
    except s3.exceptions.ClientError:
        return None


# ---------------- STREAMLIT UI ---------------- #

st.set_page_config(page_title="Certificate Viewer", layout="wide")
st.title("Employee Certificate Viewer")

st.write("Browse all employees whose certificates have been generated and stored in S3.")

employees = list_generated_certificates()

if not employees:
    st.info("No certificates found in S3 under `Gen_certificates/`. "
            "Check bucket name, prefix, and that files actually exist there.")
    st.stop()

st.subheader("Click an employee to view their certificate")

GRID_COLS = 4
cols = st.columns(GRID_COLS)

selected_emp = st.session_state.get("selected_emp")

for idx, emp in enumerate(employees):
    col = cols[idx % GRID_COLS]
    with col:
        if st.button(emp["name"], key=f"emp_{idx}", use_container_width=True):
            st.session_state["selected_emp"] = emp
            selected_emp = emp

st.markdown("---")

if selected_emp:
    st.subheader(f"Certificate for: {selected_emp['name']}")
    cert_bytes = load_certificate_bytes_by_key(selected_emp["key"])

    if cert_bytes:
        st.image(cert_bytes, caption=selected_emp["name"], use_column_width=True)
        st.download_button(
            label="Download certificate",
            data=cert_bytes,
            file_name=selected_emp["key"].split("/")[-1],
            mime="image/png",
        )
    else:
        st.error("Could not load certificate from S3. Please try again.")
else:
    st.info("Select an employee from the grid above to view their certificate.")
