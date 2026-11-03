import httpx
import time

JUDGE0_URL = "https://ce.judge0.com"
PYTHON_LANGUAGE_ID = 100

source_code = """
a = int(input())
b = int(input())
print(a + b)
"""

stdin = "10\n20\n"

try:
    response = httpx.post(
        f"{JUDGE0_URL}/submissions",
        params={"base64_encoded": "false", "wait": "false"},
        json={
            "source_code": source_code,
            "language_id": PYTHON_LANGUAGE_ID,
            "stdin": stdin,
            "cpu_time_limit": 2,
            "memory_limit": 128000
        },
        timeout=20
    )

    response.raise_for_status()
    token = response.json()["token"]

    print("Code submitted successfully!")
    print("Submission token:", token)

    while True:
        result_response = httpx.get(
            f"{JUDGE0_URL}/submissions/{token}",
            params={"base64_encoded": "false"},
            timeout=20
        )

        result_response.raise_for_status()
        result = result_response.json()

        status = result["status"]["description"]
        print("Execution status:", status)

        if result["status"]["id"] not in (1, 2):
            break

        time.sleep(1)

    print("\n--- Execution Result ---")
    print("Status:", status)
    print("Output:", result.get("stdout"))
    print("Error:", result.get("stderr"))
    print("Compile output:", result.get("compile_output"))

except httpx.HTTPError as error:
    print("Judge0 API error:", error)

except Exception as error:
    print("Unexpected error:", error)