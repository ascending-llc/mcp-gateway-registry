#!/usr/bin/env python3
"""
Test Suite for MCP Agent

This script runs a series of test commands against the agent.py script,
captures the output, and uses an LLM to evaluate the correctness of the responses.

Usage:
    python agents/test_suite.py [--mcp-registry-url URL] [--num-tests N]

Options:
    --mcp-registry-url URL    MCP Registry URL (default: http://localhost/mcpgw/sse)
    --num-tests N             Number of tests to run (default: run all tests)
"""

import subprocess
import json
import sys
import os
import argparse
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Tuple
from langchain_aws import ChatBedrockConverse

# Configure logging
def setup_logging():
    """
    Configure the logging system with detailed formatting.
    """
    # Create logs directory if it doesn't exist
    os.makedirs("agents/test_results/logs", exist_ok=True)
    
    # Generate log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"agents/test_results/logs/test_suite_{timestamp}.log"
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Create formatter with detailed information
    formatter = logging.Formatter(
        '%(asctime)s | %(process)d | %(levelname)s | %(filename)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    logging.info(f"Logging initialized. Log file: {log_file}")
    return log_file

def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments for the test suite.
    
    Returns:
        argparse.Namespace: The parsed command line arguments
    """
    parser = argparse.ArgumentParser(description='MCP Agent Test Suite')
    
    # MCP Registry URL argument
    parser.add_argument('--mcp-registry-url', type=str, default='http://localhost/mcpgw/sse',
                        help='MCP Registry URL (default: http://localhost/mcpgw/sse)')
    
    # Number of tests to run argument
    parser.add_argument('--num-tests', type=int, default=None,
                        help='Number of tests to run (default: run all tests)')
    
    return parser.parse_args()

# Define the test cases
TEST_CASES = [
    {
        "id": "test1",
        "command_template": "python agents/agent.py --mcp-registry-url {mcp_registry_url} --message \"what mcp servers do i have access to\"",
        "description": "Query available MCP servers"
    },
    {
        "id": "test2",
        "command_template": "python agents/agent.py --mcp-registry-url {mcp_registry_url} --message \"what is the current time in clarksburg, md\"",
        "description": "Query current time in Clarksburg, MD"
    },
    {
        "id": "test3",
        "command_template": "python agents/agent.py --mcp-registry-url {mcp_registry_url} --message \"stock performance for apple in the last one week\"",
        "description": "Query Apple stock performance for the last week"
    }
]

def ensure_directories_exist():
    """
    Ensure that the necessary directories for test results exist.
    Creates agents/test_results/ and agents/test_results/raw_data/ if they don't exist.
    """
    os.makedirs("agents/test_results", exist_ok=True)
    os.makedirs("agents/test_results/raw_data", exist_ok=True)
    logging.info("Ensured test results directories exist")

def run_command(command: str) -> Tuple[str, str]:
    """
    Run a command and capture its stdout and stderr.
    
    Args:
        command (str): The command to run
        
    Returns:
        Tuple[str, str]: A tuple containing (stdout, stderr)
    """
    logging.info(f"Executing command: {command}")
    start_time = time.time()
    
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate()
    
    execution_time = time.time() - start_time
    logging.info(f"Command completed in {execution_time:.2f} seconds with exit code: {process.returncode}")
    
    if stderr:
        logging.warning(f"Command produced stderr output: {stderr[:200]}...")
    
    return stdout, stderr

def evaluate_response(question: str, output: str, model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0") -> Dict[str, Any]:
    """
    Evaluate the agent's response using an LLM.
    
    Args:
        question (str): The original question asked to the agent
        output (str): The combined stdout and stderr from the agent
        model_id (str): The Bedrock model ID to use for evaluation
        
    Returns:
        Dict[str, Any]: A dictionary containing the evaluation results
    """
    logging.info(f"Evaluating response for question: {question}")
    logging.info(f"Using model: {model_id}")
    
    # Initialize the LLM
    try:
        llm = ChatBedrockConverse(model_id=model_id, region_name='us-east-1')
        logging.info("Successfully initialized Bedrock model")
    except Exception as e:
        logging.error(f"Failed to initialize Bedrock model: {str(e)}")
        return {
            "correct": False,
            "reasoning": f"Failed to initialize Bedrock model: {str(e)}",
            "summary": "Evaluation error"
        }
    
    # Create the prompt for evaluation with enhanced criteria
    prompt = f"""
    You are an expert evaluator for AI assistant responses. You need to thoroughly evaluate the following response 
    to determine if it correctly answers the given question and follows proper process.
    
    Question: {question}
    
    Response Output:
    ```
    {output}
    ```
    
    Please evaluate the response based on the following criteria:
    
    1. Tool Selection: Did the agent invoke the appropriate tool for the task? 
    2. Parameter Correctness: Did the agent pass parameters to the tool according to the tool's schema?
    3. Error Handling: Did the agent have to retry any failed requests? If so, how did it handle them?
    4. Answer Accuracy: Is the final answer correct and responsive to the question?
    5. Process Efficiency: Did the agent take a direct and efficient path to the answer?
    
    Provide your assessment in the following JSON format:
    {{
        "correct": true/false,
        "tool_selection": {{
            "appropriate": true/false,
            "comments": "Your assessment of tool selection"
        }},
        "parameter_usage": {{
            "correct": true/false,
            "comments": "Your assessment of parameter usage"
        }},
        "error_handling": {{
            "errors_encountered": true/false,
            "handled_properly": true/false,
            "comments": "Your assessment of error handling"
        }},
        "answer_quality": {{
            "accurate": true/false,
            "complete": true/false,
            "comments": "Your assessment of the answer quality"
        }},
        "reasoning": "Your detailed overall reasoning for the assessment",
        "summary": "A concise summary of the response content"
    }}
    
    Only respond with the JSON object, nothing else.
    """
    
    # Get the evaluation from the LLM
    try:
        logging.info("Sending prompt to LLM for evaluation")
        start_time = time.time()
        response = llm.invoke(prompt)
        execution_time = time.time() - start_time
        logging.info(f"LLM evaluation completed in {execution_time:.2f} seconds")
    except Exception as e:
        logging.error(f"LLM evaluation failed: {str(e)}")
        return {
            "correct": False,
            "reasoning": f"LLM evaluation failed: {str(e)}",
            "summary": "Evaluation error"
        }
    
    # Extract the JSON from the response
    try:
        # The response might contain markdown formatting, so we need to extract just the JSON part
        response_text = response.content
        
        # Find JSON content (between curly braces)
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)
            logging.info("Successfully parsed LLM response as JSON")
            return result
        else:
            # If no JSON found, return an error
            logging.error("Failed to find JSON content in LLM response")
            return {
                "correct": False,
                "reasoning": "Failed to parse LLM response as JSON",
                "summary": "Evaluation error"
            }
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse LLM response as JSON: {str(e)}")
        return {
            "correct": False,
            "reasoning": f"Failed to parse LLM response as JSON: {str(e)}",
            "summary": "Evaluation error"
        }

def run_test_case(test_case: Dict[str, str], mcp_registry_url: str) -> Dict[str, Any]:
    """
    Run a single test case and evaluate the results.
    
    Args:
        test_case (Dict[str, str]): The test case to run
        mcp_registry_url (str): The MCP Registry URL to use
        
    Returns:
        Dict[str, Any]: The test results including the evaluation
    """
    # Format the command with the MCP Registry URL
    command = test_case["command_template"].format(mcp_registry_url=mcp_registry_url)
    description = test_case["description"]
    test_id = test_case["id"]
    
    # Extract the question from the command
    question = command.split("--message")[1].strip().strip('"')
    
    logging.info(f"{'=' * 80}")
    logging.info(f"Running test: {description} (ID: {test_id})")
    logging.info(f"Command: {command}")
    logging.info(f"{'=' * 80}")
    
    # Run the command
    stdout, stderr = run_command(command)
    
    # Combine stdout and stderr for evaluation
    combined_output = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
    
    # Save the raw output to a file
    raw_data_path = f"agents/test_results/raw_data/{test_id}.json"
    try:
        with open(raw_data_path, "w") as f:
            json.dump({
                "question": question,
                "stdout": stdout,
                "stderr": stderr
            }, f, indent=2)
        logging.info(f"Raw test data saved to {raw_data_path}")
    except Exception as e:
        logging.error(f"Failed to save raw test data: {str(e)}")
    
    # Evaluate the response
    logging.info(f"Evaluating response for test: {test_id}")
    evaluation = evaluate_response(question, combined_output)
    
    # Log evaluation result
    if evaluation.get("correct", False):
        logging.info(f"Test {test_id} PASSED")
    else:
        logging.warning(f"Test {test_id} FAILED")
    
    # Return the test results (without including the full stdout/stderr)
    return {
        "id": test_id,
        "description": description,
        "question": question,
        "raw_data_file": raw_data_path,
        "evaluation": evaluation
    }

def main():
    """
    Run all test cases and display the results.
    """
    # Setup logging
    log_file = setup_logging()
    
    # Log start of test suite with Python version
    logging.info(f"Starting MCP Agent Test Suite")
    logging.info(f"Python version: {sys.version}")
    
    # Parse command line arguments
    args = parse_arguments()
    mcp_registry_url = args.mcp_registry_url
    num_tests = args.num_tests
    logging.info(f"Using MCP Registry URL: {mcp_registry_url}")
    
    # Ensure the necessary directories exist
    ensure_directories_exist()
    
    # Determine how many tests to run
    tests_to_run = TEST_CASES
    if num_tests is not None and num_tests > 0:
        tests_to_run = TEST_CASES[:num_tests]
        logging.info(f"Running first {num_tests} of {len(TEST_CASES)} test cases")
    else:
        logging.info(f"Running all {len(TEST_CASES)} test cases")
    
    results = []
    
    # Run each test case
    for i, test_case in enumerate(tests_to_run, 1):
        logging.info(f"Starting test case {i}/{len(tests_to_run)}: {test_case['id']}")
        result = run_test_case(test_case, mcp_registry_url)
        results.append(result)
    
    # Display summary of results
    logging.info(f"{'=' * 80}")
    logging.info(f"Test Suite Summary")
    logging.info(f"{'=' * 80}")
    
    for result in results:
        evaluation = result["evaluation"]
        correct = evaluation.get("correct", False)
        status = "PASSED" if correct else "FAILED"
        
        logging.info(f"Test: {result['description']} (ID: {result['id']})")
        logging.info(f"Status: {status}")
        logging.info(f"Summary: {evaluation.get('summary', 'N/A')}")
        
        # Log more detailed evaluation if available
        if "tool_selection" in evaluation:
            tool_appropriate = evaluation["tool_selection"].get("appropriate", False)
            tool_status = "Appropriate" if tool_appropriate else "Inappropriate"
            logging.info(f"Tool Selection: {tool_status} - {evaluation['tool_selection'].get('comments', '')}")
        
        if "parameter_usage" in evaluation:
            params_correct = evaluation["parameter_usage"].get("correct", False)
            params_status = "Correct" if params_correct else "Incorrect"
            logging.info(f"Parameter Usage: {params_status} - {evaluation['parameter_usage'].get('comments', '')}")
        
        if "error_handling" in evaluation and evaluation["error_handling"].get("errors_encountered", False):
            errors_handled = evaluation["error_handling"].get("handled_properly", False)
            error_status = "Properly handled" if errors_handled else "Improperly handled"
            logging.info(f"Error Handling: {error_status} - {evaluation['error_handling'].get('comments', '')}")
    
    # Count passed tests
    passed = sum(1 for result in results if result["evaluation"].get("correct", False))
    
    logging.info(f"{'-' * 80}")
    logging.info(f"Results: {passed}/{len(results)} tests passed")
    logging.info(f"{'=' * 80}")
    
    # Save summary results to a JSON file
    results_path = "agents/test_results/summary.json"
    try:
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        logging.info(f"Summary results saved to {results_path}")
    except Exception as e:
        logging.error(f"Failed to save summary results: {str(e)}")
    
    # Generate and save accuracy metrics
    total_tests = len(results)
    passed_tests = passed
    accuracy = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0
    
    accuracy_data = {
        "total_tests": total_tests,
        "tests_passed": passed_tests,
        "accuracy": round(accuracy, 2)  # Round to 2 decimal places
    }
    
    accuracy_path = "agents/test_results/accuracy.json"
    try:
        with open(accuracy_path, "w") as f:
            json.dump(accuracy_data, f, indent=2)
        logging.info(f"Accuracy metrics saved to {accuracy_path}")
        logging.info(f"Accuracy: {accuracy_data['accuracy']}% ({passed_tests}/{total_tests} tests passed)")
    except Exception as e:
        logging.error(f"Failed to save accuracy metrics: {str(e)}")
    
    logging.info(f"Test suite execution completed")
    logging.info(f"Log file: {log_file}")

if __name__ == "__main__":
    main()