import React, {useState} from "react";
import {Box, Text, useInput} from "ink";
import TextInput from "ink-text-input";

interface UrlEditorProps {
  initialUrl: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}

export function UrlEditor({initialUrl, onSubmit, onCancel}: UrlEditorProps) {
  const [value, setValue] = useState(initialUrl);

  useInput((_input, key) => {
    if (key.escape) {
      onCancel();
    }
  });

  const handleSubmit = (url: string) => {
    const trimmed = url.trim();
    if (trimmed.length > 0) {
      onSubmit(trimmed);
    } else {
      onCancel();
    }
  };

  return (
    <Box flexDirection="column" gap={1}>
      <Text bold>Gateway URL</Text>
      <TextInput value={value} onChange={setValue} onSubmit={handleSubmit} placeholder="http://localhost:7860/mcpgw/mcp" />
      <Text dimColor>Press ↵ to confirm or Esc to keep the current URL.</Text>
    </Box>
  );
}
