
import re

def test_regex():
    print("Testing Regex...")
    remainder = "FGC-"
    
    try:
        # The exact pattern I used
        pattern = r'(?i)^[\s\-_()\[\]FGC]*$'
        print(f"Pattern: {pattern}")
        
        if re.match(pattern, remainder):
            print("Match successful")
        else:
            print("Match failed")
            
    except re.error as e:
        print(f"Regex Error: {e}")
    except Exception as e:
        print(f"Other Error: {e}")

test_regex()
