import json
import logging
import os
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage

from utils.gemini_rotator import get_rotated_gemini_model

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("DebugSwarm")


@dataclass
class SwarmReport:
    command: str
    reproduction_exit_code: Optional[int] = None
    reproduction_error: Optional[str] = None
    diagnosis: Optional[str] = None
    proposed_fixes: List[str] = None
    selected_fix: Optional[str] = None
    validation_status: Optional[str] = None
    history: List[Dict] = None


class ReproductionAgent:
    def run(self, cmd: str) -> Dict[str, Any]:
        logger.info(f"Reproduction Agent: Running '{cmd}'")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=300
            )
            # Check both output and logs.log for failures
            is_success = result.returncode == 0

            error_evidence = result.stderr
            if os.path.exists("logs.log"):
                with open("logs.log", "r") as f:
                    log_content = f.read()
                    if "Traceback" in log_content or "Error" in log_content:
                        error_evidence += (
                            "\n--- FROM logs.log ---\n" + log_content[-2000:]
                        )
                        is_success = False

            if is_success and (
                "Traceback" in result.stderr or "Error" in result.stderr
            ):
                is_success = False

            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": error_evidence,
                "success": is_success,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Timeout",
                "success": False,
            }


class DiagnosticAgent:
    def __init__(self):
        self.model = get_rotated_gemini_model()

    def _execute_command(self, cmd: str) -> str:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=10
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return str(e)

    def diagnose(self, error_output: str) -> str:
        logger.info("OMG Diagnostic Agent: Analyzing failure signal...")

        history = [f"FAILURE SIGNAL:\n{error_output}"]
        for i in range(3):
            prompt = f"""
            You are the omg-debugger specialist.
            Workflow:
            1. Reproduce or narrow the failure signal.
            2. Form competing hypotheses from evidence.
            3. Isolate root cause with minimal experiments.
            
            HISTORY:
            {"\n".join(history)}
            
            Output next step as JSON:
            {{
                "hypotheses": ["H1", "H2"],
                "experiment_command": "grep -rn 'Pattern' ." or "cat file",
                "root_cause_isolation": "Only provide this if you are done"
            }}
            """
            response = self.model.invoke([HumanMessage(content=prompt)])
            content = response.content
            if isinstance(content, list):
                content = "".join(
                    [
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in content
                    ]
                )

            try:
                # Basic JSON extraction
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                data = json.loads(content)
                if "root_cause_isolation" in data and data["root_cause_isolation"]:
                    return data["root_cause_isolation"]

                if "experiment_command" in data:
                    cmd = data["experiment_command"]
                    logger.info(f"OMG Diagnostic Agent: Running experiment: {cmd}")
                    cmd_res = self._execute_command(cmd)
                    history.append(f"EXPERIMENT: {cmd}\nRESULT:\n{cmd_res[:1000]}")
            except Exception as e:
                logger.error(f"Diagnostic Agent: Loop error: {e}")
                break

        return f"Iterative diagnosis failed. Last output: {content[:200]}"


class FixProposalAgent:
    def __init__(self):
        self.model = get_rotated_gemini_model()

    def propose(self, diagnosis: str) -> List[str]:
        logger.info("Fix Proposal Agent: Generating fixes...")
        prompt = f"""
        Based on this diagnosis, propose 2-3 specific code fixes.
        For each fix, provide the code change and pros/cons.
        Format your response as a JSON list of strings.
        
        DIAGNOSIS:
        {diagnosis}
        """
        response = self.model.invoke([HumanMessage(content=prompt)])
        try:
            import json

            fixes = json.loads(response.content)
            return fixes if isinstance(fixes, list) else [response.content]
        except Exception:
            return [response.content]


class ImplementationAgent:
    def __init__(self):
        self.model = get_rotated_gemini_model()

    def apply(self, fix: str) -> bool:
        logger.info("Implementation Agent: Applying fix...")
        # In this AI-assistant context, we need to output the fix in a format
        # that the Orchestrator/Assistant can read and apply.
        # But for 'self-healing', we'll try to find the file and use simple replace.

        prompt = f"""
        Extract the file path and the exact code change from this fix proposal.
        Return a JSON object with:
        "file": "path/to/file",
        "search": "original code block",
        "replace": "new code block"
        
        FIX PROPOSAL:
        {fix}
        """
        response = self.model.invoke([HumanMessage(content=prompt)])
        content = response.content
        if isinstance(content, list):
            content = "".join(
                [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
            )

        try:
            # Extract JSON from block if needed
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            filepath = data.get("file")
            search_str = data.get("search")
            replace_str = data.get("replace")

            if not all([filepath, search_str, replace_str]):
                logger.error("Implementation Agent: Missing data in LLM response.")
                return False

            with open(filepath, "r") as f:
                content = f.read()

            if search_str not in content:
                logger.error(
                    f"Implementation Agent: Target string not found in {filepath}"
                )
                return False

            new_content = content.replace(search_str, replace_str)
            with open(filepath, "w") as f:
                f.write(new_content)

            logger.info(f"Implementation Agent: Successfully updated {filepath}")
            return True
        except Exception as e:
            logger.error(f"Implementation Agent: Failed to apply fix: {e}")
            return False


class ValidationAgent:
    def validate(self, cmd: str) -> bool:
        logger.info("Validation Agent: Verifying fix...")
        repro = ReproductionAgent()
        # Give it a bit more time to run
        result = repro.run(cmd)
        if result["success"]:
            logger.info("Validation Agent: Success! Fix verified.")
            return True
        else:
            logger.error(
                f"Validation Agent: Failed. Error: {result['stderr'][:200]}..."
            )
            return False


class DebugSwarmOrchestrator:
    def __init__(self):
        self.repro = ReproductionAgent()
        self.diag = DiagnosticAgent()
        self.proposer = FixProposalAgent()
        self.impl = ImplementationAgent()
        self.val = ValidationAgent()

    def run_swarm(self, cmd: str):
        report = SwarmReport(command=cmd, history=[], proposed_fixes=[])

        # 1. Reproduce
        result = self.repro.run(cmd)
        report.reproduction_exit_code = result["exit_code"]
        report.reproduction_error = result["stderr"]

        if result["success"]:
            logger.info("Swarm: Command succeeded. No healing needed.")
            report.validation_status = "SUCCESS (No error found)"
            return report

        # 2. Diagnose
        report.diagnosis = self.diag.diagnose(result["stderr"])

        # 3. Propose
        report.proposed_fixes = self.proposer.propose(report.diagnosis)

        # 4. Implement (take first fix)
        report.selected_fix = report.proposed_fixes[0]
        self.impl.apply(report.selected_fix)

        # 5. Validate
        if self.val.validate(cmd):
            report.validation_status = "HEALED"
        else:
            report.validation_status = "FAILED_TO_HEAL"

        with open("debugging_report.json", "w") as f:
            json.dump(asdict(report), f, indent=2)

        logger.info(f"Swarm: Debugging finished. Status: {report.validation_status}")
        return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", required=True, help="Command to debug")
    args = parser.parse_args()

    swarm = DebugSwarmOrchestrator()
    swarm.run_swarm(args.cmd)
