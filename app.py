import os
import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

HEADER_ROW = ["submitted_at", "name", "score", "problems", "other_concerns", "patient_id", "duration_seconds"]

# ---------------------------------------------------------------------------
# Google Sheets client
# ---------------------------------------------------------------------------

def get_secret(name: str, default: str = "") -> str:
    """Read a secret from st.secrets first, then environment variables."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


@st.cache_resource
def get_client():
    spreadsheet_id = get_secret("GOOGLE_SHEET_ID")
    worksheet_name = get_secret("GOOGLE_WORKSHEET_NAME", "Responses")

    if not spreadsheet_id:
        st.error("Missing GOOGLE_SHEET_ID. Add it to .env or .streamlit/secrets.toml (see README.md).")
        st.stop()

    creds_json_text = get_secret("GOOGLE_SERVICE_ACCOUNT_JSON")
    creds_file = get_secret("GOOGLE_SERVICE_ACCOUNT_FILE")

    if creds_json_text:
        info = json.loads(creds_json_text)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    elif creds_file:
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    else:
        st.error(
            "Missing Google credentials. Set GOOGLE_SERVICE_ACCOUNT_FILE (path to "
            "the JSON key) or GOOGLE_SERVICE_ACCOUNT_JSON (the JSON itself) — see README.md."
        )
        st.stop()

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)

    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=1000, cols=len(HEADER_ROW))
        ws.append_row(HEADER_ROW)

    first_row = ws.row_values(1)
    if first_row != HEADER_ROW:
        ws.update("A1", [HEADER_ROW])

    return ws


def insert_response(name, score, problems, other_concerns, patient_id="", duration_seconds=None):
    ws = get_client()
    row = [
        datetime.now(timezone.utc).isoformat(),
        name or "(not provided)",
        score,
        json.dumps(problems),
        other_concerns or "",
        patient_id or "",
        round(duration_seconds, 2) if duration_seconds is not None else "",
    ]
    ws.append_row(row, value_input_option="RAW")


def fetch_responses() -> pd.DataFrame:
    ws = get_client()
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=HEADER_ROW)
    df = pd.DataFrame(records)

    def flatten_problems(p):
        try:
            items = json.loads(p) if isinstance(p, str) and p else []
        except Exception:
            return p
        return "; ".join(i.get("item", "") for i in items if isinstance(i, dict))

    if "problems" in df.columns:
        df["problems"] = df["problems"].apply(flatten_problems)
    if "submitted_at" in df.columns:
        df = df.sort_values("submitted_at", ascending=False)
    return df


# ---------------------------------------------------------------------------
# Data: problem list categories (word-for-word from the NCCN questionnaire).
# These English strings are the PERMANENT internal identifiers -- used as
# session_state keys and saved to the Sheet -- regardless of which language
# is displayed. Kannada is a pure display-text overlay on top (see
# load_text_content() / t() / t_category() / t_item() below).
# ---------------------------------------------------------------------------

PROBLEM_LIST = {
    "Physical Concerns": [
        "Pain", "Sleep", "Fatigue", "Tobacco use", "Substance use",
        "Memory or concentration", "Sexual health", "Changes in eating",
        "Loss or change of physical abilities",
    ],
    "Emotional Concerns": [
        "Worry or anxiety", "Sadness or depression", "Loss of interest or enjoyment",
        "Grief or loss", "Fear", "Loneliness", "Anger", "Changes in appearance",
        "Feelings of worthlessness or being a burden",
    ],
    "Social Concerns": [
        "Relationship with spouse or partner", "Relationship with children",
        "Relationship with family members", "Relationship with friends or coworkers",
        "Communication with health care team", "Ability to have children",
        "Prejudice or discrimination",
    ],
    "Practical Concerns": [
        "Taking care of myself", "Taking care of others", "Safety", "Work", "School",
        "Housing/Utilities", "Finances", "Insurance", "Transportation", "Child care",
        "Having enough food", "Access to medicine", "Treatment decisions",
    ],
    "Spiritual or Religious Concerns": [
        "Sense of meaning or purpose", "Changes in faith or beliefs",
        "Death, dying, or afterlife", "Conflict between beliefs and cancer treatments",
        "Relationship with the sacred", "Ritual or dietary needs",
    ],
}

# ---------------------------------------------------------------------------
# Bilingual text loading. English is the source of truth for which keys
# exist; Kannada falls back to English automatically for anything missing
# (or, right now, for everything -- nccn_text_kn.json is currently a
# PLACEHOLDER file, see README.md).
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).parent

@st.cache_data
def load_text_content():
    with open(APP_DIR / "nccn_text_en.json", encoding="utf-8") as f:
        en = json.load(f)
    kn = {}
    kn_path = APP_DIR / "nccn_text_kn.json"
    if kn_path.exists():
        with open(kn_path, encoding="utf-8") as f:
            kn = json.load(f)
    return en, kn

TEXT_EN, TEXT_KN = load_text_content()


def t(key: str) -> str:
    """UI string lookup, falling back to English if untranslated/missing."""
    lang = st.session_state.get("language", "en")
    if lang == "kn":
        val = TEXT_KN.get("ui", {}).get(key)
        if val:
            return val
    return TEXT_EN.get("ui", {}).get(key, key)


def t_category(category: str) -> str:
    lang = st.session_state.get("language", "en")
    if lang == "kn":
        val = TEXT_KN.get("categories", {}).get(category)
        if val:
            return val
    return TEXT_EN.get("categories", {}).get(category, category)


def t_item(item: str) -> str:
    lang = st.session_state.get("language", "en")
    if lang == "kn":
        val = TEXT_KN.get("items", {}).get(item)
        if val:
            return val
    return TEXT_EN.get("items", {}).get(item, item)


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

st.set_page_config(page_title="NCCN Distress Thermometer", page_icon="🌡️", layout="centered")

CSS = """
<style>
:root{
  --nccn-blue-dark:#0b3d6e;
  --nccn-blue-mid:#1f6fae;
  --nccn-blue-light:#e7f1f9;
  --nccn-blue-pale:#f4f9fd;
}
.stApp{ background:var(--nccn-blue-pale); color:#1a1a1a; }
.block-container{ max-width:1000px; }
.masthead{
  display:flex; align-items:center; gap:16px;
  padding:10px 0 16px 0; border-bottom:3px solid var(--nccn-blue-dark); margin-bottom:20px;
}
.logo-mark{
  width:52px; height:52px; flex-shrink:0;
  background:linear-gradient(180deg,var(--nccn-blue-mid),var(--nccn-blue-dark));
  color:#fff; border-radius:6px; display:flex; align-items:center; justify-content:center;
  font-weight:bold; font-size:13px;
}
.logo-text{ font-size:11px; color:var(--nccn-blue-dark); line-height:1.25; font-weight:bold; }
.title-sub{ font-size:20px; margin:0; }
.title-main{ font-size:22px; font-weight:bold; margin:0; }
.section-title{
  color:var(--nccn-blue-dark); font-size:16px; border-bottom:2px solid var(--nccn-blue-dark);
  padding-bottom:4px; margin-top:18px; margin-bottom:10px;
}
.cat-title{ font-size:14px; text-decoration:underline; margin:10px 0 2px 0; }
.cat2a{
  border:1px solid var(--nccn-blue-dark); display:inline-block; padding:6px 10px;
  font-weight:bold; font-size:12px; margin-top:20px;
}
div[data-testid="stVerticalBlockBorderWrapper"]{ background:#fff; border-radius:6px; }
button[data-testid="stBaseButton-secondary"] p,
button[data-testid="stBaseButton-primary"] p {
  white-space: nowrap !important;
  overflow: visible !important;
  text-overflow: unset !important;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def render_header():
    st.markdown(
        f"""
        <div class="masthead">
          <div class="logo-mark">NCCN</div>
          <div class="logo-text">National<br>Comprehensive<br>Cancer<br>Network&reg;</div>
          <div>
            <p class="title-sub">{t('titleSub')}</p>
            <p class="title-main">{t('titleMain')}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def thermometer_svg(selected):
    top_y, bottom_y, bulb_r = 20, 460, 34
    step = (bottom_y - bulb_r - top_y) / 10
    tube_x, tube_w = 90, 26
    parts = [
        f'<svg width="200" height="500" viewBox="0 0 200 500" xmlns="http://www.w3.org/2000/svg">'
    ]
    parts.append(
        f'<rect x="{tube_x - tube_w/2}" y="{top_y}" width="{tube_w}" '
        f'height="{bottom_y - top_y - bulb_r}" rx="13" fill="#ffffff" stroke="#0b3d6e" stroke-width="3"/>'
    )
    parts.append(
        f'<circle cx="{tube_x}" cy="{bottom_y}" r="{bulb_r}" fill="#ffffff" stroke="#0b3d6e" stroke-width="3"/>'
    )
    for i in range(10, -1, -1):
        y = top_y + (10 - i) * step + 14
        cx = tube_x + 55
        fill = "#1f6fae" if selected == i else "#f4f9fd"
        num_fill = "#ffffff" if selected == i else "#0b3d6e"
        parts.append(
            f'<line x1="{tube_x+tube_w/2}" y1="{y}" x2="{cx-14}" y2="{y}" stroke="#0b3d6e" stroke-width="2"/>'
            f'<circle cx="{cx}" cy="{y}" r="14" fill="{fill}" stroke="#0b3d6e" stroke-width="2"/>'
            f'<text x="{cx}" y="{y+5}" text-anchor="middle" font-size="13" font-weight="bold" '
            f'fill="{num_fill}" font-family="Arial">{i}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

if "page" not in st.session_state:
    st.session_state.page = "language"  # "language" -> "form" -> "done"
if "language" not in st.session_state:
    st.session_state.language = "en"
if "score" not in st.session_state:
    st.session_state.score = None
if "name" not in st.session_state:
    st.session_state.name = ""
if "checked" not in st.session_state:
    st.session_state.checked = {}
if "other_concerns" not in st.session_state:
    st.session_state.other_concerns = ""
if "patient_id" not in st.session_state:
    # From a personalized link like ?pid=BE-P014, generated by the study
    # dashboard. Empty string if opened without one (e.g. internal testing).
    st.session_state.patient_id = st.query_params.get("pid", "")
if "session_start_time" not in st.session_state:
    st.session_state.session_start_time = datetime.now(timezone.utc)

render_header()

# ---------------------------------------------------------------------------
# PAGE: language choice
# ---------------------------------------------------------------------------

if st.session_state.page == "language":
    st.markdown(
        "<h3 style='text-align:center'>Choose your language<br>ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ</h3>",
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("English", use_container_width=True, type="primary"):
            st.session_state.language = "en"
            st.session_state.page = "form"
            st.rerun()
    with col2:
        if st.button("ಕನ್ನಡ", use_container_width=True, type="primary"):
            st.session_state.language = "kn"
            st.session_state.page = "form"
            st.rerun()

# ---------------------------------------------------------------------------
# PAGE: form (thermometer + problem list, all on one page)
# ---------------------------------------------------------------------------

elif st.session_state.page == "form":
    st.session_state.name = st.text_input(t("nameLabel"), value=st.session_state.name)

    therm_col, problems_col = st.columns([1, 2])

    with therm_col:
        st.markdown(f'<div class="section-title">{t("thermometerSectionTitle")}</div>', unsafe_allow_html=True)
        st.write(t("distressDefinition"))
        st.markdown(f"**{t('instructions')}**")

        st.markdown(
            f"<p style='text-align:center;font-weight:bold;color:#0b3d6e;margin-bottom:4px'>{t('extremeDistress')}</p>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='display:flex;justify-content:center'>{thermometer_svg(st.session_state.score)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='text-align:center;font-weight:bold;color:#0b3d6e;margin-top:4px'>{t('noDistress')}</p>",
            unsafe_allow_html=True,
        )

        score_cols = st.columns(4)
        for i in range(11):
            c = score_cols[i % 4]
            if c.button(str(i), key=f"score_{i}", use_container_width=True):
                st.session_state.score = i
                st.rerun()

        if st.session_state.score is not None:
            st.markdown(
                f"<p style='text-align:center;color:#0b3d6e;font-weight:bold;'>"
                f"{t('scoreSelectedLabel')}: {st.session_state.score} / 10</p>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<p style='text-align:center;color:#999;'>{t('noScoreLabel')}</p>",
                unsafe_allow_html=True,
            )

    with problems_col:
        st.markdown(f'<div class="section-title">{t("problemListSectionTitle")}</div>', unsafe_allow_html=True)
        st.markdown(f"**{t('problemListIntro')}**")

        left_cats = ["Physical Concerns", "Emotional Concerns", "Social Concerns"]
        right_cats = ["Practical Concerns", "Spiritual or Religious Concerns"]

        col_left, col_right = st.columns(2)

        with col_left:
            for cat in left_cats:
                st.markdown(f'<div class="cat-title">{t_category(cat)}</div>', unsafe_allow_html=True)
                for item in PROBLEM_LIST[cat]:
                    key = f"chk::{cat}::{item}"
                    st.session_state.checked[key] = st.checkbox(
                        t_item(item), value=st.session_state.checked.get(key, False), key=key
                    )

        with col_right:
            for cat in right_cats:
                st.markdown(f'<div class="cat-title">{t_category(cat)}</div>', unsafe_allow_html=True)
                for item in PROBLEM_LIST[cat]:
                    key = f"chk::{cat}::{item}"
                    st.session_state.checked[key] = st.checkbox(
                        t_item(item), value=st.session_state.checked.get(key, False), key=key
                    )

            st.markdown(f'<div class="cat-title">{t("otherConcernsLabel")}</div>', unsafe_allow_html=True)
            st.session_state.other_concerns = st.text_area(
                "Other Concerns", value=st.session_state.other_concerns,
                label_visibility="collapsed", height=100,
            )

    st.write("")
    if st.button(t("submitButton"), type="primary", use_container_width=True):
        if st.session_state.score is None:
            st.warning(t("submitMissingScore"))
        else:
            problems = []
            for key, is_checked in st.session_state.checked.items():
                if is_checked:
                    _, cat, item = key.split("::", 2)
                    problems.append({"category": cat, "item": item})
            duration_seconds = (
                datetime.now(timezone.utc) - st.session_state.session_start_time
            ).total_seconds()
            try:
                insert_response(
                    st.session_state.name,
                    st.session_state.score,
                    problems,
                    st.session_state.other_concerns,
                    patient_id=st.session_state.patient_id,
                    duration_seconds=duration_seconds,
                )
                st.session_state.page = "done"
                st.rerun()
            except Exception as e:
                st.error(f"Could not save response: {e}")

# ---------------------------------------------------------------------------
# PAGE: confirmation
# ---------------------------------------------------------------------------

elif st.session_state.page == "done":
    st.markdown(
        f"<div style='text-align:center;padding:40px 0;'>"
        f"<div style='font-size:48px;color:#1f6fae;'>&#10003;</div>"
        f"<h2 style='color:#0b3d6e;'>{t('thankYouTitle')}</h2>"
        f"<p>{t('thankYouMessage')}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.button(t("startOverButton"), type="primary"):
        st.session_state.page = "language"
        st.session_state.score = None
        st.session_state.name = ""
        st.session_state.checked = {}
        st.session_state.other_concerns = ""
        st.session_state.session_start_time = datetime.now(timezone.utc)
        st.rerun()

st.markdown(f'<div class="cat2a">{t("cat2aNote")}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Admin sidebar: view / export saved responses
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Admin")
    admin_password_required = get_secret("ADMIN_PASSWORD")
    show_admin = True
    if admin_password_required:
        entered = st.text_input("Admin password", type="password")
        show_admin = entered == admin_password_required

    if show_admin:
        if st.button("Load / refresh responses"):
            st.session_state["_admin_df"] = fetch_responses()

        df = st.session_state.get("_admin_df")
        if df is not None:
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download CSV", data=csv,
                file_name="distress_thermometer_responses.csv", mime="text/csv",
            )
        else:
            st.caption("Click 'Load / refresh responses' to view saved data.")
    elif admin_password_required:
        st.caption("Enter the admin password to view responses.")
