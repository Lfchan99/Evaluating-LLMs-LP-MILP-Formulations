import os
import subprocess
import pandas as pd
import json
import re
from datetime import datetime

# --- PATH CONFIGURATION ---
base_dir = r"C:\Users\luisf\OneDrive - ZLC\Master_Thesis\Fase_2_3_Prompting\or_results"
codes_path = os.path.join(base_dir, "codes")
log_path = os.path.join(base_dir, "experiment_log.jsonl")

# Create unique filenames with the exact date and time
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
output_excel = os.path.join(base_dir, f"execution_results_{timestamp}.xlsx")
output_json = os.path.join(base_dir, f"execution_results_{timestamp}.json")

# --- TEST CONFIGURATION ---
target_source_file = None # Set to None to process all source files, or specify one like "OR_problems_LP_MILP"
start_id = None
end_id = None
start_iter = None
end_iter = None

# --- RESUME CONFIGURATION ---
resume_from_file = None  # Set to None to start fresh, or specify the source file to resume from
resume_from_id = None   
resume_from_iter = None 

def load_llm_metadata():
    """Reads the experiment_log.jsonl and creates a lookup dictionary."""
    metadata = {}
    if not os.path.exists(log_path):
        print(f"Warning: Log file {log_path} not found.")
        return metadata

    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    src = str(entry.get("source_file", "")).replace(".xlsx", "")
                    pid = str(entry.get("problem_id", ""))
                    it = str(entry.get("iteration", ""))
                    
                    mod = str(entry.get("model_alias", entry.get("model", "Unknown")))
                    tmp = str(entry.get("temperature", "Unknown"))
                    
                    # Key remains internal, but values are normalized
                    key = f"{src}_{mod}_{tmp}_{pid}_{it}"
                    
                    metadata[key] = {
                        "difficulty": entry.get("difficulty", "unclassified"),
                        "problem_type": entry.get("problem_type", "unclassified"),
                        "llm_gen_time_s": entry.get("execution_time_seconds", "n/a") 
                    }
                except json.JSONDecodeError:
                    continue
    return metadata

def run_all_scripts():
    results_data = []
    llm_metadata = load_llm_metadata()

    if not os.path.exists(codes_path):
        print(f"Error: Folder {codes_path} not found.")
        return

    py_files = [f for f in os.listdir(codes_path) if f.endswith(".py") and "_problem_" in f and "_iter_" in f]
    
    def extract_filename_data(filename):
        match = re.search(r'_t(\d+(?:\.\d+)?)_problem_(\d+)_iter_(\d+)\.py$', filename)
        if match:
            temperature = float(match.group(1))
            problem_id = int(match.group(2))
            iteration = int(match.group(3))
            prefix_and_model = filename[:match.start()]
            
            known_files = ["OR_problems_LP_MILP", "IndustryOR_LP_MILP", "Curated_Problems_OR"]
            source_file = "unknown"
            model_alias = "unknown"
            
            for kf in known_files:
                if prefix_and_model.startswith(kf):
                    source_file = kf
                    model_alias = prefix_and_model[len(kf)+1:]
                    break
            
            if source_file == "unknown":
                parts = prefix_and_model.rsplit('_', 1)
                source_file = parts[0]
                model_alias = parts[1] if len(parts) > 1 else "unknown"
                
            return source_file, model_alias, temperature, problem_id, iteration
        else:
            raise ValueError(f"Filename format not recognized: {filename}")

    py_files.sort(key=lambda x: extract_filename_data(x) if re.search(r'_t', x) else (x, "", 0, 0, 0))
    
    print(f"A total of {len(py_files)} scripts found.\n")

    skip_mode = False
    if resume_from_file is not None and resume_from_id is not None:
        skip_mode = True

    for filename in py_files:
        file_path = os.path.join(codes_path, filename)
        
        try:
            source_file, model_alias, temperature, problem_id, iteration = extract_filename_data(filename)
        except Exception:
            source_file = "unknown"
            model_alias = "unknown"
            temperature = "unknown"
            problem_id = filename
            iteration = "n/a"

        # --- RESUME LOGIC ---
        if skip_mode:
            if not (source_file == resume_from_file and str(problem_id) == str(resume_from_id) and \
               ((resume_from_iter is None) or (str(iteration) == str(resume_from_iter)))):
                continue 
            else:
                skip_mode = False 

        # --- TEST MODE CUTOFF ---
        if target_source_file is not None and source_file != target_source_file:
            continue
        if start_id is not None and end_id is not None and isinstance(problem_id, int):
            if not (start_id <= problem_id <= end_id): continue
        if start_iter is not None and end_iter is not None and isinstance(iteration, int):
            if not (start_iter <= iteration <= end_iter): continue

        print(f"Executing {filename}...")
        extracted_optimal_value = None
        extracted_variables = ""

        try:
            process = subprocess.run(['python', file_path], capture_output=True, text=True, timeout=60)
            if process.returncode == 0:
                status = "success"
                output_text = process.stdout.strip()
                variable_lines = []
                for line in output_text.split('\n'):
                    clean_line = line.strip()
                    if not clean_line: continue
                    
                    # Robust check ignoring spaces and case
                    lower_line_no_spaces = clean_line.lower().replace(" ", "")
                    
                    if lower_line_no_spaces.startswith("optimalvalue:"):
                        try:
                            # Split by original delimiter but handle multiple colons safely
                            parts = clean_line.split(':')
                            if len(parts) >= 2:
                                value_part = ":".join(parts[1:]).strip()
                                extracted_optimal_value = float(value_part)
                        except ValueError:
                            extracted_optimal_value = value_part
                    else:
                        variable_lines.append(clean_line)
                extracted_variables = "\n".join(variable_lines)
            else:
                status = "error_code_pyomo"
                extracted_variables = process.stderr.strip()
        except subprocess.TimeoutExpired:
            status = "timeout"
            extracted_variables = "solver_cancelled_after_60s"
        except Exception as e:
            status = "system_error"
            extracted_variables = str(e)

        # --- FETCH METADATA ---
        lookup_key = f"{source_file}_{model_alias}_{temperature}_{problem_id}_{iteration}"
        meta = llm_metadata.get(lookup_key, {"difficulty": "not_found", "problem_type": "not_found", "llm_gen_time_s": "not_found"})

        results_data.append({
            "source_file": source_file,
            "model": model_alias,
            "temperature": temperature,
            "problem_id": problem_id,
            "iteration": iteration,
            "difficulty": meta["difficulty"],
            "problem_type": meta["problem_type"],
            "llm_gen_time_s": meta["llm_gen_time_s"], 
            "status": status,
            "optimal_value": extracted_optimal_value,
            "variables_errors": extracted_variables
        })

    # 3. Save Results
    if results_data:
        df_results = pd.DataFrame(results_data)
        # Sort and ensure column order is snake_case
        df_results.sort_values(by=["source_file", "model", "temperature", "problem_id", "iteration"], inplace=True)
        
        df_results.to_excel(output_excel, index=False)
        
        sorted_results = df_results.to_dict(orient='records')
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(sorted_results, f, ensure_ascii=False, indent=4)
            
        print(f"\nEvaluation finished!")
        print(f"Excel: {output_excel}")
        print(f"JSON: {output_json}")
    else:
        print("\nNo files processed.")

if __name__ == "__main__":
    run_all_scripts()