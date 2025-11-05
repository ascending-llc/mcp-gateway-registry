#!/usr/bin/env node
import "dotenv/config";
import React from "react";
import {render} from "ink";

import App from "./app.js";
import {HELP_TEXT, parseArgs} from "./parseArgs.js";

const parsed = parseArgs(process.argv.slice(2));

if (parsed.helpRequested) {
  // eslint-disable-next-line no-console
  console.log(HELP_TEXT);
  process.exit(0);
}

if (parsed.unknown.length > 0) {
  // eslint-disable-next-line no-console
  console.warn(`Ignoring unknown arguments: ${parsed.unknown.join(", ")}`);
}

render(<App options={parsed} />);
