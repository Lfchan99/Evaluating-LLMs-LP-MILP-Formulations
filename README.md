# Evaluating Large Language Models for Automatic LP/MILP Formulation
**Toward Reliable Translation of Optimization Problems from Natural Language to Solver-Compatible Models**

---

### 🎓 Thesis Information
* **Author:** Luis Fernando Chan Monsreal
* **Degree:** Master of Engineering in Logistics and Supply Chain Management
* **Institution:** MIT-Zaragoza International Logistics Program at the Zaragoza Logistics Center (ZLC), a research institute associated with the University of Zaragoza.

## 📖 Overview
This repository contains the codebase developed for the Master's thesis detailed above. The primary objective of this project is to leverage Large Language Models (LLMs) to automatically translate natural language statements of Operations Research (OR) problems into solver-compatible mathematical models. Specifically, the system generates Linear Programming (LP) and Mixed-Integer Linear Programming (MILP) formulations using the Pyomo optimization framework in Python.

## 🚀 Quick Start

### Prerequisites
Ensure you have Python installed on your system. It is highly recommended to use a virtual environment to manage dependencies.

### 1. Environment Setup
First, configure your local environment variables to authenticate with the LLM API. Copy the provided template to create your own configuration file:

```bash
cp .env.example .env
```

Open the newly created .env file in your text editor and fill in your specific BASE_URL and API_KEY values.

### 2. Install Dependencies
Install all required Python packages by running:

```bash
pip install -r requirements.txt
```

### 3. Execution

To run the bulk generation process—which communicates with the model API, processes the OR prompts, and saves the generated Pyomo formulations—execute the main script:

```bash
python codes/Code_bulk_generation.py
```

## 📂 Repository Structure

- codes/Code_bulk_generation.py: The core execution script. It handles API communication, processes inputs, and outputs the generated Pyomo code.

- .env.example: Template for required environment variables.

- requirements.txt: List of Python dependencies required to run the codebase.

## 📄 License

This repository is released under the MIT License. See the LICENSE file for full details.