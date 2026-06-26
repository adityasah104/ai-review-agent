import asyncio
from src.azure_client.auth import get_auth_headers
import httpx
from src.config.settings import settings

async def main():
    print("Testing Azure DevOps Authentication...")
    try:
        # Step 1: Try to get the token
        headers = await get_auth_headers()
        print(f"✅ Successfully generated Auth Headers! (Using {headers['Authorization'].split(' ')[0]})")
        
        # Step 2: Test the token against the Azure DevOps API
        print(f"\nTesting connection to organization: {settings.AZURE_DEVOPS_ORG}...")
        url = f"https://dev.azure.com/{settings.AZURE_DEVOPS_ORG}/_apis/projects?api-version=7.1"
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            
            if resp.status_code == 200:
                print("✅ SUCCESS: The token works! Azure DevOps accepted the connection.")
                projects = resp.json().get("value", [])
                print(f"Found {len(projects)} projects visible to this Service Principal.")
            elif resp.status_code == 203:
                print("⚠️ WARNING (203): The token is valid, but Azure DevOps is redirecting to a login page.")
                print("This usually means 'Third-party application access via OAuth' is NOT turned on in your Organization Policies.")
            elif resp.status_code == 401:
                print("❌ FAILED (401 Unauthorized): The token is invalid, or the Service Principal has no access.")
            else:
                print(f"❌ FAILED: Status code {resp.status_code}")
                print(resp.text)
                
    except httpx.HTTPStatusError as e:
        print(f"❌ FAILED: HTTP Error when generating token: {e}")
        if e.response.status_code == 401:
            print("Reason: 401 Unauthorized from Microsoft. Your Client ID or Secret in the .env is STILL incorrect.")
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
