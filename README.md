# BLE_middle-layer
A python script set as a middle layer between Google Sheet and a smart Bluetooth Scale
ROBUST BLUETOOTH SCALES 
•	Mini Crane Scale (Generic/Various manufacturers)
o	Max Capacity: 500 kg (1100 lbs)
o	Min Weight (Readability/Division): Typically 0.1 kg or 0.2 kg
o	Type: Crane/Hanging Scale (portable for field use)
•	CUBLiFT CS-500
o	Max Capacity: 500 kg (0.5 ton / 1000 lb)
o	Min Weight (Minimum Loading): 10 kg
o	Type: Crane/Hanging Scale
•	HSCo PLCHQBT500 / PLSSWBT500
o	Max Capacity: 500 kg
o	Min Weight (Accuracy): 50g (0.05 kg) for some models, or 100g (0.1 kg) for others
o	Type: Platform Scale (requires a flat surface)
•	Iscale ISP-500M
o	Max Capacity: 500 kg
o	Min Weight (Accuracy): 50g (0.05 kg)
o	Type: Platform Scale 

ARCHITECTURE 
Gateway device:
1.	Python script: reads weight (serial or BLE), parses value, local buffer (CSV/sqlite)
2.	Authenticates to Google Sheets API using service-account JSON
3.	Appends row(s) to the shared Google Sheet
End-users:
  - Open Google Sheet on laptop / phone / tablet (live view)
  - Excel can download CSV or use Sheets → Excel export
  - (Optional) Data Studio/Looker studio dashboard reads the same sheet
Key behaviours:
 Gateway immediately writes to Google Sheets if network available.
 If network is down, gateway buffers locally (CSV or SQLite) and retries periodically.
Google Sheet is shared with the service-account email so the gateway can append rows.
Python Script generated and running on pydriod
Google Sheets setup (step-by-step)
1. Create a new Google Sheet; give it the name you used in `SPREADSHEET_NAME` (e.g., ` Weight_Logger`). In the sheet, optionally create columns: `ID|UTC Timestamp | Weight `.
2. Open Google Cloud Console and create a new Project (or use an existing one).
3. Enable the Google Sheets API and Google Drive API for the project.
4. Create a Service Account inside IAM & Admin → Service Accounts.
5. Create a JSON key for that service account and download. Put it into the same folder as the Python script.
6. Share the Google Sheet with the service account email ‘e.g., `my-service-account@project.iam.gserviceaccount.com` giving Editor access (File → Share).
7. Ensure `GOOGLE_CREDS_FILE` in the script matches the filename (e.g., `creds.json`) and `SPREADSHEET_NAME` matches the sheet title.
Setting Output up
 On Windows (laptop)
1. Install Python 3.8+ from python.org and enable pip.
2. Install packages in PowerShell:
Powershell
   pip install gspread oauth2client pyserial bleak requests
3. Pair the scale (Bluetooth pairing) so a Virtual COM port (e.g., COM4) appears in Device Manager.
4. Set `SERIAL_PORT = "COM4"` in the script, run:
Powershell
 python scale_to_sheets.py
 C. On Android (quick test / field)
Use Pydroid 3 (recommended) - install from Play Store.
Copy `scale_to_sheets.py` and `json file` to the phone storage (Pydroid folder).
Install required packages inside Pydroid (it has pip).
 Connect via Bluetooth (Android may limit access to classic SPP from Python; often easier to use BLE).
 Run script from Pydroid. (Android restrictions vary — if issues, use Pi or laptop as gateway.)
