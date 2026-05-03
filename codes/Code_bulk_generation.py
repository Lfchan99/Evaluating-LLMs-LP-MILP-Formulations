from openai import OpenAI
import json
import os
import pandas as pd
from datetime import datetime
import openai
import time
from dotenv import load_dotenv

# Load environment variables from a local .env file (not committed)
load_dotenv()

# --- SERVER CONFIGURATION ---
# Configure `BASE_URL` and `API_KEY` in a local .env file (see .env.example).
# Minimal required environment variables: BASE_URL, API_KEY
BASE_URL = os.getenv("BASE_URL")
API_KEY = os.getenv("API_KEY")

if not BASE_URL or not API_KEY:
    raise RuntimeError(
        "Environment variables BASE_URL and API_KEY must be set.\n"
        "Create a local .env file (see .env.example) or export them in your shell."
    )

# 1. Setup the Client using environment variables
client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

# --- MODELS AND TEMPERATURES TO TEST ---
# Use a dictionary to map a short "Alias" to the actual "Model_ID".
# Format: {"Alias": "Actual_Model_ID"}
models_config = {
    "Llama": "Llama-4-Scout-Q6_K",
    # "Mistral": "mistral-7b-v0.1"  <-- Example of how to add more
} 
temperatures_list = [0.2]

# --- ROBUSTNESS CONFIGURATION ---
num_instances = 5  # <-- Number of new iterations you want to generate in this run

# --- TEST CONFIGURATION ---
start_id = None
end_id = None

# --- RESUME CONFIGURATION ---
# FILL ALL THESE VARIABLES IF YOU NEED TO RESUME AN INTERRUPTED EXECUTION.
# LEAVE THEM AS None FOR A NORMAL EXECUTION FROM SCRATCH.
resume_from_model_alias = None  # e.g., "Llama" (Use the Alias here!)
resume_from_temp = None   # e.g., 0.5
resume_from_file = None   # e.g., "OR_problems_LP_MILP.xlsx"
resume_from_id = None    # e.g., 2

# Output folders
out_path = "./or_results/"
codes_path = os.path.join(out_path, "codes")
os.makedirs(codes_path, exist_ok=True)

