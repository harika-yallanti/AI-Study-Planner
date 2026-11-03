from app.services.code_executor import execute_python


source_code = """
a = int(input())
b = int(input())
print(a + b)
"""

result = execute_python(source_code, "10\n20\n")

print("\n--- Code Executor Service Test ---")
print("Success:", result["success"])
print("Status:", result["status"])
print("Output:", result["stdout"])
print("Error:", result["stderr"])
print("Message:", result["message"])