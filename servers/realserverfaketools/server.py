"""
This server provides a collection of fake tools with interesting names that take different types of parameters.
These tools are stubbed out and return mock responses for demonstration purposes.
"""

import os
import time
import secrets  # Replaced random with secrets
import argparse
import logging
import json
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from typing import Annotated, List, Dict, Optional, Union, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - PID:%(process)d - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Helper functions for replacing random functions with secrets equivalents
def secure_uniform(min_val, max_val, precision=2):
    """Generate a secure random float between min_val and max_val with specified precision"""
    range_val = int((max_val - min_val) * (10 ** precision))
    return min_val + (secrets.randbelow(range_val + 1) / (10 ** precision))

def secure_random():
    """Generate a secure random float between 0 and 1"""
    return secrets.randbelow(10000) / 10000

def secure_choice(sequence):
    """Select a random element from a sequence using cryptographically secure randomness"""
    return sequence[secrets.randbelow(len(sequence))]

def secure_sample(population, k):
    """Select k unique elements from a population using cryptographically secure randomness"""
    result = []
    population_copy = list(population)
    for i in range(min(k, len(population_copy))):
        idx = secrets.randbelow(len(population_copy))
        result.append(population_copy.pop(idx))
    return result

def parse_arguments():
    """Parse command line arguments with defaults matching environment variables."""
    parser = argparse.ArgumentParser(description="Real Server Fake Tools MCP Server")

    parser.add_argument(
        "--port",
        type=str,
        default=os.environ.get("MCP_SERVER_LISTEN_PORT", "8001"),
        help="Port for the MCP server to listen on (default: 8001)",
    )

    parser.add_argument(
        "--transport",
        type=str,
        default=os.environ.get("MCP_TRANSPORT", "sse"),
        help="Transport type for the MCP server (default: sse)",
    )

    return parser.parse_args()


# Parse arguments at module level to make them available
args = parse_arguments()

# Initialize FastMCP server using parsed arguments
mcp = FastMCP("real_server_fake_tools", port=args.port)


# Define some Pydantic models for complex parameter types
class GeoCoordinates(BaseModel):
    latitude: float = Field(..., description="Latitude coordinate")
    longitude: float = Field(..., description="Longitude coordinate")
    altitude: Optional[float] = Field(None, description="Altitude in meters (optional)")


class UserProfile(BaseModel):
    username: str = Field(..., description="User's username")
    email: str = Field(..., description="User's email address")
    age: Optional[int] = Field(None, description="User's age (optional)")
    interests: List[str] = Field(default_factory=list, description="List of user interests")


class AnalysisOptions(BaseModel):
    depth: int = Field(3, description="Depth of analysis (1-10)")
    include_metadata: bool = Field(True, description="Whether to include metadata")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Filters to apply")


@mcp.prompt()
def system_prompt_for_agent(task_description: str) -> str:
    """
    Generates a system prompt for an AI Agent that wants to use the real_server_fake_tools MCP server.

    Args:
        task_description (str): Description of the task the agent wants to accomplish.

    Returns:
        str: A formatted system prompt for the AI Agent.
    """

    system_prompt = f"""
You are an expert AI agent that wants to use the real_server_fake_tools MCP server. 
This server provides a collection of fake tools with interesting names that take different types of parameters.

The task you need to accomplish is: {task_description}

You can use any of the available tools provided by the real_server_fake_tools MCP server to accomplish this task.
"""
    return system_prompt


