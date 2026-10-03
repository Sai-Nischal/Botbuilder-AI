import subprocess
import json
import os
from pathlib import Path

def run_gmaps_scraper(url: str):
    """
    Runs the node.js Playwright script and returns the extracted data.
    """
    try:
        # Path to the script we created
        script_path = Path(__file__).resolve().parent.parent / "fetch_and_save.js"
        
        # Run the script using node
        result = subprocess.run(
            ["node", str(script_path), url],
            capture_output=True,
            text=True,
            timeout=90
        )
        
        if result.returncode != 0:
            print(f"[GMAPS ERROR] Script failed: {result.stderr}")
            return None
            
        # The script prints "Successfully saved..." then the JSON object.
        # We need to extract only the JSON part.
        output = result.stdout
        lines = output.splitlines()
        
        # Find the line where the JSON object starts
        json_start_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('{'):
                json_start_idx = i
                break
        
        if json_start_idx != -1:
            json_str = "\n".join(lines[json_start_idx:])
            return json.loads(json_str)
            
        return None
    except Exception as e:
        print(f"[GMAPS INTEGRATION ERROR] {e}")
        return None
