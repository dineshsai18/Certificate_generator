import io
from pathlib import Path
from datetime import datetime
import boto3
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ----- Paths -----
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
PHOTOS_DIR = BASE_DIR / "photos"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ----- Page config -----
st.set_page_config(layout="wide")
st.title("Group Enterprise Analytics")
st.write("Year-End Appreciation Certificates (Local Version)")

# ----- Helpers -----

def load_local_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")

def list_photo_files() -> list[str]:
    if not PHOTOS_DIR.exists():
        return []
    files = [p.name for p in PHOTOS_DIR.iterdir() if p.is_file()]
    return files

def rounded_rect_mask(size, radius):
    w, h = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    return mask

def build_certificate(emp_name: str, line: str, photo_filename: str) -> bytes:
    # 1) Load base template and photo
    template_path = ASSETS_DIR / "base_certificate.png"
    template = load_local_image(template_path)
    cert_w, cert_h = template.size  # expected 1024 x 1024

    photo_path = PHOTOS_DIR / photo_filename
    photo_img = load_local_image(photo_path)

    # -------- Place photo in left rounded card --------
    photo_target_w = 415
    photo_target_h = 330
    photo_x = 168
    photo_y = 755

    photo_img = photo_img.resize((photo_target_w, photo_target_h), Image.LANCZOS)

    photo_size = (photo_target_w, photo_target_h)

    mask = rounded_rect_mask(photo_size, radius=75)
    photo_rgba = photo_img.convert("RGBA")
    photo_rgba.putalpha(mask)

    template.paste(photo_rgba, (photo_x, photo_y), mask=photo_rgba)

    draw = ImageDraw.Draw(template)

    # -------- Fonts --------
    try:
        font_line = ImageFont.truetype("DejaVuSans.ttf", 56)
        font_name = ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
    except Exception:
        font_line = ImageFont.load_default()
        font_name = ImageFont.load_default()

    def text_wh(text, font):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    # -------- One-liner under "thank you" --------
    max_line_width = int(cert_w * 0.8)

    words = line.split()
    lines = []
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        w_test, _ = text_wh(test, font_line)
        if w_test <= max_line_width:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    lines = lines[:3]

    total_h = sum(text_wh(l, font_line)[1] for l in lines) + (len(lines) - 1) * 10
    start_y = 550
    y = start_y - total_h // 2

    for l in lines:
        w_l, h_l = text_wh(l, font_line)
        x_l = (cert_w - w_l) // 2
        draw.text((x_l, y), l, font=font_line, fill=(255, 255, 255))
        y += h_l + 10

    # -------- Name in right purple pill --------
    name_text = emp_name.upper()
    pill_left = 700
    pill_right = 850
    pill_top = 800
    pill_bottom = 1000

    pill_width = pill_right - pill_left
    pill_height = pill_bottom - pill_top

    words = name_text.split()
    lines = []
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        w_test, _ = text_wh(test, font_name)
        if w_test <= pill_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    lines = lines[:2]

    line_heights = [text_wh(l, font_name)[1] for l in lines]
    total_h = sum(line_heights) + (len(lines) - 1) * 6
    y = pill_top + (pill_height - total_h) // 2

    for l in lines:
        w_l, h_l = text_wh(l, font_name)
        x_l = pill_left + (pill_width - w_l) // 2
        draw.text((x_l, y), l, font=font_name, fill=(255, 255, 255))
        y += h_l + 6

    out = io.BytesIO()
    template.save(out, format="PNG")
    out.seek(0)
    return out.getvalue()

def load_dataframes():
    emp_path = DATA_DIR / "employees.csv"
    mgr_path = DATA_DIR / "manager_passcodes.csv"

    if not emp_path.exists():
        st.error("Missing data/employees.csv. Please create it with EMP_ID,EMP_NAME,MANAGER_NAME,CERT_LINE,GENERATED_AT,GENERATED_BY.")
        st.stop()
    if not mgr_path.exists():
        st.error("Missing data/manager_passcodes.csv. Please create it with MANAGER_NAME,PASSCODE.")
        st.stop()

    emp_df = pd.read_csv(emp_path)
    mgr_df = pd.read_csv(mgr_path)
    return emp_df, mgr_df

def get_s3_client():
    s3_conf = st.secrets["s3"]
    return boto3.client(
        "s3",
        aws_access_key_id=s3_conf["aws_access_key_id"],
        aws_secret_access_key=s3_conf["aws_secret_access_key"],
        region_name=s3_conf["region"],
    )

def save_certificate_to_s3(png_bytes: bytes, key: str):
    """
    key example: 'Gen_certificates/certificate_EMPNAME.png'
    """
    s3_conf = st.secrets["s3"]
    s3 = get_s3_client()
    s3.put_object(
        Bucket=s3_conf["bucket"],
        Key=key,
        Body=png_bytes,
        ContentType="image/png",
    )

def certificate_exists_in_s3(emp_name: str) -> bool:
    s3_conf = st.secrets["s3"]
    s3 = get_s3_client()
    key = f"Gen_certificates/certificate_{emp_name}.png"
    try:
        s3.head_object(Bucket=s3_conf["bucket"], Key=key)
        return True
    except s3.exceptions.ClientError:
        return False

def load_certificate_from_s3(emp_name: str) -> bytes | None:
    s3_conf = st.secrets["s3"]
    s3 = get_s3_client()
    key = f"Gen_certificates/certificate_{emp_name}.png"
    try:
        obj = s3.get_object(Bucket=s3_conf["bucket"], Key=key)
        return obj["Body"].read()
    except s3.exceptions.ClientError:
        return None


