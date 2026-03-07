from Jarvis.core.tools import Tools

tools = Tools()

print("Test 1:", tools.calculate("2+3*4"))
print("Test 2:", tools.calculate("sqrt(16)"))
print("Test 3:", tools.calculate("sin(0)"))
print("Test 4:", tools.calculate("10/2"))

# malicious test
print("Test 5:", tools.calculate("__import__('os').system('dir')"))
