export interface TaskField {
  name: string;
  label: string;
  placeholder?: string;
  optional?: boolean;
  defaultValue?: string;
}

export interface ScriptCommand {
  command: string;
  args: string[];
  env?: Record<string, string>;
}

export interface TaskContext {
  gatewayUrl: string;
  gatewayBaseUrl: string;
  gatewayToken?: string;
  backendToken?: string;
}

export interface ScriptTask {
  key: string;
  label: string;
  description?: string;
  fields: TaskField[];
  build(values: Record<string, string>, context: TaskContext): ScriptCommand;
}

export type TaskCategory = "service" | "import" | "user" | "diagnostic";
