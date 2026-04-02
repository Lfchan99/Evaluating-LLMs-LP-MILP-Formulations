import pandas as pd
import json
import os
from datetime import datetime
from collections import Counter

# --- CONFIGURACIÓN DE RUTAS ---
PATH_EXECUTION_JSON = r"C:\Users\luisf\OneDrive - ZLC\Master_Thesis\Fase_2_3_Prompting\or_results\execution_results_2026-03-31_19-56-46.json"
PATH_INDUSTRY_OR = r"C:\Users\luisf\OneDrive - ZLC\Master_Thesis\Fase_2_3_Prompting\IndustryOR_LP_MILP.xlsx"
PATH_OR_PROBLEMS = r"C:\Users\luisf\OneDrive - ZLC\Master_Thesis\Fase_2_3_Prompting\OR_problems_LP_MILP.xlsx"
PATH_CURATED_OR = r"C:\Users\luisf\OneDrive - ZLC\Master_Thesis\Fase_2_3_Prompting\Curated_Problems_OR.xlsx"

BASE_EVAL_FOLDER = r"C:\Users\luisf\OneDrive - ZLC\Master_Thesis\Fase_2_3_Prompting\or_evaluation"

def get_next_execution_folder(base_path):
    if not os.path.exists(base_path):
        os.makedirs(base_path)
        return os.path.join(base_path, "Execution_1")
    folders = [f for f in os.listdir(base_path) if f.startswith("Execution_") and os.path.isdir(os.path.join(base_path, f))]
    if not folders:
        return os.path.join(base_path, "Execution_1")
    numbers = [int(f.split("_")[1]) for f in folders if f.split("_")[1].isdigit()]
    next_num = max(numbers) + 1 if numbers else 1
    return os.path.join(base_path, f"Execution_{next_num}")

def process_thesis_results():
    current_execution_path = get_next_execution_folder(BASE_EVAL_FOLDER)
    os.makedirs(current_execution_path, exist_ok=True)
    print(f"Created execution folder: {current_execution_path}")

    # 1. Cargar JSON de ejecución
    with open(PATH_EXECUTION_JSON, 'r', encoding='utf-8') as f:
        execution_data = json.load(f)
    
    df_exec = pd.DataFrame(execution_data)
    # Normalizar columnas del JSON
    df_exec.columns = [c.strip().lower().replace(" ", "_").replace("(", "").replace(")", "") for c in df_exec.columns]

    # 2. Cargar y Normalizar Excels de Referencia
    df_industry = pd.read_excel(PATH_INDUSTRY_OR)
    df_or = pd.read_excel(PATH_OR_PROBLEMS)
    df_curated = pd.read_excel(PATH_CURATED_OR)

    for df in [df_industry, df_or, df_curated]:
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # 3. Función de búsqueda UNIFICADA
    def get_problem_info(source_file, problem_id):
        source_clean = str(source_file).lower()
        
        # Selección de dataset
        if "curated" in source_clean:
            target_df = df_curated
        elif "industryor" in source_clean:
            target_df = df_industry
        else:
            target_df = df_or
            
        # Nombres de columnas UNIFICADOS según tu instrucción
        ans_col = 'en_answer'
        class_col = 'og_classification'
            
        # Búsqueda robusta (IDs como strings)
        target_df['problem_id_str'] = target_df['problem_id'].astype(str)
        row = target_df[target_df['problem_id_str'] == str(problem_id)]
        
        if not row.empty:
            gt = row.iloc[0][ans_col] if ans_col in row.columns else "n/a"
            clase = row.iloc[0][class_col] if class_col in row.columns else "unclassified"
            return gt, clase
        return "not_found", "not_found"

    results_detailed = []
    summary_data = []
    
    # 4. Agrupar y Procesar por Consenso
    grouped = df_exec.groupby(['source_file', 'problem_id'])

    for (source, pid), group in grouped:
        avg_time = group['llm_gen_time_s'].mean()
        
        def get_majority(series):
            clean_series = series.dropna().astype(str).str.lower()
            if clean_series.empty: return "unclear"
            counts = Counter(clean_series)
            top = counts.most_common(2)
            if len(top) > 1 and top[0][1] == top[1][1]:
                return "unclear"
            return top[0][0]

        final_diff = get_majority(group['difficulty'])
        final_type = get_majority(group['problem_type'])
        
        gt_value, classification = get_problem_info(source, pid)
        success_count = 0
        
        for _, row in group.iterrows():
            match_gt_val = "no"
            try:
                # Comparación numérica con tolerancia
                if abs(float(row['optimal_value']) - float(gt_value)) < 1e-6:
                    match_gt_val = "yes"
                    success_count += 1
            except:
                # Comparación de texto
                if str(row['optimal_value']).strip() == str(gt_value).strip():
                    match_gt_val = "yes"
                    success_count += 1

            entry = row.to_dict()
            entry.update({
                "ground_truth": gt_value,
                "og_classification": classification, # Nombre de columna unificado
                "llm_gen_avg": round(avg_time, 4),
                "final_difficulty_llm": final_diff,
                "final_problem_type_llm": final_type,
                "match_gt": match_gt_val
            })
            results_detailed.append(entry)

        summary_data.append({
            "source_file": source,
            "model": group.iloc[0]['model'],
            "temperature": group.iloc[0]['temperature'],
            "problem_id": pid,
            "num_of_iterations": len(group),
            "ground_truth": gt_value,
            "og_classification": classification, # Nombre de columna unificado
            "difficulty_consensus": final_diff,
            "problem_type_consensus": final_type,
            "avg_llm_gen_time": round(avg_time, 4),
            "success_rate": round(success_count / len(group), 4)
        })

    # 5. Exportación Total (Excel y JSON)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    
    pd.DataFrame(results_detailed).to_excel(os.path.join(current_execution_path, f"detailed_{ts}.xlsx"), index=False)
    pd.DataFrame(results_detailed).to_json(os.path.join(current_execution_path, f"detailed_{ts}.json"), orient='records', indent=4)
    
    pd.DataFrame(summary_data).to_excel(os.path.join(current_execution_path, f"summary_{ts}.xlsx"), index=False)
    pd.DataFrame(summary_data).to_json(os.path.join(current_execution_path, f"summary_{ts}.json"), orient='records', indent=4)

    print(f"Proceso finalizado. Archivos guardados en: {current_execution_path}")

if __name__ == "__main__":
    process_thesis_results()