
import re

def format_code(project):
    if not project:
        print("Project is None/Empty")
        return "—"
    
    # Mocking project object
    class Project:
        def __init__(self, po):
            self.po_number = po
            
    if isinstance(project, str):
        print(f"Project is string: {project}")
        po = project
    else:
        po = (project.po_number or "").strip()
    
    print(f"Processing PO: '{po}'")
    
    match = re.search(r'(\d{8})', po)
    if match:
        digits = match.group(1)
        remainder = po.replace(digits, "", 1)
        print(f"Digits: {digits}, Remainder: '{remainder}'")
        
        # Test the regex
        pattern = r'^(?i)[\s\-_()\[\]FGC]*$'
        try:
            if re.match(pattern, remainder):
                print("Match!")
                return digits
            else:
                print("No match")
        except re.error as e:
            print(f"Regex Error: {e}")
            
    return po or "PEI"

# Test cases
print("--- Test 1: Standard ---")
format_code(type('obj', (object,), {'po_number': 'FGC-12345678'}))

print("\n--- Test 2: Spaces ---")
format_code(type('obj', (object,), {'po_number': 'FGC 12345678'}))

print("\n--- Test 3: Suffix ---")
format_code(type('obj', (object,), {'po_number': '12345678 (FGC)'}))

print("\n--- Test 4: Invalid Regex? ---")
try:
    re.compile(r'^(?i)[\s\-_()\[\]FGC]*$')
    print("Regex compiles successfully")
except re.error as e:
    print(f"Regex compilation failed: {e}")
