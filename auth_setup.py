import os
from google_auth_oauthlib.flow import InstalledAppFlow

# Request both Calendar and Tasks scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]

def main():
    config_dir = 'config'
    credentials_path = os.path.join(config_dir, 'credentials.json')
    token_path = os.path.join(config_dir, 'token.json')

    # Ensure config directory exists
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

    if not os.path.exists(credentials_path):
        print("\n" + "="*60)
        print("⚠️  MISSING CREDENTIALS FILE")
        print("="*60)
        print(f"Please download your Desktop App OAuth Client credentials from Google Cloud Console")
        print(f"and save it as: {credentials_path}")
        print("-"*60)
        print("Steps to get credentials.json:")
        print("1. Go to Google Cloud Console (https://console.cloud.google.com/)")
        print("2. Enable 'Google Calendar API' and 'Google Tasks API' in your project.")
        print("3. Configure the OAuth Consent Screen (add your email as a Test User).")
        print("4. Go to Credentials -> Create Credentials -> OAuth Client ID.")
        print("5. Choose 'Desktop Application', name it, and click Create.")
        print("6. Download the JSON file and rename it to 'credentials.json'.")
        print("="*60 + "\n")
        return

    print("\n[OAuth Setup] Starting Google OAuth flow...")
    print("[OAuth Setup] A browser window will open asking you to sign in and grant permissions.")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)

        # Save credentials as credentials to token.json
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())
        
        print("\n" + "="*60)
        print("🎉 SUCCESS! Google Account successfully authenticated.")
        print(f"Token saved to: {token_path}")
        print("You can now run 'python start.py' to launch the Multi-MCP system.")
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n❌ Error during OAuth Setup: {str(e)}\n")

if __name__ == '__main__':
    main()