# 2. SYSTEM PROMPT FOR PYOMO AND EXTRACTION
SYSTEM_PROMPT = """
You are an expert in Operations Research and Python programming. 
Your task is to convert operational research word problems into executable Python code strictly using the 'pyomo' library.

You must output ONLY valid JSON containing four keys:
1. "reasoning": A detailed explanation of the mathematical formulation (Decision variables, Objective, Constraints).
2. "difficulty": The formulation difficulty classification. It must be exactly one of: "Easy", "Medium", or "Hard".
3. "problem_type": The problem classification. It must be exactly one of: "Transportation", "Assignment", "Network Flow", "Facility Location", "Product Mix", "Blending", "Knapsack", "Set Covering", "Lot Sizing", "Scheduling", or "Other".
4. "code": The pure, executable Python Pyomo code to solve the problem. It must be solver-ready (using glpk). Do not include markdown formatting (like ```python) inside the string.

CRITICAL RULES FOR PYOMO MODELING:
1. VARIABLE DOMAINS (INTEGER VS CONTINUOUS): You must carefully analyze the real-world context of each decision variable. If a variable represents indivisible entities (e.g., number of workers, airplanes, vehicles, food, etc.), you MUST strictly declare it as an integer in Pyomo using `within=NonNegativeIntegers` or `within=Integers`. Do not let Pyomo default them to continuous domains.

CRITICAL PYOMO CODE OUTPUT FORMAT REQUIREMENTS:
1. Decision Variables: You must print the optimal values of all decision variables without any units, descriptive words, or natural language. Print strictly in the format `VariableName: Value` (e.g., `x: 5.0`, `airplanes[1]: 10.0`). If a variable is indexed, you MUST iterate through its sets and print each element individually.
2. Objective Value: After printing the variables, you must print the final optimal objective value using exactly this Python syntax: `print(f"OptimalValue: {value(model.obj)}")` (adapt 'model.obj' to match your actual objective function's name). Do not add units or extra words to this specific print statement.

DIFFICULTY CLASSIFICATION RULES:
- Easy: A formulation with few decision variables and mostly direct capacity, demand, or bound constraints, with minimal coupling between decisions.
- Medium: A formulation with multiple related decisions and indexed constraints that require coordinating flows, assignments, or balances across products, resources, locations, or periods.
- Hard: A formulation with tightly interdependent decisions, several layers of logical or temporal linking, and nontrivial auxiliary constraints to enforce structure such as sequencing, routing, selection, or state transitions.

PROBLEM TYPE CLASSIFICATION RULES:
- Transportation: Problems that decide how much to send from multiple origins to multiple destinations, subject to origin supply limits and destination demand requirements.
- Assignment: Problems that match resources, people, machines, or jobs to tasks in one-to-one or limited-capacity patterns, usually with binary variables; a discrete special case of transportation.
- Network Flow: Problems that route flow through a general node-arc network, with flow conservation at intermediate nodes and capacity bounds on arcs; unlike transportation, the structure is not restricted to origin-destination layers.
- Facility Location: Problems that decide which facilities to open or close and how demand or flow should be allocated to them, combining binary opening decisions with assignment or transportation decisions.
- Product Mix: Problems that decide the quantities of final products to produce in order to maximize profit or minimize cost under resource, capacity, or demand constraints.
- Blending: Problems that decide the proportions of inputs to combine into one or more outputs so that composition, quality, or balance requirements are satisfied; unlike product mix, the defining feature is mixture composition.
- Knapsack: Problems that select items or projects to maximize value or minimize cost under one or a few aggregate capacity, budget, or resource constraints, usually with binary variables.
- Set Covering: Problems that choose a minimum-cost collection of subsets so that every required element is covered at least once; if coverage must be exactly once, the structure is closer to set partitioning.
- Lot Sizing: Problems that decide how much to produce or order in each time period, usually with inventory balance constraints and sometimes fixed setup decisions.
- Scheduling: Problems that decide the timing, sequencing, and sometimes assignment of jobs or tasks over limited resources, subject to constraints such as capacity, precedence, or due dates.
- Other: Problems whose main mathematical structure does not clearly match any of the classifications above, or that combine multiple structures without one being dominant.

CLASSIFICATION INSTRUCTIONS:
- You must always assign exactly one difficulty label and exactly one problem type label.
- Base both classifications on the mathematical structure of the formulation, not on the industry or application context.

CLASSIFICATION TYPE CLARIFICATIONS:
- If the problem seems to belong to multiple categories, choose the dominant one.
- If none of the types clearly dominates, use "Other".
"""

