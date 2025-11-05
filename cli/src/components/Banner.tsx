import React from "react";
import { Box, Text } from "ink";

export function Banner() {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box>
        <Text bold>
          <Text color="cyan">{"███╗   ███╗ ██████╗██████╗ "}</Text>
          <Text color="magenta">{"██████╗ ███████╗ ██████╗ ██╗███████╗████████╗██████╗ ██╗   ██╗"}</Text>
          <Text color="green">{"  ██████╗██╗     ██╗"}</Text>
        </Text>
      </Box>
      <Box>
        <Text bold>
          <Text color="cyan">{"████╗ ████║██╔════╝██╔══██╗"}</Text>
          <Text color="magenta">{"██╔══██╗██╔════╝██╔════╝ ██║██╔════╝╚══██╔══╝██╔══██╗╚██╗ ██╔╝"}</Text>
          <Text color="green">{" ██╔════╝██║     ██║"}</Text>
        </Text>
      </Box>
      <Box>
        <Text bold>
          <Text color="cyan">{"██╔████╔██║██║     ██████╔╝"}</Text>
          <Text color="magenta">{"██████╔╝█████╗  ██║  ███╗██║███████╗   ██║   ██████╔╝ ╚████╔╝ "}</Text>
          <Text color="green">{" ██║     ██║     ██║"}</Text>
        </Text>
      </Box>
      <Box>
        <Text bold>
          <Text color="cyan">{"██║╚██╔╝██║██║     ██╔═══╝ "}</Text>
          <Text color="magenta">{"██╔══██╗██╔══╝  ██║   ██║██║╚════██║   ██║   ██╔══██╗  ╚██╔╝  "}</Text>
          <Text color="green">{" ██║     ██║     ██║"}</Text>
        </Text>
      </Box>
      <Box>
        <Text bold>
          <Text color="cyan">{"██║ ╚═╝ ██║╚██████╗██║     "}</Text>
          <Text color="magenta">{"██║  ██║███████╗╚██████╔╝██║███████║   ██║   ██║  ██║   ██║   "}</Text>
          <Text color="green">{" ╚██████╗███████╗██║"}</Text>
        </Text>
      </Box>
      <Box>
        <Text bold>
          <Text color="cyan">{"╚═╝     ╚═╝ ╚═════╝╚═╝     "}</Text>
          <Text color="magenta">{"╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝   "}</Text>
          <Text color="green">{"  ╚═════╝╚══════╝╚═╝"}</Text>
        </Text>
      </Box>
    </Box>
  );
}
