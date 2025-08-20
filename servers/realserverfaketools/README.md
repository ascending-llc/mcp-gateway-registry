# Real Server Fake Tools MCP Server

This is an MCP server that provides a collection of fake tools with interesting names that take different types of parameters. These tools are stubbed out and return mock responses for demonstration purposes.

## Tools

The server provides the following tools:

1. **quantum_flux_analyzer** - Analyzes quantum flux patterns with configurable energy levels and stabilization.
2. **neural_pattern_synthesizer** - Synthesizes neural patterns into coherent structures.
3. **hyper_dimensional_mapper** - Maps geographical coordinates to hyper-dimensional space.
4. **temporal_anomaly_detector** - Detects temporal anomalies within a specified timeframe.
5. **user_profile_analyzer** - Analyzes a user profile with configurable analysis options.
6. **synthetic_data_generator** - Generates synthetic data based on a provided schema.

## Resources

The server provides the following resources:

1. **config://app** - Static configuration data for the fake tools server.
2. **docs://tools** - Documentation for the fake tools.

## Prompts

The server provides the following prompts:

1. **system_prompt_for_agent** - Generates a system prompt for an AI Agent that wants to use the real_server_fake_tools MCP server.

## Installation

```bash
# Clone the repository
git clone <repository-url>

# Navigate to the server directory
cd servers/real_server_fake_tools

# Install dependencies
pip install -e .
```

## Usage

### Running the Server

```bash
# Run the server with default settings
python server.py

# Run the server with custom port and transport
python server.py --port 8001 --transport streamable-http
```

### Using the Client

```bash
# Run the client with default settings (connects to localhost:8001)
python client.py

# Run the client with custom host and port
python client.py --host example.com --port 8001
```

## Example Tool Usage

### Quantum Flux Analyzer

```python
result = await session.call_tool(
    "quantum_flux_analyzer", 
    arguments={
        "energy_level": 7,
        "stabilization_factor": 0.85,
        "enable_temporal_shift": True
    }
)
```

### Neural Pattern Synthesizer

```python
result = await session.call_tool(
    "neural_pattern_synthesizer", 
    arguments={
        "input_patterns": ["alpha", "beta", "gamma"],
        "coherence_threshold": 0.8,
        "dimensions": 5
    }
)
```

### Hyper Dimensional Mapper

```python
result = await session.call_tool(
    "hyper_dimensional_mapper", 
    arguments={
        "coordinates": {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "altitude": 10
        },
        "dimension_count": 6,
        "reality_anchoring": 0.9
    }
)
```

## License

[MIT License](LICENSE)