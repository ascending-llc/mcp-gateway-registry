import {getTaskByKey, resolveDefaultValues, taskCatalog} from "../tasks/index.js";
import type {ScriptTask, TaskCategory, TaskField} from "../tasks/types.js";
import type {TaskCommand} from "./commandParser.js";
import {splitToken} from "./commandParser.js";

interface TaskResolutionSuccess {
  task: ScriptTask;
  values: Record<string, string>;
}

interface TaskResolutionError {
  error: string;
}

export type TaskResolution = TaskResolutionSuccess | TaskResolutionError;

export function resolveTaskCommand(command: TaskCommand): TaskResolution {
  const {category, subcommand} = command;
  const taskKey = resolveTaskKey(category, subcommand);
  if (!taskKey) {
    const available = taskCatalog[category].map((task) => task.key.replace(`${category}-`, "")).join(", ");
    return {
      error: `I don't recognise "/${category} ${subcommand}". Available subcommands: ${available}.`
    };
  }

  const task = getTaskByKey(category, taskKey);
  if (!task) {
    return {
      error: `Task "${taskKey}" is not available.`
    };
  }

  const values = resolveDefaultValues(task);
  const assignments: Record<string, string> = {...values};
  const positionalFields = task.fields.filter((field) => !field.optional && !(field.name in assignments));
  let positionalIndex = 0;

  for (const token of command.tokens) {
    const [key, value] = splitToken(token);
    if (key) {
      const field = findField(task.fields, key);
      if (!field) {
        return {error: `Unknown option "${key}" for "/${category} ${subcommand}".`};
      }
      assignments[field.name] = value ?? "";
    } else {
      if (positionalIndex >= task.fields.length) {
        return {error: `Too many positional values for "/${category} ${subcommand}".`};
      }
      let field = positionalFields[positionalIndex];
      while (field && field.name in assignments && assignments[field.name]) {
        positionalIndex += 1;
        field = positionalFields[positionalIndex];
      }
      if (!field) {
        return {error: `Unexpected extra value "${token}" for "/${category} ${subcommand}".`};
      }
      assignments[field.name] = token;
      positionalIndex += 1;
    }
  }

  for (const field of task.fields) {
    if (!field.optional) {
      const value = assignments[field.name];
      if (!value || value.trim().length === 0) {
        return {
          error: `Missing required option "${field.name}" for "/${category} ${subcommand}".`
        };
      }
    }
  }

  return {
    task,
    values: assignments
  };
}

function resolveTaskKey(category: TaskCategory, subcommand: string): string | undefined {
  const normalized = subcommand.toLowerCase().replace(/_/g, "-");
  const candidate = `${category}-${normalized}`;
  const hasTask = taskCatalog[category].some((task) => task.key === candidate);
  if (hasTask) {
    return candidate;
  }
  // Attempt to add common suffixes/prefixes
  const alt = taskCatalog[category].find((task) => {
    const suffix = task.key.replace(`${category}-`, "");
    return suffix === normalized;
  });
  return alt?.key;
}

function findField(fields: TaskField[], inputKey: string): TaskField | undefined {
  const lower = inputKey.toLowerCase();
  return fields.find((field) => field.name.toLowerCase() === lower);
}
