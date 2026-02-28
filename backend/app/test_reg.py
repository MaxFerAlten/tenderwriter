import httpx
import asyncio
import json

async def test():
    async with httpx.AsyncClient() as client:
        data = {
            "name": "Test User Manual",
            "email": "test_manual_3@example.com",
            "password": "testpassword123"
        }
        print(f"Sending data: {json.dumps(data)}")
        try:
            response = await client.post(
                "http://localhost:8000/api/auth/register", 
                json=data,
                timeout=10.0
            )
            print(f"Status: {response.status_code}")
            print(f"Body: {response.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
