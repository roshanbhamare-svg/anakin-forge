import json
import os
import asyncio
from dotenv import load_dotenv
from agent import run_laptop_agent_stream

load_dotenv()

async def run_evals():
    with open("eval_dataset.json", "r") as f:
        scenarios = json.load(f)
        
    api_key = os.getenv("GROQ_API_KEY")
    results = []
    
    print("=======================================")
    print("STARTING EVALS: Laptop Buying Agent")
    print("=======================================")
    
    for scenario in scenarios:
        print(f"\\n[RUNNING SCENARIO]: {scenario['id']}")
        print(f"Prompt: '{scenario['prompt']}'")
        
        passed = False
        actions_taken = []
        fatal_error = None
        
        try:
            # We iterate through the asynchronous generator
            async for chunk_str in run_laptop_agent_stream(scenario["prompt"], api_key, headless=True):
                if chunk_str:
                    clean_chunk = chunk_str.replace('\\n', '').strip()
                    if not clean_chunk:
                        continue
                    try:
                        chunk = json.loads(clean_chunk)
                    except Exception as json_e:
                        print(f"JSON Parse Error: {json_e}")
                        print(f"Raw chunk: {repr(chunk_str)}")
                        raise json_e
                        
                    if chunk.get("layer") == "Action":
                        if "Executing Action: " in chunk.get("status", ""):
                            actions_taken.append(chunk["status"].split(": ")[1])
                        elif chunk.get("status") == "Agent has finished.":
                            passed = True
                            
                    elif chunk.get("layer") == "Error":
                        fatal_error = chunk.get("status")
                        break
                        
        except Exception as e:
            fatal_error = str(e)
            
        # Determine success
        if passed and not fatal_error:
            print(f"✅ PASS: Scenario completed successfully.")
            results.append({"id": scenario["id"], "status": "PASS", "actions": actions_taken})
        else:
            print(f"❌ FAIL: Scenario failed.")
            print(f"Error: {fatal_error}")
            results.append({"id": scenario["id"], "status": "FAIL", "actions": actions_taken, "error": fatal_error})
            
    print("\\n=======================================")
    print("EVALUATION REPORT CARD")
    print("=======================================")
    passed_count = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    print(f"Score: {passed_count}/{total} ({(passed_count/total)*100:.1f}%)")
    for r in results:
        print(f" - {r['id']}: {r['status']}")

if __name__ == "__main__":
    asyncio.run(run_evals())