@mcp.tool()
def quantum_flux_analyzer(
    energy_level: Annotated[int, Field(
        ge=1, le=10,
        description="Energy level for quantum analysis (1-10)"
    )] = 5,
    stabilization_factor: Annotated[float, Field(
        description="Stabilization factor for quantum flux"
    )] = 0.75,
    enable_temporal_shift: Annotated[bool, Field(
        description="Whether to enable temporal shifting in the analysis"
    )] = False
) -> str:
    """
    Analyzes quantum flux patterns with configurable energy levels and stabilization.
    
    Args:
        energy_level: Energy level for quantum analysis (1-10)
        stabilization_factor: Stabilization factor for quantum flux
        enable_temporal_shift: Whether to enable temporal shifting in the analysis
        
    Returns:
        str: JSON response with mock quantum flux analysis results
    """
    # Simulate processing time
    time.sleep(secure_uniform(0.5, 1.5))
    
    # Generate mock response
    result = {
        "analysis_id": f"QFA-{10000 + secrets.randbelow(90000)}",
        "timestamp": datetime.now().isoformat(),
        "energy_level": energy_level,
        "stabilization_factor": stabilization_factor,
        "temporal_shift_enabled": enable_temporal_shift,
        "flux_patterns": [
            {"pattern_id": f"P{i}", "intensity": secure_uniform(0.1, 0.9), "stability": secure_uniform(0.2, 1.0)}
            for i in range(1, energy_level + 3)
        ],
        "analysis_summary": "Quantum flux patterns analyzed successfully with simulated data.",
        "confidence_score": secure_uniform(0.65, 0.98)
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
def neural_pattern_synthesizer(
    input_patterns: Annotated[List[str], Field(
        description="List of neural patterns to synthesize"
    )],
    coherence_threshold: Annotated[float, Field(
        ge=0.0, le=1.0,
        description="Threshold for pattern coherence (0.0-1.0)"
    )] = 0.7,
    dimensions: Annotated[int, Field(
        ge=1, le=10,
        description="Number of dimensions for synthesis (1-10)"
    )] = 3
) -> Dict[str, Any]:
    """
    Synthesizes neural patterns into coherent structures.
    
    Args:
        input_patterns: List of neural patterns to synthesize
        coherence_threshold: Threshold for pattern coherence (0.0-1.0)
        dimensions: Number of dimensions for synthesis (1-10)
        
    Returns:
        Dict[str, Any]: Dictionary with mock neural pattern synthesis results
    """
    # Simulate processing time
    time.sleep(secure_uniform(0.8, 2.0))
    
    # Generate mock response
    pattern_count = len(input_patterns)
    
    result = {
        "synthesis_id": f"NPS-{10000 + secrets.randbelow(90000)}",
        "timestamp": datetime.now().isoformat(),
        "input_pattern_count": pattern_count,
        "coherence_threshold": coherence_threshold,
        "dimensions": dimensions,
        "synthesized_patterns": [
            {
                "original": pattern,
                "synthesized": f"syn_{pattern}_{100 + secrets.randbelow(900)}",
                "coherence_score": secure_uniform(coherence_threshold - 0.2, coherence_threshold + 0.2),
                "dimensional_stability": [secure_uniform(0.5, 0.95) for _ in range(dimensions)]
            }
            for pattern in input_patterns
        ],
        "overall_synthesis_quality": secure_uniform(0.6, 0.95),
        "recommended_adjustments": [
            "Increase pattern diversity",
            "Adjust coherence threshold",
            "Consider higher dimensional analysis"
        ] if secure_random() > 0.5 else []
    }
    
    return result


@mcp.tool()
def hyper_dimensional_mapper(
    coordinates: Annotated[GeoCoordinates, Field(
        description="Geographical coordinates to map to hyper-dimensions"
    )],
    dimension_count: Annotated[int, Field(
        ge=4, le=11,
        description="Number of hyper-dimensions to map to (4-11)"
    )] = 5,
    reality_anchoring: Annotated[float, Field(
        ge=0.1, le=1.0,
        description="Reality anchoring factor (0.1-1.0)"
    )] = 0.8
) -> str:
    """
    Maps geographical coordinates to hyper-dimensional space.
    
    Args:
        coordinates: Geographical coordinates to map
        dimension_count: Number of hyper-dimensions to map to (4-11)
        reality_anchoring: Reality anchoring factor (0.1-1.0)
        
    Returns:
        str: JSON response with mock hyper-dimensional mapping results
    """
    # Simulate processing time
    time.sleep(secure_uniform(1.0, 2.5))
    
    # Generate mock response
    hyper_coords = [secure_uniform(-100, 100) for _ in range(dimension_count)]
    
    result = {
        "mapping_id": f"HDM-{10000 + secrets.randbelow(90000)}",
        "timestamp": datetime.now().isoformat(),
        "source_coordinates": {
            "latitude": coordinates.latitude,
            "longitude": coordinates.longitude,
            "altitude": coordinates.altitude if coordinates.altitude is not None else "not provided"
        },
        "hyper_dimensional_coordinates": {
            f"d{i+1}": coord for i, coord in enumerate(hyper_coords)
        },
        "reality_anchoring_factor": reality_anchoring,
        "stability_assessment": {
            "temporal_stability": secure_uniform(0.5, 0.9),
            "spatial_coherence": secure_uniform(0.6, 0.95),
            "dimensional_bleed": secure_uniform(0.05, 0.3)
        },
        "navigation_safety": "GREEN" if secure_random() > 0.7 else "YELLOW",
        "estimated_mapping_accuracy": f"{secure_uniform(85, 99):.2f}%"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
def temporal_anomaly_detector(
    timeframe: Annotated[Dict[str, str], Field(
        description="Start and end times for anomaly detection"
    )],
    sensitivity: Annotated[int, Field(
        ge=1, le=10,
        description="Sensitivity level for detection (1-10)"
    )] = 7,
    anomaly_types: Annotated[List[str], Field(
        description="Types of anomalies to detect"
    )] = ["temporal_shift", "causal_loop", "timeline_divergence"]
) -> Dict[str, Any]:
    """
    Detects temporal anomalies within a specified timeframe.
    
    Args:
        timeframe: Dictionary with 'start' and 'end' times for anomaly detection
        sensitivity: Sensitivity level for detection (1-10)
        anomaly_types: Types of anomalies to detect
        
    Returns:
        Dict[str, Any]: Dictionary with mock temporal anomaly detection results
    """
    # Simulate processing time
    time.sleep(secure_uniform(1.2, 3.0))
    
    # Generate mock response
    anomaly_count = secrets.randbelow(sensitivity + 1)
    
    result = {
        "detection_id": f"TAD-{10000 + secrets.randbelow(90000)}",
        "timestamp": datetime.now().isoformat(),
        "timeframe": timeframe,
        "sensitivity_level": sensitivity,
        "anomaly_types_monitored": anomaly_types,
        "anomalies_detected": anomaly_count,
        "anomaly_details": [
            {
                "anomaly_id": f"A{1000 + secrets.randbelow(9000)}",
                "type": secure_choice(anomaly_types),
                "severity": secure_uniform(0.1, 1.0),
                "temporal_coordinates": {
                    "t": secure_uniform(-10, 10),
                    "x": secure_uniform(-5, 5),
                    "y": secure_uniform(-5, 5),
                    "z": secure_uniform(-5, 5)
                },
                "causality_impact": secure_choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
                "recommended_action": secure_choice([
                    "Monitor", "Investigate", "Contain", "Neutralize", "Temporal reset required"
                ])
            }
            for _ in range(anomaly_count)
        ],
        "background_temporal_stability": f"{secure_uniform(85, 99.9):.2f}%",
        "detection_confidence": secure_uniform(0.7, 0.98)
    }
    
    return result


@mcp.tool()
def user_profile_analyzer(
    profile: Annotated[UserProfile, Field(
        description="User profile to analyze"
    )],
    analysis_options: Annotated[AnalysisOptions, Field(
        description="Options for the analysis"
    )] = AnalysisOptions()
) -> str:
    """
    Analyzes a user profile with configurable analysis options.
    
    Args:
        profile: User profile to analyze
        analysis_options: Options for the analysis
        
    Returns:
        str: JSON response with mock user profile analysis results
    """
    # Simulate processing time
    time.sleep(secure_uniform(0.7, 1.8))
    
    # Generate mock response
    result = {
        "analysis_id": f"UPA-{10000 + secrets.randbelow(90000)}",
        "timestamp": datetime.now().isoformat(),
        "user": {
            "username": profile.username,
            "email": profile.email,
            "age": profile.age if profile.age is not None else "not provided",
            "interest_count": len(profile.interests)
        },
        "analysis_depth": analysis_options.depth,
        "metadata_included": analysis_options.include_metadata,
        "applied_filters": analysis_options.filters if analysis_options.filters else "none",
        "analysis_results": {
            "engagement_score": secure_uniform(0, 100),
            "activity_pattern": secure_choice(["Regular", "Sporadic", "Intensive", "Declining"]),
            "interest_clusters": [
                {
                    "cluster_name": f"Cluster {i+1}",
                    "interests": secure_sample(profile.interests, min(len(profile.interests), 1 + secrets.randbelow(3))),
                    "relevance_score": secure_uniform(0.5, 0.95)
                }
                for i in range(min(3, len(profile.interests)))
            ] if profile.interests else [],
            "behavioral_insights": [
                "Prefers morning engagement",
                "Shows interest in technical topics",
                "Likely to respond to visual content"
            ],
            "recommendation_categories": [
                "Technical documentation",
                "Interactive tutorials",
                "Community discussions"
            ]
        },
        "analysis_quality": f"{secure_uniform(85, 98):.1f}%"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
def synthetic_data_generator(
    schema: Annotated[Dict[str, Any], Field(
        description="Schema defining the structure of synthetic data"
    )],
    record_count: Annotated[int, Field(
        ge=1, le=1000,
        description="Number of synthetic records to generate (1-1000)"
    )] = 10,
    seed: Annotated[Optional[int], Field(
        description="Random seed for reproducibility (optional)"
    )] = None
) -> Dict[str, Any]:
    """
    Generates synthetic data based on a provided schema.
    
    Args:
        schema: Schema defining the structure of synthetic data
        record_count: Number of synthetic records to generate (1-1000)
        seed: Random seed for reproducibility (optional)
        
    Returns:
        Dict[str, Any]: Dictionary with mock synthetic data generation results
    """
    # Note: Using seed with secrets is not appropriate as it's designed for cryptographic randomness
    # For this demo, we'll acknowledge the seed parameter but not use it, as secrets doesn't support seeding
    
    # Simulate processing time
    time.sleep(secure_uniform(0.5, 2.0))
    
    # Generate mock response
    result = {
        "generation_id": f"SDG-{10000 + secrets.randbelow(90000)}",
        "timestamp": datetime.now().isoformat(),
        "schema_fields": list(schema.keys()),
        "record_count": record_count,
        "seed_used": seed if seed is not None else "not provided",
        "generated_data": [
            {
                field: f"synthetic_{field}_{i}_{1000 + secrets.randbelow(9000)}"
                for field in schema.keys()
            }
            for i in range(record_count)
        ],
        "data_quality_metrics": {
            "completeness": secure_uniform(0.95, 1.0),
            "uniqueness": secure_uniform(0.9, 1.0),
            "consistency": secure_uniform(0.92, 0.99)
        },
        "generation_time_ms": 50 + secrets.randbelow(451)
    }
    
    return result


@mcp.resource("config://app")
def get_config() -> str:
    """Static configuration data for the fake tools server"""
    config = {
        "server_name": "real_server_fake_tools",
        "version": "0.1.0",
        "description": "A collection of fake tools with interesting names",
        "max_concurrent_requests": 10,
        "default_timeout_seconds": 30,
        "supported_features": [
            "quantum_analysis",
            "neural_synthesis",
            "hyper_mapping",
            "temporal_detection",
            "user_analysis",
            "synthetic_generation"
        ],
        "environment": "development"
    }
    return json.dumps(config, indent=2)


@mcp.resource("docs://tools")
def get_tools_documentation() -> str:
    """Documentation for the fake tools"""
    docs = {
        "quantum_flux_analyzer": {
            "description": "Analyzes quantum flux patterns with configurable energy levels and stabilization.",
            "use_cases": [
                "Quantum computing simulation",
                "Particle physics research",
                "Energy field analysis"
            ],
            "example_usage": {
                "energy_level": 7,
                "stabilization_factor": 0.85,
                "enable_temporal_shift": True
            }
        },
        "neural_pattern_synthesizer": {
            "description": "Synthesizes neural patterns into coherent structures.",
            "use_cases": [
                "AI model training",
                "Neural network optimization",
                "Pattern recognition systems"
            ],
            "example_usage": {
                "input_patterns": ["alpha", "beta", "gamma"],
                "coherence_threshold": 0.8,
                "dimensions": 5
            }
        },
        "hyper_dimensional_mapper": {
            "description": "Maps geographical coordinates to hyper-dimensional space.",
            "use_cases": [
                "Advanced navigation systems",
                "Spatial analysis",
                "Dimensional research"
            ],
            "example_usage": {
                "coordinates": {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "altitude": 10
                },
                "dimension_count": 6,
                "reality_anchoring": 0.9
            }
        },
        "temporal_anomaly_detector": {
            "description": "Detects temporal anomalies within a specified timeframe.",
            "use_cases": [
                "Time series analysis",
                "Anomaly detection",
                "Predictive modeling"
            ],
            "example_usage": {
                "timeframe": {
                    "start": "2023-01-01T00:00:00Z",
                    "end": "2023-01-31T23:59:59Z"
                },
                "sensitivity": 8,
                "anomaly_types": ["temporal_shift", "causal_loop"]
            }
        },
        "user_profile_analyzer": {
            "description": "Analyzes a user profile with configurable analysis options.",
            "use_cases": [
                "User behavior analysis",
                "Personalization systems",
                "Marketing targeting"
            ],
            "example_usage": {
                "profile": {
                    "username": "user123",
                    "email": "user@example.com",
                    "age": 30,
                    "interests": ["technology", "science", "art"]
                },
                "analysis_options": {
                    "depth": 5,
                    "include_metadata": True,
                    "filters": {"exclude_inactive": True}
                }
            }
        },
        "synthetic_data_generator": {
            "description": "Generates synthetic data based on a provided schema.",
            "use_cases": [
                "Testing environments",
                "Machine learning training",
                "Privacy-preserving analytics"
            ],
            "example_usage": {
                "schema": {
                    "name": "string",
                    "age": "integer",
                    "email": "email"
                },
                "record_count": 50,
                "seed": 12345
            }
        }
    }
    return json.dumps(docs, indent=2)


def main():
    # Run the server with the specified transport from command line args
    mount_path = "/realserverfaketools"
    mcp.run(transport=args.transport, mount_path=mount_path)
    logger.info(f"Server is running on port {args.port} with transport {args.transport}, mount path {mount_path}")


if __name__ == "__main__":
    main()