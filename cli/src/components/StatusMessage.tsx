import React from "react";
import {Text} from "ink";

interface StatusMessageProps {
  variant: "info" | "warning" | "error";
  message: string;
}

export function StatusMessage({variant, message}: StatusMessageProps) {
  if (variant === "warning") {
    return <Text color="yellow">{message}</Text>;
  }

  if (variant === "error") {
    return <Text color="red">{`❌ ${message}`}</Text>;
  }

  return <Text color="cyan">{message}</Text>;
}