# Updated to accept model_alias and model_id
def process_problems_bulk(files_list, model_alias, model_id, current_temp, resume_file=None, resume_id=None):
    log_filename = os.path.join(out_path, "experiment_log.jsonl")
    safe_model_alias = model_alias.replace("/", "-")
    
    skip_mode = False
    if resume_file is not None and resume_id is not None:
        skip_mode = True
        print(f"[*] Resume mode activated for this model/temp. Skipping until {resume_file}, Problem ID: {resume_id}...")
    
    for file in files_list:
        if skip_mode and file != resume_file:
            continue
            
        print(f"\n--- Processing file: {file} | Model: {model_alias} | Temp: {current_temp} ---")
        df = pd.read_excel(file)
        
        for index, row in df.iterrows():
            problem_id = str(row['problem_ID'])
            problem_text = str(row['description'])
            
            # --- TEST MODE CUTOFF ---
            if start_id is not None:
                if end_id is not None:
                    if not (start_id <= int(problem_id) <= end_id):
                        continue
                else:
                    if int(problem_id) < start_id:
                        continue
            
            # Check if we need to unlock the execution
            if skip_mode:
                if problem_id != str(resume_id):
                    continue  
                else:
                    skip_mode = False  
                    print(f"\n>>> RESUMING EXECUTION AT: {file} - Problem {problem_id} <<<\n")
            
            file_prefix = file.replace('.xlsx', '') 
            
            for _ in range(num_instances):
                iteration = 1
                while True:
                    # File naming now uses the short alias
                    code_filename = os.path.join(
                        codes_path, 
                        f"{file_prefix}_{safe_model_alias}_t{current_temp}_problem_{problem_id}_iter_{iteration}.py"
                    )
                    if not os.path.exists(code_filename):
                        break 
                    iteration += 1
                
                print(f"Generating code for problem {problem_id} (Targeting Iteration {iteration})...")
                
                try:
                    start_time = time.time()  
                    
                    # The API call strictly uses the full model_id
                    response = client.chat.completions.create(
                        model=model_id, 
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": problem_text}
                        ],
                        temperature=current_temp, 
                        response_format={"type": "json_object"},
                        stream=False,
                        timeout=300.0,
                        extra_body={
                            "top_k": 20,
                            "chat_template_kwargs": {"enable_thinking": False},
                        }
                    )
                    
                    end_time = time.time()  
                    execution_time = round(end_time - start_time, 2)  
                    
                    content = response.choices[0].message.content
                    
                    if not content:
                        print(f"  -> Warning: The LLM returned an empty response. Skipping to the next.")
                        continue
                        
                    result = json.loads(content)
                    
                    reasoning_out = result.get("reasoning", "")
                    difficulty_out = result.get("difficulty", "Unclassified")
                    problem_type_out = result.get("problem_type", "Unclassified")
                    code_out = result.get("code", "")
                    
                    if not code_out:
                        print(f"  -> Warning: The JSON does not contain code. Skipping to the next.")
                        continue

                    # --- SAVING --- 
                    log_entry = {
                        "model_alias": model_alias,   # Saved for easy reading  
                        "model_id": model_id,         # Saved for technical reference
                        "temperature": current_temp,  
                        "problem_id": problem_id,
                        "iteration": iteration,  
                        "source_file": file,
                        "timestamp": datetime.now().isoformat(),
                        "execution_time_seconds": execution_time,  
                        "difficulty": difficulty_out,      
                        "problem_type": problem_type_out,  
                        "reasoning": reasoning_out,
                        "code": code_out
                    }
                    
                    with open(log_filename, "a", encoding="utf-8") as log_file:
                        log_file.write(json.dumps(log_entry) + "\n")

                    with open(code_filename, "w", encoding="utf-8") as f:
                        f.write(code_out)
                        
                    print(f"  -> Success: Saved iter {iteration} in {execution_time}s.")

                except openai.APITimeoutError:
                    end_time = time.time()
                    execution_time = round(end_time - start_time, 2)
                    print(f"  -> Timeout: The model took too long ({execution_time}s). Logging and skipping.")
                    
                    # 2. Log correctly when a Timeout occurs
                    log_entry = {
                        "model_alias": model_alias,   
                        "model_id": model_id,         
                        "temperature": current_temp,  
                        "problem_id": problem_id,
                        "iteration": iteration,  
                        "source_file": file,
                        "timestamp": datetime.now().isoformat(),
                        "execution_time_seconds": execution_time,  
                        "difficulty": "Timeout",      
                        "problem_type": "Timeout",  
                        "reasoning": "The API request timed out after 300 seconds.",
                        "code": ""
                    }
                    
                    with open(log_filename, "a", encoding="utf-8") as log_file:
                        log_file.write(json.dumps(log_entry) + "\n")
                    continue
                
                except json.JSONDecodeError:
                    print(f"  -> Error: The model did not return a valid JSON. Skipping to the next.")
                    continue
                except Exception as e:
                    print(f"  -> Unexpected error: {e}. Skipping to the next.")
                    continue

# --- Execution ---
if __name__ == "__main__":
    excel_files = ["datasets/OR_problems_LP_MILP.xlsx"]
    
    # Verify if we are in resume mode globally
    is_resuming_global = (resume_from_model_alias is not None and resume_from_temp is not None)
    
    # Iterate through the dictionary keys and values
    for model_alias, model_id in models_config.items():
        for temp in temperatures_list:
            
            if is_resuming_global:
                if model_alias != resume_from_model_alias or temp != resume_from_temp:
                    print(f"[*] Skipping Model: {model_alias} | Temp: {temp} (Already processed in previous run)")
                    continue
                else:
                    is_resuming_global = False 
                    print(f"\n=======================================================")
                    print(f"RESUMING RUN -> Model: {model_alias} | Temperature: {temp}")
                    print(f"=======================================================\n")
                    process_problems_bulk(excel_files, model_alias, model_id, temp, resume_from_file, resume_from_id)
            else:
                print(f"\n=======================================================")
                print(f"STARTING RUN -> Model: {model_alias} | Temperature: {temp}")
                print(f"=======================================================\n")
                process_problems_bulk(excel_files, model_alias, model_id, temp, resume_file=None, resume_id=None)
            
    print("\nBulk processing completed for all models and temperatures!")
