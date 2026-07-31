import urllib.request
import re

with open("app.js", "r") as f:
    content = f.read()
    
# extremely basic brace matching
def check_braces(text):
    stack = []
    in_string = False
    str_char = ""
    for i, c in enumerate(text):
        if in_string:
            if c == str_char and text[i-1] != "\\":
                in_string = False
            continue
        if c in "\"'`":
            in_string = True
            str_char = c
            continue
        if c in "{[(": 
            stack.append((c, i))
        elif c in "}])":
            if not stack:
                return f"Unmatched closing {c} at {i}"
            last = stack.pop()[0]
            if (last == "{" and c != "}") or (last == "[" and c != "]") or (last == "(" and c != ")"):
                return f"Mismatched closing {c} at {i}, expected match for {last}"
    if stack:
        return f"Unclosed brackets: {stack}"
    return "OK"
    
print(check_braces(content))
