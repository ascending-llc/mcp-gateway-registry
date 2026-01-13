import React from "react";
import {Box, Text} from "ink";

interface JsonViewerProps {
  data: unknown;
  label?: string;
  raw?: boolean;
}

export function JsonViewer({data, label, raw}: JsonViewerProps) {
  const json = stringify(data, raw);
  return (
    <Box flexDirection="column">
      {label ? (
        <Text>
          <Text bold>{label}</Text>
          <Text> </Text>
        </Text>
      ) : null}
      <Text>{json}</Text>
    </Box>
  );
}

function stringify(data: unknown, raw = false): string {
  if (raw) {
    return typeof data === "string" ? data : JSON.stringify(data);
  }
  return JSON.stringify(data, null, 2);
}
