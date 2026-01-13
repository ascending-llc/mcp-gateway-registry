import React from "react";
import { Box, Text } from "ink";
import type { CommandOption } from "../utils/commands.js";

interface CommandSuggestionsProps {
  suggestions: CommandOption[];
  selectedIndex: number;
}

export function CommandSuggestions({ suggestions, selectedIndex }: CommandSuggestionsProps) {
  if (suggestions.length === 0) {
    return null;
  }

  // Calculate max command length for alignment
  const maxCommandLength = Math.max(...suggestions.map(s => s.command.length));

  return (
    <Box flexDirection="column" marginBottom={1} borderStyle="round" borderColor="gray" paddingX={1}>
      {suggestions.map((suggestion, index) => {
        const isSelected = index === selectedIndex;
        const padding = " ".repeat(maxCommandLength - suggestion.command.length);

        return (
          <Box key={suggestion.command} flexDirection="row">
            <Text color={isSelected ? "cyan" : "gray"} bold={isSelected}>
              {isSelected ? "› " : "  "}
            </Text>
            <Text
              color={isSelected ? "cyan" : "white"}
              bold={isSelected}
              backgroundColor={isSelected ? "blue" : undefined}
            >
              {suggestion.command}
            </Text>
            <Text color="gray">
              {padding}  {suggestion.description}
            </Text>
          </Box>
        );
      })}
    </Box>
  );
}
