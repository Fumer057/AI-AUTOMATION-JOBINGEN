import os
import asyncio
import litellm

async def main():
    os.environ["GEMINI_API_KEY"] = "YOUR_API_KEY_HERE"
    litellm.set_verbose=True
    try:
        response = litellm.completion(
            model="gemini/gemini-1.5-flash",
            messages=[{"role": "user", "content": "Hello"}],
        )
        print("Success:", response)
    except Exception as e:
        print("Error with gemini-1.5-flash:", e)
        
    try:
        response = litellm.completion(
            model="gemini/gemini-1.5-flash-latest",
            messages=[{"role": "user", "content": "Hello"}],
        )
        print("Success with latest:", response)
    except Exception as e:
        print("Error with latest:", e)
        
    try:
        response = litellm.completion(
            model="gemini/gemini-1.5-pro",
            messages=[{"role": "user", "content": "Hello"}],
        )
        print("Success with pro:", response)
    except Exception as e:
        print("Error with pro:", e)

if __name__ == "__main__":
    asyncio.run(main())
