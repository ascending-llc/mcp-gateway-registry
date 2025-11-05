import React, {useState} from "react";
import {Box, Text, useInput} from "ink";
import TextInput from "ink-text-input";

interface TokenFileEditorProps {
  initialPath?: string;
  onSubmit: (value?: string) => void;
  onCancel: () => void;
}

export function TokenFileEditor({initialPath, onSubmit, onCancel}: TokenFileEditorProps) {
  const [value, setValue] = useState(initialPath ?? "");

  useInput((_input, key) => {
    if (key.escape) {
      onCancel();
    }
  });

  const handleSubmit = (input: string) => {
    const trimmed = input.trim();
    onSubmit(trimmed.length > 0 ? trimmed : undefined);
  };

  return (
    <Box flexDirection="column" gap={1}>
      <Text bold>Token file path</Text>
      <TextInput value={value} onChange={setValue} onSubmit={handleSubmit} placeholder="./.oauth-tokens/ingress.json" />
      <Text dimColor>Enter a path to use, leave blank to clear, Esc to cancel.</Text>
    </Box>
  );
}
