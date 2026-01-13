import React, {useEffect, useMemo, useState} from "react";
import {Box, Text, useInput} from "ink";
import TextInput from "ink-text-input";

import type {TaskField} from "../tasks/types.js";

interface MultiStepFormProps {
  fields: TaskField[];
  initialValues?: Record<string, string>;
  onSubmit: (values: Record<string, string>) => void;
  onCancel: () => void;
  heading: string;
}

export function MultiStepForm({fields, initialValues = {}, onSubmit, onCancel, heading}: MultiStepFormProps) {
  const [stepIndex, setStepIndex] = useState(0);
  const [values, setValues] = useState<Record<string, string>>({...initialValues});
  const [inputValue, setInputValue] = useState<string>("");
  const [error, setError] = useState<string | undefined>();

  const currentField = fields[stepIndex];

  useEffect(() => {
    if (fields.length === 0) {
      onSubmit(values);
    }
  }, [fields, onSubmit, values]);

  useEffect(() => {
    if (currentField) {
      setInputValue(values[currentField.name] ?? currentField.defaultValue ?? "");
    }
  }, [currentField, values]);

  useInput((input, key) => {
    if (key.escape) {
      onCancel();
    }
    if (!currentField) {
      if (key.return) {
        onSubmit(values);
      }
      return;
    }
    if (input === "\u0017") {
      // ctrl+w clears input
      setInputValue("");
    }
  });

  const instructions = useMemo(() => {
    if (!currentField) {
      return "Press ↵ to continue or Esc to cancel.";
    }
    return currentField.optional ? "Enter a value or leave blank, ↵ to accept, Esc to cancel." : "Enter a value, ↵ to accept, Esc to cancel.";
  }, [currentField]);

  const handleSubmit = (value: string) => {
    if (!currentField) {
      onSubmit(values);
      return;
    }

    const trimmed = value.trim();
    if (!currentField.optional && trimmed.length === 0 && !(currentField.defaultValue && currentField.defaultValue.length > 0)) {
      setError("This field is required.");
      return;
    }

    setError(undefined);

    const nextValues = {
      ...values,
      [currentField.name]: trimmed.length === 0 ? "" : trimmed
    };

    setValues(nextValues);

    if (stepIndex + 1 >= fields.length) {
      onSubmit(nextValues);
      return;
    }

    setStepIndex((index) => index + 1);
  };

  if (!currentField && fields.length > 0) {
    return null;
  }

  return (
    <Box flexDirection="column" gap={1}>
      <Text bold>{heading}</Text>
      {currentField ? (
        <Box flexDirection="column" gap={1}>
          <Text>
            <Text color="cyan">{currentField.label}</Text>
            {currentField.optional ? <Text color="cyan"> (optional)</Text> : null}
          </Text>
          {currentField.placeholder ? <Text dimColor>{currentField.placeholder}</Text> : null}
          <TextInput
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSubmit}
            placeholder={currentField.placeholder}
          />
        </Box>
      ) : (
        <Text>All fields captured. Press ↵ to continue.</Text>
      )}
      <Text dimColor>{instructions}</Text>
      {error ? <Text color="red">{error}</Text> : null}
    </Box>
  );
}
