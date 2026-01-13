import {spawn} from "node:child_process";

import {REPO_ROOT} from "../paths.js";
import {taskCatalog} from "../tasks/index.js";
import type {ScriptCommand, ScriptTask, TaskCategory, TaskContext} from "../tasks/types.js";

export interface ScriptRunResult {
  stdout: string;
  stderr: string;
  exitCode: number | null;
  command: ScriptCommand;
  task: ScriptTask;
}

export function resolveTask(category: TaskCategory, key: string): ScriptTask | undefined {
  return taskCatalog[category].find((task) => task.key === key);
}

export async function runScriptTaskToString(
  category: TaskCategory,
  task: ScriptTask,
  values: Record<string, string>,
  context: TaskContext
): Promise<ScriptRunResult> {
  const command = task.build(values, context);
  const env = command.env ? {...process.env, ...command.env} : process.env;
  return new Promise<ScriptRunResult>((resolve) => {
    const child = spawn(command.command, command.args, {
      cwd: REPO_ROOT,
      env,
      stdio: ["ignore", "pipe", "pipe"]
    });

    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr?.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("close", (code) => {
      resolve({stdout, stderr, exitCode: code, command, task});
    });
    child.on("error", (error) => {
      resolve({
        stdout,
        stderr: `${stderr}\nFailed to start process: ${(error as Error).message}`,
        exitCode: -1,
        command,
        task
      });
    });
  });
}
