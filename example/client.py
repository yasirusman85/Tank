import sys
import json
import asyncio
import httpx

async def main():
    # Target URL of the Tank agent route
    url = "http://127.0.0.1:8000/chat"
    
    # Query can be passed as CLI arguments, otherwise fallback to default
    query = "Please add 123 and 456"
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])

    print(f"Connecting to {url}...")
    print(f"Sending prompt: '{query}'")
    print("-" * 60)

    headers = {
        "x-session-id": "demo-session-101",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": query,
        "session_id": "demo-session-101"
    }

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("POST", url, json=payload, headers=headers, timeout=20.0) as response:
                if response.status_code != 200:
                    print(f"\033[91mError: Server returned status code {response.status_code}\033[0m")
                    body = await response.aread()
                    print(body.decode("utf-8"))
                    return

                current_event = None
                
                # Iterate over lines of the response stream
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith("event:"):
                        current_event = line.replace("event:", "").strip()
                    elif line.startswith("data:"):
                        data_str = line.replace("data:", "").strip()
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            data = data_str
                        
                        # Print SSE chunks based on event type
                        if current_event == "thought":
                            thought = data.get("thought", "")
                            # Gray text for internal reasoning
                            print(f"\033[90m[Thought]\033[0m {thought}")
                        elif current_event == "tool_call":
                            name = data.get("name")
                            args = data.get("arguments")
                            call_id = data.get("id")
                            # Yellow text for tool call start
                            print(f"\033[93m[Tool Call]\033[0m Invoking '{name}' with {args} (id: {call_id})")
                        elif current_event == "tool_response":
                            name = data.get("name")
                            result = data.get("result")
                            call_id = data.get("id")
                            # Green text for tool execution finish
                            print(f"\033[92m[Tool Response]\033[0m Tool '{name}' returned: {result} (id: {call_id})")
                        elif current_event == "token":
                            token = data.get("token", "")
                            # Stream tokens inline
                            sys.stdout.write(token)
                            sys.stdout.flush()
                        elif current_event == "done":
                            print(f"\n\033[94m[Done]\033[0m Connection closed successfully.")
        except httpx.RequestError as exc:
            print(f"\033[91mHTTP Request failed: {exc}\033[0m")

if __name__ == "__main__":
    # Ensure ANSI codes work on Windows terminals if possible
    if sys.platform == "win32":
        import os
        os.system("color")
        
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStream interrupted by user.")
