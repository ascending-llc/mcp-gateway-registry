import React, {useEffect, useRef, useState} from "react";
import {Box, Text, useInput} from "ink";
import {spawn} from "node:child_process";

import {REPO_ROOT} from "../paths.js";
import type {ScriptCommand} from "../tasks/types.js";

type RunnerStatus = "running" | "success" | "error";

interface LogEntry {
  id: number;
  type: "stdout" | "stderr";
  text: string;
}

interface TaskRunnerProps {
  title: string;
  description?: string;
  command: ScriptCommand;
  onDone: (exitCode: number | null) => void;
}

export function TaskRunner({title, description, command, onDone}: TaskRunnerProps) {
  const [status, setStatus] = useState<RunnerStatus>("running");
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const nextId = useRef(0);
  const processRef = useRef<ReturnType<typeof spawn> | null>(null);

  useEffect(() => {
    const env = command.env ? {...process.env, ...command.env} : process.env;
    const child = spawn(command.command, command.args, {
      cwd: REPO_ROOT,
      env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    processRef.current = child;

    const handleData = (type: LogEntry["type"]) => (chunk: Buffer) => {
      const text = chunk.toString();
      const lines = text.replace(/\r\n/g, "\n").split("\n");
      setLogs((prev) => [
        ...prev,
        ...lines
          .filter((line) => line.length > 0)
          .map((line) => ({
            id: nextId.current++,
            type,
            text: line
          }))
      ]);
    };

    child.stdout?.on("data", handleData("stdout"));
    child.stderr?.on("data", handleData("stderr"));

    child.on("close", (code) => {
      setExitCode(code);
      setStatus(code === 0 ? "success" : "error");
    });

    child.on("error", (error) => {
      setLogs((prev) => [
        ...prev,
        {
          id: nextId.current++,
          type: "stderr",
          text: `Failed to start process: ${error.message}`
        }
      ]);
      setExitCode(-1);
      setStatus("error");
    });

    return () => {
      if (processRef.current && status === "running") {
        processRef.current.kill("SIGTERM");
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useInput((input, key) => {
    if (status === "running") {
      if (key.escape || (key.ctrl && input === "c")) {
        processRef.current?.kill("SIGINT");
      }
      return;
    }

    if (key.return || input === "q") {
      onDone(exitCode);
    }
  });

  return (
    <Box flexDirection="column" gap={1}>
      <Text>
        <Text bold>{title}</Text>
      </Text>
      {description ? <Text dimColor>{description}</Text> : null}
      <Text dimColor>
        Command:&nbsp;
        <Text>
          {command.command} {command.args.join(" ")}
        </Text>
      </Text>
      <Box flexDirection="column" borderStyle="round" paddingX={1} paddingY={0} width={80}>
        {logs.length === 0 ? <Text dimColor>No output yet...</Text> : null}
        {logs.map((entry) => (
          <Text key={entry.id} color={entry.type === "stderr" ? "red" : undefined}>
            {entry.text}
          </Text>
        ))}
      </Box>
      {status === "running" ? (
        <Text dimColor>Running… (Esc to cancel)</Text>
      ) : status === "success" ? (
        <Text color="green">
          ✓ Completed with exit code {exitCode ?? 0}. Press ↵ to return or q to quit this view.
        </Text>
      ) : (
        <Text color="red">
          ✗ Failed with exit code {exitCode ?? -1}. Press ↵ to return or q to quit this view.
        </Text>
      )}
    </Box>
  );
}
