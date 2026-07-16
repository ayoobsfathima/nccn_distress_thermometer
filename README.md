# NCCN Distress Thermometer — Streamlit + Google Sheets

A local, editable replica of the NCCN Distress Management questionnaire
(2 pages: Distress Thermometer + Problem List), with every response saved
as a new row in a Google Sheet.

## 1. Create the Google Sheet

1. Go to https://sheets.google.com and create a new blank spreadsheet.
   Name it whatever you like, e.g. "Distress Thermometer Responses".
2. Copy its ID out of the URL:
   `https://docs.google.com/spreadsheets/d/THIS_PART_IS_THE_ID/edit`
   -> this is your `GOOGLE_SHEET_ID`.
3. Leave the sheet otherwise empty — the app creates a "Responses" tab
   and header row automatically the first time it runs.

## 2. Create a Google service account (so the app can write to the sheet)

1. Go to https://console.cloud.google.com and create a project (or reuse one).
2. Enable two APIs for that project: **Google Sheets API** and **Google Drive API**
   (search for each under "APIs & Services -> Library" and click Enable).
3. Go to **APIs & Services -> Credentials -> Create Credentials -> Service account**.
   Give it any name, click through the defaults, then **Done**.
4. Open the new service account -> **Keys** tab -> **Add Key -> Create new key -> JSON**.
   This downloads a `.json` file — save it as `service_account.json` in this project folder.
5. Open that JSON file and copy the `client_email` value
   (looks like `something@your-project.iam.gserviceaccount.com`).
6. Back in your Google Sheet, click **Share** and share it with that email
   address, giving it **Editor** access. This step is required — without it
   the app can't write to the sheet.

## 3. Set up the project in VS Code

```bash
# create and activate a virtual environment
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate

# install dependencies
pip install -r requirements.txt

# add your credentials
cp .env.example .env
# then open .env and set GOOGLE_SHEET_ID
# (GOOGLE_SERVICE_ACCOUNT_FILE already points to service_account.json —
# just make sure that file is sitting in this same folder)
```

**Important:** add `service_account.json` and `.env` to `.gitignore` if you
put this in a git repo — both contain private credentials.

## 4. Run it

```bash
streamlit run app.py
```

This opens the app at `http://localhost:8501`. Fill out the thermometer and
problem list, submit — a new row appears in your Google Sheet.

## 5. Viewing saved responses

Open the **Admin** panel in the left sidebar and click **Load / refresh
responses** to see every submission in a table, with a **Download CSV**
button. Or just open the Google Sheet directly — every response is a
plain row there too. If you set `ADMIN_PASSWORD` in `.env`, the sidebar
panel is gated behind that password.

## 6. Deploying so others can access it

Locally it only runs on your machine. To get a public URL:
- **Streamlit Community Cloud** (free): push this folder to a GitHub repo
  (excluding `service_account.json` and `.env`!), connect it at
  https://share.streamlit.io, and add `GOOGLE_SHEET_ID`,
  `GOOGLE_SERVICE_ACCOUNT_JSON` (paste the full JSON key contents here
  instead of using the file), and `ADMIN_PASSWORD` under the app's
  **Secrets** settings.
- Any other host that runs Streamlit works the same way — just set the
  same environment variables (using `GOOGLE_SERVICE_ACCOUNT_JSON` instead
  of a file, since you usually can't upload files to those hosts).

## Files

- `app.py` — the Streamlit app
- `requirements.txt` — Python dependencies
- `.env.example` — template for local credentials
