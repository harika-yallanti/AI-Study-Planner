import time
import httpx


JUDGE0_URL = "https://ce.judge0.com"
PYTHON_LANGUAGE_ID = 100

MAX_SOURCE_LENGTH = 20000
MAX_WAIT_SECONDS = 15


def execute_python(source_code: str, stdin: str = ""):

    if not source_code or not source_code.strip():
        return {
            "success": False,
            "status": "Invalid",
            "stdout": None,
            "stderr": "Python code cannot be empty.",
            "message": "Please enter your code."
        }

    if len(source_code) > MAX_SOURCE_LENGTH:
        return {
            "success": False,
            "status": "Invalid",
            "stdout": None,
            "stderr": "Code length exceeds the allowed limit.",
            "message": "The submitted code is too long."
        }

    try:
        with httpx.Client(timeout=20) as client:

            # Submit code to Judge0
            response = client.post(
                f"{JUDGE0_URL}/submissions",
                params={
                    "base64_encoded": "false",
                    "wait": "false"
                },
                json={
                    "source_code": source_code,
                    "language_id": PYTHON_LANGUAGE_ID,
                    "stdin": stdin,
                    "cpu_time_limit": 2,
                    "memory_limit": 128000
                }
            )

            response.raise_for_status()
            token = response.json()["token"]

            # Wait for execution result
            start_time = time.time()

            while time.time() - start_time < MAX_WAIT_SECONDS:

                result_response = client.get(
                    f"{JUDGE0_URL}/submissions/{token}",
                    params={"base64_encoded": "false"}
                )

                result_response.raise_for_status()
                result = result_response.json()

                status_id = result["status"]["id"]
                status_description = result["status"]["description"]

                # 1 = In Queue, 2 = Processing
                if status_id not in (1, 2):
                    return {
                        "success": status_id == 3,
                        "status": status_description,
                        "stdout": result.get("stdout"),
                        "stderr": result.get("stderr"),
                        "compile_output": result.get("compile_output"),
                        "time": result.get("time"),
                        "memory": result.get("memory"),
                        "message": status_description
                    }

                time.sleep(1)

            return {
                "success": False,
                "status": "Processing Timeout",
                "stdout": None,
                "stderr": None,
                "message": "Execution took too long. Please try again."
            }

    except httpx.HTTPError as error:
        return {
            "success": False,
            "status": "Service Error",
            "stdout": None,
            "stderr": str(error),
            "message": "Unable to connect to the code execution service."
        }

    except Exception as error:
        return {
            "success": False,
            "status": "Error",
            "stdout": None,
            "stderr": str(error),
            "message": "An unexpected execution error occurred."
        }