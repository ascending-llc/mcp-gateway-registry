import React, {useState} from "react";
import {Box, Text, useInput} from "ink";
import TextInput from "ink-text-input";

export interface CallToolPayload {
  tool: string;
  args: string;
}

interface CallToolFormProps {
  initialTool?: string;
  initialArgs?: string;
  onSubmit: (payload: CallToolPayload) => void;
  onCancel: () => void;
}

const DEFAULT_ARGS = "{}";

export function CallToolForm({initialTool, initialArgs, onSubmit, onCancel}: CallToolFormProps) {
  const [step, setStep] = useState<"tool" | "args">("tool");
  const [tool, setTool] = useState(initialTool ?? "");
  const [args, setArgs] = useState(initialArgs ?? DEFAULT_ARGS);

  useInput((_input, key) => {
    if (key.escape) {
      onCancel();
    }
  });

  const handleToolSubmit = (value: string) => {
    const trimmed = value.trim();
    if (trimmed.length === 0) {
      return;
    }
    setTool(trimmed);
    setStep("args");
  };

  const handleArgsSubmit = (value: string) => {
    onSubmit({
      tool,
      args: value.trim().length === 0 ? DEFAULT_ARGS : value.trim()
    });
  };

  return (
    <Box flexDirection="column" gap={1}>
      <Box flexDirection="column">
        <Text bold>Tool name</Text>
        <TextInput value={tool} onChange={setTool} onSubmit={handleToolSubmit} placeholder="current_time_by_timezone" />
      </Box>
      {step === "args" && (
        <Box flexDirection="column">
          <Text bold>Tool arguments (JSON)</Text>
          <TextInput value={args} onChange={setArgs} onSubmit={handleArgsSubmit} placeholder='{"tz_name":"America/New_York"}' />
          <Text dimColor>
            Press ↵ to run, Esc to cancel. Leave blank to send {DEFAULT_ARGS}.
          </Text>
        </Box>
      )}
    </Box>
  );
}