def save_employees(emp_df: pd.DataFrame):
    emp_path = DATA_DIR / "employees.csv"
    emp_df.to_csv(emp_path, index=False)

# ----- Session state for verification -----
if "verified" not in st.session_state:
    st.session_state.verified = False

# ----- Layout: Inputs and Certificate -----
Inputs_col, Certificate_col = st.columns([3, 7])

emp_df, mgr_pass_df = load_dataframes()

with Inputs_col:
    # Manager dropdown
    mgr_names = sorted(emp_df["MANAGER_NAME"].dropna().unique().tolist())
    manager_options = ["-- Select your name --"] + mgr_names
    manager = st.selectbox("Manager", manager_options, index=0)

    if manager == "-- Select your name --":
        st.stop()

    pass_input = st.text_input("Enter your passcode", type="password")

    if st.button("Verify"):
        row = mgr_pass_df[mgr_pass_df["MANAGER_NAME"] == manager]
        if row.empty or pass_input != str(row.iloc[0]["PASSCODE"]):
            st.error("Invalid passcode.")
            st.stop()
        else:
            st.session_state.verified = True
            st.success("Verified.")

    if not st.session_state.verified:
        st.stop()

    # Team members for this manager
    manager_emp_df = emp_df[emp_df["MANAGER_NAME"] == manager].copy()
    if manager_emp_df.empty:
        st.warning("No team members found for this manager.")
        st.stop()

    #def label_row(row):
    #    status = "generated" if pd.notna(row["GENERATED_AT"]) else "not generated"
    #    return f"{row['EMP_NAME']} ({status})"
    
    def label_row(row):
        exists = certificate_exists_in_s3(row["EMP_NAME"])
        status = "generated" if exists else "not generated"
        return f"{row['EMP_NAME']} ({status})"

    #def label_row(row):
    #    try:
    #        exists = certificate_exists_in_s3(row["EMP_NAME"])
    #        status = "generated" if exists else "not generated"
    #        return f"{row['EMP_NAME']} ({status})"
    #    except Exception as e:
    #        st.write("Error in label_row for row:", dict(row))
    #        st.write("Exception:", str(e))
    #        return f"{row.get('EMP_NAME', 'UNKNOWN')} (error)"
    #
    #st.write("manager_emp_df columns:", list(manager_emp_df.columns))
    manager_emp_df["LABEL"] = manager_emp_df.apply(label_row, axis=1)
    emp_choice = st.selectbox("Select team member", manager_emp_df["LABEL"])
    row = manager_emp_df[manager_emp_df["LABEL"] == emp_choice].iloc[0]

    # Photo choice from local photos folder
    photo_files = list_photo_files()
    if not photo_files:
        st.error("No photos found in the 'photos' folder.")
        st.stop()

    photo_options = ["-- Select photo --"] + photo_files
    photo_choice = st.selectbox("Choose the Photo", photo_options, index=0)

    if photo_choice == "-- Select photo --":
        st.stop()

    st.caption("Preview of selected photo:")
    st.image(str(PHOTOS_DIR / photo_choice), width=250)

with Certificate_col:
    st.header("Write a catchy one liner about the team member")
    #cert_line = st.text_input(" ", value=row.get("CERT_LINE", "") or "")
    cert_line = st.text_input(" ", value=(row.get("CERT_LINE") or ""))
    st.caption(" ")

    Sample, Certificate = st.columns([3, 7])

    with Sample:
        emp_name = row["EMP_NAME"]
        existing_png = load_certificate_from_s3(str(emp_name))

        if existing_png is not None:
            st.caption("Already generated (from S3). You can regenerate.")
            st.image(existing_png)
        else:
            sample_path = ASSETS_DIR / "sample_certificate.png"
            if sample_path.exists():
                st.caption("Certificate not generated yet. Sample template below.")
                st.image(str(sample_path))
            else:
                st.caption("Certificate not generated yet.")
            
        #generated_file = OUTPUT_DIR / f"certificate_{emp_name}.png"
        #if generated_file.exists():
        #    st.caption("Already generated. You can regenerate.")
        #    st.image(str(generated_file))
        #else:
        #    sample_path = ASSETS_DIR / "sample_certificate.png"
        #    if sample_path.exists():
        #        st.caption("Certificate not generated yet. Sample template below.")
        #        st.image(str(sample_path))
        #    else:
        #        st.caption("Certificate not generated yet.")

    with Certificate:
        if st.button("Generate certificate"):
            png_bytes = build_certificate(
                emp_name=row["EMP_NAME"],
                line=cert_line,
                photo_filename=photo_choice,
            )

            # Save to output folder
            # file_name = f"certificate_{row['EMP_NAME']}.png"
            # out_path = OUTPUT_DIR / file_name
            # with open(out_path, "wb") as f:
            #     f.write(png_bytes)
                
            s3_key = f"Gen_certificates/certificate_{row['EMP_NAME']}.png"
            save_certificate_to_s3(png_bytes, s3_key)

            # Update dataframe and CSV (mark generated)
            emp_df.loc[emp_df["EMP_ID"] == row["EMP_ID"], "GENERATED_AT"] = datetime.now().isoformat()
            emp_df.loc[emp_df["EMP_ID"] == row["EMP_ID"], "GENERATED_BY"] = manager
            emp_df.loc[emp_df["EMP_ID"] == row["EMP_ID"], "CERT_LINE"] = cert_line
            save_employees(emp_df)

            st.success("Certificate generated & saved. Download below.")
            st.image(png_bytes, caption=row["EMP_NAME"])
            st.download_button(
                label="Download PNG",
                data=png_bytes,
                file_name=f"certificate_{row['EMP_NAME']}.png",
                mime="image/png",
            )
