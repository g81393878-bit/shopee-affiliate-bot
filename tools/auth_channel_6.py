import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from google_auth_oauthlib.flow import InstalledAppFlow

TOOLS_DIR = pathlib.Path(__file__).resolve().parent
secret_file = TOOLS_DIR / "client_secret_6.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
print("Opening browser for OAuth...")
creds = flow.run_local_server(port=0, open_browser=True, prompt='consent', access_type='offline')

target_token_file = TOOLS_DIR / "youtube_token_6.json"
target_token_file.write_text(creds.to_json(), encoding="utf-8")
print("SUCCESS: Saved youtube_token_6.json successfully!")
